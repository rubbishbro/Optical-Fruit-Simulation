#!/usr/bin/env python3
"""Generate controlled, one-variable Monte Carlo comparisons for PPT figures.

Each comparison reuses the same mesh, tissue coefficients and random seed.  It
changes exactly one optical control: source-ring radius, source incident angle,
or lateral detector position.  The detector-rate metric is explicitly labelled
as a guided-MC visual response proxy, not an unbiased efficiency estimator.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import os
from pathlib import Path

_RESULTS = Path(os.environ.get("FRUITSIM_RESULTS_ROOT", "results"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from simulate_guided_photon_paths import (
    COLORS,
    RadialProportionalApple,
    read_ascii_ply,
    transport_one,
)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Noto Sans SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


WAVELENGTHS = (650, 800, 950)
BASE_SEED = 20260923


def simulate(config: dict, vertices: np.ndarray, faces: np.ndarray, seed: int) -> tuple[dict, dict]:
    model = RadialProportionalApple(
        vertices,
        np.zeros(3),
        config["layer_fractions"],
        int(config["boundary_samples"]),
    )
    rng = np.random.default_rng(seed)
    attempts = int(config["photons_per_wavelength"])
    keep_paths = int(config["accepted_paths_per_wavelength"])
    paths: dict[int, list[np.ndarray]] = {}
    metrics: dict[int, dict[str, float]] = {}
    for wavelength in WAVELENGTHS:
        accepted = 0
        event_counts: list[int] = []
        path_lengths: list[float] = []
        hits: list[np.ndarray] = []
        retained: list[np.ndarray] = []
        for _ in range(attempts):
            result = transport_one(rng, model, config, wavelength)
            if result is None:
                continue
            path, hit = result
            accepted += 1
            event_counts.append(max(0, len(path) - 1))
            path_lengths.append(float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum()))
            hits.append(np.asarray(hit, dtype=float))
            if len(retained) < keep_paths:
                retained.append(path)
        paths[wavelength] = retained
        hit_array = np.asarray(hits, dtype=float) if hits else np.empty((0, 3))
        metrics[wavelength] = {
            "attempts": attempts,
            "accepted_paths": accepted,
            "response_proxy": accepted / max(attempts, 1),
            "mean_events": float(np.mean(event_counts)) if event_counts else 0.0,
            "mean_path_length_mm": float(np.mean(path_lengths)) if path_lengths else 0.0,
            "mean_hit_x_mm": float(np.mean(hit_array[:, 0])) if len(hit_array) else float("nan"),
            "mean_hit_y_mm": float(np.mean(hit_array[:, 1])) if len(hit_array) else float("nan"),
            "mean_hit_z_mm": float(np.mean(hit_array[:, 2])) if len(hit_array) else float("nan"),
        }
    return paths, metrics


def apply_condition(config: dict, factor: str, value: float) -> None:
    if factor == "ring_radius":
        config["source"]["ring_radius_mm"] = float(value)
    elif factor == "incident_angle":
        config["source"]["incident_angle_deg"] = float(value)
    elif factor == "detector_offset":
        offset = float(value)
        config["detector"]["center_mm"] = [offset, 0.0, -41.25]
        config["detector"]["axis_toward_sample"] = [-offset, 0.0, 41.25]
    else:
        raise ValueError(f"unknown comparison factor: {factor}")


def condition_text(factor: str, value: float) -> str:
    if factor == "ring_radius":
        return f"R={value:g} mm"
    if factor == "incident_angle":
        return f"θ={value:g}°"
    return f"x={value:g} mm"


def plot_factor(output: Path, factor: str, title: str, unit: str,
                values: list[float], results: list[dict]) -> None:
    fig = plt.figure(figsize=(14, 8.2), facecolor="#F8FAFC")
    grid = fig.add_gridspec(2, 3, height_ratios=[1.05, 1.65], hspace=0.34, wspace=0.16)
    ax_response = fig.add_subplot(grid[0, :])
    x = np.arange(len(values))
    for wavelength in WAVELENGTHS:
        y = [item["metrics"][wavelength]["response_proxy"] for item in results]
        ax_response.plot(x, y, marker="o", linewidth=2.2, markersize=7,
                         color=COLORS[wavelength], label=f"{wavelength} nm")
        for index, metric in enumerate(y):
            ax_response.annotate(f"{metric:.3f}", (index, metric), textcoords="offset points",
                                 xytext=(0, 7), ha="center", fontsize=8, color=COLORS[wavelength])
    ax_response.set_xticks(x, [condition_text(factor, value) for value in values])
    ax_response.set_ylabel("Detected path rate proxy")
    ax_response.set_xlabel(f"Controlled variable ({unit})")
    ax_response.set_title("Detector response point plot / 探测器响应点图", loc="left", fontweight="bold")
    ax_response.grid(axis="y", alpha=0.22)
    ax_response.legend(frameon=False, ncol=3, loc="upper right")
    ax_response.text(0.0, -0.25,
                     "Same mesh, tissue coefficients, photon budget and seed; one control changed per row.",
                     transform=ax_response.transAxes, fontsize=9, color="#475569")

    for index, item in enumerate(results):
        ax = fig.add_subplot(grid[1, index])
        paths = item["paths"].get(800, [])
        for path in paths:
            ax.plot(path[:, 0], path[:, 2], color=COLORS[800], alpha=0.42, linewidth=0.85)
            ax.scatter(path[-1, 0], path[-1, 2], color="#DC2626", s=18, marker="*", zorder=3)
        detector = item["config"]["detector"]
        source = item["config"]["source"]
        ax.axhline(float(detector["center_mm"][2]), color="#0369A1", linewidth=2.0, alpha=0.8)
        ax.axhline(float(source["center_mm"][2]), color="#DC2626", linewidth=1.7, alpha=0.85)
        ax.set_title(condition_text(factor, values[index]), fontsize=11, fontweight="bold")
        ax.set_xlabel("X / mm")
        if index == 0:
            ax.set_ylabel("Z / mm")
        ax.grid(alpha=0.18)
        ax.set_aspect("equal", adjustable="box")
        ax.text(0.02, 0.04, f"800 nm paths: {len(paths)}\nmean events: {item['metrics'][800]['mean_events']:.1f}",
                transform=ax.transAxes, fontsize=8.5, color="#334155",
                bbox={"facecolor": "white", "alpha": 0.75, "edgecolor": "none"})
    fig.suptitle(f"{title}\nSimulation / 仿真结果", fontsize=18, fontweight="bold", color="#0F172A")
    fig.text(0.015, 0.012,
             "Blue lines: sensor plane · red line: ring source plane · red stars: accepted sensor hits · 800 nm representative paths",
             fontsize=9, color="#475569")
    fig.savefig(output, dpi=220, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def write_table(output: Path, rows: list[dict]) -> None:
    fields = ["factor", "factor_cn", "condition", "value", "unit", "wavelength_nm",
              "attempts", "accepted_paths", "response_proxy", "mean_events",
              "mean_path_length_mm", "mean_hit_x_mm", "mean_hit_y_mm", "mean_hit_z_mm"]
    with (output / "causal_comparison_table.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# Simulation / 仿真结果：单变量因果对比",
        "",
        "除表中控制变量外，其余网格、组织系数、光子预算、波长和随机种子保持一致。",
        "`response_proxy` = accepted detector-returning paths / attempted photons；本实验使用引导采样，不能当作无偏检测效率。",
        "",
        "| 对比组 | 控制变量 | 650 nm | 800 nm | 950 nm |",
        "|---|---:|---:|---:|---:|",
    ]
    grouped: dict[tuple[str, str], dict[int, float]] = {}
    for row in rows:
        key = (row["factor_cn"], row["condition"])
        grouped.setdefault(key, {})[int(row["wavelength_nm"])] = float(row["response_proxy"])
    for (factor_cn, condition), values in grouped.items():
        lines.append(f"| {factor_cn} | {condition} | {values.get(650, 0):.4f} | {values.get(800, 0):.4f} | {values.get(950, 0):.4f} |")
    (output / "causal_comparison_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh", type=Path, default=_RESULTS / "photon_paths_demo/outer_mesh.ply")
    parser.add_argument("--config", type=Path, default=Path("configs/guided_mc_skin_flesh_core.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/causal_comparisons"))
    args = parser.parse_args()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    base = json.loads(args.config.read_text(encoding="utf-8"))
    base["photons_per_wavelength"] = 600
    base["accepted_paths_per_wavelength"] = 14
    vertices, faces = read_ascii_ply(args.mesh)

    definitions = [
        ("ring_radius", "环形光源半径", "mm", [6.0, 8.0, 10.0], "Ring-source radius variation"),
        ("incident_angle", "入射角", "deg", [0.0, 15.0, 30.0], "Incident-angle variation"),
        ("detector_offset", "探测器横向位置", "mm", [0.0, 4.0, 8.0], "Detector-position variation"),
    ]
    all_rows: list[dict] = []
    manifest: dict[str, object] = {"mode": "controlled_one_variable_guided_monte_carlo",
                                    "label": "Simulation / 仿真结果", "comparisons": []}
    for factor, factor_cn, unit, values, title in definitions:
        results: list[dict] = []
        for value in values:
            config = copy.deepcopy(base)
            apply_condition(config, factor, value)
            paths, metrics = simulate(config, vertices, faces, BASE_SEED)
            result = {"value": value, "config": config, "paths": paths, "metrics": metrics}
            results.append(result)
            for wavelength in WAVELENGTHS:
                all_rows.append({
                    "factor": factor, "factor_cn": factor_cn, "condition": condition_text(factor, value),
                    "value": value, "unit": unit, "wavelength_nm": wavelength,
                    **metrics[wavelength],
                })
        plot_factor(output / f"{len(manifest['comparisons']) + 1:02d}_{factor}.png",
                    factor, title, unit, values, results)
        manifest["comparisons"].append({"factor": factor, "factor_cn": factor_cn,
                                         "unit": unit, "values": values,
                                         "fixed_seed": BASE_SEED})
    write_table(output, all_rows)
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
