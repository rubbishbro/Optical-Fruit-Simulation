#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from fruitsim_ml.workflow import (
    ExperimentRun,
    FeatureSelectionSpec,
    MethodSpec,
    PipelineDefinition,
    PipelineEngine,
    Stage,
    StageCache,
    spectrum_from_run,
)


def pipeline_a() -> PipelineDefinition:
    return PipelineDefinition(
        preprocessing=(
            MethodSpec("savgol", {"window_length": 15, "polyorder": 3}),
            MethodSpec("snv"),
        ),
        feature_analysis=(
            MethodSpec("pca", {"n_components": 5}),
            MethodSpec("cars", {"iterations": 8, "min_features": 8, "decay": 0.72, "pls_components": 3}),
        ),
        feature_selection=FeatureSelectionSpec(MethodSpec("cars.select"), "cars"),
        modeling=(MethodSpec("plsr", {"n_components": 3}),),
    )


def pipeline_b() -> PipelineDefinition:
    return PipelineDefinition(
        preprocessing=(MethodSpec("snv"),),
        feature_analysis=(
            MethodSpec("pca", {"n_components": 3}),
            MethodSpec("cars", {"iterations": 5, "min_features": 6, "decay": 0.60, "pls_components": 2}),
        ),
        feature_selection=FeatureSelectionSpec(MethodSpec("cars.select"), "cars"),
        modeling=(MethodSpec("plsr", {"n_components": 2}),),
    )


def selected_indices(experiment: ExperimentRun) -> np.ndarray:
    return next(stage.output.selected_indices for stage in experiment.stage_runs if stage.stage is Stage.FEATURE_SELECTION)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    spectrum = spectrum_from_run(args.run_dir)
    cache = StageCache()
    engine = PipelineEngine(cache=cache)
    first = engine.execute(spectrum, "p0-correctness-a", str(spectrum.metadata["dataset_id"]), 20260920, pipeline_a(), args.output / "a")
    second = engine.execute(spectrum, "p0-correctness-b", str(spectrum.metadata["dataset_id"]), 20260920, pipeline_b(), args.output / "b")
    loaded_first = ExperimentRun.load(args.output / "a" / "experiment.json")
    loaded_second = ExperimentRun.load(args.output / "b" / "experiment.json")

    if loaded_first.final_metrics.to_dict() != first.final_metrics.to_dict():
        raise RuntimeError("pipeline A metrics changed after reload")
    if loaded_second.final_metrics.to_dict() != second.final_metrics.to_dict():
        raise RuntimeError("pipeline B metrics changed after reload")
    if not np.array_equal(selected_indices(loaded_first), selected_indices(first)):
        raise RuntimeError("pipeline A selected indices changed after reload")
    if not np.array_equal(selected_indices(loaded_second), selected_indices(second)):
        raise RuntimeError("pipeline B selected indices changed after reload")

    first_cars = next(stage for stage in first.stage_runs if stage.method_chain == ["cars"])
    second_cars = next(stage for stage in second.stage_runs if stage.method_chain == ["cars"])
    if first_cars.cache_key == second_cars.cache_key or second_cars.cache_hit:
        raise RuntimeError("different CARS parameters incorrectly shared a cache entry")

    report = {
        "dataset_id": spectrum.metadata["dataset_id"],
        "sample_count": len(spectrum.sample_ids),
        "feature_count": int(spectrum.X.shape[1]),
        "stage_order_a": [stage.stage.value for stage in first.stage_runs],
        "pipeline_a": first.pipeline_definition.to_dict(),
        "pipeline_b": second.pipeline_definition.to_dict(),
        "metrics_a": first.final_metrics.to_dict(),
        "metrics_b": second.final_metrics.to_dict(),
        "selected_indices_a": selected_indices(first).tolist(),
        "selected_indices_b": selected_indices(second).tolist(),
        "cars_cache_keys_distinct": first_cars.cache_key != second_cars.cache_key,
        "pipeline_b_cars_cache_hit": second_cars.cache_hit,
        "reload_metrics_equal": True,
        "reload_selected_indices_equal": True,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
