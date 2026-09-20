#!/usr/bin/env python3
"""Render the bundled statistical apple mesh and its radial flesh inset."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from fruitsim_shape import StatisticalFujiShape  # noqa: E402


def mesh_collection(vertices: np.ndarray, faces: np.ndarray, color, alpha: float,
                    face_mask: np.ndarray | None = None) -> Poly3DCollection:
    selected = faces if face_mask is None else faces[face_mask]
    collection = Poly3DCollection(vertices[selected], linewidths=0.08, alpha=alpha)
    collection.set_facecolor((*color, alpha))
    collection.set_edgecolor((0.18, 0.04, 0.01, min(0.25, alpha)))
    return collection


def set_axes(axis, vertices: np.ndarray, title: str) -> None:
    minimum = vertices.min(axis=0)
    maximum = vertices.max(axis=0)
    center = 0.5 * (minimum + maximum)
    half_range = 0.55 * float(np.max(maximum - minimum))
    axis.set_xlim(center[0] - half_range, center[0] + half_range)
    axis.set_ylim(center[1] - half_range, center[1] + half_range)
    axis.set_zlim(center[2] - half_range, center[2] + half_range)
    axis.set_box_aspect((1, 1, 1))
    axis.view_init(elev=20, azim=35)
    axis.set_xlabel("X (mm)")
    axis.set_ylabel("Y (mm)")
    axis.set_zlabel("Z (mm)")
    axis.set_title(title, weight="bold", pad=14)


def render(model_path: Path, output: Path, ply_output: Path, seed: int,
           skin_thickness_mm: float, modes: int | None) -> None:
    model = StatisticalFujiShape.load(model_path)
    instance = model.sample(seed=seed, mode_count=modes, sigma_clip=3.0)
    outer = instance.vertices_mm
    inner = instance.inset_vertices_mm(skin_thickness_mm)
    instance.write_ply(ply_output)

    fig = plt.figure(figsize=(14, 7), dpi=180)
    full = fig.add_subplot(121, projection="3d")
    cutaway = fig.add_subplot(122, projection="3d")

    full.add_collection3d(mesh_collection(outer, instance.faces, (0.78, 0.10, 0.04), 0.88))
    full.add_collection3d(mesh_collection(inner, instance.faces, (1.00, 0.72, 0.18), 0.23))
    set_axes(full, outer, "Full statistical apple")

    centroids = outer[instance.faces].mean(axis=1)
    visible_outer = centroids[:, 0] >= 0.0
    cutaway.add_collection3d(mesh_collection(outer, instance.faces, (0.78, 0.10, 0.04),
                                             0.34, visible_outer))
    cutaway.add_collection3d(mesh_collection(inner, instance.faces, (0.98, 0.62, 0.12),
                                             0.94))
    set_axes(cutaway, outer, "Cutaway: skin shell + flesh boundary")

    fig.suptitle(
        "StatisticalFujiShape 3D geometry\n"
        f"seed={seed} | radial skin thickness={skin_thickness_mm:g} mm | "
        f"vertices={len(outer)} | triangles={len(instance.faces)}",
        weight="bold",
    )
    fig.text(0.5, 0.02, "red = outer skin surface   gold = inner flesh boundary   "
             "right panel hides half of the outer shell", ha="center", fontsize=10)
    fig.tight_layout(rect=(0, 0.05, 1, 0.93))
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    print(f"Rendered: {output}")
    print(f"Mesh: {ply_output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path,
                        default=ROOT / "data/shape_models/statistical_fuji_shape_zenodo_v1.json")
    parser.add_argument("--output", type=Path, default=ROOT / "pics/05_real_apple_3d_structure.png")
    parser.add_argument("--ply-output", type=Path,
                        default=ROOT / "results/shapes/random_apple_structure_seed42.ply")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skin-thickness-mm", type=float, default=1.0)
    parser.add_argument("--modes", type=int, default=None)
    args = parser.parse_args()
    render(args.model, args.output, args.ply_output, args.seed, args.skin_thickness_mm, args.modes)


if __name__ == "__main__":
    main()
