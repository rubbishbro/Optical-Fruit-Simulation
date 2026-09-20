#!/usr/bin/env python3
"""Build the small, source-backed figure bundle used by the WebGL teaching UI."""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static"
MATH = ROOT / "results/frontend_acceptance_20260920/student_demo_final/math_seed20260919/visualizations"
PHYSICAL = ROOT / "results/frontend_acceptance_20260920/student_demo_final/physical_seed20260919/visualizations"
ML = ROOT / "results/ml_golden_demo"

COPIES = {
    ROOT / "pics/03_absorption_heatmap.png": "absorption_heatmap.png",
    ROOT / "pics/10_weighted_photon_paths.png": "photon_paths.png",
    MATH / "spectra_heatmap.png": "spectra_heatmap.png",
    MATH / "pca_scatter.png": "pca_scatter.png",
    MATH / "spectra_overview.png": "spectra_overview.png",
    MATH / "proxy_correlation_heatmap.png": "proxy_correlation_heatmap.png",
    MATH / "pipeline_path.png": "ml_pipeline.png",
    PHYSICAL / "detector_spectrum.png": "detector_spectrum.png",
    PHYSICAL / "detector_path_statistics.png": "detector_path_statistics.png",
    PHYSICAL / "energy_audit.png": "energy_audit.png",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main() -> int:
    sys.path.insert(0, str(ROOT / "python"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    OUTPUT.mkdir(parents=True, exist_ok=True)
    missing = [str(path) for path in COPIES if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing research figures: " + ", ".join(missing))
    for source, name in COPIES.items():
        shutil.copy2(source, OUTPUT / name)

    metrics = json.loads((ML / "metrics.json").read_text(encoding="utf-8"))
    best = metrics["best"]
    predictions = [
        row for row in _read_csv(ML / "predictions.csv")
        if row["feature_set"] == best["feature_set"]
        and row["preprocessing"] == best["preprocessing"]
        and row["model"] == best["model"]
        and row["set"] == "validation"
    ]
    reference = np.asarray([float(row["reference_ssc_brix"]) for row in predictions])
    predicted = np.asarray([float(row["predicted_ssc_brix"]) for row in predictions])

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.edgecolor": "#3b4652",
        "axes.labelcolor": "#202832",
        "xtick.color": "#59636e",
        "ytick.color": "#59636e",
        "grid.color": "#d8dde2",
    })
    figure, axis = plt.subplots(figsize=(7.2, 5.2), facecolor="white")
    low = float(min(reference.min(), predicted.min()))
    high = float(max(reference.max(), predicted.max()))
    axis.scatter(reference, predicted, s=24, color="#1f5a89", alpha=0.72,
                 edgecolors="white", linewidths=0.35)
    axis.plot([low, high], [low, high], color="#b45f38", linewidth=1.4,
              linestyle="--", label="Ideal 1:1")
    axis.set(title="Validation prediction versus reference",
             xlabel="Reference SSC (°Brix)", ylabel="Predicted SSC (°Brix)")
    axis.grid(True, linewidth=0.6)
    axis.legend(frameon=False, loc="upper left")
    axis.text(0.98, 0.03,
              f"n={len(predictions)}  R²={best['validation_r2']:.3f}  RMSEP={best['rmsep']:.3f} °Brix",
              transform=axis.transAxes, ha="right", va="bottom", fontsize=9, color="#3b4652")
    figure.tight_layout()
    figure.savefig(OUTPUT / "ml_prediction_scatter.png", dpi=150, bbox_inches="tight")
    plt.close(figure)

    leaderboard = _read_csv(ML / "leaderboard.csv")[:8]
    labels = [row["run_id"].replace("__", " · ") for row in reversed(leaderboard)]
    rmsep = [float(row["rmsep"]) for row in reversed(leaderboard)]
    figure, axis = plt.subplots(figsize=(8.8, 5.2), facecolor="white")
    bars = axis.barh(labels, rmsep, color="#557a95", edgecolor="#27465c", linewidth=0.55)
    bars[-1].set_color("#b45f38")
    axis.set(title="Lowest validation error across candidate pipelines", xlabel="RMSEP (°Brix)")
    axis.set_xlim(0, max(rmsep) * 1.18)
    axis.grid(axis="x", linewidth=0.6)
    axis.set_axisbelow(True)
    for bar, value in zip(bars, rmsep):
        axis.text(value + max(rmsep) * 0.015, bar.get_y() + bar.get_height() / 2,
                  f"{value:.3f}", va="center", fontsize=8.5, color="#202832")
    figure.tight_layout()
    figure.savefig(OUTPUT / "ml_model_comparison.png", dpi=150, bbox_inches="tight")
    plt.close(figure)

    summary = {
        "schema_version": 1,
        "source": "results/ml_golden_demo",
        "data_boundary": "synthetic demonstration; not a real-apple performance claim",
        "best": best,
        "validation_prediction_count": len(predictions),
    }
    (OUTPUT / "ml_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    from fruitsim_ml.workflow import run_workflow_from_run
    from fruitsim_ml.workflow import (
        FeatureSelectionSpec,
        MethodSpec,
        PipelineDefinition,
        PipelineEngine,
        _json_value,
        run_preprocessing_comparison,
        spectrum_from_run,
    )

    workflow_output = ROOT / "results/ml_workflow_demo"
    experiment = run_workflow_from_run(
        ROOT / "results/frontend_acceptance_20260920/student_demo_final/math_seed20260919",
        workflow_output,
        experiment_id="web_ml_workflow_demo",
        seed=20260920,
    )
    spectrum = spectrum_from_run(ROOT / "results/frontend_acceptance_20260920/student_demo_final/math_seed20260919")
    data_stage = next(stage for stage in experiment.stage_runs if stage.stage.value == "data_inspection")
    preprocessing_stage = next(stage for stage in experiment.stage_runs if stage.stage.value == "preprocessing")
    analysis_stages = [stage for stage in experiment.stage_runs if stage.stage.value == "feature_analysis"]
    selection_stage = next(stage for stage in experiment.stage_runs if stage.stage.value == "feature_selection")
    modeling_stage = next(stage for stage in experiment.stage_runs if stage.stage.value == "modeling")
    results_stage = next(stage for stage in experiment.stage_runs if stage.stage.value == "results")
    fit_indices = set(experiment.configuration_snapshot.get("fit_indices", []))
    validation_indices = set(experiment.configuration_snapshot.get("validation_indices", []))
    split = [
        "calibration" if index in fit_indices else "validation" if index in validation_indices else "unused"
        for index in range(len(spectrum.sample_ids))
    ]

    def stage_contract(stage: Any) -> dict[str, Any]:
        return {
            "stage_run_id": stage.stage_run_id,
            "stage": stage.stage.value,
            "methods": stage.method_chain,
            "method_specs": [spec.to_dict() for spec in stage.method_specs],
            "input_ref": stage.input_ref,
            "output_ref": stage.output_ref,
            "output_kind": stage.output_kind.value,
            "parameters": stage.parameters,
            "statistics": stage.statistics,
            "execution_metadata": stage.execution_metadata,
            "intermediate_state_count": len(stage.intermediate_states),
            "states": [state.to_dict() for state in stage.intermediate_states],
            "cache_hit": stage.cache_hit,
        }

    def experiment_contract(value: Any) -> dict[str, Any]:
        modeling = [stage for stage in value.stage_runs if stage.stage.value == "modeling"]
        selection = next((stage for stage in value.stage_runs if stage.stage.value == "feature_selection"), None)
        selected_count = None
        if selection is not None and hasattr(selection.output, "selected_indices"):
            selected_count = int(len(selection.output.selected_indices))
        return {
            "experiment_id": value.experiment_id,
            "dataset_id": value.dataset_id,
            "pipeline": value.pipeline_definition.to_dict(),
            "final_model_id": value.final_model_id,
            "final_metrics": None if value.final_metrics is None else value.final_metrics.to_dict(),
            "selected_feature_count": selected_count,
            "model_invocations": [
                {
                    "stage_run_id": stage.stage_run_id,
                    "invocation_id": stage.method_specs[0].invocation_id,
                    "method_id": stage.method_specs[0].method_id,
                    "parameters": stage.parameters,
                    "metrics": stage.statistics,
                }
                for stage in modeling
            ],
        }

    original = data_stage.output
    processed = preprocessing_stage.output
    pca_stage = next(stage for stage in analysis_stages if stage.method_chain == ["pca"])
    cars_stage = next(stage for stage in analysis_stages if stage.method_chain == ["cars"])
    pca_output = pca_stage.output
    cars_output = cars_stage.output
    selection_output = selection_stage.output
    model_output = modeling_stage.output
    validation_prediction = model_output.predictions.validation_view()
    target_std = float(np.std(validation_prediction.y_true))
    collapse_ratio = float(np.std(validation_prediction.y_pred) / target_std) if target_std > 1e-12 else None

    comparison_specs = (
        (MethodSpec("raw", invocation_id="raw"),),
        (MethodSpec("snv", invocation_id="snv"),),
        (MethodSpec("savgol", {"window_length": 5, "polyorder": 2}, invocation_id="sg5"),),
        (MethodSpec("savgol", {"window_length": 15, "polyorder": 2}, invocation_id="sg15"),),
        (
            MethodSpec("savgol", {"window_length": 15, "polyorder": 2}, invocation_id="sg15"),
            MethodSpec("snv", invocation_id="snv-after-sg15"),
        ),
    )
    comparison_runs = run_preprocessing_comparison(spectrum, comparison_specs, seed=20260920)
    comparisons = []
    for run in comparison_runs:
        comparisons.append({
            **stage_contract(run),
            "visual": {
                "sample_ids": list(original.sample_ids),
                "wavelengths": original.wavelengths,
                "before": original.X,
                "after": run.output.X,
            },
        })

    cars_states = []
    for state in cars_stage.intermediate_states:
        cars_states.append({
            "name": state.name,
            "event": state.event,
            "arrays": state.arrays,
            "values": state.values,
        })

    p1_stages = {
        "data_inspection": {
            **stage_contract(data_stage),
            "visual": {
                "sample_ids": list(original.sample_ids),
                "wavelengths": original.wavelengths,
                "spectra": original.X,
                "target": original.y,
                "split": split,
                "groups": original.metadata.get("groups", []),
            },
        },
        "preprocessing": {
            **stage_contract(preprocessing_stage),
            "visual": {
                "sample_ids": list(original.sample_ids),
                "wavelengths": original.wavelengths,
                "before": original.X,
                "after": processed.X,
            },
            "comparisons": comparisons,
        },
        "feature_analysis": [
            {
                **stage_contract(pca_stage),
                "visual": {
                    "sample_ids": list(pca_output.source.sample_ids),
                    "feature_names": list(pca_output.feature_names),
                    "wavelengths": original.wavelengths,
                    "scores": pca_output.scores,
                    "loadings": pca_output.loadings,
                    "explained_variance_ratio": pca_output.statistics["explained_variance_ratio"],
                    "target": original.y,
                    "groups": original.metadata.get("groups", []),
                },
            },
            {
                **stage_contract(cars_stage),
                "visual": {
                    "sample_ids": list(cars_output.source.sample_ids),
                    "wavelengths": original.wavelengths,
                    "feature_names": list(cars_output.feature_names),
                    "target": original.y,
                    "states": cars_states,
                    "selected_indices": cars_output.selected_indices,
                    "rmsecv_progression": cars_output.statistics["rmsecv_progression"],
                    "best_rmsecv": cars_output.statistics["best_rmsecv"],
                },
            },
        ],
        "feature_selection": {
            **stage_contract(selection_stage),
            "visual": {
                "wavelengths": original.wavelengths,
                "feature_names": list(original.feature_names),
                "selected_indices": selection_output.selected_indices,
                "selected_feature_names": list(selection_output.feature_names),
                "source_invocation_id": experiment.pipeline_definition.feature_selection.source_invocation_id,
                "original_feature_count": int(len(original.feature_names)),
                "selected_feature_count": int(len(selection_output.selected_indices)),
            },
        },
        "modeling": {
            **stage_contract(modeling_stage),
            "visual": {
                "sample_ids": list(model_output.predictions.sample_ids),
                "y_true": model_output.predictions.y_true,
                "y_pred": model_output.predictions.y_pred,
                "residuals": model_output.predictions.residuals,
                "split": list(model_output.predictions.split),
                "scores": model_output.model_metadata.get("x_scores", []),
                "coefficients": model_output.model_metadata.get("coefficients", []),
                "evaluation": model_output.evaluation.to_dict(),
                "collapse_ratio": collapse_ratio,
            },
        },
        "results": {
            **stage_contract(results_stage),
            "visual": {
                "metrics": experiment.final_metrics.to_dict() if experiment.final_metrics else {},
                "collapse_ratio": collapse_ratio,
                "pipeline_stage_ids": [stage.stage_run_id for stage in experiment.stage_runs],
            },
        },
    }

    comparison_definition = PipelineDefinition(
        preprocessing=(
            MethodSpec("savgol", {"window_length": 15, "polyorder": 2}, invocation_id="sg15"),
            MethodSpec("snv", invocation_id="snv-after-sg15"),
        ),
        feature_analysis=(
            MethodSpec("pca", {"n_components": 2}, invocation_id="pca-2"),
            MethodSpec("cars", {"iterations": 3, "min_features": 8, "decay": 0.65, "pls_components": 2}, invocation_id="cars-compact"),
        ),
        feature_selection=FeatureSelectionSpec(MethodSpec("cars.select", invocation_id="cars-select-compact"), "cars-compact"),
        modeling=(MethodSpec("plsr", {"n_components": 3}, invocation_id="plsr-3"),),
    )
    compare_output = ROOT / "results/ml_workflow_demo_compare"
    comparison_experiment = PipelineEngine().execute(
        spectrum, "web_ml_workflow_compare", experiment.dataset_id, 20260920, comparison_definition, compare_output,
    )
    serialized_stages = [stage.to_dict() for stage in experiment.stage_runs]
    workflow_summary = {
        "schema_version": 1,
        "experiment_id": experiment.experiment_id,
        "dataset_id": experiment.dataset_id,
        "data_boundary": "synthetic demonstration; inspect source manifest before scientific use",
        "pipeline": experiment.pipeline_definition.to_dict(),
        "stages": [
            {
                "stage_run_id": stage["stage_run_id"],
                "stage": stage["stage"],
                "methods": stage["method_chain"],
                "input_ref": stage["input_ref"],
                "output_ref": stage["output_ref"],
                "output_kind": stage["output_kind"],
                "parameters": stage["parameters"],
                "statistics": stage["statistics"],
                "intermediate_state_count": len(stage["intermediate_states"]),
                "cache_hit": stage["cache_hit"],
            }
            for stage in serialized_stages
        ],
        "final_model_id": experiment.final_model_id,
        "final_metrics": experiment.final_metrics.to_dict() if experiment.final_metrics else None,
        "reloadable_artifact": "experiment.json",
    }
    (OUTPUT / "ml_workflow_summary.json").write_text(
        json.dumps(workflow_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    p1_bundle = {
        "schema_version": 1,
        "experiment_id": experiment.experiment_id,
        "dataset_id": experiment.dataset_id,
        "source": {
            "source_type": spectrum.metadata.get("source_type", "unknown"),
            "data_boundary": "synthetic demonstration; inspect source manifest before scientific use",
            "target_name": spectrum.metadata.get("target_name"),
            "sample_count": len(original.sample_ids),
            "feature_count": len(original.feature_names),
            "wavelength_min_nm": float(original.wavelengths.min()),
            "wavelength_max_nm": float(original.wavelengths.max()),
        },
        "selected_sample_id": original.sample_ids[0] if original.sample_ids else None,
        "active_stage": "data_inspection",
        "experiments": [experiment_contract(experiment), experiment_contract(comparison_experiment)],
        "experiment": experiment_contract(experiment),
        "configuration_snapshot": experiment.configuration_snapshot,
        "stages": p1_stages,
        "pipeline_order": ["data_inspection", "preprocessing", "feature_analysis", "feature_selection", "modeling", "results"],
        "animation_events": [
            "show_spectrum", "highlight_sample", "morph_curve", "show_mean", "show_std", "show_formula", "project_points",
            "highlight_loading", "remove_features", "select_features", "connect_feature_to_prediction",
            "show_prediction", "show_residual", "show_metric",
        ],
    }
    (OUTPUT / "ml_p1_bundle.json").write_text(
        json.dumps(_json_value(p1_bundle), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Built research UI assets in {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
