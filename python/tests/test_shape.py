from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from fruitsim_shape import StatisticalFujiShape, TrainingOptions, train_statistical_shape
from fruitsim_shape.training import fibonacci_directions, read_ply_xyz


def write_binary_ply(path: Path, points: np.ndarray) -> None:
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {len(points)}\n"
        "property double x\nproperty double y\nproperty double z\n"
        "property double nx\nproperty double ny\nproperty double nz\n"
        "end_header\n"
    ).encode("ascii")
    normals = points / np.linalg.norm(points, axis=1)[:, None]
    records = np.column_stack((points, normals)).astype("<f8")
    with path.open("wb") as stream:
        stream.write(header)
        records.tofile(stream)


class StatisticalShapeTests(unittest.TestCase):
    def test_train_load_and_reproducible_sample(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            directions = fibonacci_directions(2000)
            for index, axes in enumerate([
                (38.0, 42.0, 39.0),
                (40.0, 44.0, 38.0),
                (42.0, 41.0, 40.0),
                (39.0, 46.0, 41.0),
            ], start=2):
                scaled = directions * np.asarray(axes)[None, :]
                # Ellipsoid radius in each sampled direction.
                radius = 1.0 / np.linalg.norm(scaled / np.square(axes), axis=1)
                points = directions * radius[:, None] + np.array([5.0, -3.0, 2.0])
                write_binary_ply(directory / f"apple{index}.ply", points)

            loaded = read_ply_xyz(directory / "apple2.ply")
            self.assertEqual(loaded.shape, (2000, 3))
            model_path = directory / "statistical_fuji_shape.json"
            train_statistical_shape(
                directory,
                model_path,
                TrainingOptions(
                    direction_count=128,
                    mode_count=2,
                    neighbor_count=4,
                    max_points_per_cloud=2000,
                    input_unit_to_mm=1.0,
                    robust_quantile=0.0,
                ),
            )
            document = json.loads(model_path.read_text(encoding="utf-8"))
            self.assertEqual(document["training"]["sample_count"], 4)
            self.assertEqual(document["cultivar_status"], "unverified_in_source_record")

            model = StatisticalFujiShape.load(model_path)
            first = model.sample(seed=42, mode_count=2)
            second = model.sample(seed=42, mode_count=2)
            np.testing.assert_array_equal(first.vertices_mm, second.vertices_mm)
            self.assertEqual(first.vertices_mm.shape, (128, 3))
            self.assertGreater(len(first.faces), 200)
            inner = first.inset_vertices_mm(1.0)
            np.testing.assert_allclose(
                np.linalg.norm(first.vertices_mm, axis=1)
                - np.linalg.norm(inner, axis=1),
                1.0,
                atol=1.0e-10,
            )
            output = first.write_ply(directory / "sample.ply")
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()
