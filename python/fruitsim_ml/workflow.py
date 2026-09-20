"""Typed, stage-constrained ML workflow for Fruitsim.

This module is deliberately independent from the GUI.  Algorithms return
structured objects and intermediate states; renderers may later turn those
states into PNGs, HTML, ImPlot views, or teaching animations.
"""

from __future__ import annotations

import csv
import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
from sklearn.cross_decomposition import PLSRegression
from sklearn.decomposition import PCA
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GroupKFold, KFold
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler
from scipy.signal import savgol_filter


class Stage(str, Enum):
    DATA_INSPECTION = "data_inspection"
    PREPROCESSING = "preprocessing"
    FEATURE_ANALYSIS = "feature_analysis"
    FEATURE_SELECTION = "feature_selection"
    MODELING = "modeling"
    RESULTS = "results"


class DataKind(str, Enum):
    SPECTRUM_SET = "spectrum_set"
    LATENT_FEATURE_SET = "latent_feature_set"
    FEATURE_ANALYSIS = "feature_analysis"
    SELECTED_FEATURE_SET = "selected_feature_set"
    MODEL_RESULT = "model_result"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, np.ndarray):
        return {
            "__ndarray__": value.tolist(),
            "dtype": str(value.dtype),
            "shape": list(value.shape),
        }
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _from_json_value(value: Any) -> Any:
    if isinstance(value, dict) and "__ndarray__" in value:
        return np.asarray(value["__ndarray__"], dtype=value.get("dtype"))
    if isinstance(value, dict):
        return {key: _from_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_from_json_value(item) for item in value]
    return value


def _matrix_shape(matrix: np.ndarray, names: Sequence[str], sample_ids: Sequence[str]) -> None:
    if matrix.ndim != 2:
        raise ValueError("feature matrix must be two-dimensional")
    if matrix.shape[1] != len(names):
        raise ValueError("feature name count does not match matrix width")
    if matrix.shape[0] != len(sample_ids):
        raise ValueError("sample id count does not match matrix height")
    if not np.isfinite(matrix).all():
        raise ValueError("feature matrix contains non-finite values")


@dataclass
class SpectrumSet:
    X: np.ndarray
    wavelengths: np.ndarray
    sample_ids: tuple[str, ...]
    y: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    kind: DataKind = field(default=DataKind.SPECTRUM_SET, init=False)

    def __post_init__(self) -> None:
        self.X = np.asarray(self.X, dtype=float)
        self.wavelengths = np.asarray(self.wavelengths, dtype=float)
        self.sample_ids = tuple(str(item) for item in self.sample_ids)
        if self.X.ndim != 2 or self.X.shape[1] != len(self.wavelengths):
            raise ValueError("SpectrumSet X must have one column per wavelength")
        if self.X.shape[0] != len(self.sample_ids):
            raise ValueError("SpectrumSet X must have one row per sample id")
        if not np.isfinite(self.X).all() or not np.isfinite(self.wavelengths).all():
            raise ValueError("SpectrumSet contains non-finite values")
        if self.y is not None:
            self.y = np.asarray(self.y, dtype=float)
            if self.y.shape != (self.X.shape[0],):
                raise ValueError("SpectrumSet y must have one value per sample")
        self.metadata = dict(self.metadata)

    @property
    def feature_names(self) -> tuple[str, ...]:
        return tuple(f"wavelength_{value:g}nm" for value in self.wavelengths)

    def copy(self, X: np.ndarray | None = None, **metadata: Any) -> "SpectrumSet":
        merged = dict(self.metadata)
        merged.update(metadata)
        return SpectrumSet(
            self.X.copy() if X is None else np.asarray(X),
            self.wavelengths.copy(),
            self.sample_ids,
            None if self.y is None else self.y.copy(),
            merged,
        )


@dataclass
class LatentFeatureSet:
    X: np.ndarray
    feature_names: tuple[str, ...]
    sample_ids: tuple[str, ...]
    y: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    loadings: np.ndarray | None = None

    kind: DataKind = field(default=DataKind.LATENT_FEATURE_SET, init=False)

    def __post_init__(self) -> None:
        self.X = np.asarray(self.X, dtype=float)
        self.feature_names = tuple(str(item) for item in self.feature_names)
        self.sample_ids = tuple(str(item) for item in self.sample_ids)
        _matrix_shape(self.X, self.feature_names, self.sample_ids)
        if self.y is not None:
            self.y = np.asarray(self.y, dtype=float)
            if self.y.shape != (self.X.shape[0],):
                raise ValueError("LatentFeatureSet y must have one value per sample")
        if self.loadings is not None:
            self.loadings = np.asarray(self.loadings, dtype=float)
        self.metadata = dict(self.metadata)


@dataclass
class SelectedFeatureSet:
    X: np.ndarray
    feature_names: tuple[str, ...]
    selected_indices: np.ndarray
    sample_ids: tuple[str, ...]
    y: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    kind: DataKind = field(default=DataKind.SELECTED_FEATURE_SET, init=False)

    def __post_init__(self) -> None:
        self.X = np.asarray(self.X, dtype=float)
        self.feature_names = tuple(str(item) for item in self.feature_names)
        self.selected_indices = np.asarray(self.selected_indices, dtype=int)
        self.sample_ids = tuple(str(item) for item in self.sample_ids)
        _matrix_shape(self.X, self.feature_names, self.sample_ids)
        if len(self.selected_indices) != self.X.shape[1]:
            raise ValueError("selected_indices must match selected matrix width")
        if self.y is not None:
            self.y = np.asarray(self.y, dtype=float)
            if self.y.shape != (self.X.shape[0],):
                raise ValueError("SelectedFeatureSet y must have one value per sample")
        self.metadata = dict(self.metadata)


@dataclass
class FeatureAnalysisResult:
    method_id: str
    source: SpectrumSet | LatentFeatureSet
    feature_names: tuple[str, ...]
    selected_indices: np.ndarray | None = None
    scores: np.ndarray | None = None
    loadings: np.ndarray | None = None
    statistics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    kind: DataKind = field(default=DataKind.FEATURE_ANALYSIS, init=False)

    def __post_init__(self) -> None:
        self.feature_names = tuple(str(item) for item in self.feature_names)
        if self.selected_indices is not None:
            self.selected_indices = np.asarray(self.selected_indices, dtype=int)
        if self.scores is not None:
            self.scores = np.asarray(self.scores, dtype=float)
        if self.loadings is not None:
            self.loadings = np.asarray(self.loadings, dtype=float)
        self.statistics = dict(self.statistics)
        self.metadata = dict(self.metadata)


@dataclass
class PredictionSet:
    sample_ids: tuple[str, ...]
    y_true: np.ndarray
    y_pred: np.ndarray
    residuals: np.ndarray
    split: tuple[str, ...]
    fold_ids: tuple[int, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.sample_ids = tuple(str(item) for item in self.sample_ids)
        self.y_true = np.asarray(self.y_true, dtype=float)
        self.y_pred = np.asarray(self.y_pred, dtype=float)
        self.residuals = np.asarray(self.residuals, dtype=float)
        self.split = tuple(str(item) for item in self.split)
        if not (len(self.sample_ids) == len(self.y_true) == len(self.y_pred) == len(self.residuals) == len(self.split)):
            raise ValueError("PredictionSet columns must have equal length")
        if not self.fold_ids:
            self.fold_ids = tuple(-1 for _ in self.sample_ids)
        if len(self.fold_ids) != len(self.sample_ids):
            raise ValueError("fold_ids must match prediction rows")
        self.metadata = dict(self.metadata)


@dataclass
class EvaluationResult:
    rmse: float
    mae: float
    r2: float
    sample_count: int
    feature_count: int
    cv_rmse: float | None = None
    bias: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _json_value({
            "rmse": self.rmse,
            "mae": self.mae,
            "r2": self.r2,
            "sample_count": self.sample_count,
            "feature_count": self.feature_count,
            "cv_rmse": self.cv_rmse,
            "bias": self.bias,
            "metadata": self.metadata,
        })


@dataclass
class ModelResult:
    method_id: str
    predictions: PredictionSet
    evaluation: EvaluationResult
    model_metadata: dict[str, Any] = field(default_factory=dict)

    kind: DataKind = field(default=DataKind.MODEL_RESULT, init=False)


@dataclass
class IntermediateState:
    name: str
    kind: str
    event: str
    arrays: dict[str, np.ndarray] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _json_value({
            "name": self.name,
            "kind": self.kind,
            "event": self.event,
            "arrays": self.arrays,
            "values": self.values,
        })

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "IntermediateState":
        return cls(
            str(document["name"]),
            str(document["kind"]),
            str(document["event"]),
            {key: _from_json_value(value) for key, value in document.get("arrays", {}).items()},
            _from_json_value(document.get("values", {})),
        )


@dataclass
class MethodExecutionResult:
    output: Any
    metrics: dict[str, Any] = field(default_factory=dict)
    intermediate_states: list[IntermediateState] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


MethodExecutor = Callable[[Any, Mapping[str, Any], int], MethodExecutionResult]


@dataclass
class Method:
    id: str
    name: str
    stage: Stage
    input_type: DataKind
    output_type: DataKind
    parameter_schema: dict[str, Any]
    execute: MethodExecutor
    metadata: dict[str, Any] = field(default_factory=dict)


class MethodRegistry:
    def __init__(self) -> None:
        self._methods: dict[str, Method] = {}

    def register(self, method: Method) -> None:
        if method.id in self._methods:
            raise ValueError(f"method already registered: {method.id}")
        self._methods[method.id] = method

    def get(self, method_id: str) -> Method:
        try:
            return self._methods[method_id]
        except KeyError as exc:
            raise ValueError(f"unknown method: {method_id}") from exc

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._methods))


def _copy_spectrum(values: SpectrumSet, *, method_id: str, X: np.ndarray | None = None) -> SpectrumSet:
    return values.copy(
        X=X,
        preprocessing_chain=[*values.metadata.get("preprocessing_chain", []), method_id],
    )


def _fit_indices(parameters: Mapping[str, Any], count: int) -> np.ndarray:
    indices = np.asarray(parameters.get("fit_indices", np.arange(count)), dtype=int)
    if indices.ndim != 1 or len(indices) == 0 or np.any(indices < 0) or np.any(indices >= count):
        raise ValueError("fit_indices must contain valid non-empty row indices")
    return indices


def _raw(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, SpectrumSet):
        raise TypeError("Raw expects SpectrumSet")
    output = _copy_spectrum(values, method_id="raw")
    return MethodExecutionResult(
        output,
        metrics={"sample_count": len(output.sample_ids), "feature_count": output.X.shape[1]},
        intermediate_states=[IntermediateState("raw", "spectrum", "morph_curve", {"spectrum": output.X.copy()})],
    )


def _snv(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, SpectrumSet):
        raise TypeError("SNV expects SpectrumSet")
    means = values.X.mean(axis=1, keepdims=True)
    scales = values.X.std(axis=1, keepdims=True)
    scales[scales == 0.0] = 1.0
    normalized = (values.X - means) / scales
    output = _copy_spectrum(values, X=normalized, method_id="snv")
    return MethodExecutionResult(
        output,
        metrics={"mean_before": float(np.mean(means)), "std_before": float(np.mean(scales))},
        intermediate_states=[IntermediateState(
            "snv_normalization", "spectrum", "show_formula",
            {"raw": values.X.copy(), "sample_mean": means.reshape(-1), "sample_std": scales.reshape(-1), "normalized": normalized.copy()},
            {"formula": "(x - mean(x)) / std(x)"},
        )],
    )


def _savgol(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, SpectrumSet):
        raise TypeError("Savitzky-Golay expects SpectrumSet")
    requested = int(parameters.get("window_length", 9))
    window = min(requested, values.X.shape[1] if values.X.shape[1] % 2 else values.X.shape[1] - 1)
    window = max(3, window)
    if window % 2 == 0:
        window -= 1
    polyorder = min(int(parameters.get("polyorder", 2)), window - 1)
    smoothed = savgol_filter(values.X, window_length=window, polyorder=polyorder, axis=1)
    output = _copy_spectrum(values, X=smoothed, method_id="savgol")
    return MethodExecutionResult(
        output,
        metrics={"window_length": window, "polyorder": polyorder},
        intermediate_states=[IntermediateState(
            "savgol_smoothing", "spectrum", "morph_curve",
            {"raw": values.X.copy(), "smoothed": smoothed.copy()},
            {"window_length": window, "polyorder": polyorder},
        )],
    )


def _pca(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, SpectrumSet):
        raise TypeError("PCA expects SpectrumSet")
    fit = _fit_indices(parameters, values.X.shape[0])
    n_components = max(1, min(
        int(parameters.get("n_components", 3)),
        values.X.shape[1],
        len(fit),
    ))
    center = StandardScaler(with_std=False)
    centered_fit = center.fit_transform(values.X[fit])
    centered_all = center.transform(values.X)
    model = PCA(n_components=n_components, random_state=seed)
    model.fit(centered_fit)
    scores = model.transform(centered_all)
    names = tuple(f"PC{index + 1}" for index in range(n_components))
    output = LatentFeatureSet(scores, names, values.sample_ids, values.y, dict(values.metadata), model.components_.T)
    output.metadata.update({"source_method": "pca", "fit_indices": fit.tolist()})
    analysis = FeatureAnalysisResult(
        "pca", output, names, scores=scores, loadings=model.components_.T,
        statistics={"explained_variance_ratio": model.explained_variance_ratio_.tolist()},
        metadata={"fit_indices": fit.tolist(), "source_feature_count": values.X.shape[1]},
    )
    return MethodExecutionResult(
        analysis,
        metrics={"component_count": n_components, "explained_variance": float(np.sum(model.explained_variance_ratio_))},
        intermediate_states=[IntermediateState(
            "pca_projection", "latent_features", "project_points",
            {"centered_X": centered_all.copy(), "scores": scores.copy(), "loadings": model.components_.T.copy()},
            {"explained_variance_ratio": model.explained_variance_ratio_.tolist()},
        )],
    )


def _splitter(X: np.ndarray, groups: np.ndarray | None, seed: int) -> Iterable[tuple[np.ndarray, np.ndarray]]:
    if groups is not None and len(np.unique(groups)) >= 2:
        splitter = GroupKFold(n_splits=min(5, len(np.unique(groups))))
        yield from splitter.split(X, groups=groups)
    else:
        splitter = KFold(n_splits=min(5, len(X)), shuffle=True, random_state=seed)
        yield from splitter.split(X)


def _safe_pls_components(features: int, samples: int, requested: int) -> int:
    return max(1, min(int(requested), features, max(1, samples - 1)))


def _cars(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, SpectrumSet):
        raise TypeError("CARS analysis expects SpectrumSet")
    fit = _fit_indices(parameters, values.X.shape[0])
    X_fit = values.X[fit]
    y_fit = values.y[fit] if values.y is not None else None
    if y_fit is None:
        raise ValueError("CARS requires a target y")
    iterations = max(1, int(parameters.get("iterations", 6)))
    min_features = max(1, min(int(parameters.get("min_features", 8)), values.X.shape[1]))
    decay = float(parameters.get("decay", 0.72))
    current = np.arange(values.X.shape[1], dtype=int)
    best_indices = current.copy()
    best_rmse = float("inf")
    states: list[IntermediateState] = []
    progression: list[float] = []
    rng = np.random.default_rng(seed)
    groups = values.metadata.get("groups")
    group_fit = None if groups is None else np.asarray(groups)[fit]
    for iteration in range(iterations):
        components = _safe_pls_components(len(current), len(fit), int(parameters.get("pls_components", 5)))
        model = PLSRegression(n_components=components, scale=True, max_iter=1000)
        fold_predictions = np.empty(len(fit), dtype=float)
        for train_fold, valid_fold in _splitter(X_fit[:, current], group_fit, seed + iteration):
            fold_model = PLSRegression(n_components=_safe_pls_components(len(current), len(train_fold), components), scale=True, max_iter=1000)
            fold_model.fit(X_fit[train_fold][:, :], y_fit[train_fold])
            fold_predictions[valid_fold] = np.asarray(fold_model.predict(X_fit[valid_fold][:, :])).reshape(-1)
        # Fit the coefficient model on the current features.  The fold model
        # above deliberately evaluates the same reduced matrix for leakage-safe
        # CARS ranking and RMSECV tracking.
        model.fit(X_fit[:, current], y_fit)
        coefficients = np.abs(np.asarray(model.coef_).reshape(-1))
        rmsecv = float(np.sqrt(mean_squared_error(y_fit, fold_predictions)))
        progression.append(rmsecv)
        if rmsecv <= best_rmse:
            best_rmse = rmsecv
            best_indices = current.copy()
        if len(current) <= min_features:
            retained = current.copy()
        else:
            retained_count = max(min_features, int(np.ceil(len(current) * decay)))
            ranking = np.argsort(-coefficients, kind="stable")
            retained = np.sort(current[ranking[:retained_count]])
        states.append(IntermediateState(
            f"cars_iteration_{iteration + 1}", "feature_selection", "remove_features",
            {"retained_indices": retained.copy(), "coefficients": coefficients.copy()},
            {"iteration": iteration + 1, "rmsecv": rmsecv, "feature_count": len(retained)},
        ))
        current = retained
        if len(current) <= min_features:
            break
        # A deterministic tie-breaker keeps future animation keyframes stable.
        rng.random(1)
    analysis = FeatureAnalysisResult(
        "cars", values, values.feature_names, selected_indices=best_indices,
        statistics={"rmsecv_progression": progression, "best_rmsecv": best_rmse},
        metadata={"fit_indices": fit.tolist(), "iterations": len(states), "min_features": min_features},
    )
    return MethodExecutionResult(
        analysis,
        metrics={"selected_features": int(len(best_indices)), "best_rmsecv": best_rmse},
        intermediate_states=states,
    )


def _cars_select(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, FeatureAnalysisResult) or values.method_id != "cars":
        raise TypeError("CARS selection expects a CARS FeatureAnalysisResult")
    if values.selected_indices is None:
        raise ValueError("CARS analysis did not provide selected indices")
    source = values.source
    indices = values.selected_indices
    if isinstance(source, SpectrumSet):
        names = tuple(source.feature_names[index] for index in indices)
        output = SelectedFeatureSet(source.X[:, indices], names, indices, source.sample_ids, source.y, dict(source.metadata))
    elif isinstance(source, LatentFeatureSet):
        names = tuple(source.feature_names[index] for index in indices)
        output = SelectedFeatureSet(source.X[:, indices], names, indices, source.sample_ids, source.y, dict(source.metadata))
    else:
        raise TypeError("unsupported CARS source type")
    output.metadata.update({"selection_method": "cars", "selection_statistics": values.statistics})
    return MethodExecutionResult(
        output,
        metrics={"original_features": len(values.feature_names), "selected_features": len(indices)},
        intermediate_states=[IntermediateState(
            "selected_wavelengths", "feature_selection", "select_features",
            {"selected_indices": indices.copy()},
            {"selected_feature_names": list(output.feature_names)},
        )],
    )


def _plsr(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, SelectedFeatureSet):
        raise TypeError("PLSR expects SelectedFeatureSet")
    if values.y is None:
        raise ValueError("PLSR requires a target y")
    fit = _fit_indices(parameters, values.X.shape[0])
    validation = np.asarray(parameters.get("validation_indices", np.setdiff1d(np.arange(len(values.sample_ids)), fit)), dtype=int)
    if len(validation) == 0:
        validation = fit.copy()
    components = _safe_pls_components(values.X.shape[1], len(fit), int(parameters.get("n_components", 5)))
    model = PLSRegression(n_components=components, scale=True, max_iter=1000)
    model.fit(values.X[fit], values.y[fit])
    prediction = np.asarray(model.predict(values.X)).reshape(-1)
    split = np.asarray(["calibration"] * len(values.sample_ids), dtype=object)
    split[validation] = "validation"
    residual = prediction - values.y
    validation_prediction = prediction[validation]
    validation_y = values.y[validation]
    evaluation = EvaluationResult(
        rmse=float(np.sqrt(mean_squared_error(validation_y, validation_prediction))),
        mae=float(mean_absolute_error(validation_y, validation_prediction)),
        r2=float(r2_score(validation_y, validation_prediction)) if len(validation) > 1 else 0.0,
        sample_count=int(len(validation)),
        feature_count=int(values.X.shape[1]),
        bias=float(np.mean(validation_prediction - validation_y)),
        metadata={"split": "validation", "fit_sample_count": int(len(fit))},
    )
    cv_scores: list[float] = []
    groups = values.metadata.get("groups")
    group_fit = None if groups is None else np.asarray(groups)[fit]
    for train_fold, valid_fold in _splitter(values.X[fit], group_fit, seed):
        fold_model = PLSRegression(n_components=_safe_pls_components(values.X.shape[1], len(train_fold), components), scale=True, max_iter=1000)
        fold_model.fit(values.X[fit][train_fold], values.y[fit][train_fold])
        fold_prediction = np.asarray(fold_model.predict(values.X[fit][valid_fold])).reshape(-1)
        cv_scores.append(float(np.sqrt(mean_squared_error(values.y[fit][valid_fold], fold_prediction))))
    evaluation.cv_rmse = float(np.mean(cv_scores)) if cv_scores else None
    predictions = PredictionSet(
        values.sample_ids, values.y, prediction, residual, tuple(split),
        metadata={"model": "PLSR", "validation_indices": validation.tolist()},
    )
    return MethodExecutionResult(
        ModelResult(
            "plsr", predictions, evaluation,
            {"n_components": components, "coefficients": np.asarray(model.coef_).reshape(-1), "x_scores": np.asarray(model.x_scores_)},
        ),
        metrics=evaluation.to_dict(),
        intermediate_states=[IntermediateState(
            "plsr_fit", "model", "connect_feature_to_prediction",
            {"scores": np.asarray(model.x_scores_), "coefficients": np.asarray(model.coef_).reshape(-1), "predictions": prediction.copy(), "residuals": residual.copy()},
            {"n_components": components},
        )],
    )


def _inspect(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, SpectrumSet):
        raise TypeError("Data inspection expects SpectrumSet")
    groups = values.metadata.get("groups", [])
    statistics = {
        "sample_count": len(values.sample_ids),
        "feature_count": int(values.X.shape[1]),
        "wavelength_min_nm": float(values.wavelengths.min()),
        "wavelength_max_nm": float(values.wavelengths.max()),
        "group_count": int(len(set(groups))) if len(groups) else 0,
        "has_target": values.y is not None,
    }
    return MethodExecutionResult(values, metrics=statistics, intermediate_states=[IntermediateState(
        "dataset_snapshot", "data", "highlight_sample", {"spectrum": values.X.copy()}, statistics,
    )])


def _summarize_results(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, ModelResult):
        raise TypeError("Results summary expects ModelResult")
    return MethodExecutionResult(
        values,
        metrics=values.evaluation.to_dict(),
        intermediate_states=[IntermediateState(
            "experiment_summary", "results", "show_residual",
            {"y_true": values.predictions.y_true.copy(), "y_pred": values.predictions.y_pred.copy(), "residuals": values.predictions.residuals.copy()},
            values.evaluation.to_dict(),
        )],
    )


def build_default_registry() -> MethodRegistry:
    registry = MethodRegistry()
    registry.register(Method("data.inspect", "Data Inspection", Stage.DATA_INSPECTION, DataKind.SPECTRUM_SET, DataKind.SPECTRUM_SET, {}, _inspect))
    registry.register(Method("raw", "Raw passthrough", Stage.PREPROCESSING, DataKind.SPECTRUM_SET, DataKind.SPECTRUM_SET, {}, _raw))
    registry.register(Method("snv", "SNV", Stage.PREPROCESSING, DataKind.SPECTRUM_SET, DataKind.SPECTRUM_SET, {}, _snv))
    registry.register(Method("savgol", "Savitzky–Golay", Stage.PREPROCESSING, DataKind.SPECTRUM_SET, DataKind.SPECTRUM_SET, {"window_length": 9, "polyorder": 2}, _savgol))
    registry.register(Method("pca", "PCA", Stage.FEATURE_ANALYSIS, DataKind.SPECTRUM_SET, DataKind.FEATURE_ANALYSIS, {"n_components": 3}, _pca))
    registry.register(Method("cars", "CARS stability analysis", Stage.FEATURE_ANALYSIS, DataKind.SPECTRUM_SET, DataKind.FEATURE_ANALYSIS, {"iterations": 6, "min_features": 8, "decay": 0.72}, _cars))
    registry.register(Method("cars.select", "CARS selected wavelengths", Stage.FEATURE_SELECTION, DataKind.FEATURE_ANALYSIS, DataKind.SELECTED_FEATURE_SET, {}, _cars_select))
    registry.register(Method("plsr", "PLSR", Stage.MODELING, DataKind.SELECTED_FEATURE_SET, DataKind.MODEL_RESULT, {"n_components": 5}, _plsr))
    registry.register(Method("results.summarize", "Experiment results summary", Stage.RESULTS, DataKind.MODEL_RESULT, DataKind.MODEL_RESULT, {}, _summarize_results))
    return registry


@dataclass(frozen=True)
class PipelineDefinition:
    preprocessing: tuple[str, ...] = ("snv",)
    feature_analysis: tuple[str, ...] = ("pca", "cars")
    feature_selection: str = "cars.select"
    modeling: tuple[str, ...] = ("plsr",)

    def validate(self, registry: MethodRegistry) -> None:
        if not self.preprocessing:
            raise ValueError("pipeline requires at least one preprocessing method")
        if not self.feature_analysis:
            raise ValueError("pipeline requires at least one feature analysis method")
        previous = DataKind.SPECTRUM_SET
        for method_id in self.preprocessing:
            method = registry.get(method_id)
            if method.stage is not Stage.PREPROCESSING or method.input_type is not previous or method.output_type is not DataKind.SPECTRUM_SET:
                raise TypeError(f"incompatible preprocessing method: {method_id}")
            previous = method.output_type
        for method_id in self.feature_analysis:
            method = registry.get(method_id)
            if method.stage is not Stage.FEATURE_ANALYSIS or method.input_type is not DataKind.SPECTRUM_SET:
                raise TypeError(f"feature analysis must consume SpectrumSet: {method_id}")
        selection = registry.get(self.feature_selection)
        if selection.stage is not Stage.FEATURE_SELECTION or selection.input_type is not DataKind.FEATURE_ANALYSIS:
            raise TypeError(f"invalid feature selection method: {self.feature_selection}")
        if not self.modeling:
            raise ValueError("pipeline requires at least one modeling method")
        for method_id in self.modeling:
            method = registry.get(method_id)
            if method.stage is not Stage.MODELING or method.input_type is not DataKind.SELECTED_FEATURE_SET:
                raise TypeError(f"modeling method must consume SelectedFeatureSet: {method_id}")

    def to_dict(self) -> dict[str, Any]:
        return _json_value({
            "preprocessing": self.preprocessing,
            "feature_analysis": self.feature_analysis,
            "feature_selection": self.feature_selection,
            "modeling": self.modeling,
        })


@dataclass
class StageRun:
    stage: Stage
    stage_run_id: str
    method_chain: list[str]
    input_ref: str
    output_ref: str
    parameters: dict[str, Any]
    output_kind: DataKind
    output: Any
    intermediate_states: list[IntermediateState]
    statistics: dict[str, Any]
    execution_metadata: dict[str, Any]
    random_seed: int
    created_at: str = field(default_factory=_now)
    cache_hit: bool = False

    @property
    def cache_key(self) -> str:
        document = {
            "stage": self.stage.value,
            "method_chain": self.method_chain,
            "input_ref": self.input_ref,
            "parameters": self.parameters,
            "seed": self.random_seed,
        }
        return hashlib.sha256(json.dumps(_json_value(document), sort_keys=True).encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "stage": self.stage.value,
            "stage_run_id": self.stage_run_id,
            "method_chain": self.method_chain,
            "input_ref": self.input_ref,
            "output_ref": self.output_ref,
            "parameters": _json_value(self.parameters),
            "output_kind": self.output_kind.value,
            "output": _serialize_output(self.output),
            "intermediate_states": [state.to_dict() for state in self.intermediate_states],
            "statistics": _json_value(self.statistics),
            "execution_metadata": _json_value(self.execution_metadata),
            "random_seed": self.random_seed,
            "created_at": self.created_at,
            "cache_hit": self.cache_hit,
        }

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "StageRun":
        return cls(
            Stage(document["stage"]), str(document["stage_run_id"]), list(document["method_chain"]),
            str(document["input_ref"]), str(document["output_ref"]), _from_json_value(document["parameters"]),
            DataKind(document["output_kind"]), _deserialize_output(document["output"]),
            [IntermediateState.from_dict(state) for state in document.get("intermediate_states", [])],
            _from_json_value(document.get("statistics", {})), _from_json_value(document.get("execution_metadata", {})),
            int(document["random_seed"]), str(document.get("created_at", _now())), bool(document.get("cache_hit", False)),
        )

    @classmethod
    def load(cls, path: Path) -> "StageRun":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass
class ExperimentRun:
    experiment_id: str
    dataset_id: str
    pipeline_definition: PipelineDefinition
    random_seed: int
    configuration_snapshot: dict[str, Any]
    stage_runs: list[StageRun] = field(default_factory=list)
    final_metrics: EvaluationResult | None = None
    final_model_id: str | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=_now)

    def add_stage_run(self, stage_run: StageRun) -> None:
        self.stage_runs.append(stage_run)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "experiment_id": self.experiment_id,
            "dataset_id": self.dataset_id,
            "pipeline_definition": self.pipeline_definition.to_dict(),
            "random_seed": self.random_seed,
            "configuration_snapshot": _json_value(self.configuration_snapshot),
            "stage_runs": [stage.to_dict() for stage in self.stage_runs],
            "final_metrics": None if self.final_metrics is None else self.final_metrics.to_dict(),
            "final_model_id": self.final_model_id,
            "artifacts": _json_value(self.artifacts),
            "created_at": self.created_at,
        }

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "ExperimentRun":
        definition_document = document["pipeline_definition"]
        metrics_document = document.get("final_metrics")
        metrics = None if metrics_document is None else EvaluationResult(**_from_json_value(metrics_document))
        return cls(
            str(document["experiment_id"]), str(document["dataset_id"]),
            PipelineDefinition(
                tuple(definition_document["preprocessing"]), tuple(definition_document["feature_analysis"]),
                str(definition_document["feature_selection"]), tuple(definition_document["modeling"]),
            ), int(document["random_seed"]), _from_json_value(document.get("configuration_snapshot", {})),
            [StageRun.from_dict(item) for item in document.get("stage_runs", [])], metrics,
            document.get("final_model_id"), _from_json_value(document.get("artifacts", [])), str(document.get("created_at", _now())),
        )

    @classmethod
    def load(cls, path: Path) -> "ExperimentRun":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _serialize_output(output: Any) -> dict[str, Any]:
    if isinstance(output, SpectrumSet):
        return {"kind": output.kind.value, "X": _json_value(output.X), "wavelengths": _json_value(output.wavelengths), "sample_ids": list(output.sample_ids), "y": _json_value(output.y), "metadata": _json_value(output.metadata)}
    if isinstance(output, LatentFeatureSet):
        return {"kind": output.kind.value, "X": _json_value(output.X), "feature_names": list(output.feature_names), "sample_ids": list(output.sample_ids), "y": _json_value(output.y), "metadata": _json_value(output.metadata), "loadings": _json_value(output.loadings)}
    if isinstance(output, SelectedFeatureSet):
        return {"kind": output.kind.value, "X": _json_value(output.X), "feature_names": list(output.feature_names), "selected_indices": _json_value(output.selected_indices), "sample_ids": list(output.sample_ids), "y": _json_value(output.y), "metadata": _json_value(output.metadata)}
    if isinstance(output, FeatureAnalysisResult):
        return {"kind": output.kind.value, "method_id": output.method_id, "source": _serialize_output(output.source), "feature_names": list(output.feature_names), "selected_indices": _json_value(output.selected_indices), "scores": _json_value(output.scores), "loadings": _json_value(output.loadings), "statistics": _json_value(output.statistics), "metadata": _json_value(output.metadata)}
    if isinstance(output, ModelResult):
        return {"kind": output.kind.value, "method_id": output.method_id, "predictions": _serialize_prediction(output.predictions), "evaluation": output.evaluation.to_dict(), "model_metadata": _json_value(output.model_metadata)}
    raise TypeError(f"cannot serialize workflow output: {type(output).__name__}")


def _serialize_prediction(output: PredictionSet) -> dict[str, Any]:
    return {"sample_ids": list(output.sample_ids), "y_true": _json_value(output.y_true), "y_pred": _json_value(output.y_pred), "residuals": _json_value(output.residuals), "split": list(output.split), "fold_ids": list(output.fold_ids), "metadata": _json_value(output.metadata)}


def _deserialize_output(document: Mapping[str, Any]) -> Any:
    kind = DataKind(document["kind"])
    if kind is DataKind.SPECTRUM_SET:
        return SpectrumSet(_from_json_value(document["X"]), _from_json_value(document["wavelengths"]), tuple(document["sample_ids"]), _from_json_value(document.get("y")), _from_json_value(document.get("metadata", {})))
    if kind is DataKind.LATENT_FEATURE_SET:
        return LatentFeatureSet(_from_json_value(document["X"]), tuple(document["feature_names"]), tuple(document["sample_ids"]), _from_json_value(document.get("y")), _from_json_value(document.get("metadata", {})), _from_json_value(document.get("loadings")))
    if kind is DataKind.SELECTED_FEATURE_SET:
        return SelectedFeatureSet(_from_json_value(document["X"]), tuple(document["feature_names"]), _from_json_value(document["selected_indices"]), tuple(document["sample_ids"]), _from_json_value(document.get("y")), _from_json_value(document.get("metadata", {})))
    if kind is DataKind.FEATURE_ANALYSIS:
        return FeatureAnalysisResult(document["method_id"], _deserialize_output(document["source"]), tuple(document["feature_names"]), _from_json_value(document.get("selected_indices")), _from_json_value(document.get("scores")), _from_json_value(document.get("loadings")), _from_json_value(document.get("statistics", {})), _from_json_value(document.get("metadata", {})))
    if kind is DataKind.MODEL_RESULT:
        prediction = document["predictions"]
        predictions = PredictionSet(tuple(prediction["sample_ids"]), _from_json_value(prediction["y_true"]), _from_json_value(prediction["y_pred"]), _from_json_value(prediction["residuals"]), tuple(prediction["split"]), tuple(prediction.get("fold_ids", [])), _from_json_value(prediction.get("metadata", {})))
        return ModelResult(document["method_id"], predictions, EvaluationResult(**_from_json_value(document["evaluation"])), _from_json_value(document.get("model_metadata", {})))
    raise ValueError(f"unknown workflow output kind: {kind}")


class StageCache:
    """In-memory cache for stage switching; optional disk persistence is explicit."""

    def __init__(self) -> None:
        self._items: dict[str, StageRun] = {}

    def get(self, key: str) -> StageRun | None:
        item = self._items.get(key)
        if item is None:
            return None
        cached = copy.deepcopy(item)
        cached.cache_hit = True
        return cached

    def put(self, item: StageRun) -> None:
        self._items[item.cache_key] = item
        cache_key = item.execution_metadata.get("cache_key")
        if isinstance(cache_key, str):
            self._items[cache_key] = item


def _fingerprint(value: Any) -> str:
    if isinstance(value, SpectrumSet):
        document = {"X": value.X.tolist(), "wavelengths": value.wavelengths.tolist(), "sample_ids": value.sample_ids, "y": None if value.y is None else value.y.tolist()}
    else:
        document = _serialize_output(value) if isinstance(value, (LatentFeatureSet, SelectedFeatureSet, FeatureAnalysisResult, ModelResult)) else _json_value(value)
    return hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()[:16]


class PipelineEngine:
    def __init__(self, registry: MethodRegistry | None = None, cache: StageCache | None = None) -> None:
        self.registry = registry or build_default_registry()
        self.cache = cache or StageCache()

    def _execute_method(self, method_id: str, value: Any, parameters: Mapping[str, Any], seed: int, stage: Stage, input_ref: str) -> tuple[Any, MethodExecutionResult]:
        method = self.registry.get(method_id)
        if method.stage is not stage:
            raise TypeError(f"{method_id} belongs to stage {method.stage.value}, not {stage.value}")
        actual_kind = getattr(value, "kind", None)
        if actual_kind is not method.input_type:
            raise TypeError(f"{method_id} expects {method.input_type.value}, got {actual_kind}")
        result = method.execute(value, parameters, seed)
        actual_output_kind = getattr(result.output, "kind", None)
        if actual_output_kind is not method.output_type:
            raise TypeError(f"{method_id} returned {actual_output_kind}, expected {method.output_type.value}")
        return result.output, result

    def _stage_run(self, stage: Stage, method_chain: Sequence[str], value: Any, parameters: Mapping[str, Any], seed: int, input_ref: str, stage_run_id: str) -> tuple[Any, StageRun]:
        key_document = {"input": _fingerprint(value), "stage": stage.value, "methods": list(method_chain), "parameters": _json_value(parameters), "seed": seed}
        key = hashlib.sha256(json.dumps(key_document, sort_keys=True).encode()).hexdigest()
        cached = self.cache.get(key)
        if cached is not None:
            return cached.output, cached
        current = value
        states: list[IntermediateState] = []
        metrics: dict[str, Any] = {}
        method_metadata: list[dict[str, Any]] = []
        for method_id in method_chain:
            current, result = self._execute_method(method_id, current, parameters, seed, stage, input_ref)
            states.extend(result.intermediate_states)
            metrics[method_id] = result.metrics
            method_metadata.append({"method_id": method_id, "metadata": result.metadata})
        stage_run = StageRun(stage, stage_run_id, list(method_chain), input_ref, _fingerprint(current), dict(parameters), getattr(current, "kind"), current, states, metrics, {"methods": method_metadata, "cache_key": key}, seed)
        self.cache.put(stage_run)
        return current, stage_run

    def execute(self, spectrum: SpectrumSet, experiment_id: str, dataset_id: str, seed: int, definition: PipelineDefinition | None = None, output_dir: Path | None = None) -> ExperimentRun:
        definition = definition or PipelineDefinition()
        definition.validate(self.registry)
        groups = spectrum.metadata.get("groups")
        if groups is not None and len(np.unique(groups)) >= 2:
            unique_groups = np.unique(groups)
            split = max(1, int(np.ceil(len(unique_groups) * 0.25)))
            rng = np.random.default_rng(seed)
            validation_groups = set(rng.choice(unique_groups, size=split, replace=False).tolist())
            validation_indices = np.asarray([index for index, group in enumerate(groups) if group in validation_groups], dtype=int)
        else:
            rng = np.random.default_rng(seed)
            order = rng.permutation(len(spectrum.sample_ids))
            validation_indices = np.sort(order[:max(1, int(len(order) * 0.25))])
        fit_indices = np.setdiff1d(np.arange(len(spectrum.sample_ids)), validation_indices)
        experiment = ExperimentRun(
            experiment_id, dataset_id, definition, seed,
            {"stage_order": [stage.value for stage in Stage], "fit_indices": fit_indices.tolist(), "validation_indices": validation_indices.tolist(), "target": spectrum.metadata.get("target_name")},
        )
        current, stage_run = self._stage_run(Stage.DATA_INSPECTION, ["data.inspect"], spectrum, {}, seed, "dataset:" + dataset_id, "data-inspection")
        experiment.add_stage_run(stage_run)
        current, stage_run = self._stage_run(Stage.PREPROCESSING, definition.preprocessing, current, {"fit_indices": fit_indices.tolist()}, seed, "stage:data-inspection", "preprocessing")
        experiment.add_stage_run(stage_run)
        analyses: dict[str, FeatureAnalysisResult] = {}
        for method_id in definition.feature_analysis:
            analysis_output, analysis_run = self._stage_run(Stage.FEATURE_ANALYSIS, [method_id], current, {"fit_indices": fit_indices.tolist()}, seed, "stage:preprocessing", f"feature-analysis-{method_id.replace('.', '-')}")
            experiment.add_stage_run(analysis_run)
            analyses[method_id] = analysis_output
        selection_source = analyses.get("cars") or next(iter(analyses.values()))
        selected, selection_run = self._stage_run(Stage.FEATURE_SELECTION, [definition.feature_selection], selection_source, {}, seed, f"stage:feature-analysis-{selection_source.method_id}", "feature-selection")
        experiment.add_stage_run(selection_run)
        model_results: list[tuple[str, ModelResult]] = []
        for method_id in definition.modeling:
            model, model_run = self._stage_run(Stage.MODELING, [method_id], selected, {"fit_indices": fit_indices.tolist(), "validation_indices": validation_indices.tolist()}, seed, "stage:feature-selection", f"modeling-{method_id.replace('.', '-')}")
            experiment.add_stage_run(model_run)
            model_results.append((method_id, model))
        if model_results:
            final_id, final_model = min(model_results, key=lambda item: item[1].evaluation.rmse)
            experiment.final_model_id = final_id
            experiment.final_metrics = final_model.evaluation
            _, results_run = self._stage_run(
                Stage.RESULTS,
                ["results.summarize"],
                final_model,
                {},
                seed,
                f"stage:modeling-{final_id.replace('.', '-')}",
                "results",
            )
            experiment.add_stage_run(results_run)
        if output_dir is not None:
            output_dir = Path(output_dir)
            experiment.artifacts.append({"type": "experiment", "path": "experiment.json"})
            experiment.save(output_dir / "experiment.json")
            for stage_run in experiment.stage_runs:
                stage_run.save(output_dir / "stages" / f"{stage_run.stage_run_id}.json")
        return experiment


def spectrum_from_run(run_dir: Path) -> SpectrumSet:
    root = Path(run_dir).resolve()
    samples_path = root / "data" / "samples.csv"
    spectra_path = root / "data" / "spectra.csv"
    with samples_path.open(newline="", encoding="utf-8") as stream:
        samples = list(csv.DictReader(stream))
    with spectra_path.open(newline="", encoding="utf-8") as stream:
        spectra = list(csv.DictReader(stream))
    if not samples or not spectra:
        raise ValueError("run must contain non-empty sample and spectra tables")
    sample_ids = [row["sample_id"] for row in samples]
    wavelengths = sorted({float(row["wavelength_nm"]) for row in spectra})
    lookup = {(row["sample_id"], float(row["wavelength_nm"])): row for row in spectra}
    X = np.asarray([[float(lookup[(sample_id, wavelength)]["reflectance"]) for wavelength in wavelengths] for sample_id in sample_ids], dtype=float)
    target_name = "ssc_brix" if "ssc_brix" in samples[0] else "synthetic_ssc_proxy"
    if target_name not in samples[0]:
        target_name = target_name if target_name in spectra[0] else None
    y = None if target_name is None else np.asarray([float(row[target_name]) for row in samples], dtype=float)
    groups = np.asarray([row.get("batch_id", row.get("fruit_id", sample_id)) for row, sample_id in zip(samples, sample_ids)])
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    return SpectrumSet(X, np.asarray(wavelengths), tuple(sample_ids), y, {
        "dataset_id": manifest.get("dataset_id", root.name),
        "source_type": manifest.get("source_type", samples[0].get("source_type", "unknown")),
        "target_name": target_name,
        "groups": groups,
        "run_dir": str(root),
    })


def run_workflow_from_run(run_dir: Path, output_dir: Path, experiment_id: str | None = None, seed: int = 20260920, definition: PipelineDefinition | None = None) -> ExperimentRun:
    spectrum = spectrum_from_run(run_dir)
    experiment_id = experiment_id or f"experiment_{Path(run_dir).name}"
    return PipelineEngine().execute(spectrum, experiment_id, str(spectrum.metadata.get("dataset_id", Path(run_dir).name)), seed, definition, output_dir)


def run_preprocessing_comparison(
    spectrum: SpectrumSet,
    chains: Sequence[Sequence[str]],
    seed: int = 20260920,
    cache: StageCache | None = None,
) -> list[StageRun]:
    """Run comparable preprocessing chains over the same samples and axis."""
    engine = PipelineEngine(cache=cache)
    results: list[StageRun] = []
    for index, chain in enumerate(chains, start=1):
        if not chain:
            raise ValueError("each preprocessing comparison chain must be non-empty")
        for method_id in chain:
            method = engine.registry.get(method_id)
            if method.stage is not Stage.PREPROCESSING:
                raise TypeError(f"comparison method is not preprocessing: {method_id}")
        _, stage_run = engine._stage_run(
            Stage.PREPROCESSING,
            tuple(chain),
            spectrum,
            {},
            seed,
            "dataset:" + str(spectrum.metadata.get("dataset_id", "unknown")),
            f"preprocessing-comparison-{index}",
        )
        results.append(stage_run)
    return results


__all__ = [
    "DataKind", "EvaluationResult", "ExperimentRun", "FeatureAnalysisResult", "IntermediateState", "LatentFeatureSet", "Method", "MethodRegistry", "ModelResult", "PipelineDefinition", "PipelineEngine", "PredictionSet", "SelectedFeatureSet", "SpectrumSet", "Stage", "StageCache", "StageRun", "build_default_registry", "run_preprocessing_comparison", "run_workflow_from_run", "spectrum_from_run",
]
