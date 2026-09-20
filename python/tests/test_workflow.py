from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fruitsim_pipeline.synthetic_math import MathSyntheticConfig, generate_math_run
from fruitsim_ml.workflow import (
    ExperimentRun,
    PipelineDefinition,
    PipelineEngine,
    StageCache,
    Stage,
    run_preprocessing_comparison,
    run_workflow_from_run,
    spectrum_from_run,
)


class WorkflowTests(unittest.TestCase):
    def _make_run(self, root: Path) -> Path:
        return generate_math_run(root / "runs", "workflow_input", MathSyntheticConfig(samples=32, seed=11, batch_count=4))

    def test_default_workflow_preserves_stages_and_reload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = self._make_run(root)
            experiment = run_workflow_from_run(run_dir, root / "experiment", seed=11)
            self.assertEqual(
                [stage.stage for stage in experiment.stage_runs],
                [Stage.DATA_INSPECTION, Stage.PREPROCESSING, Stage.FEATURE_ANALYSIS,
                 Stage.FEATURE_ANALYSIS, Stage.FEATURE_SELECTION, Stage.MODELING, Stage.RESULTS],
            )
            self.assertEqual(experiment.final_model_id, "plsr")
            self.assertIsNotNone(experiment.final_metrics)
            self.assertTrue((root / "experiment" / "experiment.json").is_file())
            self.assertGreaterEqual(len(experiment.stage_runs[3].intermediate_states), 2)
            self.assertTrue(any(state.event == "remove_features" for state in experiment.stage_runs[3].intermediate_states))

            loaded = ExperimentRun.load(root / "experiment" / "experiment.json")
            self.assertEqual(len(loaded.stage_runs), len(experiment.stage_runs))
            self.assertEqual(loaded.final_model_id, experiment.final_model_id)
            self.assertEqual(loaded.final_metrics.to_dict(), experiment.final_metrics.to_dict())

    def test_stage_cache_reuses_the_same_processing_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spectrum = spectrum_from_run(self._make_run(root))
            cache = StageCache()
            engine = PipelineEngine(cache=cache)
            first = engine.execute(
                spectrum, "first", "workflow_input", 11,
                PipelineDefinition(preprocessing=("raw", "snv")),
            )
            second = engine.execute(
                spectrum, "second", "workflow_input", 11,
                PipelineDefinition(preprocessing=("raw", "snv")),
            )
            self.assertFalse(first.stage_runs[1].cache_hit)
            self.assertTrue(second.stage_runs[1].cache_hit)
            self.assertEqual(first.stage_runs[1].output_kind, second.stage_runs[1].output_kind)

    def test_preprocessing_comparison_uses_one_input_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spectrum = spectrum_from_run(self._make_run(root))
            cache = StageCache()
            first = run_preprocessing_comparison(spectrum, (("raw",), ("snv",), ("savgol", "snv")), cache=cache)
            second = run_preprocessing_comparison(spectrum, (("raw",), ("snv",), ("savgol", "snv")), cache=cache)
            self.assertEqual([item.output.X.shape for item in first], [(32, 51)] * 3)
            self.assertEqual([item.output.kind.value for item in second], ["spectrum_set"] * 3)
            self.assertTrue(all(item.cache_hit for item in second))

    def test_pipeline_rejects_cross_stage_method_chain(self) -> None:
        engine = PipelineEngine()
        with self.assertRaises(TypeError):
            PipelineDefinition(preprocessing=("plsr",)).validate(engine.registry)


if __name__ == "__main__":
    unittest.main()
