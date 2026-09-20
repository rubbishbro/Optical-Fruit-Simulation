from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fruitsim_pipeline.synthetic_math import MathSyntheticConfig, generate_math_run
from fruitsim_ml.visualize import build_visualizations


class VisualizationTests(unittest.TestCase):
    def test_standard_figure_set_is_generated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = generate_math_run(Path(directory), "visual_run", MathSyntheticConfig(samples=16, seed=3))
            output = build_visualizations(run_dir)
            expected = {
                "pipeline_path.png", "spectra_heatmap.png", "pca_scatter.png",
                "proxy_correlation_heatmap.png", "spectra_overview.png",
                "visualization_manifest.json",
            }
            self.assertEqual(expected, {path.name for path in output.iterdir()})
            for path in output.glob("*.png"):
                self.assertGreater(path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
