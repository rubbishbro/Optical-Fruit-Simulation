"""Generate auditable static figures from a Fruitsim Run directory."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from fruitsim_pipeline.contracts import validate_run_directory


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _load_run(run_dir: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    root = Path(run_dir).resolve()
    validate_run_directory(root)
    samples = _read_csv(root / "data" / "samples.csv")
    spectra = _read_csv(root / "data" / "spectra.csv")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not samples or not spectra:
        raise ValueError("Run must contain non-empty samples.csv and spectra.csv")
    return samples, spectra, manifest


def _matrix(spectra: list[dict[str, str]], field: str) -> tuple[list[str], np.ndarray, np.ndarray]:
    sample_ids = sorted({row["sample_id"] for row in spectra})
    wavelengths = sorted({float(row["wavelength_nm"]) for row in spectra})
    sample_index = {value: index for index, value in enumerate(sample_ids)}
    wavelength_index = {value: index for index, value in enumerate(wavelengths)}
    values = np.full((len(sample_ids), len(wavelengths)), np.nan, dtype=float)
    for row in spectra:
        values[sample_index[row["sample_id"]], wavelength_index[float(row["wavelength_nm"])] ] = float(row[field])
    if np.isnan(values).any():
        raise ValueError(f"spectra.csv has an incomplete grid for {field}")
    return sample_ids, np.asarray(wavelengths), values


def _save_figure(figure: Any, path: Path) -> None:
    figure.savefig(path, dpi=150, bbox_inches="tight")
    figure.clf()


def _build_physical_visualizations(
    root: Path, output: Path, spectra: list[dict[str, str]], manifest: dict[str, Any], plt: Any
) -> Path:
    wavelengths = np.asarray([float(row["wavelength_nm"]) for row in spectra])
    detected = np.asarray([float(row["detected_reflectance"]) for row in spectra])
    depth = np.asarray([float(row["detected_penetration_mean_mm"]) for row in spectra])
    flesh_fraction = np.asarray([float(row["flesh_path_fraction"]) for row in spectra])
    summary_path = root / "simulation" / "cpp" / "summary.csv"
    summary = _read_csv(summary_path)
    accepted_counts = np.asarray([int(row["detected_photon_count"]) for row in summary])
    figures: list[dict[str, Any]] = []

    figure, axis = plt.subplots(figsize=(10, 3.2))
    stages = ["C++ Monte Carlo", "Escape\nweight", "Detector\nfilter", "Run\nartifacts", "Unity\nviewer"]
    for index, stage in enumerate(stages):
        axis.text(index, 0.5, stage, ha="center", va="center", fontsize=10,
                  bbox={"boxstyle": "round,pad=0.55", "facecolor": "#edf7ed", "edgecolor": "#32733a"})
        if index < len(stages) - 1:
            axis.annotate("", xy=(index + 0.7, 0.5), xytext=(index + 0.3, 0.5),
                          arrowprops={"arrowstyle": "->", "color": "#566"})
    axis.set_xlim(-0.5, len(stages) - 0.5)
    axis.set_ylim(0, 1)
    axis.axis("off")
    figure.suptitle("Fruitsim physical result path — synthetic optical assumptions")
    path = output / "pipeline_path.png"
    _save_figure(figure, path)
    figures.append({"id": "pipeline_path", "path": path.name, "kind": "pipeline_graph"})

    figure, axis = plt.subplots(figsize=(8, 4.8))
    count_axis = axis.twinx()
    count_axis.bar(wavelengths, accepted_counts, width=44, alpha=0.22, color="#f28e2b",
                   label="Accepted photon count")
    axis.plot(wavelengths, detected, marker="o", linewidth=2.0, color="#1f77b4",
              label="Detected reflectance")
    axis.set(title="Detector response with sampling support", xlabel="Wavelength (nm)",
             ylabel="Detected reflectance (weight / launched photon)")
    count_axis.set_ylabel("Accepted photon count")
    count_axis.set_ylim(bottom=0)
    count_axis.locator_params(axis="y", integer=True)
    axis.grid(alpha=0.25)
    lines, labels = axis.get_legend_handles_labels()
    bars, bar_labels = count_axis.get_legend_handles_labels()
    axis.legend(lines + bars, labels + bar_labels, loc="best")
    path = output / "detector_spectrum.png"
    _save_figure(figure, path)
    figures.append({"id": "detector_spectrum", "path": path.name, "kind": "line_plot"})

    figure, axis = plt.subplots(figsize=(8, 4.8))
    fraction_axis = axis.twinx()
    axis.plot(wavelengths, depth, marker="s", linewidth=2.0, color="#f28e2b",
              label="Mean detected penetration depth")
    fraction_axis.plot(wavelengths, flesh_fraction, marker="o", linewidth=2.0, color="#2ca02c",
                       label="Flesh path fraction")
    axis.set(title="Detected sampling depth and tissue contribution", xlabel="Wavelength (nm)",
             ylabel="Mean detected penetration depth (mm)")
    fraction_axis.set_ylabel("Flesh path fraction")
    fraction_axis.set_ylim(0, 1)
    axis.grid(alpha=0.25)
    lines, labels = axis.get_legend_handles_labels()
    fraction_lines, fraction_labels = fraction_axis.get_legend_handles_labels()
    axis.legend(lines + fraction_lines, labels + fraction_labels, loc="best")
    path = output / "detector_path_statistics.png"
    _save_figure(figure, path)
    figures.append({"id": "detector_path_statistics", "path": path.name, "kind": "line_plot"})

    residuals = np.asarray([float(row["energy_residual"]) for row in summary])
    figure, axis = plt.subplots(figsize=(8, 3.8))
    axis.axhline(0.0, color="black", linewidth=0.8)
    axis.plot(wavelengths, residuals, marker="o", color="#b23a48")
    axis.set(title="Energy residual audit", xlabel="Wavelength (nm)", ylabel="1 − R − T − A − discarded")
    axis.grid(alpha=0.25)
    path = output / "energy_audit.png"
    _save_figure(figure, path)
    figures.append({"id": "energy_audit", "path": path.name, "kind": "audit_plot"})

    (output / "visualization_manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "run_id": manifest["run_id"],
        "source_type": manifest["source_type"],
        "warning": "Synthetic physics visualization; not valid for real apple SSC prediction.",
        "sample_count": 1,
        "wavelength_count": len(wavelengths),
        "figures": figures,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def build_visualizations(run_dir: Path, output_dir: Path | None = None) -> Path:
    """Write the standard WP4 figure set and a machine-readable figure manifest."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.decomposition import PCA

    root = Path(run_dir).resolve()
    samples, spectra, manifest = _load_run(root)
    output = Path(output_dir).resolve() if output_dir else root / "visualizations"
    output.mkdir(parents=True, exist_ok=True)
    if "detected_reflectance" in spectra[0]:
        return _build_physical_visualizations(root, output, spectra, manifest, plt)
    sample_ids, wavelengths, reflectance = _matrix(spectra, "reflectance")
    _, _, absorption = _matrix(spectra, "mu_a")
    proxy_by_id = {row["sample_id"]: float(row["synthetic_ssc_proxy"]) for row in samples}
    proxy = np.asarray([proxy_by_id[sample_id] for sample_id in sample_ids], dtype=float)

    figures: list[dict[str, Any]] = []
    figure = plt.figure(figsize=(12, 3.2))
    axis = figure.add_axes((0.02, 0.22, 0.96, 0.62))
    stages = ["Run\nsource", "Spectra", "Preprocess", "PCA /\nfeatures", "Model", "Evaluate", "Unity\nviewer"]
    for index, stage in enumerate(stages):
        axis.text(index, 0.5, stage, ha="center", va="center", fontsize=10,
                  bbox={"boxstyle": "round,pad=0.55", "facecolor": "#e7f0fa", "edgecolor": "#24527a"})
        if index < len(stages) - 1:
            axis.annotate("", xy=(index + 0.72, 0.5), xytext=(index + 0.28, 0.5),
                          arrowprops={"arrowstyle": "->", "color": "#566"})
    axis.set_xlim(-0.5, len(stages) - 0.5)
    axis.set_ylim(0, 1)
    axis.axis("off")
    figure.suptitle("Fruitsim data processing path — synthetic demonstration")
    path = output / "pipeline_path.png"
    _save_figure(figure, path)
    figures.append({"id": "pipeline_path", "path": path.name, "kind": "pipeline_graph"})

    figure, axis = plt.subplots(figsize=(10, 5.5))
    image = axis.imshow(reflectance, aspect="auto", interpolation="nearest", cmap="viridis")
    axis.set(title="Sample × wavelength reflectance", xlabel="Wavelength (nm)", ylabel="Sample index")
    axis.set_xticks(np.arange(0, len(wavelengths), max(1, len(wavelengths) // 8)))
    axis.set_xticklabels([f"{wavelengths[i]:g}" for i in axis.get_xticks().astype(int)])
    figure.colorbar(image, ax=axis, label="Reflectance")
    path = output / "spectra_heatmap.png"
    _save_figure(figure, path)
    figures.append({"id": "spectra_heatmap", "path": path.name, "kind": "heatmap"})

    scaled = (reflectance - reflectance.mean(axis=0)) / np.maximum(reflectance.std(axis=0), 1e-12)
    components = PCA(n_components=2, random_state=0).fit_transform(scaled)
    figure, axis = plt.subplots(figsize=(7, 5.5))
    scatter = axis.scatter(components[:, 0], components[:, 1], c=proxy, cmap="plasma", s=22, alpha=0.85)
    axis.set(title="PCA of reflectance spectra", xlabel="PC1", ylabel="PC2")
    figure.colorbar(scatter, ax=axis, label="Synthetic SSC proxy")
    path = output / "pca_scatter.png"
    _save_figure(figure, path)
    figures.append({"id": "pca_scatter", "path": path.name, "kind": "scatter", "points": len(sample_ids)})

    correlations = np.asarray([
        np.corrcoef(reflectance[:, index], proxy)[0, 1] if np.std(reflectance[:, index]) > 0 else 0.0
        for index in range(reflectance.shape[1])
    ])
    figure, axis = plt.subplots(figsize=(10, 2.8))
    image = axis.imshow(correlations[np.newaxis, :], aspect="auto", cmap="coolwarm", vmin=-1, vmax=1)
    axis.set(title="Wavelength correlation with synthetic SSC proxy", xlabel="Wavelength (nm)", yticks=[])
    axis.set_xticks(np.arange(0, len(wavelengths), max(1, len(wavelengths) // 8)))
    axis.set_xticklabels([f"{wavelengths[i]:g}" for i in axis.get_xticks().astype(int)])
    figure.colorbar(image, ax=axis, label="Pearson r")
    path = output / "proxy_correlation_heatmap.png"
    _save_figure(figure, path)
    figures.append({"id": "proxy_correlation_heatmap", "path": path.name, "kind": "correlation_heatmap"})

    figure, axis = plt.subplots(figsize=(9, 5.5))
    draw_indices = np.linspace(0, len(sample_ids) - 1, min(12, len(sample_ids)), dtype=int)
    for index in draw_indices:
        axis.plot(wavelengths, reflectance[index], alpha=0.55, linewidth=0.8)
    axis.plot(wavelengths, reflectance.mean(axis=0), color="black", linewidth=2.0, label="Mean")
    axis.set(title="Representative spectra", xlabel="Wavelength (nm)", ylabel="Reflectance")
    axis.legend()
    path = output / "spectra_overview.png"
    _save_figure(figure, path)
    figures.append({"id": "spectra_overview", "path": path.name, "kind": "line_plot"})

    manifest_path = output / "visualization_manifest.json"
    manifest_path.write_text(json.dumps({
        "schema_version": 1,
        "run_id": manifest["run_id"],
        "source_type": manifest["source_type"],
        "warning": "Synthetic visualization; not valid for real apple SSC prediction.",
        "sample_count": len(sample_ids),
        "wavelength_count": len(wavelengths),
        "figures": figures,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output
