#!/usr/bin/env python3
"""Serve a Unity WebGL build plus an opt-in, read-only Run results API.

Static behaviour (gzip/brotli Content-Encoding, health check, MIME types) is
preserved. The ``/api/runs/...`` endpoints are only exposed when ``--runs-root``
is given explicitly; they serve an allowlisted view of immutable Run directories
without exposing machine paths or arbitrary files.
"""

from __future__ import annotations

import argparse
import json
from io import BytesIO
import mimetypes
from pathlib import Path
import re
import shutil
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import quote, unquote, urlsplit


SCHEMA_VERSION = 1
API_PREFIX = "/api/runs/"
# Mirrors fruitsim_pipeline.contracts.RUN_ID_RE but capped like the orchestrator.
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")
RESERVED_IDS = {".", ".."}
TERMINAL_STATES = {"completed", "failed", "cancelled"}

# Only explicitly registered artifacts whose media type AND role are listed here
# may ever be downloaded. This blocks a malicious artifacts.json from turning the
# endpoint into an arbitrary file server (e.g. text/html or an unknown role).
ALLOWED_MEDIA_TYPES = {
    "text/csv",
    "text/plain",
    "application/json",
    "application/octet-stream",  # spectra.npz and similar registered tensors
}
ALLOWED_ROLES = {
    "sample_table",
    "spectral_table",
    "spectral_tensor",
    "ml_input",
    "ml_input_pending_label",
    "data_provenance",
    "simulation_summary",
    "simulation_provenance",
    "detector_spectrum",
    "detector_spectrum_table",
    "detector_path_statistics",
    "performance",
}
# Never leak request.json (contains output_dir) or internal logs through the API.
BLOCKED_RELATIVE_PARTS = {"request.json", "logs"}
METADATA_FILES = ("manifest.json", "status.json", "artifacts.json")

MAX_METADATA_BYTES = 256 * 1024  # cap parsing of run metadata
PREVIEW_MAX_BYTES = 512 * 1024  # client-side CSV preview budget, echoed in summary


class RunsApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _safe_segment(segment: str) -> str:
    decoded = unquote(segment)
    if decoded in RESERVED_IDS:
        raise RunsApiError(404, "not_found", "unknown resource")
    if "/" in decoded or "\\" in decoded or "\x00" in decoded:
        raise RunsApiError(404, "not_found", "unknown resource")
    if not SAFE_ID_RE.fullmatch(decoded):
        raise RunsApiError(404, "not_found", "unknown resource")
    return decoded


class RunsApi:
    """Read-only, allowlisted view over ``runs_root``."""

    def __init__(self, runs_root: Path) -> None:
        self.runs_root = Path(runs_root).resolve()

    # ------------------------------------------------------------- run loading
    def resolve_run_dir(self, run_id: str) -> Path:
        candidate = (self.runs_root / run_id).resolve()
        if not candidate.is_relative_to(self.runs_root):
            raise RunsApiError(404, "run_not_found", "run not found")
        if candidate.name != run_id or not candidate.is_dir():
            raise RunsApiError(404, "run_not_found", "run not found")
        return candidate

    def _load_metadata_file(self, run_dir: Path, name: str, run_id: str) -> dict[str, Any]:
        path = run_dir / name
        # Metadata must be a regular file directly inside the Run: a symlink to
        # another Run or an external file must never be read.
        if path.is_symlink():
            raise RunsApiError(503, "run_unreadable", "run metadata is not a regular file")
        if not path.is_file():
            raise RunsApiError(503, "run_unreadable", "run metadata is missing")
        if not path.resolve().is_relative_to(run_dir):
            raise RunsApiError(503, "run_unreadable", "run metadata escapes the run")
        try:
            if path.stat().st_size > MAX_METADATA_BYTES:
                raise RunsApiError(503, "run_unreadable", "run metadata is too large")
            document = json.loads(path.read_text(encoding="utf-8"))
        except RunsApiError:
            raise
        except (OSError, ValueError):
            raise RunsApiError(503, "run_unreadable", "run metadata is corrupt")
        if not isinstance(document, dict):
            raise RunsApiError(503, "run_unreadable", "run metadata is corrupt")
        if document.get("schema_version") != SCHEMA_VERSION:
            raise RunsApiError(503, "run_unreadable", "run metadata schema is unsupported")
        declared = document.get("run_id")
        # manifest/status carry a required Run identity; artifacts.json does
        # not, but an optional identity there must agree if supplied.
        if (name in {"manifest.json", "status.json"} or declared is not None) and declared != run_id:
            raise RunsApiError(503, "run_unreadable", "run metadata identity mismatch")
        return document

    def _load_run(self, run_id: str) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
        run_dir = self.resolve_run_dir(run_id)
        manifest = self._load_metadata_file(run_dir, "manifest.json", run_id)
        status_doc = self._load_metadata_file(run_dir, "status.json", run_id)
        artifacts_doc = self._load_metadata_file(run_dir, "artifacts.json", run_id)
        state = status_doc.get("state")
        if not isinstance(state, str) or not state:
            raise RunsApiError(503, "run_unreadable", "run status is invalid")
        return run_dir, manifest, status_doc, artifacts_doc

    # ------------------------------------------------------------- artifacts
    def _eligible_entry(self, run_dir: Path, entry: Any) -> dict[str, Any] | None:
        """Single source of truth for which artifacts may be listed or served."""
        if not isinstance(entry, dict):
            return None
        artifact_id = entry.get("artifact_id")
        relative_path = entry.get("relative_path")
        media_type = entry.get("media_type")
        role = entry.get("role")
        if not isinstance(artifact_id, str) or not SAFE_ID_RE.fullmatch(artifact_id):
            return None
        if not isinstance(relative_path, str) or not isinstance(media_type, str) or media_type not in ALLOWED_MEDIA_TYPES:
            return None
        if not isinstance(role, str) or role not in ALLOWED_ROLES:
            return None
        raw = Path(relative_path)
        if raw.is_absolute() or ".." in raw.parts:
            return None
        if any(part in BLOCKED_RELATIVE_PARTS for part in raw.parts):
            return None
        candidate = run_dir / relative_path
        # Artifact symlinks are never served: a link could alias request.json,
        # logs, another Run, or a file outside the Run.
        if candidate.is_symlink():
            return None
        resolved = candidate.resolve()
        if not resolved.is_relative_to(run_dir) or not resolved.is_file():
            return None
        rel_resolved = resolved.relative_to(run_dir)
        if any(part in BLOCKED_RELATIVE_PARTS for part in rel_resolved.parts):
            return None
        try:
            size = resolved.stat().st_size
        except OSError:
            return None
        return {
            "artifact_id": artifact_id,
            "role": role,
            "media_type": media_type,
            "relative_path": relative_path,
            "sha256": entry.get("sha256") if isinstance(entry.get("sha256"), str) else None,
            "size": size,
            "previewable": media_type == "text/csv" and size <= PREVIEW_MAX_BYTES,
            "path": resolved,
        }

    def _allowed_artifacts(self, run_dir: Path, artifacts_doc: dict[str, Any]) -> list[dict[str, Any]]:
        entries = artifacts_doc.get("artifacts")
        if not isinstance(entries, list):
            raise RunsApiError(503, "run_unreadable", "artifact index is corrupt")
        allowed: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in entries:
            artifact_id = entry.get("artifact_id") if isinstance(entry, dict) else None
            if not isinstance(artifact_id, str) or artifact_id in seen:
                # Unsafe or duplicate ids are never listed with a URL.
                continue
            seen.add(artifact_id)
            eligible = self._eligible_entry(run_dir, entry)
            if eligible is not None:
                allowed.append(eligible)
        return allowed

    # ------------------------------------------------------------- public
    def summary(self, run_id: str) -> dict[str, Any]:
        run_dir, manifest, status_doc, artifacts_doc = self._load_run(run_id)
        state = status_doc["state"]
        public_artifacts = []
        for entry in self._allowed_artifacts(run_dir, artifacts_doc):
            public_artifacts.append(
                {
                    "artifact_id": entry["artifact_id"],
                    "role": entry["role"],
                    "media_type": entry["media_type"],
                    "relative_path": entry["relative_path"],
                    "sha256": entry["sha256"],
                    "size": entry["size"],
                    "previewable": entry["previewable"],
                    "url": f"{API_PREFIX}{quote(run_id, safe='')}/artifacts/{quote(entry['artifact_id'], safe='')}",
                }
            )
        configuration_hash = manifest.get("configuration_hash")
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "state": state,
            "complete": state in TERMINAL_STATES,
            "terminal": state in TERMINAL_STATES,
            "succeeded": state == "completed",
            "source_type": manifest.get("source_type"),
            "seed": manifest.get("seed"),
            "created_at": manifest.get("created_at"),
            "generator_version": manifest.get("generator_version"),
            "configuration_hash": configuration_hash if isinstance(configuration_hash, str) else None,
            "model_status": manifest.get("model_status"),
            "data_status": manifest.get("data_status"),
            "warnings": manifest.get("warnings") if isinstance(manifest.get("warnings"), list) else [],
            "artifacts": public_artifacts,
        }

    def artifact(self, run_id: str, artifact_id: str) -> dict[str, Any]:
        """Return descriptor for an allowlisted artifact (path, type, filename)."""
        if not SAFE_ID_RE.fullmatch(artifact_id):
            raise RunsApiError(404, "artifact_not_found", "artifact not found")
        run_dir, _manifest, _status_doc, artifacts_doc = self._load_run(run_id)
        for entry in self._allowed_artifacts(run_dir, artifacts_doc):
            if entry["artifact_id"] == artifact_id:
                resolved = entry["path"]
                suffix = resolved.suffix if resolved.suffix and len(resolved.suffix) <= 8 else ""
                safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", artifact_id)
                return {
                    "path": resolved,
                    "media_type": entry["media_type"],
                    "filename": f"{safe_id}{suffix}",
                    "size": entry["size"],
                }
        raise RunsApiError(404, "artifact_not_found", "artifact not found")


class WebGLRequestHandler(SimpleHTTPRequestHandler):
    server_version = "FruitsimWebGL/1"
    runs_api: RunsApi | None = None

    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    # ------------------------------------------------------------------ API
    def _api_route(self) -> list[str]:
        remainder = urlsplit(self.path).path[len(API_PREFIX):]
        segments = remainder.split("/")
        if any(segment == "" for segment in segments):
            # Trailing slash / double slash: treat as a directory-style request.
            raise RunsApiError(404, "not_found", "unknown resource")
        return segments

    def _send_json(self, status: int, document: dict[str, Any], *, head_only: bool) -> None:
        body = json.dumps(document, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _handle_runs_api(self, *, head_only: bool) -> None:
        if self.runs_api is None:
            # API is not enabled: do not reveal whether a run exists.
            self._send_json(404, {"error": "api_disabled"}, head_only=head_only)
            return
        try:
            segments = self._api_route()
            if len(segments) == 1:
                run_id = _safe_segment(segments[0])
                self._send_json(200, self.runs_api.summary(run_id), head_only=head_only)
                return
            if len(segments) == 3 and segments[1] == "artifacts":
                run_id = _safe_segment(segments[0])
                artifact_id = _safe_segment(segments[2])
                info = self.runs_api.artifact(run_id, artifact_id)
                self.send_response(200)
                self.send_header("Content-Type", info["media_type"])
                self.send_header("Content-Length", str(info["size"]))
                self.send_header("Content-Disposition", f'attachment; filename="{info["filename"]}"')
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                if not head_only:
                    with info["path"].open("rb") as stream:
                        shutil.copyfileobj(stream, self.wfile, length=64 * 1024)
                return
            raise RunsApiError(404, "not_found", "unknown resource")
        except RunsApiError as error:
            self._send_json(error.status, {"error": error.code}, head_only=head_only)
        except Exception:  # noqa: BLE001 - never leak internals via a 500 body
            self._send_json(503, {"error": "run_unreadable"}, head_only=head_only)

    def _is_api_path(self) -> bool:
        return urlsplit(self.path).path.startswith(API_PREFIX)

    def _serve_static(self, *, head_only: bool) -> None:
        if head_only:
            super().do_HEAD()
        else:
            super().do_GET()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self._is_api_path():
            self._handle_runs_api(head_only=False)
            return
        if urlsplit(self.path).path == "/health":
            body = json.dumps({"ok": True, "service": "fruitsim-webgl-static"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._serve_static(head_only=False)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        if self._is_api_path():
            self._handle_runs_api(head_only=True)
            return
        self._serve_static(head_only=True)

    def send_head(self):  # noqa: N802 - stdlib handler API
        requested = Path(self.translate_path(self.path))
        served = requested
        encoding = None
        content_path = requested
        if served.is_file() and served.suffix in {".br", ".gz"}:
            encoding = "br" if served.suffix == ".br" else "gzip"
            content_path = Path(str(served)[: -len(served.suffix)])
        if not served.is_file():
            for suffix, value in ((".br", "br"), (".gz", "gzip")):
                candidate = Path(str(requested) + suffix)
                if candidate.is_file():
                    served = candidate
                    encoding = value
                    content_path = requested
                    break
        if not served.is_file():
            return super().send_head()
        try:
            content = served.read_bytes()
        except OSError:
            self.send_error(404, "File not readable")
            return None
        content_type = mimetypes.guess_type(str(content_path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        if encoding:
            self.send_header("Content-Encoding", encoding)
        self.end_headers()
        return BytesIO(content)


def main() -> int:
    parser = argparse.ArgumentParser(prog="serve_webgl_demo")
    parser.add_argument("--root", type=Path, default=Path("apps/fruitsim_unity/build/WebGL"))
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=None,
        help="opt-in: expose the read-only /api/runs result API under this directory",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"WebGL build directory does not exist: {root}")
    WebGLRequestHandler.runs_api = RunsApi(args.runs_root.resolve()) if args.runs_root is not None else None
    server = ThreadingHTTPServer(
        (args.bind, args.port), lambda *items: WebGLRequestHandler(*items, directory=str(root))
    )
    api_note = f" (runs API: {args.runs_root.resolve()})" if args.runs_root else " (runs API disabled)"
    print(f"Serving {root} at http://{args.bind}:{args.port}{api_note}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
