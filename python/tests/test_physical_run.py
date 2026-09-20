from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from fruitsim_pipeline.contracts import validate_run_directory
from fruitsim_pipeline.physical_run import PhysicalRunConfig, generate_physical_run
from fruitsim_ml.visualize import build_visualizations


class PhysicalRunTests(unittest.TestCase):
    def test_cpp_result_is_adapted_to_run_contract(self) -> None:
        root = Path(__file__).resolve().parents[2]
        binary = root / "build-mesh" / "apps" / "fruitsim_cli" / "fruitsim_cli"
        config = root / "configs" / "ring_sensor_demo.json"
        if not binary.is_file():
            self.skipTest("current C++ mesh build is not available")
        with tempfile.TemporaryDirectory() as directory:
            run_dir = generate_physical_run(
                Path(directory),
                "physical_test",
                PhysicalRunConfig(binary, config, photons=16, seed=9, threads=1),
            )
            report = validate_run_directory(run_dir)
            self.assertTrue(report["valid"])
            self.assertEqual(report["source_type"], "synthetic_physics")
            with (run_dir / "data" / "spectra.csv").open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 6)
            self.assertTrue(all(row["source_type"] == "synthetic_physics" for row in rows))
            self.assertTrue((run_dir / "simulation" / "cpp" / "manifest.json").is_file())
            visualization_dir = build_visualizations(run_dir)
            self.assertTrue((visualization_dir / "detector_spectrum.png").is_file())
            self.assertTrue((visualization_dir / "energy_audit.png").is_file())

    def test_cpp_same_seed_is_byte_reproducible(self) -> None:
        root = Path(__file__).resolve().parents[2]
        binary = root / "build-mesh" / "apps" / "fruitsim_cli" / "fruitsim_cli"
        config = root / "configs" / "ring_sensor_demo.json"
        if not binary.is_file():
            self.skipTest("current C++ mesh build is not available")
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_run = generate_physical_run(
                Path(first), "same_physical", PhysicalRunConfig(binary, config, photons=16, seed=19, threads=1),
            )
            second_run = generate_physical_run(
                Path(second), "same_physical", PhysicalRunConfig(binary, config, photons=16, seed=19, threads=1),
            )
            for filename in ("summary.csv", "instrument.csv", "instrument_regions.csv"):
                self.assertEqual(
                    (first_run / "simulation" / "cpp" / filename).read_bytes(),
                    (second_run / "simulation" / "cpp" / filename).read_bytes(),
                    filename,
                )


if __name__ == "__main__":
    unittest.main()
