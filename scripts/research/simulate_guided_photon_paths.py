#!/usr/bin/env python3
"""Guided Monte Carlo photon paths on radial-proportional apple layers.

The outer Fruitsim mesh is treated as a closed star-shaped surface.  At each
direction u from the model center, the outer radial distance R(u) is estimated
from nearby mesh vertices.  The three closed tissue regions are then

    core  : r < f_core  * R(u)
    flesh : f_core R(u) <= r < f_flesh R(u)
    skin  : f_flesh R(u) <= r < R(u)

Photons use exponential free paths, absorption, Henyey-Greenstein scattering,
Fresnel reflection/refraction, Russian roulette, and a mixture of physical and
sensor-guided direction proposals.  The guide changes the sampling proposal;
the generated paths are still event-by-event Monte Carlo paths, not smoothed
Bezier curves.  The output is intended for path visualization.  The guided
proposal must not be used as an uncorrected detector-efficiency estimator.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import defaultdict
from pathlib import Path

_RESULTS = Path(os.environ.get("FRUITSIM_RESULTS_ROOT", "results"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Noto Sans SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

try:
    from scipy.spatial import cKDTree
except ImportError as exc:  # pragma: no cover - documented runtime dependency
    raise SystemExit("This script needs scipy (cKDTree) in the Fruitsim Python environment") from exc


REGIONS = {0: "skin", 1: "flesh", 2: "core"}
REGION_IDS = {"skin": 0, "flesh": 1, "core": 2}
COLORS = {650: "#F97316", 800: "#0891B2", 950: "#7C3AED"}


def norm(vector: np.ndarray) -> float:
    return float(np.linalg.norm(vector))


def unit(vector: np.ndarray) -> np.ndarray:
    length = norm(vector)
    return vector / max(length, 1.0e-15)


def read_ascii_ply(path: Path) -> tuple[np.ndarray, np.ndarray]:
    lines = path.read_text(encoding="utf-8").splitlines()
    end = lines.index("end_header")
    vertex_count = int(next(row.split()[-1] for row in lines[:end]
                            if row.startswith("element vertex")))
    face_count = int(next(row.split()[-1] for row in lines[:end]
                          if row.startswith("element face")))
    vertices = np.asarray(
        [[float(value) for value in row.split()[:3]]
         for row in lines[end + 1:end + 1 + vertex_count]], dtype=float)
    faces = np.asarray(
        [[int(value) for value in row.split()[1:4]]
         for row in lines[end + 1 + vertex_count:end + 1 + vertex_count + face_count]],
        dtype=int,
    )
    return vertices, faces


class RadialProportionalApple:
    """Closed proportional shells defined by the outer mesh radial field."""

    def __init__(self, vertices: np.ndarray, center: np.ndarray,
                 fractions: dict[str, float], boundary_samples: int) -> None:
        self.vertices = vertices
        self.center = center
        offsets = vertices - center
        radii = np.linalg.norm(offsets, axis=1)
        self.directions = offsets / np.maximum(radii[:, None], 1.0e-12)
        self.radii = radii
        self.tree = cKDTree(self.directions)
        self.fractions = fractions
        self.boundary_samples = boundary_samples
        self.max_radius = float(radii.max())
        self.radius_cache: dict[tuple[int, int], float] = {}

    def outer_radius(self, direction: np.ndarray) -> float:
        direction = unit(direction)
        theta = int(round(math.degrees(math.acos(max(-1.0, min(1.0, direction[2])))) / 2.0))
        phi = int(round(math.degrees(math.atan2(direction[1], direction[0])) / 2.0))
        cache_key = (theta, phi)
        cached = self.radius_cache.get(cache_key)
        if cached is not None:
            return cached
        distances, indices = self.tree.query(direction, k=min(8, len(self.radii)))
        distances = np.atleast_1d(distances)
        indices = np.atleast_1d(indices)
        weights = 1.0 / np.maximum(distances, 1.0e-8)
        value = float(np.sum(weights * self.radii[indices]) / np.sum(weights))
        self.radius_cache[cache_key] = value
        return value

    def shell_radius(self, direction: np.ndarray, fraction: float) -> float:
        return fraction * self.outer_radius(direction)

    def radial_ratio(self, point: np.ndarray) -> float:
        offset = point - self.center
        radius = norm(offset)
        return radius / max(self.outer_radius(offset), 1.0e-12)

    def region_at(self, point: np.ndarray) -> int:
        ratio = self.radial_ratio(point)
        if ratio < self.fractions["core"]:
            return 2
        if ratio < self.fractions["flesh"]:
            return 1
        if ratio < self.fractions["skin"]:
            return 0
        return -1

    def _first_region_change(self, origin: np.ndarray, direction: np.ndarray,
                             current_region: int, maximum: float,
                             epsilon: float) -> tuple[float, int] | None:
        samples = np.linspace(epsilon, maximum, self.boundary_samples)
        previous_t = epsilon
        previous_region = self.region_at(origin + previous_t * direction)
        if previous_region != current_region:
            return epsilon, previous_region
        for current_t in samples[1:]:
            current_region_at_t = self.region_at(origin + current_t * direction)
            if current_region_at_t == current_region:
                previous_t = current_t
                continue
            lo, hi = previous_t, current_t
            for _ in range(34):
                mid = 0.5 * (lo + hi)
                if self.region_at(origin + mid * direction) == current_region:
                    lo = mid
                else:
                    hi = mid
            next_region = self.region_at(origin + hi * direction)
            return hi, next_region
        return None

    def next_boundary(self, origin: np.ndarray, direction: np.ndarray,
                      current_region: int, epsilon: float) -> tuple[float, int] | None:
        return self._first_region_change(origin, unit(direction), current_region,
                                         self.max_radius * 2.8, epsilon)

    def radial_normal(self, point: np.ndarray) -> np.ndarray:
        # A numerical normal follows the radial-proportional surface rather than
        # assuming a sphere.  F is zero on a shell: |p-c|-f R((p-c)/|p-c|).
        offset = point - self.center
        direction = unit(offset)
        fraction = self.radial_ratio(point) / max(norm(offset) / self.outer_radius(direction), 1.0e-12)
        fraction = min((self.fractions["core"], self.fractions["flesh"], self.fractions["skin"]),
                       key=lambda value: abs(value - self.radial_ratio(point)))
        h = 1.0e-3
        gradient = np.zeros(3)
        for axis in range(3):
            delta = np.zeros(3)
            delta[axis] = h
            plus = norm(offset + delta) - fraction * self.outer_radius(offset + delta)
            minus = norm(offset - delta) - fraction * self.outer_radius(offset - delta)
            gradient[axis] = (plus - minus) / (2.0 * h)
        return unit(gradient)


def random_disk_point(rng: np.random.Generator, center: np.ndarray, radius: float,
                      margin: float) -> np.ndarray:
    radial = radius * margin * math.sqrt(float(rng.random()))
    angle = 2.0 * math.pi * float(rng.random())
    return center + np.array([radial * math.cos(angle), radial * math.sin(angle), 0.0])


def ring_source_launch(rng: np.random.Generator, source_config: dict) -> tuple[np.ndarray, np.ndarray]:
    """Sample one emitter from a Blender-style evenly spaced ring light."""
    center = np.asarray(source_config["center_mm"], float)
    normal = unit(np.asarray(source_config["plane_normal"], float))
    tangent, bitangent = basis(normal)
    emitter_count = max(1, int(source_config.get("emitter_count", 24)))
    emitter_index = int(rng.integers(0, emitter_count))
    jitter = math.radians(float(source_config.get("azimuth_jitter_deg", 0.0)))
    angle = 2.0 * math.pi * (emitter_index + 0.5) / emitter_count
    angle += float(rng.uniform(-jitter, jitter))
    ring_radius = float(source_config["ring_radius_mm"])
    ring_width = float(source_config.get("ring_width_mm", 0.0))
    if ring_width > 0.0:
        inner = max(0.0, ring_radius - 0.5 * ring_width)
        outer = ring_radius + 0.5 * ring_width
        radius = math.sqrt(inner * inner + float(rng.random()) * (outer * outer - inner * inner))
    else:
        radius = ring_radius
    position = center + radius * (math.cos(angle) * tangent + math.sin(angle) * bitangent)
    target = np.asarray(source_config.get("target_mm", [0.0, 0.0, 0.0]), float)
    direction = unit(target - position)
    incident_angle = math.radians(float(source_config.get("incident_angle_deg", 0.0)))
    if abs(incident_angle) > 1.0e-9:
        inward = unit(center - position)
        direction = unit(math.cos(incident_angle) * direction + math.sin(incident_angle) * inward)
    return position, direction


def detector_hit(point: np.ndarray, direction: np.ndarray, center: np.ndarray,
                 axis: np.ndarray, radius: float) -> np.ndarray | None:
    denominator = float(np.dot(direction, axis))
    if denominator >= -1.0e-12:
        return None
    distance = float(np.dot(center - point, axis) / denominator)
    if distance < 0.0:
        return None
    hit = point + distance * direction
    radial = hit - center - np.dot(hit - center, axis) * axis
    return hit if norm(radial) <= radius else None


def reflect(direction: np.ndarray, normal_from_current: np.ndarray) -> np.ndarray:
    return unit(direction - 2.0 * np.dot(direction, normal_from_current) * normal_from_current)


def refract(direction: np.ndarray, normal_from_current: np.ndarray,
            n1: float, n2: float) -> np.ndarray | None:
    cos_i = max(0.0, min(1.0, float(np.dot(direction, normal_from_current))))
    eta = n1 / n2
    sin2_t = eta * eta * max(0.0, 1.0 - cos_i * cos_i)
    if sin2_t >= 1.0:
        return None
    cos_t = math.sqrt(max(0.0, 1.0 - sin2_t))
    tangent = direction - cos_i * normal_from_current
    return unit(eta * tangent + cos_t * normal_from_current)


def fresnel(cos_i: float, n1: float, n2: float) -> float:
    cos_i = max(0.0, min(1.0, cos_i))
    eta = n1 / n2
    sin2_t = eta * eta * max(0.0, 1.0 - cos_i * cos_i)
    if sin2_t >= 1.0:
        return 1.0
    cos_t = math.sqrt(max(0.0, 1.0 - sin2_t))
    rs = ((n1 * cos_i - n2 * cos_t) / (n1 * cos_i + n2 * cos_t)) ** 2
    rp = ((n1 * cos_t - n2 * cos_i) / (n1 * cos_t + n2 * cos_i)) ** 2
    return 0.5 * (rs + rp)


def basis(direction: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    helper = np.array([1.0, 0.0, 0.0]) if abs(direction[0]) < 0.8 else np.array([0.0, 1.0, 0.0])
    tangent = unit(np.cross(direction, helper))
    return tangent, np.cross(direction, tangent)


def sample_cone(rng: np.random.Generator, axis: np.ndarray, half_angle: float) -> np.ndarray:
    axis = unit(axis)
    tangent, bitangent = basis(axis)
    cosine = 1.0 - float(rng.random()) * (1.0 - math.cos(half_angle))
    sine = math.sqrt(max(0.0, 1.0 - cosine * cosine))
    angle = 2.0 * math.pi * float(rng.random())
    return unit(cosine * axis + sine * (math.cos(angle) * tangent + math.sin(angle) * bitangent))


def sample_hg(rng: np.random.Generator, direction: np.ndarray, g: float) -> np.ndarray:
    xi = float(rng.random())
    if abs(g) < 1.0e-8:
        cosine = 1.0 - 2.0 * xi
    else:
        ratio = (1.0 - g * g) / (1.0 - g + 2.0 * g * xi)
        cosine = (1.0 + g * g - ratio * ratio) / (2.0 * g)
        cosine = max(-1.0, min(1.0, cosine))
    sine = math.sqrt(max(0.0, 1.0 - cosine * cosine))
    tangent, bitangent = basis(unit(direction))
    angle = 2.0 * math.pi * float(rng.random())
    return unit(cosine * unit(direction) + sine * (math.cos(angle) * tangent + math.sin(angle) * bitangent))


def guided_direction(rng: np.random.Generator, current: np.ndarray, region: int,
                     model: RadialProportionalApple, detector: dict, optical: dict,
                     guide: dict) -> tuple[np.ndarray, bool, float]:
    names = {0: "skin", 1: "flesh", 2: "core"}
    alpha = float(guide["base_probability"])
    alpha = max(alpha, float(guide.get(f"{names.get(region, 'core')}_probability", alpha)))
    # Guiding gets stronger near the sensor-facing outer layer.
    alpha *= 1.0 + 0.35 * max(0.0, 1.0 - model.radial_ratio(current))
    alpha = min(0.72, alpha)
    if float(rng.random()) < alpha:
        target = random_disk_point(rng, np.asarray(detector["center_mm"], float),
                                   float(detector["radius_mm"]), float(guide["target_radius_margin"]))
        direction = sample_cone(rng, target - current,
                                math.radians(float(guide["cone_half_angle_deg"])))
        return direction, True, alpha
    return sample_hg(rng, current * 0.0 + np.array([0.0, 0.0, 1.0]), optical["g"]), False, alpha


def transport_one(rng: np.random.Generator, model: RadialProportionalApple,
                  config: dict, wavelength: int) -> tuple[np.ndarray, np.ndarray] | None:
    optical = config["spectra"][str(wavelength)]
    detector = config["detector"]
    detector_center = np.asarray(detector["center_mm"], float)
    detector_axis = unit(np.asarray(detector["axis_toward_sample"], float))
    detector_radius = float(detector["radius_mm"])
    source_config = config["source"]
    if source_config.get("type", "pencil") == "ring":
        source, direction = ring_source_launch(rng, source_config)
    else:
        source = np.asarray(source_config["position_mm"], float)
        direction = unit(np.asarray(source_config["direction"], float))
    path = [source.copy()]
    region = -1
    weight = 1.0
    visited_regions = set()

    entry = model.next_boundary(source, direction, region, float(config["boundary_epsilon_mm"]))
    if entry is None:
        return None
    entry_distance, next_region = entry
    entry_point = source + entry_distance * direction
    radial_normal = unit(entry_point - model.center)
    normal = -radial_normal if np.dot(direction, radial_normal) < 0.0 else radial_normal
    n1, n2 = 1.0, optical[REGIONS[next_region]]["n"]
    reflected = reflect(direction, normal)
    transmitted = refract(direction, normal, n1, n2)
    if transmitted is None or float(rng.random()) < fresnel(float(np.dot(direction, normal)), n1, n2):
        return None
    direction = transmitted
    region = next_region
    visited_regions.add(region)
    position = entry_point + float(config["boundary_epsilon_mm"]) * direction
    path.append(entry_point.copy())

    for _ in range(int(config["max_events"])):
        material = optical[REGIONS[region]]
        mu_s = material["mu_s_prime_mm_inv"] / max(1.0 - material["g"], 1.0e-6)
        mu_t = material["mu_a_mm_inv"] + mu_s
        free_path = -math.log(max(float(rng.random()), 1.0e-12)) / mu_t
        boundary = model.next_boundary(position, direction, region,
                                       float(config["boundary_epsilon_mm"]))
        if boundary is None:
            return None
        boundary_distance, boundary_region = boundary
        if free_path < boundary_distance:
            position = position + free_path * direction
            path.append(position.copy())
            weight *= mu_s / mu_t
            if weight <= 0.0:
                return None
            guide = config["guide"]
            # Do not guide immediately at the entrance.  The photon must first
            # penetrate through the proportional shells; this prevents a
            # visually misleading collection of shallow skin-only returns.
            guide_allowed = 2 in visited_regions
            if not guide_allowed:
                # A weak inward proposal improves penetration without forcing
                # the path onto one deterministic centerline.
                if float(rng.random()) < 0.28:
                    direction = sample_cone(rng, model.center - position, math.radians(24.0))
                else:
                    direction = sample_hg(rng, direction, material["g"])
            else:
                target = random_disk_point(rng, detector_center, detector_radius,
                                            float(guide["target_radius_margin"]))
                alpha = float(guide.get(f"{REGIONS[region]}_probability", guide["base_probability"]))
                if float(rng.random()) < alpha:
                    direction = sample_cone(rng, target - position,
                                            math.radians(float(guide["cone_half_angle_deg"])))
                else:
                    direction = sample_hg(rng, direction, material["g"])
            roulette = config["roulette"]
            if weight < float(roulette["threshold"]):
                if float(rng.random()) > float(roulette["survival_probability"]):
                    return None
                weight /= float(roulette["survival_probability"])
            continue

        position = position + boundary_distance * direction
        path.append(position.copy())
        radial_normal = unit(position - model.center)
        normal = radial_normal if np.dot(direction, radial_normal) > 0.0 else -radial_normal
        n1 = material["n"]
        n2 = 1.0 if boundary_region == -1 else optical[REGIONS[boundary_region]]["n"]
        reflectance = fresnel(float(np.dot(direction, normal)), n1, n2)
        if float(rng.random()) < reflectance:
            direction = reflect(direction, normal)
            position = position + float(config["boundary_epsilon_mm"]) * direction
            path.append(position.copy())
            continue
        transmitted = refract(direction, normal, n1, n2)
        if transmitted is None:
            direction = reflect(direction, normal)
            position = position + float(config["boundary_epsilon_mm"]) * direction
            path.append(position.copy())
            continue
        direction = transmitted
        if boundary_region == -1:
            hit = detector_hit(position, direction, detector_center, detector_axis, detector_radius)
            if hit is not None and len(path) >= 8 and 2 in visited_regions:
                path.append(hit.copy())
                return np.asarray(path), hit
            return None
        region = boundary_region
        visited_regions.add(region)
        position = position + float(config["boundary_epsilon_mm"]) * direction
        path.append(position.copy())
    return None


def detector_disk(center: np.ndarray, radius: float) -> np.ndarray:
    angle = np.linspace(0.0, 2.0 * math.pi, 100)
    return np.column_stack([radius * np.cos(angle), radius * np.sin(angle), np.zeros_like(angle)]) + center


def source_ring_geometry(source_config: dict) -> np.ndarray | None:
    if source_config.get("type", "pencil") != "ring":
        return None
    center = np.asarray(source_config["center_mm"], float)
    normal = unit(np.asarray(source_config["plane_normal"], float))
    tangent, bitangent = basis(normal)
    angle = np.linspace(0.0, 2.0 * math.pi, 120)
    radius = float(source_config["ring_radius_mm"])
    return center + radius * (np.cos(angle)[:, None] * tangent + np.sin(angle)[:, None] * bitangent)


def render(output: Path, vertices: np.ndarray, faces: np.ndarray, paths: dict[int, list[np.ndarray]],
           config: dict, title: str, wavelengths: list[int], view: tuple[float, float]) -> None:
    center = np.asarray(config["detector"]["center_mm"], float)
    radius = float(config["detector"]["radius_mm"])
    fractions = config["layer_fractions"]
    model_center = np.zeros(3)
    shells = {
        "core": model_center + (vertices - model_center) * fractions["core"],
        "flesh": model_center + (vertices - model_center) * fractions["flesh"],
        "skin": vertices,
    }
    fig = plt.figure(figsize=(13.33, 7.5), facecolor="#F8FAFC")
    ax = fig.add_subplot(111, projection="3d", facecolor="#F8FAFC")
    for name, color, alpha in (("skin", "#EF4444", 0.07), ("flesh", "#F59E0B", 0.045), ("core", "#22C55E", 0.035)):
        ax.add_collection3d(Poly3DCollection(shells[name][faces], facecolor=color,
                                             edgecolor="none", alpha=alpha))
    disk = detector_disk(center, radius)
    ax.add_collection3d(Poly3DCollection([disk], facecolor="#38BDF8", edgecolor="#0369A1", alpha=0.34))
    ax.plot(disk[:, 0], disk[:, 1], disk[:, 2], color="#0369A1", linewidth=1.3)
    ring = source_ring_geometry(config["source"])
    if ring is not None:
        ax.plot(ring[:, 0], ring[:, 1], ring[:, 2], color="#DC2626", linewidth=2.0, alpha=0.95)
        ax.scatter(ring[::6, 0], ring[::6, 1], ring[::6, 2], color="#F97316", s=12, depthshade=False)
    count = 0
    for wavelength in wavelengths:
        for path in paths.get(wavelength, []):
            ax.plot(path[:, 0], path[:, 1], path[:, 2], color=COLORS[wavelength], linewidth=0.85, alpha=0.72)
            ax.scatter(path[:-1, 0], path[:-1, 1], path[:-1, 2], color=COLORS[wavelength], s=3, alpha=0.45)
            ax.scatter(*path[-1], color=COLORS[wavelength], marker="*", s=55, edgecolors="white", linewidths=0.5)
            count += 1
    all_points = np.vstack([vertices, center + np.array([radius, radius, radius]), center - np.array([radius, radius, radius])])
    mins, maxs = all_points.min(axis=0), all_points.max(axis=0)
    midpoint, half = (mins + maxs) / 2.0, float(np.max(maxs - mins) / 2.0)
    ax.set_xlim(midpoint[0] - half, midpoint[0] + half)
    ax.set_ylim(midpoint[1] - half, midpoint[1] + half)
    ax.set_zlim(midpoint[2] - half, midpoint[2] + half)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=view[0], azim=view[1])
    ax.set_xlabel("X / mm"); ax.set_ylabel("Y / mm"); ax.set_zlabel("Z / mm")
    ax.grid(True, alpha=0.16)
    ax.xaxis.pane.set_alpha(0.0); ax.yaxis.pane.set_alpha(0.0); ax.zaxis.pane.set_alpha(0.0)
    fig.suptitle(title, fontsize=18, fontweight="bold", color="#0F172A", y=0.96)
    ax.set_title(f"逐碰撞事件折线｜skin–flesh–core 径向比例闭合层｜有效路径 {count} 条",
                 fontsize=10.5, color="#475569", pad=10)
    legend = [Line2D([0], [0], color=COLORS[w], lw=2.5, label=f"{w} nm") for w in wavelengths]
    legend += [Line2D([0], [0], color="#EF4444", lw=6, alpha=0.28, label="skin / flesh / core shell"),
               Line2D([0], [0], color="#DC2626", lw=2.5, label="Blender ring source"),
               Line2D([0], [0], marker="o", color="none", markerfacecolor="#38BDF8", markeredgecolor="#0369A1", markersize=8, label="sensor")]
    ax.legend(handles=legend, loc="upper left", bbox_to_anchor=(0.0, 0.98), frameon=False)
    fig.text(0.015, 0.018, "引导采样用于提高回传路径的可见数量；路径本身由随机步进、散射和边界概率事件产生。", fontsize=9.2, color="#475569")
    fig.savefig(output, dpi=220, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh", type=Path, default=_RESULTS / "photon_paths_demo/outer_mesh.ply")
    parser.add_argument("--config", type=Path, default=Path("configs/guided_mc_skin_flesh_core.json"))
    parser.add_argument("--output-dir", type=Path, default=_RESULTS / "guided_mc_skin_flesh_core_ring")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    vertices, faces = read_ascii_ply(args.mesh)
    center = np.zeros(3)
    model = RadialProportionalApple(vertices, center, config["layer_fractions"], int(config["boundary_samples"]))
    rng = np.random.default_rng(int(config["seed"]))
    target = int(config["accepted_paths_per_wavelength"])
    attempts = int(config["photons_per_wavelength"])
    paths: dict[int, list[np.ndarray]] = defaultdict(list)
    summary: dict[str, dict[str, int]] = {}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for wavelength in (650, 800, 950):
        for _ in range(attempts):
            if len(paths[wavelength]) >= target:
                break
            result = transport_one(rng, model, config, wavelength)
            if result is not None:
                paths[wavelength].append(result[0])
        summary[str(wavelength)] = {"attempts": attempts, "accepted_paths": len(paths[wavelength])}
    with (args.output_dir / "paths.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["wavelength_nm", "path_id", "event", "x_mm", "y_mm", "z_mm"])
        for wavelength, wavelength_paths in sorted(paths.items()):
            for path_id, path in enumerate(wavelength_paths):
                for event, point in enumerate(path):
                    writer.writerow([wavelength, path_id, event, *point])
    summary_payload = {
        "mode": "guided_event_by_event_monte_carlo_visualization",
        "radial_shell_definition": "R_layer(u)=fraction*R_outer(u), with R_outer estimated from the outer mesh radial field",
        "layer_fractions": config["layer_fractions"],
        "summary": summary,
        "note": "Guided proposal improves path collection; do not use unweighted counts as detector efficiency."
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    wavelengths = [w for w in (650, 800, 950) if paths[w]]
    if not wavelengths:
        raise RuntimeError("No detector-returning Monte Carlo paths were collected")
    render(args.output_dir / "01_guided_mc_overview.png", vertices, faces, paths, config,
           "Fruitsim：径向比例 skin–flesh–core 引导蒙特卡洛路径", wavelengths, (19, -57))
    render(args.output_dir / "02_guided_mc_sensor_view.png", vertices, faces, paths, config,
           "Fruitsim：传感器侧视角的随机回传路径", wavelengths, (7, -90))
    for wavelength in wavelengths:
        render(args.output_dir / f"guided_mc_{wavelength}nm.png", vertices, faces,
               {wavelength: paths[wavelength]}, config, f"Fruitsim：{wavelength} nm 引导蒙特卡洛路径",
               [wavelength], (18, -54))
    print(json.dumps(summary_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
