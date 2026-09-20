from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fruitsim_pipeline.contracts import ContractError, validate_run_directory


IDENTITY_MM_TO_UNITY = [
    0.001, 0.0, 0.0, 0.0,
    0.0, 0.001, 0.0, 0.0,
    0.0, 0.0, -0.001, 0.0,
    0.0, 0.0, 0.0, 1.0,
]


def write_valid_run(root: Path) -> Path:
    run_dir = root / "run_contract_test"
    (run_dir / "data").mkdir(parents=True)
    sample_path = run_dir / "data" / "samples.csv"
    sample_path.write_text(
        "sample_id,fruit_id,batch_id,source_type\n"
        "S-0001,F-0001,B-0001,synthetic_math\n",
        encoding="utf-8",
    )
    artifact_digest = hashlib.sha256(sample_path.read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "run_id": "run_contract_test",
        "created_at": "2026-09-19T00:00:00Z",
        "status": "completed",
        "source_type": "synthetic_math",
        "generator_version": "0.1.0",
        "configuration_hash": "sha256:test-config",
        "seed": 20260819,
        "software": {"fruitsim_pipeline": "0.1.0"},
        "git_commit": None,
        "backend": "none",
        "coordinate_system": {
            "name": "fruitsim_rh_y_up",
            "handedness": "right",
            "up_axis": "+Y",
            "length_unit": "mm",
            "world_to_unity": IDENTITY_MM_TO_UNITY,
        },
        "data_status": "synthetic_demonstration",
        "model_status": "method_demo",
        "warnings": ["Synthetic data; not valid for real SSC prediction."],
        "artifacts_index": "artifacts.json",
    }
    request = {
        "schema_version": 1,
        "run_id": "run_contract_test",
        "source_type": "synthetic_math",
        "seed": 20260819,
        "output_dir": str(run_dir),
        "steps": ["generate", "validate"],
    }
    # "validate" is intentionally rejected by the request contract; the helper
    # only writes files needed by directory validation, not request validation.
    request.pop("steps")
    request["steps"] = ["generate"]
    status = {
        "schema_version": 1,
        "run_id": "run_contract_test",
        "state": "completed",
        "updated_at": "2026-09-19T00:00:01Z",
    }
    artifacts = {
        "schema_version": 1,
        "artifacts": [{
            "artifact_id": "samples",
            "role": "sample_table",
            "relative_path": "data/samples.csv",
            "media_type": "text/csv",
            "schema_version": 1,
            "producer": "test",
            "unit": None,
            "shape": [1, 4],
            "dtype": "text",
            "sha256": artifact_digest,
        }],
    }
    run_dir.joinpath("manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    run_dir.joinpath("request.json").write_text(json.dumps(request), encoding="utf-8")
    run_dir.joinpath("status.json").write_text(json.dumps(status), encoding="utf-8")
    run_dir.joinpath("artifacts.json").write_text(json.dumps(artifacts), encoding="utf-8")
    return run_dir


class RunContractTests(unittest.TestCase):
    def test_valid_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = validate_run_directory(write_valid_run(Path(directory)))
            self.assertTrue(report["valid"])
            self.assertEqual(report["artifacts_checked"], 1)
            self.assertTrue(report["samples_checked"])

    def test_hash_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = write_valid_run(Path(directory))
            (run_dir / "data" / "samples.csv").write_text("corrupted\n", encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "hash mismatch"):
                validate_run_directory(run_dir)

    def test_synthetic_run_requires_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = write_valid_run(Path(directory))
            manifest_path = run_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["warnings"] = []
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "must contain at least one warning"):
                validate_run_directory(run_dir)

    def test_artifact_path_cannot_escape_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = write_valid_run(Path(directory))
            artifacts_path = run_dir / "artifacts.json"
            artifacts = json.loads(artifacts_path.read_text(encoding="utf-8"))
            artifacts["artifacts"][0]["relative_path"] = "../outside.csv"
            artifacts_path.write_text(json.dumps(artifacts), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "escape"):
                validate_run_directory(run_dir)


if __name__ == "__main__":
    unittest.main()
