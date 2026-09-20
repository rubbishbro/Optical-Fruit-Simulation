from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from .contracts import ContractError, validate_run_directory


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _add(report: dict[str, Any], check_id: str, passed: bool, evidence: str,
         *, severity: str = "high", caveat: bool = False) -> None:
    report["checks"].append({
        "id": check_id,
        "status": "caveat" if caveat else ("pass" if passed else "fail"),
        "severity": severity,
        "evidence": evidence,
    })
    if caveat:
        report["caveats"] += 1
    elif not passed:
        report["failures"] += 1


def _float(row: dict[str, str], key: str) -> float:
    value = float(row[key])
    if not math.isfinite(value):
        raise ValueError(f"{key} is not finite")
    return value


def _audit_common(root: Path, report: dict[str, Any], source_type: str) -> None:
    samples_path = root / "data" / "samples.csv"
    spectra_path = root / "data" / "spectra.csv"
    samples = _read_csv(samples_path)
    spectra = _read_csv(spectra_path)
    sample_ids = [row.get("sample_id", "") for row in samples]
    spectral_keys = [(row.get("sample_id", ""), row.get("wavelength_nm", "")) for row in spectra]
    _add(report, "sample_primary_key", len(sample_ids) == len(set(sample_ids)),
         f"{len(sample_ids)} sample rows, {len(set(sample_ids))} unique sample_id values")
    _add(report, "spectral_key_unique", len(spectral_keys) == len(set(spectral_keys)),
         f"{len(spectral_keys)} spectral rows, {len(set(spectral_keys))} unique sample/wavelength keys")
    _add(report, "spectra_foreign_keys", set(key[0] for key in spectral_keys) <= set(sample_ids),
         "Every spectral sample_id appears in samples.csv")
    groups: dict[str, set[str]] = {}
    for sample_id, wavelength in spectral_keys:
        groups.setdefault(sample_id, set()).add(wavelength)
    grid_sizes = {len(values) for values in groups.values()}
    wavelength_sets = list(groups.values())
    same_grid = bool(wavelength_sets) and all(values == wavelength_sets[0] for values in wavelength_sets[1:])
    _add(report, "complete_wavelength_grid", len(grid_sizes) == 1 and same_grid,
         f"Per-sample wavelength counts: {sorted(grid_sizes)}; identical grids: {same_grid}")
    sample_header = set(samples[0]) if samples else set()
    spectral_header = set(spectra[0]) if spectra else set()
    _add(report, "synthetic_label_boundary", "ssc_brix" not in sample_header and "ssc_brix" not in spectral_header,
         "No numeric ssc_brix column exists in the Run tables")
    _add(report, "source_declared", all(row.get("source_type") == source_type for row in samples + spectra),
         f"All records declare source_type={source_type}")


def _audit_math(root: Path, report: dict[str, Any]) -> None:
    rows = _read_csv(root / "data" / "spectra.csv")
    formula_ok = True
    formula_field_missing = False
    reflectance_ok = True
    proxy_by_sample: dict[str, set[str]] = {}
    for row in rows:
        try:
            mu_a = _float(row, "mu_a")
            mu_s_prime = _float(row, "mu_s_prime")
            reflectance = _float(row, "reflectance")
            _float(row, "synthetic_ssc_proxy")
            expected_mu_eff = math.sqrt(3.0 * mu_a * (mu_a + mu_s_prime))
            try:
                stored_mu_eff = _float(row, "mu_eff")
            except KeyError:
                formula_field_missing = True
            else:
                formula_ok = formula_ok and math.isclose(
                    stored_mu_eff, expected_mu_eff, rel_tol=2e-6, abs_tol=2e-7
                )
            reflectance_ok = reflectance_ok and 0.0 <= reflectance <= 1.0 and mu_a >= 0.0 and mu_s_prime >= 0.0
            proxy_by_sample.setdefault(row["sample_id"], set()).add(row["synthetic_ssc_proxy"])
        except (KeyError, ValueError, OverflowError):
            formula_ok = False
            reflectance_ok = False
    _add(report, "optical_formula_domain", formula_ok and not formula_field_missing,
         "Stored mu_eff is re-computed from sqrt(3 * mu_a * (mu_a + mu_s_prime)) within tolerance",
         caveat=formula_field_missing, severity="high")
    _add(report, "reflectance_domain", reflectance_ok,
         "Synthetic reflectance and optical coefficients remain in their declared domains")
    _add(report, "label_constant_per_sample", all(len(values) == 1 for values in proxy_by_sample.values()),
         "The synthetic proxy is a sample-level target, not a wavelength-specific leaked feature")
    _add(report, "synthetic_claim_boundary", True,
         "Run is explicitly synthetic and the target is synthetic_ssc_proxy, not ssc_brix", severity="low", caveat=True)


def _audit_physical(root: Path, report: dict[str, Any]) -> None:
    summary = _read_csv(root / "simulation" / "cpp" / "summary.csv")
    instrument = _read_csv(root / "simulation" / "cpp" / "instrument.csv")
    try:
        max_residual = max((abs(_float(row, "energy_residual")) for row in summary), default=float("inf"))
        energy_ok = bool(summary) and max_residual <= 1e-3
    except (KeyError, ValueError):
        max_residual = float("inf")
        energy_ok = False
    _add(report, "energy_residual", energy_ok,
         f"Maximum absolute 1-R-T-A-discarded residual: {max_residual:.6g}")
    identity_ok = True
    efficiency_ok = True
    try:
        for row in instrument:
            launched = _float(row, "launched_photons")
            detected = _float(row, "detected_weight")
            efficiency = _float(row, "detection_efficiency")
            specular = _float(row, "detected_specular_weight")
            diffuse = _float(row, "detected_diffuse_weight")
            detected_reflectance = _float(row, "detected_reflectance")
            identity_ok = identity_ok and math.isclose(detected, specular + diffuse, rel_tol=1e-8, abs_tol=1e-8)
            efficiency_ok = efficiency_ok and launched > 0.0 and 0.0 <= efficiency <= 1.0 and math.isclose(
                efficiency, detected / launched, rel_tol=1e-8, abs_tol=1e-8
            ) and math.isclose(detected_reflectance, efficiency, rel_tol=1e-8, abs_tol=1e-8)
    except (KeyError, ValueError, ZeroDivisionError):
        identity_ok = False
        efficiency_ok = False
    _add(report, "detector_weight_identity", identity_ok,
         "detected_weight equals detected_specular_weight + detected_diffuse_weight")
    _add(report, "detector_efficiency_definition", efficiency_ok,
         "detection_efficiency equals detected_weight / launched_photons and detected_reflectance")
    _add(report, "physical_target_boundary", True,
         "C++ physical Run carries no measured SSC target; calibration is still pending",
         severity="medium", caveat=True)


def _audit_ml_split(root: Path, report: dict[str, Any]) -> None:
    fold_path = root / "cv_folds.csv"
    schema_path = root / "feature_schema.json"
    if not fold_path.exists() and not schema_path.exists():
        _add(report, "ml_split_leakage", True,
             "No trained-model artifact in this Run; no ML split claim is made", severity="low", caveat=True)
        return
    if fold_path.exists():
        rows = _read_csv(fold_path)
        ids = [row.get("sample_id", "") for row in rows]
        sets = {row.get("set", "") for row in rows}
        calibration = {row["sample_id"] for row in rows if row.get("set") == "calibration"}
        validation = {row["sample_id"] for row in rows if row.get("set") == "validation"}
        _add(report, "ml_sample_split_disjoint", not (calibration & validation),
             f"Calibration/validation overlap: {len(calibration & validation)} sample_id values")
        _add(report, "ml_assignment_unique", len(ids) == len(set(ids)) and sets <= {"calibration", "validation"},
             f"{len(ids)} assignments, {len(set(ids))} unique sample_id values")
    if schema_path.exists():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        features = set(schema.get("features", []))
        target = schema.get("target")
        _add(report, "ml_target_not_feature", target not in features,
             f"Target {target!r} is absent from {len(features)} feature names")


def audit_run(run_dir: Path) -> dict[str, Any]:
    root = Path(run_dir).resolve()
    report: dict[str, Any] = {
        "schema_version": 1,
        "run_dir": str(root),
        "checks": [],
        "failures": 0,
        "caveats": 0,
    }
    try:
        validation = validate_run_directory(root)
    except ContractError as exc:
        report["overall"] = "fail"
        report["error"] = str(exc)
        report["failures"] = 1
        return report
    report.update({key: validation[key] for key in ("run_id", "status", "source_type")})
    _audit_common(root, report, validation["source_type"])
    if validation["source_type"] == "synthetic_math":
        _audit_math(root, report)
    elif validation["source_type"] == "synthetic_physics":
        _audit_physical(root, report)
    else:
        _add(report, "source_specific_checks", False,
             f"No final-package audit rules for source_type={validation['source_type']}", caveat=True, severity="medium")
    _audit_ml_split(root, report)
    report["overall"] = "fail" if report["failures"] else ("pass_with_caveats" if report["caveats"] else "pass")
    return report


def write_audit_report(run_dir: Path, output: Path | None = None) -> Path:
    report = audit_run(run_dir)
    destination = Path(output) if output else Path(run_dir) / "qa" / "audit_report.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination
