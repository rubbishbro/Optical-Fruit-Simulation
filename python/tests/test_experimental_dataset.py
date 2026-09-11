from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from fruitsim_ml.datasets import load_experimental_dataset, validate_experimental_dataset
from fruitsim_ml.datasets.loader import ExperimentalDatasetLoadError


def manifest(channels: list[str]) -> dict:
    return {
        "schema_version": 2,
        "dataset_id": "TEST_FIXTURE_v2",
        "source_type": "experimental",
        "status": "processed",
        "paper": {"title": "TEST FIXTURE", "journal": None, "year": None, "doi": None},
        "provenance": {"data_received_from": "TEST FIXTURE", "received_date": None,
                       "redistribution": {"allowed": True}, "raw_files": []},
        "available_channels": channels,
        "units": {"wavelength": "nm", "reflectance": "fraction_0_1",
                  "transmittance": "fraction_0_1", "mu_a": "mm^-1",
                  "mu_s_prime": "mm^-1", "ssc": "degree_brix", "firmness": "N",
                  "sample_thickness": "mm"},
        "wavelength": {"min_nm": 700, "max_nm": 800, "count": 2},
        "iad_settings": {"sample_thickness_mm": None, "refractive_index": None,
                          "anisotropy_factor": None, "software": None},
        "measurement": {"reflectance_method": None, "transmittance_method": None,
                         "instrument": None},
        "field_mapping": {}, "notes": "TEST FIXTURE; not experimental evidence",
    }


def make_dataset(root: Path, *, channels=None, wavelengths=(700.0, 800.0), spectra_rows=None) -> None:
    channels = channels or ["reflectance", "transmittance", "mu_a", "mu_s_prime"]
    root.mkdir(parents=True)
    (root / "processed").mkdir()
    (root / "manifest.json").write_text(json.dumps(manifest(channels)), encoding="utf-8")
    pd.DataFrame([
        {"dataset_id": "TEST_FIXTURE_v2", "sample_id": "S1", "cultivar": "TEST",
         "tissue": "flesh", "batch_id": "B1", "storage_day": 3, "ssc_brix": 12.2,
         "firmness_n": 41.0, "sample_thickness_mm": None, "notes": "TEST FIXTURE"},
    ]).to_csv(root / "processed" / "samples.csv", index=False)
    if spectra_rows is None:
        spectra_rows = [{
            "dataset_id": "TEST_FIXTURE_v2", "sample_id": "S1", "tissue": "flesh",
            "wavelength_nm": wavelength, "reflectance": 0.3, "transmittance": 0.2,
            "mu_a_mm_inv": 0.02, "mu_s_prime_mm_inv": 1.1,
        } for wavelength in wavelengths]
    pd.DataFrame(spectra_rows).to_csv(root / "processed" / "spectra.csv", index=False)


class ExperimentalDatasetTests(unittest.TestCase):
    def test_loads_all_channels_and_generates_internal_measurement_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dataset"
            make_dataset(root)
            dataset = load_experimental_dataset(root)
            report = validate_experimental_dataset(dataset)
            self.assertTrue(report["valid"], report)
            self.assertEqual(dataset.samples.loc[0, "measurement_id"], "S1")
            self.assertEqual(report["stats"]["sample_count"], 1)

    def test_only_absorption_and_scattering_are_legal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dataset"
            make_dataset(root, channels=["mu_a", "mu_s_prime"])
            spectra = pd.read_csv(root / "processed" / "spectra.csv").drop(columns=["reflectance", "transmittance"])
            spectra.to_csv(root / "processed" / "spectra.csv", index=False)
            report = validate_experimental_dataset(load_experimental_dataset(root))
            self.assertTrue(report["valid"], report)

    def test_missing_g_and_n_do_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dataset"
            make_dataset(root, channels=["mu_a", "mu_s_prime"])
            report = validate_experimental_dataset(root)
            self.assertTrue(report["valid"], report)
            self.assertFalse(report["checks"]["iad_g_and_refractive_index_required"])

    def test_wavelength_grid_mismatch_is_reported_without_interpolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dataset"
            make_dataset(root, spectra_rows=[
                {"dataset_id": "TEST_FIXTURE_v2", "sample_id": "S1", "tissue": "flesh", "wavelength_nm": 700, "reflectance": .3, "transmittance": .2, "mu_a_mm_inv": .02, "mu_s_prime_mm_inv": 1.1},
                {"dataset_id": "TEST_FIXTURE_v2", "sample_id": "S1", "tissue": "flesh", "wavelength_nm": 800, "reflectance": .3, "transmittance": .2, "mu_a_mm_inv": .02, "mu_s_prime_mm_inv": 1.1},
            ])
            samples = pd.DataFrame([{"dataset_id": "TEST_FIXTURE_v2", "sample_id": "S1", "tissue": "flesh", "ssc_brix": 12.2, "firmness_n": 41}, {"dataset_id": "TEST_FIXTURE_v2", "sample_id": "S2", "tissue": "flesh", "ssc_brix": 13.0, "firmness_n": 39}])
            samples.to_csv(root / "processed" / "samples.csv", index=False)
            spectra = pd.read_csv(root / "processed" / "spectra.csv")
            spectra = pd.concat([spectra, spectra.iloc[[0]].assign(sample_id="S2", wavelength_nm=750)], ignore_index=True)
            spectra.to_csv(root / "processed" / "spectra.csv", index=False)
            report = validate_experimental_dataset(root)
            self.assertFalse(report["valid"])
            self.assertTrue(any(item["code"] == "wavelength_grid_mismatch" for item in report["errors"]))
            self.assertFalse(report["checks"]["interpolation_performed"])

    def test_duplicate_and_fraction_range_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dataset"
            make_dataset(root)
            spectra = pd.read_csv(root / "processed" / "spectra.csv")
            spectra.loc[0, "reflectance"] = 1.2
            spectra = pd.concat([spectra, spectra.iloc[[0]]], ignore_index=True)
            spectra.to_csv(root / "processed" / "spectra.csv", index=False)
            report = validate_experimental_dataset(root)
            codes = {item["code"] for item in report["errors"]}
            self.assertIn("fraction_range", codes)
            self.assertIn("duplicate_spectrum_point", codes)

    def test_declared_missing_channel_is_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dataset"
            make_dataset(root)
            spectra = pd.read_csv(root / "processed" / "spectra.csv").drop(columns=["reflectance"])
            spectra.to_csv(root / "processed" / "spectra.csv", index=False)
            report = validate_experimental_dataset(root)
            self.assertFalse(report["valid"])
            self.assertTrue(any(item["code"] == "declared_channel_column_missing" for item in report["errors"]))

    def test_table_dataset_id_must_match_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dataset"
            make_dataset(root)
            samples = pd.read_csv(root / "processed" / "samples.csv")
            samples.loc[0, "dataset_id"] = "OTHER_DATASET"
            samples.to_csv(root / "processed" / "samples.csv", index=False)
            report = validate_experimental_dataset(root)
            self.assertFalse(report["valid"])
            self.assertTrue(any(item["code"] == "samples_dataset_id_mismatch" for item in report["errors"]))

    def test_manifest_wavelength_metadata_drift_is_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dataset"
            make_dataset(root)
            document = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            document["wavelength"]["count"] = 99
            (root / "manifest.json").write_text(json.dumps(document), encoding="utf-8")
            report = validate_experimental_dataset(root)
            self.assertFalse(report["valid"])
            self.assertTrue(any(item["code"] == "wavelength_metadata_drift" for item in report["errors"]))

    def test_missing_sample_id_uses_designed_loader_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dataset"
            make_dataset(root)
            samples = pd.read_csv(root / "processed" / "samples.csv").drop(columns=["sample_id"])
            samples.to_csv(root / "processed" / "samples.csv", index=False)
            with self.assertRaises(ExperimentalDatasetLoadError) as context:
                load_experimental_dataset(root)
            self.assertIn("samples.csv is missing required columns", str(context.exception))

    def test_pending_cli_reports_state_without_fake_table_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "pending"
            (root / "processed").mkdir(parents=True)
            pending_manifest = manifest([])
            pending_manifest["status"] = "pending"
            (root / "manifest.json").write_text(json.dumps(pending_manifest), encoding="utf-8")
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).parents[1])
            result = subprocess.run(
                [sys.executable, "-m", "fruitsim_ml", "validate-experimental", "--input", str(root)],
                env=env, capture_output=True, text=True, check=True,
            )
            self.assertIn("dataset pending; canonical tables not present yet", result.stdout)

    def test_metadata_joins_and_unknown_columns_are_not_filled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dataset"
            make_dataset(root)
            samples = pd.read_csv(root / "processed" / "samples.csv")
            samples["author_extra"] = "kept"
            samples["firmness_n"] = None
            samples.to_csv(root / "processed" / "samples.csv", index=False)
            dataset = load_experimental_dataset(root)
            report = validate_experimental_dataset(dataset)
            self.assertTrue(report["valid"], report)
            self.assertIn("author_extra", dataset.samples.columns)
            self.assertTrue(dataset.samples["firmness_n"].isna().all())
            joined = dataset.spectra.merge(dataset.samples[["sample_id", "ssc_brix", "firmness_n"]], on="sample_id")
            self.assertEqual(float(joined.loc[0, "ssc_brix"]), 12.2)
            self.assertTrue(joined["firmness_n"].isna().all())


if __name__ == "__main__":
    unittest.main()
