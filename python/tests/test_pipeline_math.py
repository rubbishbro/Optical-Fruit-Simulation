from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np

from fruitsim_pipeline.contracts import ContractError, validate_run_directory
from fruitsim_pipeline.run_manager import RunManager
from fruitsim_pipeline.synthetic_math import MathSyntheticConfig, generate_math_run


class PipelineMathTests(unittest.TestCase):
    def test_math_run_is_reproducible_and_valid(self) -> None:
        config = MathSyntheticConfig(samples=12, seed=77, batch_count=3)
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_run = generate_math_run(Path(first), "same_run", config)
            second_run = generate_math_run(Path(second), "same_run", config)
            self.assertEqual(
                (first_run / "data" / "samples.csv").read_bytes(),
                (second_run / "data" / "samples.csv").read_bytes(),
            )
            first_npz = np.load(first_run / "data" / "spectra.npz")
            second_npz = np.load(second_run / "data" / "spectra.npz")
            for key in first_npz.files:
                if first_npz[key].dtype.kind in "OUS":
                    self.assertEqual(first_npz[key].tolist(), second_npz[key].tolist())
                else:
                    np.testing.assert_array_equal(first_npz[key], second_npz[key])
            report = validate_run_directory(first_run)
            self.assertTrue(report["valid"])
            self.assertEqual(report["status"], "completed")
            with (first_run / "data" / "samples.csv").open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 12)
            self.assertEqual({row["source_type"] for row in rows}, {"synthetic_math"})
            self.assertTrue(all("synthetic_ssc_proxy" in row for row in rows))
            self.assertTrue(all("ssc_brix" not in row for row in rows))

    def test_math_run_has_complete_grouped_wavelength_table(self) -> None:
        config = MathSyntheticConfig(samples=8, seed=12, batch_count=2,
                                     wavelength_start_nm=500.0,
                                     wavelength_end_nm=520.0,
                                     wavelength_step_nm=10.0)
        with tempfile.TemporaryDirectory() as directory:
            run_dir = generate_math_run(Path(directory), "small_run", config)
            with (run_dir / "data" / "spectra.csv").open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 8 * 3)
            groups = {}
            for row in rows:
                groups.setdefault(row["sample_id"], set()).add(row["wavelength_nm"])
            self.assertEqual(len(groups), 8)
            self.assertTrue(all(len(values) == 3 for values in groups.values()))

    def test_run_manager_rejects_overwrite_and_invalid_transition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager.create(Path(directory), "one", "synthetic_math", 1, ["generate"])
            with self.assertRaisesRegex(ContractError, "already exists"):
                RunManager.create(Path(directory), "one", "synthetic_math", 1, ["generate"])
            with self.assertRaisesRegex(ContractError, "invalid Run transition"):
                manager.set_state("completed")

    def test_failed_run_preserves_failure_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = RunManager.create(Path(directory), "failed_run", "synthetic_math", 1, ["generate"])
            manager.fail("expected test failure", error_code="test_failure")
            status = (manager.root / "status.json").read_text(encoding="utf-8")
            self.assertIn('"state": "failed"', status)
            self.assertIn('"error_code": "test_failure"', status)
            self.assertTrue(validate_run_directory(manager.root)["valid"])


if __name__ == "__main__":
    unittest.main()
