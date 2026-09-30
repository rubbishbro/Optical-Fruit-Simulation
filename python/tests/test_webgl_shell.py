from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "apply_webgl_demo_shell.py"
STATIC_URL = re.compile(r"static/[A-Za-z0-9_./-]+\.(?:png|json|js|css)")
SPEC = importlib.util.spec_from_file_location("apply_webgl_demo_shell", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WebGLShellTests(unittest.TestCase):
    def test_research_ui_exposes_simulation_figures_and_ml_pages(self) -> None:
        template = SCRIPT.parents[1] / "apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/index.html"
        source = template.read_text(encoding="utf-8")
        for marker in (
            'data-page="simulation"',
            'data-page="figures"',
            'data-page="ml"',
            'data-page="run"',
            "static/absorption_heatmap.png",
            "static/photon_paths.png",
            "static/ml_p1.js",
            "static/ml_p1_contract.js",
            "ml-stage-tabs",
            "ml-dataset-select",
            "ApplyWebParameters",
            "FruitsimOrbitCamera",
        ):
            self.assertIn(marker, source)

    def test_every_static_reference_resolves_on_disk(self) -> None:
        template = SCRIPT.parents[1] / "apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/index.html"
        root = template.parent
        source = template.read_text(encoding="utf-8")
        for script in (root / "static").glob("*.js"):
            source += script.read_text(encoding="utf-8")
        for url in sorted(set(STATIC_URL.findall(source))):
            self.assertTrue((root / url).is_file(), f"missing static reference: {url}")

    def test_dataset_catalog_bundles_exist(self) -> None:
        root = SCRIPT.parents[1] / "apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo"
        catalog = json.loads((root / "static/ml_p1_datasets.json").read_text(encoding="utf-8"))
        self.assertTrue(catalog["datasets"], "dataset catalog must not be empty")
        for dataset in catalog["datasets"]:
            bundle = root / dataset["bundle_url"]
            self.assertTrue(bundle.is_file(), f"missing dataset bundle: {dataset['bundle_url']}")
            payload = json.loads(bundle.read_text(encoding="utf-8"))
            self.assertEqual(payload["dataset_id"], dataset["dataset_id"])

    def test_shell_resolves_each_asset_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root / "Build"
            build.mkdir()
            for filename in MODULE.TOKENS.values():
                (build / filename).write_bytes(b"test")
            template_root = root / "template"
            template_root.mkdir()
            source = template_root / "template.html"
            static = template_root / "static"
            static.mkdir()
            (static / "figure.png").write_bytes(b"png")
            (static / "figure.png.meta").write_text("unity metadata", encoding="utf-8")
            source.write_text(
                "Fruitsim 实验台\n"
                "const buildUrl = 'Build';\n"
                "const loader = buildUrl + '/{{{ LOADER_FILENAME }}}';\n"
                "const data = buildUrl + '/{{{ DATA_FILENAME }}}';\n"
                "const framework = buildUrl + '/{{{ FRAMEWORK_FILENAME }}}';\n"
                "const code = buildUrl + '/{{{ CODE_FILENAME }}}';\n",
                encoding="utf-8",
            )
            output = MODULE.apply_shell(root, source)
            rendered = output.read_text(encoding="utf-8")
            self.assertNotIn("{{{", rendered)
            self.assertNotIn("/Build/Build/", rendered)
            self.assertIn("buildUrl + '/WebGL.loader.js'", rendered)
            self.assertEqual((root / "static" / "figure.png").read_bytes(), b"png")
            self.assertFalse((root / "static" / "figure.png.meta").exists())

    def test_shell_rejects_missing_build_asset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "template.html"
            source.write_text("Fruitsim 实验台 {{{ LOADER_FILENAME }}}", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "assets are missing"):
                MODULE.apply_shell(root, source)


if __name__ == "__main__":
    unittest.main()
