#!/usr/bin/env python3
"""Validate the static and published WebGL teaching assets end to end.

The check follows the references the page actually uses instead of only looking
for substrings: it resolves every ``static/`` URL in the HTML/JS, every bundle in
``ml_p1_datasets.json``, and (with ``--build-root``) the Unity loader and data
files in a finished build. ``--http-base`` additionally fetches each URL so a
served build can be verified the same way a browser loads it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATIC = (
    ROOT / "apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/static"
)
DEFAULT_TEMPLATE = (
    ROOT / "apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/index.html"
)
CATALOG_NAME = "ml_p1_datasets.json"
REQUIRED_BUNDLE_KEYS = {
    "schema_version",
    "experiment_id",
    "dataset_id",
    "source",
    "stages",
    "pipeline_order",
    "playback_plan",
    "results_graph",
}
REQUIRED_BUILD_FILES = (
    "Build/WebGL.loader.js",
    "Build/WebGL.data.gz",
    "Build/WebGL.framework.js.gz",
    "Build/WebGL.wasm.gz",
)
STATIC_URL = re.compile(r"static/[A-Za-z0-9_./-]+\.(?:png|json|js|css)")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.checked: list[str] = []

    def require(self, condition: bool, message: str) -> None:
        if condition:
            self.checked.append(message)
        else:
            self.errors.append(message)


def _load_json(path: Path, report: Report) -> dict | None:
    if not path.is_file():
        report.require(False, f"missing JSON: {path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        report.require(False, f"invalid JSON {path}: {error}")
        return None


def resolve_static_url(url: str, root: Path, report: Report) -> Path:
    relative = url.split("?", 1)[0]
    path = (root / relative).resolve()
    report.require(path.is_file(), f"static reference resolves: {relative}")
    return path


def check_catalog(static_dir: Path, report: Report) -> list[dict]:
    catalog_path = static_dir / CATALOG_NAME
    report.require(catalog_path.is_file(), f"catalog exists: {CATALOG_NAME}")
    catalog = _load_json(catalog_path, report) or {}
    datasets = catalog.get("datasets", [])
    report.require(bool(datasets), "catalog lists at least one dataset")
    report.require(
        catalog.get("source_type") == "SYNTHETIC_TEACHING",
        "catalog is labelled SYNTHETIC_TEACHING",
    )
    for dataset in datasets:
        url = dataset.get("bundle_url")
        if not url:
            report.require(False, f"dataset {dataset.get('dataset_id')!r} has a bundle_url")
            continue
        path = resolve_static_url(url, static_dir.parent, report)
        if not path.is_file():
            continue
        bundle = _load_json(path, report)
        if bundle is None:
            continue
        missing = REQUIRED_BUNDLE_KEYS - set(bundle)
        report.require(
            not missing,
            f"{url} has required keys (missing: {sorted(missing)})",
        )
        source = bundle.get("source", {})
        report.require(
            source.get("source_type") == "SYNTHETIC_TEACHING" and source.get("synthetic") is True,
            f"{url} keeps the synthetic teaching boundary",
        )
        report.require(
            bundle.get("dataset_id") == dataset.get("dataset_id"),
            f"{url} dataset_id matches the catalog",
        )
    return datasets


def check_html_references(template: Path, root: Path, report: Report) -> None:
    report.require(template.is_file(), f"template exists: {template}")
    if not template.is_file():
        return
    text = template.read_text(encoding="utf-8")
    for url in sorted(set(STATIC_URL.findall(text))):
        if url.endswith(CATALOG_NAME):
            continue
        resolve_static_url(url, root, report)
    for script in template.parent.glob("static/*.js"):
        script_text = script.read_text(encoding="utf-8")
        for url in sorted(set(STATIC_URL.findall(script_text))):
            resolve_static_url(url, root, report)


def check_publish(build_root: Path, report: Report) -> None:
    for name in REQUIRED_BUILD_FILES:
        report.require((build_root / name).is_file(), f"build file exists: {name}")
    index = build_root / "index.html"
    report.require(index.is_file(), "publish index.html exists")
    if index.is_file():
        text = index.read_text(encoding="utf-8")
        report.require("{{{" not in text, "publish index.html has no unresolved Unity macro")
        check_html_references(index, build_root, report)
    static_dir = build_root / "static"
    if (static_dir / CATALOG_NAME).is_file():
        check_catalog(static_dir, report)
    else:
        report.require(False, f"publish static catalog missing: {static_dir / CATALOG_NAME}")
    build_dir = build_root / "Build"
    if build_dir.is_dir():
        report.require(
            any(path.name.endswith(".loader.js") for path in build_dir.iterdir()),
            "publish Build directory contains a Unity loader",
        )


def check_http(base: str, urls: Iterable[str], report: Report) -> None:
    base = base.rstrip("/")
    for url in urls:
        target = f"{base}/{url}"
        try:
            with urllib.request.urlopen(target, timeout=15) as response:
                status = response.status
        except Exception as error:  # noqa: BLE001 - surface any transport error
            report.require(False, f"HTTP GET {target}: {error}")
            continue
        report.require(status == 200, f"HTTP 200 {target}")


def collect_urls(static_dir: Path, template: Path) -> list[str]:
    urls: set[str] = {f"static/{CATALOG_NAME}"}
    catalog = static_dir / CATALOG_NAME
    if catalog.is_file():
        try:
            for dataset in json.loads(catalog.read_text(encoding="utf-8")).get("datasets", []):
                if dataset.get("bundle_url"):
                    urls.add(dataset["bundle_url"])
        except json.JSONDecodeError:
            pass
    for source in (template, *template.parent.glob("static/*.js")):
        if source.is_file():
            urls.update(STATIC_URL.findall(source.read_text(encoding="utf-8")))
    return sorted(urls)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--static", type=Path, default=DEFAULT_STATIC)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--build-root", type=Path)
    parser.add_argument("--http-base", help="e.g. http://127.0.0.1:8080")
    parser.add_argument("--require-catalog", action="store_true",
                        help="fail when the static catalog/bundles are absent")
    args = parser.parse_args()

    report = Report()
    if args.static.is_dir():
        check_catalog(args.static, report)
        check_html_references(args.template, args.static.parent, report)
    elif args.require_catalog:
        report.require(False, f"static asset directory missing: {args.static}")
    else:
        print(f"skip static catalog (not present): {args.static}")

    if args.build_root is not None:
        check_publish(args.build_root, report)

    if args.http_base and args.static.is_dir():
        check_http(args.http_base, collect_urls(args.static, args.template), report)

    for line in report.checked:
        print(f"ok   {line}")
    for line in report.errors:
        print(f"FAIL {line}", file=sys.stderr)
    print(
        f"\n{len(report.checked)} checks passed, {len(report.errors)} failed"
    )
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
