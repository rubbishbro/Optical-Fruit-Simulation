from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull, cKDTree


ZENODO_RECORD = "https://zenodo.org/records/15635995"
ZENODO_DOI = "10.5281/zenodo.15635995"
ZENODO_ARCHIVE_MD5 = "dee3f690c983fdceb0332000eb9d1ed2"
ZENODO_TITLE = "3D high-resolution point cloud of apple shapes and UAV videos in apple orchards"
ZENODO_CREATORS = [
    "Kaiwen Wang", "Tianyi Jia", "Zhen Cao", "Lammert Kooistra",
    "Alvaro Lau Sarmiento", "Wensheng Wang", "João Valente",
]

_PLY_TYPES = {
    "char": "i1", "uchar": "u1", "int8": "i1", "uint8": "u1",
    "short": "<i2", "ushort": "<u2", "int16": "<i2", "uint16": "<u2",
    "int": "<i4", "uint": "<u4", "int32": "<i4", "uint32": "<u4",
    "float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8",
}


@dataclass(frozen=True)
class TrainingOptions:
    direction_count: int = 2048
    mode_count: int = 8
    neighbor_count: int = 12
    max_points_per_cloud: int = 300_000
    input_unit_to_mm: float = 1000.0
    robust_quantile: float = 0.002

    def validate(self) -> None:
        if self.direction_count < 32 or self.mode_count < 1:
            raise ValueError("direction_count >= 32 and mode_count >= 1 are required")
        if self.neighbor_count < 1 or self.max_points_per_cloud < self.neighbor_count:
            raise ValueError("invalid neighbor or point limit")
        if self.input_unit_to_mm <= 0.0 or not 0.0 <= self.robust_quantile < 0.1:
            raise ValueError("invalid unit scale or robust quantile")


def fibonacci_directions(count: int) -> np.ndarray:
    index = np.arange(count, dtype=np.float64)
    golden_angle = np.pi * (3.0 - np.sqrt(5.0))
    z = 1.0 - 2.0 * (index + 0.5) / count
    radius = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    phi = golden_angle * index
    return np.column_stack((radius * np.cos(phi), radius * np.sin(phi), z))


def triangulate_directions(directions: np.ndarray) -> np.ndarray:
    faces = ConvexHull(directions).simplices.astype(np.int64)
    for index, face in enumerate(faces):
        a, b, c = directions[face]
        if np.dot(np.cross(b - a, c - a), a + b + c) < 0.0:
            faces[index, 1], faces[index, 2] = faces[index, 2], faces[index, 1]
    return faces


def read_ply_xyz(path: Path) -> np.ndarray:
    path = Path(path)
    with path.open("rb") as stream:
        header_lines = 1
        first = stream.readline()
        if first != b"ply\n":
            raise ValueError(f"{path}: not a PLY file")
        fmt = None
        vertex_count = None
        properties: list[tuple[str, str]] = []
        in_vertex = False
        while True:
            line = stream.readline()
            header_lines += 1
            if not line:
                raise ValueError(f"{path}: truncated PLY header")
            text = line.decode("ascii").strip()
            fields = text.split()
            if fields[:1] == ["format"]:
                fmt = fields[1]
            elif fields[:1] == ["element"]:
                in_vertex = fields[1] == "vertex"
                if in_vertex:
                    vertex_count = int(fields[2])
            elif fields[:1] == ["property"] and in_vertex:
                if fields[1] == "list":
                    raise ValueError(f"{path}: list property in vertex element is unsupported")
                properties.append((fields[2], fields[1]))
            elif text == "end_header":
                data_offset = stream.tell()
                break
    if vertex_count is None or fmt not in {"binary_little_endian", "ascii"}:
        raise ValueError(f"{path}: only ASCII or little-endian binary vertices are supported")
    names = [name for name, _ in properties]
    if not {"x", "y", "z"}.issubset(names):
        raise ValueError(f"{path}: x/y/z vertex properties are required")
    if fmt == "ascii":
        values = np.loadtxt(path, skiprows=header_lines, max_rows=vertex_count)
        return values[:, [names.index("x"), names.index("y"), names.index("z")]]
    try:
        dtype = np.dtype([(name, _PLY_TYPES[kind]) for name, kind in properties])
    except KeyError as error:
        raise ValueError(f"{path}: unsupported PLY property type {error.args[0]}") from error
    with path.open("rb") as stream:
        stream.seek(data_offset)
        vertices = np.fromfile(stream, dtype=dtype, count=vertex_count)
    if len(vertices) != vertex_count:
        raise ValueError(f"{path}: expected {vertex_count} vertices, read {len(vertices)}")
    return np.column_stack((vertices["x"], vertices["y"], vertices["z"]))


def radial_correspondence(
    points: np.ndarray, directions: np.ndarray, options: TrainingOptions
) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(points, dtype=np.float64)
    points = points[np.isfinite(points).all(axis=1)] * options.input_unit_to_mm
    if len(points) < options.neighbor_count:
        raise ValueError("point cloud has too few finite points")
    low = np.quantile(points, options.robust_quantile, axis=0)
    high = np.quantile(points, 1.0 - options.robust_quantile, axis=0)
    center = 0.5 * (low + high)
    centered = points - center
    radii = np.linalg.norm(centered, axis=1)
    valid = radii > 0.0
    centered, radii = centered[valid], radii[valid]
    if len(radii) > options.max_points_per_cloud:
        # Deterministic coverage of the already scanner-ordered point array.
        selection = np.linspace(
            0, len(radii) - 1, options.max_points_per_cloud, dtype=np.int64
        )
        centered, radii = centered[selection], radii[selection]
    unit = centered / radii[:, None]
    distances, indices = cKDTree(unit).query(
        directions, k=min(options.neighbor_count, len(unit)), workers=-1
    )
    if indices.ndim == 1:
        indices, distances = indices[:, None], distances[:, None]
    weights = 1.0 / np.maximum(distances, 1.0e-8)
    radial = np.sum(weights * radii[indices], axis=1) / np.sum(weights, axis=1)
    return radial, center


def _shape_files(input_directory: Path) -> list[Path]:
    files = sorted(Path(input_directory).glob("*.ply"), key=lambda path: (
        int("".join(character for character in path.stem if character.isdigit()) or 0),
        path.name,
    ))
    if len(files) < 2:
        raise ValueError("at least two PLY point clouds are required")
    return files


def train_statistical_shape(
    input_directory: Path,
    output_path: Path,
    options: TrainingOptions = TrainingOptions(),
    *,
    cultivar_label: str = "Fuji",
) -> Path:
    options.validate()
    files = _shape_files(input_directory)
    if options.mode_count > len(files) - 1:
        raise ValueError("mode_count cannot exceed sample_count - 1")
    directions = fibonacci_directions(options.direction_count)
    radial_shapes: list[np.ndarray] = []
    centers: list[np.ndarray] = []
    for index, path in enumerate(files, start=1):
        print(f"[shape] {index}/{len(files)} {path.name}", flush=True)
        radial, center = radial_correspondence(read_ply_xyz(path), directions, options)
        radial_shapes.append(radial)
        centers.append(center)
    matrix = np.vstack(radial_shapes)
    mean = matrix.mean(axis=0)
    centered = matrix - mean
    _, singular_values, components = np.linalg.svd(centered, full_matrices=False)
    eigenvalues = singular_values ** 2 / (len(files) - 1)
    total_variance = float(eigenvalues.sum())
    modes = []
    for index in range(options.mode_count):
        modes.append({
            "index": index,
            "eigenvalue_mm2": float(eigenvalues[index]),
            "explained_variance_ratio": (
                float(eigenvalues[index] / total_variance) if total_variance else 0.0
            ),
            "deformation_mm": (
                np.sqrt(eigenvalues[index]) * components[index]
            ).tolist(),
        })
    document = {
        "schema_version": 1,
        "geometry_type": "StatisticalFujiShape",
        "coordinate_system": "centered registered scanner frame",
        "length_unit": "mm",
        "cultivar_label_requested": cultivar_label,
        "cultivar_status": "unverified_in_source_record",
        "cultivar_warning": (
            "Zenodo record 15635995 describes 100 aligned apple point clouds but does not "
            "identify the cultivar. Do not claim Fuji specificity without independent metadata."
        ),
        "provenance": {
            "source_record": ZENODO_RECORD,
            "source_doi": ZENODO_DOI,
            "source_title": ZENODO_TITLE,
            "source_creators": ZENODO_CREATORS,
            "source_publication_date": "2025-06-10",
            "source_license": "CC BY 4.0",
            "source_archive": "LabDataset.zip",
            "source_archive_md5": ZENODO_ARCHIVE_MD5,
            "sample_files": [path.name for path in files],
        },
        "training": {
            "sample_count": len(files),
            "direction_count": options.direction_count,
            "mode_count": options.mode_count,
            "neighbor_count": options.neighbor_count,
            "max_points_per_cloud": options.max_points_per_cloud,
            "input_unit_to_mm": options.input_unit_to_mm,
            "robust_quantile": options.robust_quantile,
            "parameterization": "common Fibonacci directions with inverse-angular-neighbor radial interpolation",
            "centering": "midpoint of per-axis robust quantile bounds; no scale normalization",
            "pca": "SVD of sample-by-direction radial matrix; deformation_mm is one standard deviation",
            "cumulative_explained_variance": float(
                eigenvalues[:options.mode_count].sum() / total_variance
            ) if total_variance else 0.0,
            "centers_input_frame_mm": np.vstack(centers).tolist(),
        },
        "directions": directions.tolist(),
        "mean_radius_mm": mean.tolist(),
        "pca_modes": modes,
        "faces": triangulate_directions(directions).tolist(),
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    return output_path
