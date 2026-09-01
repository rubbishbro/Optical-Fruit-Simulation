#!/usr/bin/env python3
"""End-to-end StatisticalFujiShape sampling and interactive 3D smoke test."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from fruitsim_shape import StatisticalFujiShape  # noqa: E402


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a StatisticalFujiShape artifact, generate one deterministic "
            "random apple, export PLY, and optionally display an interactive 3D mesh."
        )
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=REPOSITORY_ROOT
        / "data/shape_models/statistical_fuji_shape_zenodo_v1.json",
        help="Statistical shape JSON artifact",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "results/shapes/random_apple.ply",
        help="Generated triangle-mesh PLY",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random shape seed")
    parser.add_argument(
        "--sample-id",
        type=int,
        default=0,
        help="Additional deterministic stream identifier mixed into the seed",
    )
    parser.add_argument(
        "--modes",
        type=int,
        default=None,
        help="Number of leading PCA modes; default uses all available modes",
    )
    parser.add_argument(
        "--sigma-clip",
        type=float,
        default=3.0,
        help="Clamp each standard-normal PCA coefficient to +/- this value",
    )
    parser.add_argument(
        "--skin-thickness-mm",
        type=float,
        default=1.0,
        help="Validate a radial inner skin/flesh surface with this thickness",
    )
    parser.add_argument("--elevation", type=float, default=20.0)
    parser.add_argument("--azimuth", type=float, default=35.0)
    parser.add_argument(
        "--surface-alpha", type=float, default=0.96, help="Outer mesh opacity in [0, 1]"
    )
    parser.add_argument(
        "--screenshot",
        type=Path,
        help="Optional PNG path; useful with --no-show for headless validation",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Do not open a window; still validate, export PLY, and optionally save PNG",
    )
    return parser.parse_args()


def combined_seed(seed: int, sample_id: int) -> int:
    # NumPy SeedSequence mixes both integers without relying on Python's salted hash.
    state = np.random.SeedSequence([seed, sample_id]).generate_state(2, dtype=np.uint64)
    return int(state[0] ^ state[1])


def validate_instance(model: StatisticalFujiShape, first, second, skin_thickness_mm: float) -> dict:
    if not np.array_equal(first.vertices_mm, second.vertices_mm):
        raise RuntimeError("fixed model/seed parameters did not reproduce identical vertices")
    vertices = first.vertices_mm
    faces = first.faces
    if vertices.shape != (len(model.directions), 3) or not np.isfinite(vertices).all():
        raise RuntimeError("generated vertices have invalid shape or non-finite values")
    radii = np.linalg.norm(vertices, axis=1)
    if np.any(radii <= 0.0):
        raise RuntimeError("generated surface contains a non-positive radius")
    if faces.ndim != 2 or faces.shape[1] != 3 or faces.min() < 0 \
            or faces.max() >= len(vertices):
        raise RuntimeError("generated triangle topology is invalid")
    inner = first.inset_vertices_mm(skin_thickness_mm)
    inner_radii = np.linalg.norm(inner, axis=1)
    if not np.allclose(radii - inner_radii, skin_thickness_mm, atol=1.0e-9):
        raise RuntimeError("skin/flesh radial inset validation failed")
    minimum = vertices.min(axis=0)
    maximum = vertices.max(axis=0)
    return {
        "valid": True,
        "vertex_count": int(len(vertices)),
        "triangle_count": int(len(faces)),
        "diameters_mm": (maximum - minimum).tolist(),
        "radius_min_mm": float(radii.min()),
        "radius_max_mm": float(radii.max()),
        "coefficients_sigma": first.coefficients_sigma.tolist(),
        "skin_thickness_mm": skin_thickness_mm,
        "cultivar_status": model.metadata.get("cultivar_status"),
    }


def render(instance, summary: dict, args: argparse.Namespace) -> None:
    try:
        import matplotlib
        if args.no_show:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    except ImportError as error:
        raise RuntimeError(
            "3D display requires matplotlib; install with: pip install './python[shape-view]'"
        ) from error

    vertices = instance.vertices_mm
    figure = plt.figure(figsize=(10, 9))
    axis = figure.add_subplot(111, projection="3d")
    surface = Poly3DCollection(
        vertices[instance.faces], linewidths=0.08, alpha=args.surface_alpha
    )
    surface.set_facecolor((0.78, 0.10, 0.04, args.surface_alpha))
    surface.set_edgecolor((0.20, 0.02, 0.01, 0.20))
    axis.add_collection3d(surface)

    minimum = vertices.min(axis=0)
    maximum = vertices.max(axis=0)
    center = 0.5 * (minimum + maximum)
    half_range = 0.55 * float(np.max(maximum - minimum))
    axis.set_xlim(center[0] - half_range, center[0] + half_range)
    axis.set_ylim(center[1] - half_range, center[1] + half_range)
    axis.set_zlim(center[2] - half_range, center[2] + half_range)
    axis.set_box_aspect((1, 1, 1))
    axis.view_init(elev=args.elevation, azim=args.azimuth)
    axis.set_xlabel("X (mm)")
    axis.set_ylabel("Y (mm)")
    axis.set_zlabel("Z (mm)")
    axis.set_title(
        "StatisticalFujiShape random apple\n"
        f"seed={args.seed}, sample_id={args.sample_id}, modes={len(instance.coefficients_sigma)}\n"
        f"diameters={np.round(summary['diameters_mm'], 2)} mm\n"
        f"cultivar status: {summary['cultivar_status']}"
    )
    figure.tight_layout()
    if args.screenshot:
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(args.screenshot, dpi=180)
        print(f"screenshot: {args.screenshot}")
    if not args.no_show:
        plt.show()
    plt.close(figure)


def main() -> None:
    args = parse_arguments()
    if args.skin_thickness_mm < 0.0:
        raise ValueError("--skin-thickness-mm must be non-negative")
    if not 0.0 <= args.surface_alpha <= 1.0:
        raise ValueError("--surface-alpha must be in [0, 1]")

    model = StatisticalFujiShape.load(args.model)
    active_modes = model.mode_count if args.modes is None else args.modes
    seed = combined_seed(args.seed, args.sample_id)
    first = model.sample(
        seed=seed, mode_count=active_modes, sigma_clip=args.sigma_clip
    )
    second = model.sample(
        seed=seed, mode_count=active_modes, sigma_clip=args.sigma_clip
    )
    summary = validate_instance(model, first, second, args.skin_thickness_mm)
    summary.update({
        "model": str(args.model),
        "output": str(args.output),
        "seed": args.seed,
        "sample_id": args.sample_id,
        "active_modes": active_modes,
        "sigma_clip": args.sigma_clip,
    })
    first.write_ply(args.output)
    print(json.dumps(summary, indent=2))
    render(first, summary, args)


if __name__ == "__main__":
    main()
