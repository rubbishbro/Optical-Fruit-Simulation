from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from fruitsim_ml.data import generate_synthetic_golden_delicious
from fruitsim_ml.features import build_feature_matrix
from fruitsim_pipeline.audit import audit_run
from fruitsim_pipeline.synthetic_math import MathSyntheticConfig, generate_math_run


class AuditTests(unittest.TestCase):
    def test_math_run_audit_passes_with_explicit_synthetic_caveat(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = generate_math_run(Path(directory), "audit_math", MathSyntheticConfig(samples=12, seed=5))
            report = audit_run(run_dir)
            self.assertEqual(report["overall"], "pass_with_caveats")
            self.assertEqual(report["failures"], 0)
            self.assertEqual({check["status"] for check in report["checks"] if check["id"] == "synthetic_claim_boundary"}, {"caveat"})

    def test_target_is_not_in_feature_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dataset = generate_synthetic_golden_delicious(Path(directory) / "demo.csv", samples=12, seed=5)
            frame = pd.read_csv(dataset)
            matrix, labels, _, _, names = build_feature_matrix(frame, "reflectance")
            self.assertEqual(matrix.shape[0], 12)
            self.assertEqual(labels.shape[0], 12)
            self.assertTrue(all("ssc_brix" not in name for name in names))


if __name__ == "__main__":
    unittest.main()
