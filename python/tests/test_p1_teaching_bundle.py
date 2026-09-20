from __future__ import annotations

import json
from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[2]
BUNDLE = REPO / "apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static/ml_p1_bundle.json"
TEMPLATE = REPO / "apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/index.html"


class P1TeachingBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))

    def test_bundle_has_six_stage_contract(self) -> None:
        self.assertEqual(
            set(self.bundle["stages"]),
            {"data_inspection", "preprocessing", "feature_analysis", "feature_selection", "modeling", "results"},
        )
        self.assertEqual(
            self.bundle["pipeline_order"],
            ["data_inspection", "preprocessing", "feature_analysis", "feature_selection", "modeling", "results"],
        )

    def test_preprocessing_comparison_keeps_invocations(self) -> None:
        combinations = self.bundle["stages"]["preprocessing"]["comparisons"]
        invocation_sets = {
            tuple(spec["invocation_id"] for spec in item["method_specs"])
            for item in combinations
        }
        self.assertIn(("sg5",), invocation_sets)
        self.assertIn(("sg15",), invocation_sets)
        self.assertIn(("sg15", "snv-after-sg15"), invocation_sets)

    def test_feature_analysis_and_model_identity_are_explicit(self) -> None:
        analyses = self.bundle["stages"]["feature_analysis"]
        self.assertEqual({item["method_specs"][0]["invocation_id"] for item in analyses}, {"pca", "cars"})
        self.assertEqual(self.bundle["experiment"]["final_model_id"], "plsr")
        self.assertEqual(
            self.bundle["experiment"]["model_invocations"][0]["stage_run_id"],
            self.bundle["stages"]["modeling"]["stage_run_id"],
        )

    def test_stage_refs_are_resolvable(self) -> None:
        stage_ids = {
            item["stage_run_id"]
            for value in self.bundle["stages"].values()
            for item in (value if isinstance(value, list) else [value])
        }
        for value in self.bundle["stages"].values():
            for item in (value if isinstance(value, list) else [value]):
                reference = item["input_ref"]
                if reference.startswith("stage:"):
                    self.assertIn(reference.removeprefix("stage:"), stage_ids)
        self.assertEqual(self.bundle["stages"]["results"]["input_ref"], "stage:modeling-plsr")

    def test_animation_contract_and_ui_entrypoints_exist(self) -> None:
        events = set(self.bundle["animation_events"])
        self.assertTrue({"show_spectrum", "show_mean", "show_std", "show_formula", "morph_curve"}.issubset(events))
        source = TEMPLATE.read_text(encoding="utf-8")
        for marker in (
            "ml-play-pipeline", "ml-restart", "ml-previous", "ml-next", "ml-pause",
            "ml-sample-select", "ml-feature-select", "Generate Apple", "Generate Batch",
            "GenerateBatchJson", "FruitsimAppleGenerated", "metadata",
        ):
            self.assertIn(marker, source)
        bridge = (REPO / "apps/fruitsim_unity/Assets/Scripts/Optics/FruitsimAppleGeneratorBridge.cs").read_text(encoding="utf-8")
        self.assertIn("class FruitsimAppleGeneratorBridge", bridge)


if __name__ == "__main__":
    unittest.main()
