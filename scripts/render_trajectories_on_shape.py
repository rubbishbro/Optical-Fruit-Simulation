#!/usr/bin/env python3
"""Overlay recorded photon trajectories on a sampled statistical apple mesh."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import Normalize
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from mpl_toolkits.mplot3d.art3d import Line3DCollection


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

def add_mesh(axis, vertices: np.ndarray, faces: np.ndarray) -> None:
    mesh = Poly3DCollection(vertices[faces], linewidths=0.06, alpha=0.20)
    mesh.set_facecolor((0.76, 0.12, 0.04, 0.20))
    mesh.set_edgecolor((0.20, 0.03, 0.01, 0.14))
    axis.add_collection3d(mesh)


def configure_axis(axis, vertices: np.ndarray) -> None:
    minimum = vertices.min(axis=0)
    maximum = vertices.max(axis=0)
    center = (minimum + maximum) * 0.5
    half_range = 0.56 * float(np.max(maximum - minimum))
    axis.set_xlim(center[0] - half_range, center[0] + half_range)
    axis.set_ylim(center[1] - half_range, center[1] + half_range)
    axis.set_zlim(center[2] - half_range, center[2] + half_range)
    axis.set_box_aspect((1, 1, 1))
    axis.view_init(elev=20, azim=35)
    axis.set_xlabel("X (mm)")
    axis.set_ylabel("Y (mm)")
    axis.set_zlabel("Z (mm)")


def read_ascii_ply(path: Path) -> tuple[np.ndarray, np.ndarray]:
    lines = path.read_text(encoding="ascii").splitlines()
    vertex_count = face_count = 0
    header_end = None
    for index, line in enumerate(lines):
        fields = line.split()
        if fields[:2] == ["element", "vertex"]:
            vertex_count = int(fields[2])
        elif fields[:2] == ["element", "face"]:
            face_count = int(fields[2])
        elif line == "end_header":
            header_end = index + 1
            break
    if header_end is None or vertex_count == 0 or face_count == 0:
        raise ValueError(f"unsupported or empty ASCII PLY: {path}")
    vertices = np.asarray([[float(value) for value in line.split()[:3]]
                           for line in lines[header_end:header_end + vertex_count]], dtype=float)
    faces = np.asarray([[int(value) for value in line.split()[1:4]]
                        for line in lines[header_end + vertex_count:
                                          header_end + vertex_count + face_count]], dtype=int)
    return vertices, faces


def render(model_path: Path, mesh_path: Path | None, trajectories_path: Path,
           output: Path, seed: int, modes: int | None, max_photons: int | None,
           detector_only: bool, weighted: bool, max_points_per_path: int) -> None:
    if mesh_path is not None:
        vertices, faces = read_ascii_ply(mesh_path)
        shape_label = f"mesh={mesh_path.name}"
    else:
        from fruitsim_shape import StatisticalFujiShape

        model = StatisticalFujiShape.load(model_path)
        instance = model.sample(seed=seed, mode_count=modes, sigma_clip=3.0)
        vertices, faces = instance.vertices_mm, instance.faces
        shape_label = f"shape seed={seed}"
    data = pd.read_csv(trajectories_path)
    if detector_only:
        if "detector_accepted" not in data.columns:
            raise ValueError("trajectory CSV has no detector_accepted column")
        data = data[data["detector_accepted"] == 1].copy()
        if data.empty:
            raise ValueError("no detector-accepted trajectories were recorded")
    if max_photons is not None:
        keep = data["photon_id"].drop_duplicates().sort_values().head(max_photons)
        data = data[data["photon_id"].isin(keep)]

    fig = plt.figure(figsize=(11, 10), dpi=180)
    axis = fig.add_subplot(111, projection="3d")
    add_mesh(axis, vertices, faces)

    wavelengths = sorted(data["wavelength_nm"].unique())
    trajectory_groups = data.groupby(["wavelength_nm", "photon_id"]).ngroups
    cmap = plt.get_cmap("turbo")
    color_for = {w: cmap(i / max(1, len(wavelengths) - 1))
                 for i, w in enumerate(wavelengths)}
    for (wavelength, photon_id), path in data.sort_values("event").groupby(
        ["wavelength_nm", "photon_id"]
    ):
        if max_points_per_path > 1 and len(path) > max_points_per_path:
            indices = np.linspace(0, len(path) - 1, max_points_per_path).astype(int)
            path = path.iloc[np.unique(indices)]
        if weighted and len(path) > 1:
            points = path[["x_mm", "y_mm", "z_mm"]].to_numpy()
            segments = np.stack([points[:-1], points[1:]], axis=1)
            segment_weight = path.weight.to_numpy()[:-1]
            collection = Line3DCollection(segments, cmap="viridis", norm=Normalize(0.0, 1.0))
            collection.set_array(segment_weight)
            collection.set_linewidth(0.45 + 1.7 * np.sqrt(np.clip(segment_weight, 0.0, 1.0)))
            collection.set_alpha(0.20 + 0.80 * np.sqrt(np.clip(segment_weight, 0.0, 1.0)))
            axis.add_collection3d(collection)
        else:
            axis.plot(path.x_mm, path.y_mm, path.z_mm, color=color_for[wavelength],
                      linewidth=1.05, alpha=0.86)
        axis.scatter(path.x_mm.iloc[0], path.y_mm.iloc[0], path.z_mm.iloc[0],
                     color=color_for[wavelength], s=34 if detector_only else 15,
                     depthshade=False, edgecolors="black" if detector_only else None,
                     linewidths=0.35 if detector_only else 0.0)

    configure_axis(axis, vertices)
    axis.set_title(
        "Photon trajectories over real 3D apple mesh\n"
        f"{shape_label} | trajectory packets={trajectory_groups} | "
        + ("final detector-accepted photons | " if detector_only else "")
        + "trajectory transport: statistical mesh (CPU)",
        weight="bold", pad=18,
    )
    handles = [plt.Line2D([0], [0], color=color_for[w], lw=2, label=f"{int(w)} nm")
               for w in wavelengths]
    handles.append(plt.Line2D([0], [0], color=(0.76, 0.12, 0.04), alpha=0.45,
                              lw=5, label="real statistical mesh"))
    axis.legend(handles=handles, loc="upper left", fontsize=8, title="legend")
    if weighted:
        mappable = plt.cm.ScalarMappable(norm=Normalize(0.0, 1.0), cmap="viridis")
        mappable.set_array(np.array([0.0, 1.0]))
        fig.colorbar(mappable, ax=axis, shrink=0.62, pad=0.08,
                     label="photon weight (relative intensity)")
    fig.text(0.5, 0.02,
             "Paths are intersected with the sampled outer/inner triangle meshes using the CPU BVH.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    print(f"Rendered: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path,
                        default=ROOT / "data/shape_models/statistical_fuji_shape_zenodo_v1.json")
    parser.add_argument("--mesh", type=Path, default=None,
                        help="ASCII outer mesh PLY exported by a mesh transport run")
    parser.add_argument("--trajectories", type=Path,
                        default=ROOT / "results/golden_delicious_demo/trajectories.csv")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "pics/06_trajectories_on_real_apple.png")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--modes", type=int, default=None)
    parser.add_argument("--max-photons", type=int, default=None,
                        help="optional cap on distinct photon ids")
    parser.add_argument("--detector-only", action="store_true",
                        help="render only trajectories finally accepted by the detector")
    parser.add_argument("--weighted", action="store_true",
                        help="color path segments by photon weight and attenuate line opacity")
    parser.add_argument("--max-points-per-path", type=int, default=600,
                        help="uniformly downsample long paths for readable rendering")
    args = parser.parse_args()
    render(args.model, args.mesh, args.trajectories, args.output,
           args.seed, args.modes, args.max_photons, args.detector_only,
           args.weighted, args.max_points_per_path)


if __name__ == "__main__":
    main()
