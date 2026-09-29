#!/usr/bin/env python3
"""Search a local joint optimum and verify the top candidates at higher budget."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

_RESULTS = Path(os.environ.get("FRUITSIM_RESULTS_ROOT", "results"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from generate_causal_comparisons import apply_condition, simulate
from simulate_guided_photon_paths import COLORS, read_ascii_ply

WAVELENGTHS = (650, 800, 950)
SEEDS = (20260923, 20260924, 20260925)


def evaluate(task: tuple[dict, int, str]) -> dict:
    values, seed, mesh_path = task
    config = copy.deepcopy(values["base"])
    for factor in ("ring_radius", "incident_angle", "detector_offset"):
        apply_condition(config, factor, values[factor])
    vertices, faces = read_ascii_ply(Path(mesh_path))
    _, metrics = simulate(config, vertices, faces, seed)
    response = [metrics[w]["response_proxy"] for w in WAVELENGTHS]
    return {
        "ring_radius": values["ring_radius"],
        "incident_angle": values["incident_angle"],
        "detector_offset": values["detector_offset"],
        "seed": seed,
        "mean_response": float(np.mean(response)),
        "response_650": response[0],
        "response_800": response[1],
        "response_950": response[2],
    }


def run_tasks(tasks: list[tuple[dict, int, str]], workers: int) -> list[dict]:
    rows = []
    with ProcessPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(evaluate, task) for task in tasks]
        for index, future in enumerate(as_completed(futures), start=1):
            rows.append(future.result())
            if index % 10 == 0 or index == len(futures):
                print(f"completed {index}/{len(futures)}", flush=True)
    return rows


def aggregate(rows: list[dict]) -> list[dict]:
    grouped = {}
    for row in rows:
        key = (row["ring_radius"], row["incident_angle"], row["detector_offset"])
        grouped.setdefault(key, []).append(row)
    result = []
    for (radius, angle, offset), items in grouped.items():
        result.append({
            "ring_radius": radius,
            "incident_angle": angle,
            "detector_offset": offset,
            "replicates": len(items),
            "mean_response": float(np.mean([x["mean_response"] for x in items])),
            "std_response": float(np.std([x["mean_response"] for x in items], ddof=1)),
            "response_650": float(np.mean([x["response_650"] for x in items])),
            "response_800": float(np.mean([x["response_800"] for x in items])),
            "response_950": float(np.mean([x["response_950"] for x in items])),
        })
    return sorted(result, key=lambda x: x["mean_response"], reverse=True)


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def plot_grid(output: Path, rows: list[dict], angle_values: list[float]) -> None:
    radius_values = sorted({r["ring_radius"] for r in rows})
    offset_values = sorted({r["detector_offset"] for r in rows})
    fig, axes = plt.subplots(1, len(angle_values), figsize=(15, 5.0), sharex=True, sharey=True)
    axes = np.atleast_1d(axes)
    vmin = min(r["mean_response"] for r in rows)
    vmax = max(r["mean_response"] for r in rows)
    for ax, angle in zip(axes, angle_values):
        values = np.full((len(offset_values), len(radius_values)), np.nan)
        for row in rows:
            if row["incident_angle"] == angle:
                values[offset_values.index(row["detector_offset"]), radius_values.index(row["ring_radius"])] = row["mean_response"]
        im = ax.imshow(values, origin="lower", aspect="auto", vmin=vmin, vmax=vmax, cmap="viridis")
        ax.set_title(f"入射角 {angle:g}°")
        ax.set_xticks(range(len(radius_values)), [f"{v:g}" for v in radius_values])
        ax.set_yticks(range(len(offset_values)), [f"{v:g}" for v in offset_values])
        ax.set_xlabel("环形光源半径 (mm)")
        for iy in range(values.shape[0]):
            for ix in range(values.shape[1]):
                ax.text(ix, iy, f"{values[iy, ix]:.3f}", ha="center", va="center", fontsize=8,
                        color="white" if values[iy, ix] < (vmin + vmax) / 2 else "black")
    axes[0].set_ylabel("探测器横向位置 (mm)")
    # Place the color legend in a dedicated horizontal strip below all panels.
    # This keeps it away from the third panel title and the heatmap annotations.
    fig.subplots_adjust(left=0.075, right=0.985, bottom=0.22, top=0.78, wspace=0.12)
    colorbar_axis = fig.add_axes([0.34, 0.095, 0.32, 0.026])
    colorbar = fig.colorbar(im, cax=colorbar_axis, orientation="horizontal")
    colorbar.set_label("Response proxy", labelpad=6)
    fig.suptitle("Local joint parameter grid / 局部联合参数网格\nSimulation / 仿真结果", fontsize=16, fontweight="bold", y=0.965)
    fig.text(0.015, 0.015, "Each cell: 3 fixed-budget random-seed replicates; higher response proxy is preferred.", fontsize=9, color="#475569")
    fig.savefig(output, dpi=220, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesh", type=Path, default=_RESULTS / "photon_paths_demo/outer_mesh.ply")
    parser.add_argument("--config", type=Path, default=Path("configs/guided_mc_skin_flesh_core.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/causal_joint_grid"))
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    base = json.loads(args.config.read_text(encoding="utf-8"))
    base["photons_per_wavelength"] = 100
    base["accepted_paths_per_wavelength"] = 10
    radius_values = [3.0, 4.0, 5.0]
    angle_values = [-10.0, 0.0, 10.0]
    offset_values = [-4.0, -2.0, 0.0, 2.0, 4.0]
    points = []
    for radius in radius_values:
        for angle in angle_values:
            for offset in offset_values:
                point = {"base": base, "ring_radius": radius, "incident_angle": angle, "detector_offset": offset}
                for seed in SEEDS:
                    points.append((point, seed, str(args.mesh)))
    raw = run_tasks(points, args.workers)
    raw.sort(key=lambda r: (r["ring_radius"], r["incident_angle"], r["detector_offset"], r["seed"]))
    agg = aggregate(raw)
    write_csv(output / "joint_grid_raw_replicates.csv", raw)
    write_csv(output / "joint_grid_aggregate.csv", agg)
    plot_grid(output / "joint_grid_heatmaps.png", agg, angle_values)

    top = agg[:3]
    verify_base = copy.deepcopy(base)
    verify_base["photons_per_wavelength"] = 400
    verify_base["accepted_paths_per_wavelength"] = 20
    verify_points = []
    for row in top:
        point = {"base": verify_base, "ring_radius": row["ring_radius"], "incident_angle": row["incident_angle"], "detector_offset": row["detector_offset"]}
        for seed in SEEDS:
            verify_points.append((point, seed, str(args.mesh)))
    verify_raw = run_tasks(verify_points, args.workers)
    verify_agg = aggregate(verify_raw)
    write_csv(output / "top3_validation_raw.csv", verify_raw)
    write_csv(output / "top3_validation.csv", verify_agg)
    baseline = {"ring_radius": 8.0, "incident_angle": 0.0, "detector_offset": 0.0}
    best = verify_agg[0]
    baseline_point = {"base": verify_base, **baseline}
    baseline_raw = run_tasks([(baseline_point, seed, str(args.mesh)) for seed in SEEDS], args.workers)
    baseline_agg = aggregate(baseline_raw)[0]
    summary = [
        "# Simulation / 仿真结果：联合参数搜索与复核",
        "",
        "先在局部联合网格中扫描 3×3×5=45 个组合，每个组合使用 3 个随机种子；再对联合网格前 3 名使用更高光子预算复核。",
        "排序目标为 650/800/950 nm 平均 detector response proxy；该指标用于本项目引导蒙特卡洛的方案比较，不等同于无偏检测效率。",
        "",
        "| 联合候选 | 半径 (mm) | 入射角 (deg) | 探测器偏移 (mm) | 扫描均值 | 高预算复核均值 | 复核标准差 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    verify_map = {(r["ring_radius"], r["incident_angle"], r["detector_offset"]): r for r in verify_agg}
    for row in top:
        check = verify_map[(row["ring_radius"], row["incident_angle"], row["detector_offset"])]
        summary.append(f"| candidate | {row['ring_radius']:g} | {row['incident_angle']:g} | {row['detector_offset']:g} | {row['mean_response']:.4f} | {check['mean_response']:.4f} | {check['std_response']:.4f} |")
    summary.extend(["", "## 与基线的高预算复核", "", f"基线 (半径 8 mm, 入射角 0°, 探测器偏移 0 mm)：{baseline_agg['mean_response']:.4f}", f"联合最优候选 ({best['ring_radius']:g} mm, {best['incident_angle']:g}°, {best['detector_offset']:g} mm)：{best['mean_response']:.4f}"])
    (output / "joint_grid_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    (output / "joint_optimal_settings.json").write_text(json.dumps({"label": "Simulation / 仿真结果", "scan_best": top[0], "top3_validation": verify_agg, "baseline_validation": baseline_agg}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "scan_best": top[0], "top3_validation": verify_agg, "baseline_validation": baseline_agg}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
