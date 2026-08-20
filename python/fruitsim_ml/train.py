from __future__ import annotations

import json
import math
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cross_decomposition import PLSRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_selection import VarianceThreshold
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV, GroupKFold, GroupShuffleSplit, KFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler
from sklearn.svm import SVR

from . import __version__
from .data import WARNING, validate_dataset
from .features import build_feature_matrix
from .preprocessing import savgol_derivative, savgol_smooth, snv


def emit(event: str, **payload) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True)


def _preprocessor(name: str):
    if name == "raw":
        return "passthrough"
    if name == "standard":
        return StandardScaler()
    functions = {"snv": snv, "savgol": savgol_smooth, "savgol_derivative": savgol_derivative}
    if name not in functions:
        raise ValueError(f"Unknown preprocessing method: {name}")
    return FunctionTransformer(functions[name], validate=False)


def _model(name: str, seed: int):
    if name == "mlr":
        return LinearRegression(), {}
    if name == "plsr":
        return PLSRegression(scale=True, max_iter=1000), {"model__n_components": [2, 4, 6, 8]}
    if name == "svr":
        return SVR(kernel="rbf"), {
            "model__C": [1.0, 10.0, 100.0],
            "model__gamma": ["scale", 0.01, 0.1],
            "model__epsilon": [0.05, 0.1],
        }
    if name == "rf":
        return RandomForestRegressor(random_state=seed, n_jobs=1), {
            "model__n_estimators": [150, 300],
            "model__max_depth": [None, 8, 16],
        }
    raise ValueError(f"Unknown model: {name}")


def _metrics(y_true: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    residual = prediction - y_true
    rmse = math.sqrt(mean_squared_error(y_true, prediction))
    rp = float(np.corrcoef(y_true, prediction)[0, 1]) if len(y_true) > 1 else 0.0
    std = float(np.std(y_true, ddof=1)) if len(y_true) > 1 else 0.0
    return {
        "r2": float(r2_score(y_true, prediction)),
        "rp": rp,
        "rmse": rmse,
        "mae": float(mean_absolute_error(y_true, prediction)),
        "bias": float(np.mean(residual)),
        "rpd": std / rmse if rmse > 0.0 else float("inf"),
    }


def _one_run(task: dict) -> dict:
    frame = pd.read_csv(task["dataset"])
    x, y, groups, sample_ids, feature_names = build_feature_matrix(frame, task["feature_set"])
    seed = task["seed"]
    if task["validation_mode"] == "paper_compatible":
        train_idx, test_idx = train_test_split(
            np.arange(len(y)), test_size=0.25, random_state=seed
        )
        cv = KFold(n_splits=5, shuffle=True, random_state=seed)
        fit_groups = None
    elif task["validation_mode"] == "research":
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed)
        train_idx, test_idx = next(splitter.split(x, y, groups))
        unique_groups = np.unique(groups[train_idx])
        cv = GroupKFold(n_splits=min(5, len(unique_groups)))
        fit_groups = groups[train_idx]
    else:
        raise ValueError(f"Unknown validation mode: {task['validation_mode']}")

    estimator, grid = _model(task["model"], seed)
    pipeline = Pipeline([
        ("preprocess", _preprocessor(task["preprocessing"])),
        ("variance", VarianceThreshold()),
        ("model", estimator),
    ])
    search = GridSearchCV(
        pipeline, grid or [{}], scoring="neg_root_mean_squared_error", cv=cv,
        n_jobs=1, refit=True, error_score="raise"
    )
    fit_kwargs = {"groups": fit_groups} if fit_groups is not None else {}
    search.fit(x[train_idx], y[train_idx], **fit_kwargs)
    train_prediction = np.asarray(search.predict(x[train_idx])).reshape(-1)
    test_prediction = np.asarray(search.predict(x[test_idx])).reshape(-1)
    train_metrics = _metrics(y[train_idx], train_prediction)
    test_metrics = _metrics(y[test_idx], test_prediction)
    run_id = f"{task['feature_set']}__{task['preprocessing']}__{task['model']}"
    run_dir = Path(task["output"]) / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(search.best_estimator_, run_dir / "pipeline.joblib")
    predictions = pd.DataFrame({
        "sample_id": sample_ids[test_idx], "set": "validation",
        "reference_ssc_brix": y[test_idx], "predicted_ssc_brix": test_prediction,
        "feature_set": task["feature_set"], "preprocessing": task["preprocessing"],
        "model": task["model"],
    })
    predictions.to_csv(run_dir / "predictions.csv", index=False)
    assignments = pd.DataFrame({
        "sample_id": sample_ids,
        "set": np.where(np.isin(np.arange(len(y)), test_idx), "validation", "calibration"),
        "batch_id": groups,
    })
    assignments.to_csv(run_dir / "cv_folds.csv", index=False)
    result = {
        "run_id": run_id,
        "feature_set": task["feature_set"], "preprocessing": task["preprocessing"],
        "model": task["model"], "best_params": search.best_params_,
        "rmsec": train_metrics["rmse"], "rmsecv": float(-search.best_score_),
        "rmsep": test_metrics["rmse"], **{f"validation_{k}": v for k, v in test_metrics.items()},
        "calibration_samples": int(len(train_idx)), "validation_samples": int(len(test_idx)),
        "feature_count": len(feature_names),
    }
    (run_dir / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (run_dir / "feature_schema.json").write_text(json.dumps({
        "schema_version": 1, "features": feature_names, "target": "ssc_brix", "units": "degree Brix"
    }, indent=2), encoding="utf-8")
    return result


def train_from_config(config_path: Path) -> Path:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ValueError("Unsupported ML config schema_version")
    dataset = (config_path.parent / config["dataset"]).resolve() if not Path(config["dataset"]).is_absolute() else Path(config["dataset"])
    dataset_report = validate_dataset(dataset)
    source_types = dataset_report["source_types"]
    source_type = source_types[0] if len(source_types) == 1 else "mixed"
    requested_status = config.get("model_status", "method_demo")
    if requested_status == "experiment_calibrated" and (
        source_type != "experimental" or not config.get("external_validation_confirmed", False)
    ):
        raise ValueError(
            "experiment_calibrated requires exclusively experimental data and explicit external validation"
        )
    output = Path(config["output"]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    seed = int(config.get("seed", 20260819))
    tasks = [
        {
            "dataset": str(dataset), "output": str(output), "seed": seed,
            "validation_mode": config.get("validation_mode", "paper_compatible"),
            "feature_set": feature, "preprocessing": preprocessing, "model": model,
        }
        for feature in config["feature_sets"]
        for preprocessing in config["preprocessing"]
        for model in config["models"]
    ]
    warning = WARNING if source_type != "experimental" else ""
    emit("started", jobs=len(tasks), warning=warning)
    results = []
    workers = min(int(config.get("parallel_jobs", 2)), len(tasks))
    with ProcessPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(_one_run, task): task for task in tasks}
        for completed, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            results.append(result)
            emit("progress", completed=completed, total=len(tasks), run_id=result["run_id"])
    leaderboard = pd.DataFrame(results).sort_values(["rmsep", "validation_r2"], ascending=[True, False])
    leaderboard.to_csv(output / "leaderboard.csv", index=False)
    best = results[int(np.argmin([result["rmsep"] for result in results]))]
    shutil.copy2(output / "runs" / best["run_id"] / "pipeline.joblib", output / "pipeline.joblib")
    all_predictions = pd.concat([
        pd.read_csv(output / "runs" / result["run_id"] / "predictions.csv") for result in results
    ], ignore_index=True)
    all_predictions.to_csv(output / "predictions.csv", index=False)
    manifest = {
        "schema_version": 1, "software": "fruitsim_ml", "software_version": __version__,
        "dataset": str(dataset), "dataset_report": dataset_report,
        "source_type": source_type, "best_run": best["run_id"],
        "validation_mode": config.get("validation_mode", "paper_compatible"),
        "model_status": requested_status, "warning": warning,
        "models_are_real_world_valid": requested_status == "experiment_calibrated",
    }
    (output / "model_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "metrics.json").write_text(json.dumps({"best": best, "runs": results}, indent=2), encoding="utf-8")
    shutil.copy2(output / "runs" / best["run_id"] / "feature_schema.json", output / "feature_schema.json")
    shutil.copy2(output / "runs" / best["run_id"] / "cv_folds.csv", output / "cv_folds.csv")
    emit("completed", best_run=best["run_id"], output=str(output), warning=warning)
    return output
