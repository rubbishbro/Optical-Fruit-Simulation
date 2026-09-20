#!/usr/bin/env python3
"""Render a compact fruitsim Monte Carlo visualization set.

The script consumes the CSV files written by ``fruitsim_cli`` and produces
publication/demo-friendly PNGs.  It deliberately keeps the rendering layer
independent from the C++ transport implementation.

Example:
    python scripts/render_demo.py
    python scripts/render_demo.py --input results/my_run --output pics/my_run
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LogNorm, Normalize


ROOT = Path(__file__).resolve().parents[1]


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required input is missing: {path}")
    return pd.read_csv(path)


def _style(ax: plt.Axes, title: str) -> None:
    ax.set_title(title, pad=12, weight="bold")
    ax.grid(alpha=0.18)


def _set_equal_3d(ax, radius: float) -> None:
    ax.set_xlim(-radius, radius)
    ax.set_ylim(-radius, radius)
    ax.set_zlim(-radius, radius)
    ax.set_box_aspect((1, 1, 1))
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_zlabel("z (mm)")


def _draw_fruit_wireframe(ax, radius: float) -> None:
    u = np.linspace(0, 2 * np.pi, 36)
    v = np.linspace(0, np.pi, 18)
    x = radius * np.outer(np.cos(u), np.sin(v))
    y = radius * np.outer(np.sin(u), np.sin(v))
    z = radius * np.outer(np.ones_like(u), np.cos(v))
    ax.plot_wireframe(x, y, z, rstride=3, cstride=3, color="#806040", alpha=0.10,
                      linewidth=0.45)


def render_trajectories(data: pd.DataFrame, output: Path) -> None:
    fig = plt.figure(figsize=(10, 8), dpi=150)
    ax = fig.add_subplot(111, projection="3d")
    wavelengths = sorted(data["wavelength_nm"].unique())
    cmap = plt.get_cmap("turbo")
    colors = {w: cmap(i / max(1, len(wavelengths) - 1)) for i, w in enumerate(wavelengths)}
    radius = max(data[["x_mm", "y_mm", "z_mm"]].abs().max()) * 1.08
    for (wavelength, photon_id), path in data.sort_values("event").groupby(
        ["wavelength_nm", "photon_id"]
    ):
        ax.plot(path.x_mm, path.y_mm, path.z_mm, color=colors[wavelength], alpha=0.72,
                linewidth=0.9)
        ax.scatter(path.x_mm.iloc[0], path.y_mm.iloc[0], path.z_mm.iloc[0],
                   color=colors[wavelength], s=10, alpha=0.9)
    _draw_fruit_wireframe(ax, radius / 1.08)
    _set_equal_3d(ax, radius)
    ax.set_title("Photon trajectories", pad=18, weight="bold")
    handles = [plt.Line2D([0], [0], color=colors[w], lw=2, label=f"{int(w)} nm")
               for w in wavelengths]
    ax.legend(handles=handles, loc="upper left", fontsize=8, title="wavelength")
    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def render_scattering_points(data: pd.DataFrame, output: Path) -> None:
    points = data[data["event"] > 1].copy()
    points = points[points["weight"] > 0]
    fig = plt.figure(figsize=(10, 8), dpi=150)
    ax = fig.add_subplot(111, projection="3d")
    if points.empty:
        ax.text2D(0.35, 0.5, "No scattering points", transform=ax.transAxes)
        radius = 1.0
    else:
        weights = points["weight"].to_numpy()
        sizes = 5 + 34 * np.sqrt(weights / max(weights.max(), 1e-12))
        ax.scatter(points.x_mm, points.y_mm, points.z_mm, c=weights, s=sizes,
                   cmap="magma", norm=LogNorm(vmin=max(weights.min(), 1e-12),
                   vmax=max(weights.max(), 1e-12)), alpha=0.62, linewidths=0)
        radius = max(points[["x_mm", "y_mm", "z_mm"]].abs().max()) * 1.08
        _draw_fruit_wireframe(ax, radius / 1.08)
        mappable = plt.cm.ScalarMappable(norm=LogNorm(vmin=max(weights.min(), 1e-12),
                                                       vmax=max(weights.max(), 1e-12)),
                                          cmap="magma")
        fig.colorbar(mappable, ax=ax, shrink=0.65, pad=0.08, label="photon weight")
    _set_equal_3d(ax, radius)
    ax.set_title("Collision / scattering points", pad=18, weight="bold")
    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def render_absorption(data: pd.DataFrame, output: Path) -> None:
    size = int(max(data[["x_index", "y_index", "z_index"]].max()) + 1)
    volume = np.zeros((size, size, size), dtype=float)
    for row in data.itertuples(index=False):
        volume[int(row.z_index), int(row.y_index), int(row.x_index)] += row.absorbed_weight
    z = size // 2
    xy = volume[z]
    integrated = volume.sum(axis=0)
    extent = (-size / 2, size / 2, -size / 2, size / 2)
    positive = volume[volume > 0]
    norm = LogNorm(vmin=max(positive.min() if positive.size else 1e-12, 1e-12),
                   vmax=max(positive.max() if positive.size else 1e-12, 1e-12))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), dpi=150)
    for ax, image, title in ((axes[0], xy, f"central z slice (z index={z})"),
                             (axes[1], integrated, "depth-integrated absorption")):
        im = ax.imshow(np.where(image > 0, image, np.nan), origin="lower", extent=extent,
                       cmap="inferno", norm=norm)
        ax.set_xlabel("x index / relative mm")
        ax.set_ylabel("y index / relative mm")
        _style(ax, title)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="absorbed weight")
    fig.suptitle("Absorption heatmap", weight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def render_spectrum(summary: pd.DataFrame, instrument: pd.DataFrame, output: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), dpi=150)
    wavelength = summary["wavelength_nm"]
    axes[0, 0].plot(wavelength, summary["reflectance"], "o-", label="all escaped reflectance")
    axes[0, 0].plot(instrument["wavelength_nm"], instrument["detected_reflectance"], "s--",
                     label="detector response")
    axes[0, 0].set_xlabel("wavelength (nm)")
    axes[0, 0].set_ylabel("weight / launched photons")
    axes[0, 0].legend(fontsize=8)
    _style(axes[0, 0], "Spectral response")

    axes[0, 1].plot(instrument["wavelength_nm"], instrument["detected_penetration_mean_mm"],
                    "o-", label="detected mean depth")
    axes[0, 1].plot(summary["wavelength_nm"], summary["penetration_q90_mm"], "s--",
                    label="all-photon q90 depth")
    axes[0, 1].set_xlabel("wavelength (nm)")
    axes[0, 1].set_ylabel("depth (mm)")
    axes[0, 1].legend(fontsize=8)
    _style(axes[0, 1], "Penetration depth")

    axes[1, 0].plot(instrument["wavelength_nm"], instrument["skin_path_fraction"], "o-",
                    label="skin")
    axes[1, 0].plot(instrument["wavelength_nm"], instrument["flesh_path_fraction"], "o-",
                    label="flesh")
    axes[1, 0].set_ylim(0, 1)
    axes[1, 0].set_xlabel("wavelength (nm)")
    axes[1, 0].set_ylabel("detector path fraction")
    axes[1, 0].legend(fontsize=8)
    _style(axes[1, 0], "Region contribution")

    axes[1, 1].plot(summary["wavelength_nm"], summary["reflectance"], "o-", label="R")
    axes[1, 1].plot(summary["wavelength_nm"], summary["transmittance"], "o-", label="T")
    axes[1, 1].plot(summary["wavelength_nm"], summary["absorbed_total"], "o-", label="A")
    axes[1, 1].set_xlabel("wavelength (nm)")
    axes[1, 1].set_ylabel("energy fraction")
    axes[1, 1].legend(fontsize=8)
    _style(axes[1, 1], "R / T / A energy balance")
    fig.suptitle("Spectral and detector statistics", weight="bold")
    fig.tight_layout()
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "results" / "golden_delicious_demo",
                        help="fruitsim result directory containing CSV outputs")
    parser.add_argument("--output", type=Path, default=ROOT / "pics",
                        help="directory for rendered PNGs")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    trajectories = _read_csv(args.input / "trajectories.csv")
    absorption = _read_csv(args.input / "absorption_grid.csv")
    summary = _read_csv(args.input / "summary.csv")
    instrument = _read_csv(args.input / "instrument.csv")
    render_trajectories(trajectories, args.output / "01_photon_trajectories.png")
    render_scattering_points(trajectories, args.output / "02_scattering_points.png")
    render_absorption(absorption, args.output / "03_absorption_heatmap.png")
    render_spectrum(summary, instrument, args.output / "04_spectral_detector_statistics.png")
    print(f"Rendered 4 figures to {args.output}")


if __name__ == "__main__":
    main()
