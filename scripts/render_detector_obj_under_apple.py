#!/usr/bin/env python3
"""Render a detector OBJ beneath the sampled statistical apple mesh."""

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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_trajectories_on_shape import read_ascii_ply  # noqa: E402


def read_mtl(path: Path) -> dict[str, tuple[float, float, float, float]]:
    materials = {}
    current = None
    if not path.exists():
        return materials
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.strip().split()
        if not fields:
            continue
        if fields[0] == "newmtl":
            current = " ".join(fields[1:])
            materials[current] = (0.65, 0.65, 0.65, 1.0)
        elif current and fields[0] == "Kd":
            values = tuple(float(value) for value in fields[1:4])
            materials[current] = (*values, materials[current][3])
        elif current and fields[0] in ("d", "Tr"):
            alpha = float(fields[1])
            if fields[0] == "Tr":
                alpha = 1.0 - alpha
            materials[current] = (*materials[current][:3], alpha)
    return materials


def read_obj(path: Path) -> tuple[np.ndarray, np.ndarray, list[str], dict[str, tuple[float, float, float, float]]]:
    vertices = []
    faces = []
    face_materials = []
    material = "default"
    material_file = None
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.strip().split()
        if not fields:
            continue
        if fields[0] == "mtllib":
            material_file = path.parent / fields[1]
        elif fields[0] == "usemtl":
            material = " ".join(fields[1:])
        if fields[0] == "v":
            vertices.append([float(value) for value in fields[1:4]])
        elif fields[0] == "f":
            indices = []
            for token in fields[1:]:
                index = int(token.split("/")[0])
                indices.append(index - 1 if index > 0 else len(vertices) + index)
            for offset in range(1, len(indices) - 1):
                faces.append([indices[0], indices[offset], indices[offset + 1]])
                face_materials.append(material)
    if not vertices or not faces:
        raise ValueError(f"OBJ has no renderable mesh: {path}")
    materials = read_mtl(material_file) if material_file else {}
    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=int), face_materials, materials


def bounds(axis, vertices: np.ndarray, padding: float = 1.08) -> None:
    minimum = vertices.min(axis=0)
    maximum = vertices.max(axis=0)
    center = (minimum + maximum) * 0.5
    half_range = padding * float(np.max(maximum - minimum)) * 0.5
    axis.set_xlim(center[0] - half_range, center[0] + half_range)
    axis.set_ylim(center[1] - half_range, center[1] + half_range)
    axis.set_zlim(center[2] - half_range, center[2] + half_range)
    axis.set_box_aspect((1, 1, 1))
    axis.set_xlabel("X (mm)")
    axis.set_ylabel("Y (mm)")
    axis.set_zlabel("Z (mm)")
    axis.view_init(elev=20, azim=35)


def render(mesh_path: Path, detector_path: Path, output: Path,
           detector_scale_mm: float, detector_center_z_mm: float) -> None:
    apple_vertices, apple_faces = read_ascii_ply(mesh_path)
    detector_vertices, detector_faces, face_materials, materials = read_obj(detector_path)

    # Blender OBJ convention here has a thin local Y axis. Put that axis along
    # world Z so the detector lies horizontally below the apple.
    local_center = (detector_vertices.min(axis=0) + detector_vertices.max(axis=0)) * 0.5
    local = (detector_vertices - local_center) * detector_scale_mm
    detector_world = np.column_stack((local[:, 0], local[:, 2], local[:, 1]))
    detector_world[:, 2] += detector_center_z_mm

    combined = np.vstack((apple_vertices, detector_world))
    fig = plt.figure(figsize=(11, 10), dpi=180)
    axis = fig.add_subplot(111, projection="3d")

    apple = Poly3DCollection(apple_vertices[apple_faces], linewidths=0.0, alpha=0.22)
    apple.set_facecolor((0.78, 0.10, 0.04, 0.22))
    apple.set_edgecolor((0.20, 0.02, 0.01, 0.0))
    axis.add_collection3d(apple)

    for material_name in sorted(set(face_materials)):
        face_indices = np.asarray([index for index, name in enumerate(face_materials)
                                   if name == material_name], dtype=int)
        detector = Poly3DCollection(detector_world[detector_faces[face_indices]],
                                    linewidths=0.0, alpha=0.92)
        color = materials.get(material_name, (0.08, 0.35, 0.82, 0.92))
        detector.set_facecolor(color)
        detector.set_edgecolor((*color[:3], 0.0))
        axis.add_collection3d(detector)

    bounds(axis, combined, padding=1.16)
    axis.set_title(
        "Detector OBJ beneath real 3D apple mesh\n"
        f"detector scale={detector_scale_mm:g} mm / OBJ unit | "
        f"detector center z={detector_center_z_mm:g} mm | "
        f"materials={len(materials)}",
        weight="bold", pad=18,
    )
    handles = [
        plt.Line2D([0], [0], color=(0.78, 0.10, 0.04), lw=7, alpha=0.45,
                   label="statistical apple mesh"),
        plt.Line2D([0], [0], color=next(iter(materials.values()), (0.08, 0.35, 0.82, 1.0)), lw=7,
                   label="detector.obj"),
    ]
    axis.legend(handles=handles, loc="upper left", fontsize=9)
    fig.text(0.5, 0.02,
             "OBJ axes mapped: local X→world X, local Z→world Y, local Y→world Z",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight")
    plt.close(fig)
    print(f"Rendered: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh", type=Path,
                        default=ROOT / "results/statistical_mesh_detector_demo/outer_mesh.ply")
    parser.add_argument("--detector", type=Path,
                        default=Path("/home/rubbishbro/下载/detector.obj"))
    parser.add_argument("--output", type=Path,
                        default=ROOT / "pics/08_detector_obj_under_apple.png")
    parser.add_argument("--detector-scale-mm", type=float, default=20.0)
    parser.add_argument("--detector-center-z-mm", type=float, default=-42.0)
    args = parser.parse_args()
    render(args.mesh, args.detector, args.output,
           args.detector_scale_mm, args.detector_center_z_mm)


if __name__ == "__main__":
    main()
