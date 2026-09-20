#!/usr/bin/env python3
"""Apply the Fruitsim teaching shell to a completed Unity WebGL build.

Unity 6 can reject an otherwise valid project-local WebGL template on some
Linux editor installations. Keeping this post-build step deterministic lets
the Unity build use its stable Default template while retaining our checked-in
teaching UI and replacing Unity's loader macros with the actual build files.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil


TOKENS = {
    "{{{ LOADER_FILENAME }}}": "WebGL.loader.js",
    "{{{ DATA_FILENAME }}}": "WebGL.data.gz",
    "{{{ FRAMEWORK_FILENAME }}}": "WebGL.framework.js.gz",
    "{{{ CODE_FILENAME }}}": "WebGL.wasm.gz",
}


def apply_shell(build_root: Path, source: Path) -> Path:
    source_text = source.read_text(encoding="utf-8")
    rendered = source_text
    for token, filename in TOKENS.items():
        rendered = rendered.replace(token, filename)
    if "{{{" in rendered:
        raise RuntimeError("WebGL teaching shell still contains an unresolved Unity macro")
    if "/Build/Build/" in rendered:
        raise RuntimeError("WebGL teaching shell contains a duplicated Build path")
    if "Fruitsim 实验台" not in rendered:
        raise RuntimeError("WebGL teaching shell marker is missing")
    missing_assets = [name for name in TOKENS.values() if not (build_root / "Build" / name).is_file()]
    if missing_assets:
        raise RuntimeError(f"WebGL build assets are missing: {', '.join(missing_assets)}")
    build_root.mkdir(parents=True, exist_ok=True)
    static_source = source.parent / "static"
    static_destination = build_root / "static"
    if static_source.is_dir() and static_source.resolve() != static_destination.resolve():
        static_destination.mkdir(parents=True, exist_ok=True)
        for stale_meta in static_destination.rglob("*.meta"):
            stale_meta.unlink()
        shutil.copytree(
            static_source,
            static_destination,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("*.meta"),
        )
    output = build_root / "index.html"
    output.write_text(rendered, encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "apps/fruitsim_unity/Assets/WebGLTemplates/FruitsimDemo/index.html",
    )
    args = parser.parse_args()
    output = apply_shell(args.build_root, args.source)
    print(f"Applied Fruitsim WebGL teaching shell: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
