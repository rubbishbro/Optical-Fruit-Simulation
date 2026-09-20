from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import fruitsim_ml.workflow as workflow
from fruitsim_ml.workflow import (
    DataKind,
    EvaluationResult,
    ExperimentRun,
    FeatureAnalysisResult,
    FeatureSelectionSpec,
    MethodSpec,
    ModelResult,
    PipelineDefinition,
    PipelineEngine,
    PredictionSet,
    SelectedFeatureSet,
    SpectrumSet,
    Stage,
    StageCache,
    StageRun,
    deserialize_workflow_output,
    evaluate_predictions,
    run_preprocessing_comparison,
    select_final_model_by_cv,
    serialize_workflow_output,
)


def make_spectrum(*, display_label: str = "A", groups: np.ndarray | None = None) -> SpectrumSet:
    rng = np.random.default_rng(1204)
    sample_count = 30
    wavelengths = np.linspace(500.0, 700.0, 21)
    latent = rng.normal(size=sample_count)
    pattern = np.sin(np.linspace(0.0, np.pi, len(wavelengths)))
    X = 0.45 + 0.08 * latent[:, None] * pattern[None, :] + rng.normal(0.0, 0.006, (sample_count, len(wavelengths)))
    y = 12.0 + 1.7 * latent + rng.normal(0.0, 0.04, sample_count)
    if groups is None:
        groups = np.repeat(np.arange(6), 5)
    return SpectrumSet(
        X,
        wavelengths,
        tuple(f"sample-{index:03d}" for index in range(sample_count)),
        y,
        {
            "dataset_id": "controlled-synthetic-v1",
            "source_id": "unit-test-generator-1204",
            "source_type": "synthetic_math",
            "target_name": "ssc_brix",
            "groups": np.asarray(groups),
            "display": {"label": display_label},
        },
    )


def definition_a() -> PipelineDefinition:
    return PipelineDefinition(
        preprocessing=(
            MethodSpec("savgol", {"window_length": 5, "polyorder": 2}),
            MethodSpec("snv"),
        ),
        feature_analysis=(
            MethodSpec("pca", {"n_components": 3}),
            MethodSpec("cars", {"iterations": 4, "min_features": 5, "decay": 0.70, "pls_components": 2}),
        ),
        feature_selection=FeatureSelectionSpec(MethodSpec("cars.select"), "cars"),
        modeling=(MethodSpec("plsr", {"n_components": 2}),),
    )


def definition_b() -> PipelineDefinition:
    return PipelineDefinition(
        preprocessing=(MethodSpec("snv"),),
        feature_analysis=(
            MethodSpec("pca", {"n_components": 2}),
            MethodSpec("cars", {"iterations": 3, "min_features": 4, "decay": 0.55, "pls_components": 1}),
        ),
        feature_selection=FeatureSelectionSpec(MethodSpec("cars.select"), "cars"),
        modeling=(MethodSpec("plsr", {"n_components": 1}),),
    )


def dummy_model(model_id: str, cv_rmse: float, validation_rmse: float) -> ModelResult:
    predictions = PredictionSet(
        ("a", "b"), np.asarray([1.0, 2.0]), np.asarray([1.0, 2.0]), np.asarray([0.0, 0.0]),
        ("validation", "validation"),
    )
    return ModelResult(
        model_id,
        predictions,
        EvaluationResult(validation_rmse, validation_rmse, 0.0, 2, 1, cv_rmse=cv_rmse),
    )


class WorkflowCorrectnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spectrum = make_spectrum()

    def run_experiment(self, definition: PipelineDefinition | None = None, seed: int = 41) -> ExperimentRun:
        return PipelineEngine().execute(self.spectrum, "correctness", "controlled-synthetic-v1", seed, definition or definition_a())

    def assert_output_roundtrip(self, output: object) -> None:
        document = serialize_workflow_output(output)
        restored = deserialize_workflow_output(json.loads(json.dumps(document)))
        self.assertEqual(document, serialize_workflow_output(restored))

    # A. Serialization / deserialization
    def test_output_roundtrips_preserve_arrays_and_intermediate_states(self) -> None:
        experiment = self.run_experiment()
        self.assert_output_roundtrip(self.spectrum)
        for stage in experiment.stage_runs:
            self.assert_output_roundtrip(stage.output)
            restored = StageRun.from_dict(json.loads(json.dumps(stage.to_dict())))
            self.assertEqual(stage.to_dict(), restored.to_dict())
            self.assertEqual(
                [state.to_dict() for state in stage.intermediate_states],
                [state.to_dict() for state in restored.intermediate_states],
            )
        spectrum_roundtrip = deserialize_workflow_output(serialize_workflow_output(self.spectrum))
        self.assertEqual(self.spectrum.X.dtype, spectrum_roundtrip.X.dtype)
        self.assertEqual(self.spectrum.X.shape, spectrum_roundtrip.X.shape)

    def test_experiment_roundtrip_preserves_method_specs_and_metrics(self) -> None:
        experiment = self.run_experiment()
        restored = ExperimentRun.from_dict(json.loads(json.dumps(experiment.to_dict())))
        self.assertEqual(experiment.pipeline_definition.to_dict(), restored.pipeline_definition.to_dict())
        self.assertEqual(experiment.final_metrics.to_dict(), restored.final_metrics.to_dict())
        self.assertEqual(experiment.stage_runs[-1].method_specs, restored.stage_runs[-1].method_specs)

    # B. Pipeline type constraints
    def test_stage_type_constraints_and_unknown_methods(self) -> None:
        engine = PipelineEngine()
        selected = SelectedFeatureSet(
            self.spectrum.X[:, :2], self.spectrum.feature_names[:2], np.asarray([0, 1]),
            self.spectrum.sample_ids, self.spectrum.y, self.spectrum.metadata,
        )
        with self.assertRaises(TypeError):
            engine._stage_run(Stage.PREPROCESSING, [MethodSpec("snv")], selected, {}, 1, "selected", "bad")
        with self.assertRaises(TypeError):
            engine._stage_run(Stage.FEATURE_ANALYSIS, [MethodSpec("pca")], selected, {}, 1, "selected", "bad")
        with self.assertRaises(TypeError):
            engine._stage_run(Stage.MODELING, [MethodSpec("plsr")], self.spectrum, {}, 1, "spectrum", "bad")
        with self.assertRaises(TypeError):
            PipelineDefinition(preprocessing=(MethodSpec("plsr"),)).validate(engine.registry)
        with self.assertRaises(ValueError):
            PipelineDefinition(preprocessing=(MethodSpec("missing"),)).validate(engine.registry)

    def test_invalid_parameter_and_wrong_analysis_source_fail_explicitly(self) -> None:
        engine = PipelineEngine()
        with self.assertRaises(ValueError):
            PipelineDefinition(preprocessing=(MethodSpec("savgol", {"window_length": 4}),)).validate(engine.registry)
        with self.assertRaises(ValueError):
            PipelineDefinition(preprocessing=(MethodSpec("savgol", {"unknown": 3}),)).validate(engine.registry)
        wrong = PipelineDefinition(
            feature_analysis=(MethodSpec("pca"), MethodSpec("cars")),
            feature_selection=FeatureSelectionSpec(MethodSpec("cars.select"), "pca"),
        )
        with self.assertRaises(TypeError):
            wrong.validate(engine.registry)
        missing = PipelineDefinition(feature_selection=FeatureSelectionSpec(MethodSpec("cars.select"), "vip"))
        with self.assertRaises(ValueError):
            missing.validate(engine.registry)

    # C. Parameter correctness
    def test_method_defaults_overrides_and_output_shapes(self) -> None:
        engine = PipelineEngine()
        _, default_pca = engine._stage_run(
            Stage.FEATURE_ANALYSIS, [MethodSpec("pca")], self.spectrum,
            {"fit_indices": list(range(20))}, 3, "data", "pca-default",
        )
        _, override_pca = engine._stage_run(
            Stage.FEATURE_ANALYSIS, [MethodSpec("pca", {"n_components": 5})], self.spectrum,
            {"fit_indices": list(range(20))}, 3, "data", "pca-five",
        )
        self.assertEqual(default_pca.method_specs[0].resolved_parameters["n_components"], 3)
        self.assertEqual(override_pca.method_specs[0].resolved_parameters["n_components"], 5)
        self.assertEqual(default_pca.output.scores.shape, (30, 3))
        self.assertEqual(override_pca.output.scores.shape, (30, 5))

    def test_savgol_parameters_change_result_and_plsr_is_resolved(self) -> None:
        engine = PipelineEngine()
        out5, run5 = engine._stage_run(Stage.PREPROCESSING, [MethodSpec("savgol", {"window_length": 5})], self.spectrum, {}, 3, "data", "sg5")
        out9, run9 = engine._stage_run(Stage.PREPROCESSING, [MethodSpec("savgol", {"window_length": 9})], self.spectrum, {}, 3, "data", "sg9")
        self.assertFalse(np.allclose(out5.X, out9.X))
        self.assertNotEqual(run5.cache_key, run9.cache_key)
        experiment = self.run_experiment()
        modeling = next(stage for stage in experiment.stage_runs if stage.stage is Stage.MODELING)
        self.assertEqual(modeling.method_specs[0].resolved_parameters["n_components"], 2)
        self.assertIn("fit_indices", modeling.method_specs[0].resolved_parameters)
        self.assertIn("validation_indices", modeling.method_specs[0].resolved_parameters)

    def test_preprocessing_comparison_accepts_parameterized_method_specs(self) -> None:
        comparisons = run_preprocessing_comparison(
            self.spectrum,
            (
                (MethodSpec("savgol", {"window_length": 5, "polyorder": 2}, invocation_id="sg-5"),),
                (MethodSpec("savgol", {"window_length": 15, "polyorder": 2}, invocation_id="sg-15"),),
            ),
            seed=3,
        )
        self.assertEqual(
            [stage.method_specs[0].invocation_id for stage in comparisons],
            ["sg-5", "sg-15"],
        )
        self.assertEqual(
            [stage.method_specs[0].resolved_parameters["window_length"] for stage in comparisons],
            [5, 15],
        )
        self.assertFalse(np.allclose(comparisons[0].output.X, comparisons[1].output.X))
        self.assertNotEqual(comparisons[0].cache_key, comparisons[1].cache_key)

    # D. Cache correctness
    def test_cache_identity_seed_metadata_chain_and_reload(self) -> None:
        cache = StageCache()
        engine = PipelineEngine(cache=cache)
        _, first = engine._stage_run(Stage.PREPROCESSING, [MethodSpec("snv")], self.spectrum, {}, 1, "data", "snv-1")
        _, same = engine._stage_run(Stage.PREPROCESSING, [MethodSpec("snv")], self.spectrum, {}, 999, "data", "snv-2")
        self.assertTrue(same.cache_hit, "deterministic SNV should ignore seed in its cache identity")

        changed_groups = make_spectrum(groups=np.roll(np.asarray(self.spectrum.metadata["groups"]), 1))
        _, group_run = engine._stage_run(Stage.PREPROCESSING, [MethodSpec("snv")], changed_groups, {}, 1, "data", "snv-groups")
        self.assertFalse(group_run.cache_hit)

        display_only = make_spectrum(display_label="different label")
        _, display_run = engine._stage_run(Stage.PREPROCESSING, [MethodSpec("snv")], display_only, {}, 1, "data", "snv-display")
        self.assertTrue(display_run.cache_hit, "display-only metadata is intentionally excluded from cache identity")

        _, different_chain = engine._stage_run(Stage.PREPROCESSING, [MethodSpec("raw"), MethodSpec("snv")], self.spectrum, {}, 1, "data", "raw-snv")
        self.assertFalse(different_chain.cache_hit)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stage.json"
            first.save(path)
            loaded = StageRun.load(path)
            restored_cache = StageCache()
            restored_cache.put(loaded)
            _, restored_hit = PipelineEngine(cache=restored_cache)._stage_run(
                Stage.PREPROCESSING, [MethodSpec("snv")], self.spectrum, {}, 7, "data", "restored",
            )
            self.assertTrue(restored_hit.cache_hit)
            self.assertEqual(first.cache_key, restored_hit.cache_key)

    def test_seed_sensitive_cars_does_not_share_cache(self) -> None:
        cache = StageCache()
        engine = PipelineEngine(cache=cache)
        spec = MethodSpec("cars", {"iterations": 4, "min_features": 5, "decay": 0.7, "pls_components": 2})
        runtime = {"fit_indices": list(range(25))}
        _, first = engine._stage_run(Stage.FEATURE_ANALYSIS, [spec], self.spectrum, runtime, 10, "data", "cars-10")
        _, second = engine._stage_run(Stage.FEATURE_ANALYSIS, [spec], self.spectrum, runtime, 11, "data", "cars-11")
        self.assertFalse(first.cache_hit)
        self.assertFalse(second.cache_hit)
        self.assertNotEqual(first.cache_key, second.cache_key)

    def test_cache_reuse_keeps_current_invocation_identity(self) -> None:
        cache = StageCache()
        engine = PipelineEngine(cache=cache)
        spec_a = MethodSpec("savgol", {"window_length": 5}, invocation_id="sg-a")
        spec_b = MethodSpec("savgol", {"window_length": 5}, invocation_id="sg-b")
        _, first = engine._stage_run(Stage.PREPROCESSING, [spec_a], self.spectrum, {}, 1, "data", "sg-a-run")
        _, second = engine._stage_run(Stage.PREPROCESSING, [spec_b], self.spectrum, {}, 1, "data", "sg-b-run")
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(second.method_specs[0].invocation_id, "sg-b")
        self.assertEqual(set(second.statistics), {"sg-b"})
        self.assertEqual(second.execution_metadata["methods"][0]["invocation_id"], "sg-b")

    # E. Leakage
    def test_pca_fit_uses_only_fit_indices(self) -> None:
        real_pca = workflow.PCA
        fit_row_counts: list[int] = []

        class SpyPCA:
            def __init__(self, *args: object, **kwargs: object) -> None:
                self.inner = real_pca(*args, **kwargs)

            def fit(self, X: np.ndarray) -> "SpyPCA":
                fit_row_counts.append(len(X))
                self.inner.fit(X)
                self.components_ = self.inner.components_
                self.explained_variance_ratio_ = self.inner.explained_variance_ratio_
                return self

            def transform(self, X: np.ndarray) -> np.ndarray:
                return self.inner.transform(X)

        with patch.object(workflow, "PCA", SpyPCA):
            PipelineEngine()._stage_run(
                Stage.FEATURE_ANALYSIS, [MethodSpec("pca", {"n_components": 3})], self.spectrum,
                {"fit_indices": list(range(20))}, 1, "data", "pca-spy",
            )
        self.assertEqual(fit_row_counts, [20])

    def test_cars_and_plsr_never_fit_validation_rows(self) -> None:
        controlled = make_spectrum()
        controlled.X[24:] = 1_000_000.0
        real_pls = workflow.PLSRegression
        fitted_matrices: list[np.ndarray] = []

        class SpyPLS:
            def __init__(self, *args: object, **kwargs: object) -> None:
                self.inner = real_pls(*args, **kwargs)

            def fit(self, X: np.ndarray, y: np.ndarray) -> "SpyPLS":
                fitted_matrices.append(np.asarray(X).copy())
                self.inner.fit(X, y)
                return self

            def predict(self, X: np.ndarray) -> np.ndarray:
                return self.inner.predict(X)

            def __getattr__(self, name: str) -> object:
                return getattr(self.inner, name)

        fit = list(range(24))
        validation = list(range(24, 30))
        with patch.object(workflow, "PLSRegression", SpyPLS):
            cars, _ = PipelineEngine()._stage_run(
                Stage.FEATURE_ANALYSIS,
                [MethodSpec("cars", {"iterations": 3, "min_features": 5, "decay": 0.7, "pls_components": 2})],
                controlled, {"fit_indices": fit}, 2, "data", "cars-spy",
            )
            selected, _ = PipelineEngine()._stage_run(
                Stage.FEATURE_SELECTION, [MethodSpec("cars.select")], cars, {}, 2, "cars", "select-spy",
            )
            PipelineEngine()._stage_run(
                Stage.MODELING, [MethodSpec("plsr", {"n_components": 2})], selected,
                {"fit_indices": fit, "validation_indices": validation}, 2, "selected", "plsr-spy",
            )
        self.assertGreater(len(fitted_matrices), 3)
        self.assertTrue(all(float(np.max(matrix)) < 100_000.0 for matrix in fitted_matrices))

    def test_model_selection_uses_cv_not_validation(self) -> None:
        models = [("one", dummy_model("one", 0.2, 9.0)), ("two", dummy_model("two", 0.4, 0.1))]
        self.assertEqual(select_final_model_by_cv(models)[0], "one")
        changed_validation = [("one", dummy_model("one", 0.2, 0.01)), ("two", dummy_model("two", 0.4, 99.0))]
        self.assertEqual(select_final_model_by_cv(changed_validation)[0], "one")
        changed_cv = [("one", dummy_model("one", 0.8, 0.01)), ("two", dummy_model("two", 0.1, 99.0))]
        self.assertEqual(select_final_model_by_cv(changed_cv)[0], "two")

    def test_fit_and_validation_indices_must_be_disjoint(self) -> None:
        selected = SelectedFeatureSet(
            self.spectrum.X[:, :5], self.spectrum.feature_names[:5], np.arange(5),
            self.spectrum.sample_ids, self.spectrum.y, self.spectrum.metadata,
        )
        with self.assertRaises(ValueError):
            PipelineEngine()._stage_run(
                Stage.MODELING, [MethodSpec("plsr", {"n_components": 2})], selected,
                {"fit_indices": list(range(20)), "validation_indices": list(range(19, 25))},
                1, "selected", "overlap",
            )

    # F. Feature analysis / selection
    def test_parallel_analyses_and_explicit_cars_selection(self) -> None:
        experiment = self.run_experiment()
        analyses = [stage for stage in experiment.stage_runs if stage.stage is Stage.FEATURE_ANALYSIS]
        self.assertEqual([stage.method_chain for stage in analyses], [["pca"], ["cars"]])
        self.assertEqual(
            analyses[0].execution_metadata["input_fingerprint"],
            analyses[1].execution_metadata["input_fingerprint"],
        )
        selection = next(stage for stage in experiment.stage_runs if stage.stage is Stage.FEATURE_SELECTION)
        source = analyses[1].output.source
        indices = selection.output.selected_indices
        self.assertTrue(np.array_equal(selection.output.X, source.X[:, indices]))
        self.assertEqual(selection.output.feature_names, tuple(source.feature_names[index] for index in indices))

    def test_duplicate_methods_have_unique_invocations_and_exact_stage_references(self) -> None:
        definition = PipelineDefinition(
            preprocessing=(MethodSpec("snv", invocation_id="snv-main"),),
            feature_analysis=(
                MethodSpec(
                    "cars",
                    {"iterations": 3, "min_features": 5, "decay": 0.65, "pls_components": 2},
                    invocation_id="cars-a",
                ),
                MethodSpec(
                    "cars",
                    {"iterations": 5, "min_features": 8, "decay": 0.80, "pls_components": 3},
                    invocation_id="cars-b",
                ),
            ),
            feature_selection=FeatureSelectionSpec(
                MethodSpec("cars.select", invocation_id="cars-select-b"),
                "cars-b",
            ),
            modeling=(
                MethodSpec("plsr", {"n_components": 2}, invocation_id="plsr-2"),
                MethodSpec("plsr", {"n_components": 5}, invocation_id="plsr-5"),
            ),
        )
        experiment = self.run_experiment(definition)
        analyses = [stage for stage in experiment.stage_runs if stage.stage is Stage.FEATURE_ANALYSIS]
        self.assertEqual(
            [stage.method_specs[0].invocation_id for stage in analyses],
            ["cars-a", "cars-b"],
        )
        self.assertEqual([stage.method_chain for stage in analyses], [["cars"], ["cars"]])

        selection = next(stage for stage in experiment.stage_runs if stage.stage is Stage.FEATURE_SELECTION)
        cars_b_run = next(stage for stage in analyses if stage.method_specs[0].invocation_id == "cars-b")
        self.assertEqual(selection.input_ref, f"stage:{cars_b_run.stage_run_id}")

        model_runs = {
            str(stage.method_specs[0].invocation_id): stage
            for stage in experiment.stage_runs
            if stage.stage is Stage.MODELING
        }
        self.assertEqual(set(model_runs), {"plsr-2", "plsr-5"})
        expected_final = min(
            model_runs,
            key=lambda invocation_id: float(model_runs[invocation_id].output.evaluation.cv_rmse),
        )
        self.assertEqual(experiment.final_model_id, expected_final)

        results = next(stage for stage in experiment.stage_runs if stage.stage is Stage.RESULTS)
        selected_model_run = model_runs[expected_final]
        self.assertEqual(results.input_ref, f"stage:{selected_model_run.stage_run_id}")
        referenced_id = results.input_ref.removeprefix("stage:")
        referenced_run = next(stage for stage in experiment.stage_runs if stage.stage_run_id == referenced_id)
        self.assertIs(referenced_run, selected_model_run)
        self.assertEqual(referenced_run.method_specs[0].invocation_id, experiment.final_model_id)

    def test_cars_select_rejects_pca_analysis(self) -> None:
        pca, _ = PipelineEngine()._stage_run(
            Stage.FEATURE_ANALYSIS, [MethodSpec("pca")], self.spectrum,
            {"fit_indices": list(range(20))}, 1, "data", "pca",
        )
        with self.assertRaises(TypeError):
            PipelineEngine()._stage_run(Stage.FEATURE_SELECTION, [MethodSpec("cars.select")], pca, {}, 1, "pca", "bad-select")

    # G. Prediction / evaluation
    def test_metric_formulas_residual_sign_and_split_views(self) -> None:
        prediction = PredictionSet(
            ("a", "b", "c", "d"),
            np.asarray([1.0, 2.0, 4.0, 8.0]),
            np.asarray([2.0, 2.0, 1.0, 7.0]),
            np.asarray([1.0, 0.0, -3.0, -1.0]),
            ("calibration", "validation", "validation", "calibration"),
        )
        validation = prediction.validation_view()
        self.assertEqual(validation.sample_ids, ("b", "c"))
        self.assertEqual(prediction.calibration_view().sample_ids, ("a", "d"))
        metrics = evaluate_predictions(validation, 2)
        self.assertAlmostEqual(metrics.rmse, math.sqrt(4.5))
        self.assertAlmostEqual(metrics.mae, 1.5)
        self.assertAlmostEqual(metrics.r2, -3.5)
        self.assertAlmostEqual(metrics.bias, -1.5)
        self.assertTrue(np.array_equal(prediction.residuals, prediction.y_pred - prediction.y_true))

    def test_results_metrics_and_renderer_contract_are_validation_only(self) -> None:
        experiment = self.run_experiment()
        model_stage = next(stage for stage in experiment.stage_runs if stage.stage is Stage.MODELING)
        results_stage = next(stage for stage in experiment.stage_runs if stage.stage is Stage.RESULTS)
        validation = model_stage.output.predictions.validation_view()
        manual = evaluate_predictions(validation, model_stage.output.evaluation.feature_count, model_stage.output.evaluation.cv_rmse)
        self.assertAlmostEqual(experiment.final_metrics.rmse, manual.rmse)
        self.assertAlmostEqual(experiment.final_metrics.mae, manual.mae)
        self.assertAlmostEqual(experiment.final_metrics.r2, manual.r2)
        state = results_stage.intermediate_states[0]
        self.assertEqual(len(state.arrays["y_true"]), len(validation.sample_ids))
        self.assertEqual(state.values["default_prediction_view"], "validation")

        altered = PredictionSet(
            model_stage.output.predictions.sample_ids,
            model_stage.output.predictions.y_true.copy(),
            model_stage.output.predictions.y_pred.copy(),
            model_stage.output.predictions.residuals.copy(),
            model_stage.output.predictions.split,
        )
        calibration_indices = np.asarray([i for i, name in enumerate(altered.split) if name == "calibration"])
        altered.y_true[calibration_indices] += 500.0
        fixed_validation = evaluate_predictions(altered.validation_view(), model_stage.output.evaluation.feature_count)
        self.assertAlmostEqual(fixed_validation.rmse, manual.rmse)

    # H. Reproducibility and E2E
    def test_reproducibility_seed_behavior_and_replay(self) -> None:
        first = self.run_experiment(seed=77)
        second = self.run_experiment(seed=77)
        self.assertEqual(first.final_metrics.to_dict(), second.final_metrics.to_dict())
        first_selection = next(stage.output.selected_indices for stage in first.stage_runs if stage.stage is Stage.FEATURE_SELECTION)
        second_selection = next(stage.output.selected_indices for stage in second.stage_runs if stage.stage is Stage.FEATURE_SELECTION)
        self.assertTrue(np.array_equal(first_selection, second_selection))

        different = self.run_experiment(seed=78)
        first_cars = next(stage for stage in first.stage_runs if stage.method_chain == ["cars"])
        different_cars = next(stage for stage in different.stage_runs if stage.method_chain == ["cars"])
        self.assertNotEqual(first_cars.cache_key, different_cars.cache_key)
        self.assertNotEqual(
            first_cars.output.statistics["rmsecv_progression"],
            different_cars.output.statistics["rmsecv_progression"],
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "experiment.json"
            first.save(path)
            loaded = ExperimentRun.load(path)
            replayed = PipelineEngine().replay(loaded, self.spectrum)
            self.assertEqual(loaded.final_metrics.to_dict(), replayed.final_metrics.to_dict())
            replayed_selection = next(stage.output.selected_indices for stage in replayed.stage_runs if stage.stage is Stage.FEATURE_SELECTION)
            self.assertTrue(np.array_equal(first_selection, replayed_selection))

    def test_two_parameterized_e2e_runs_do_not_cross_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = StageCache()
            engine = PipelineEngine(cache=cache)
            first = engine.execute(self.spectrum, "e2e-a", "controlled-synthetic-v1", 31, definition_a(), root / "a")
            second = engine.execute(self.spectrum, "e2e-b", "controlled-synthetic-v1", 31, definition_b(), root / "b")
            first_cars = next(stage for stage in first.stage_runs if stage.method_chain == ["cars"])
            second_cars = next(stage for stage in second.stage_runs if stage.method_chain == ["cars"])
            self.assertFalse(first_cars.cache_hit)
            self.assertFalse(second_cars.cache_hit)
            self.assertNotEqual(first_cars.cache_key, second_cars.cache_key)
            self.assertNotEqual(first.pipeline_definition.to_dict(), second.pipeline_definition.to_dict())
            self.assertEqual(ExperimentRun.load(root / "a" / "experiment.json").final_metrics.to_dict(), first.final_metrics.to_dict())
            self.assertEqual(ExperimentRun.load(root / "b" / "experiment.json").final_metrics.to_dict(), second.final_metrics.to_dict())


if __name__ == "__main__":
    unittest.main()
