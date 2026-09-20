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

    workflow_output = ROOT / "results/ml_workflow_demo"
    experiment = run_workflow_from_run(
        ROOT / "results/frontend_acceptance_20260920/student_demo_final/math_seed20260919",
        workflow_output,
        experiment_id="web_ml_workflow_demo",
        seed=20260920,
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
    print(f"Built research UI assets in {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
