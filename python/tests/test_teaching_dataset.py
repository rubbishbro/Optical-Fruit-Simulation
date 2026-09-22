import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_teaching_dataset import build_teaching_run


class TeachingDatasetTests(unittest.TestCase):
    def test_dataset_is_deterministic_and_marked_for_teaching(self):
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = build_teaching_run(Path(first_dir), samples=128, seed=20260922)
            second = build_teaching_run(Path(second_dir), samples=128, seed=20260922)
            self.assertEqual((first / "manifest.json").read_bytes(), (second / "manifest.json").read_bytes())
            self.assertEqual((first / "data/samples.csv").read_bytes(), (second / "data/samples.csv").read_bytes())
            self.assertEqual((first / "data/spectra.csv").read_bytes(), (second / "data/spectra.csv").read_bytes())
            manifest = json.loads((first / "manifest.json").read_text())
            self.assertEqual(manifest["source_type"], "SYNTHETIC_TEACHING")
            self.assertEqual(manifest["purpose"], "visualization_and_teaching")
            self.assertTrue(manifest["not_experimental_evidence"])
            with (first / "data/samples.csv").open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            with (first / "data/spectra.csv").open(newline="") as handle:
                spectra = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 128)
            self.assertEqual(len(spectra), 128 * 61)
            self.assertEqual({row["batch_id"] for row in rows}, {"teaching-batch-1", "teaching-batch-2", "teaching-batch-3"})
            self.assertEqual(len({row["wavelength_nm"] for row in spectra}), 61)


if __name__ == "__main__":
    unittest.main()
