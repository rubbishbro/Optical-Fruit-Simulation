from __future__ import annotations

import json
from pathlib import Path
import socket
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.serve_webgl_demo import RunsApi, WebGLRequestHandler


def _write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def _make_run(runs_root: Path, run_id: str, **overrides) -> Path:
    run_dir = runs_root / run_id
    _write(run_dir / "data" / "samples.csv", "sample_id,fruit_id,batch_id,source_type\nS1,F1,B1,synthetic_math\n")
    _write(run_dir / "data" / "spectra.csv", "sample_id,500,510\nS1,0.1,0.2\n")
    artifacts = overrides.pop(
        "artifacts",
        [
            {"artifact_id": "samples", "role": "sample_table", "media_type": "text/csv", "relative_path": "data/samples.csv", "sha256": "a" * 64},
            {"artifact_id": "spectra", "role": "spectral_table", "media_type": "text/csv", "relative_path": "data/spectra.csv", "sha256": "b" * 64},
        ],
    )
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "status": overrides.pop("status", "completed"),
        "source_type": "synthetic_math",
        "seed": 20260920,
        "created_at": "2026-09-30T00:00:00Z",
        "generator_version": "0.1.0",
        "configuration_hash": "c" * 64,
        "model_status": "method_demo",
        "data_status": "synthetic_demonstration",
        "warnings": ["Synthetic data; not valid for real apple SSC prediction."],
    }
    manifest.update(overrides.pop("manifest_overrides", {}))
    status_doc = {"schema_version": 1, "run_id": run_id, "state": manifest["status"], "updated_at": "2026-09-30T00:00:00Z"}
    status_doc.update(overrides.pop("status_overrides", {}))
    _write(run_dir / "manifest.json", json.dumps(manifest))
    if not overrides.pop("omit_status", False):
        _write(run_dir / "status.json", json.dumps(status_doc))
    if not overrides.pop("omit_artifacts", False):
        _write(run_dir / "artifacts.json", json.dumps({"schema_version": 1, "artifacts": artifacts}))
    _write(run_dir / "request.json", json.dumps({"output_dir": "/srv/secret/absolute/path", "run_id": run_id}))
    return run_dir


class _Server:
    def __init__(self, root: Path, runs_root: Path | None) -> None:
        WebGLRequestHandler.runs_api = RunsApi(runs_root) if runs_root is not None else None
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", 0), lambda *items: WebGLRequestHandler(*items, directory=str(root))
        )
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def _request(url: str, method: str = "GET"):
    request = Request(url, method=method)
    try:
        response = urlopen(request, timeout=10)
    except HTTPError as error:
        return error.code, dict(error.headers), error.read()
    return response.status, dict(response.headers), response.read()


def _raw_request(port: int, target: str, method: str = "GET") -> tuple[int, bytes]:
    """Send an unnormalized request line so the server's own checks are tested."""
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.sendall(
            f"{method} {target} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n".encode()
        )
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    raw = b"".join(chunks)
    head, _, body = raw.partition(b"\r\n\r\n")
    status = int(head.split(b" ", 2)[1]) if head else 0
    return status, body


class RunsApiHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        self.static_root = root / "static"
        _write(self.static_root / "index.html", "<html>demo</html>")
        _write(self.static_root / "Build" / "WebGL.framework.js.gz", b"\x1f\x8bcompressed")
        _write(self.static_root / "Build" / "WebGL.wasm.gz", b"\x1f\x8bwasm")
        self.runs_root = root / "runs"
        self.runs_root.mkdir(parents=True)
        _make_run(self.runs_root, "run_one")

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _server(self, runs_root=True):
        server = _Server(self.static_root, self.runs_root if runs_root else None)
        self.addCleanup(server.close)
        return server

    # ------------------------------------------------------------------ happy
    def test_summary_and_artifact_roundtrip(self) -> None:
        server = self._server()
        status, headers, body = _request(f"{server.base}/api/runs/run_one")
        self.assertEqual(status, 200)
        document = json.loads(body)
        self.assertEqual(document["run_id"], "run_one")
        self.assertEqual(document["state"], "completed")
        self.assertTrue(document["complete"])
        self.assertEqual(len(document["artifacts"]), 2)
        urls = {item["artifact_id"]: item["url"] for item in document["artifacts"]}
        self.assertEqual(urls["samples"], "/api/runs/run_one/artifacts/samples")
        samples = next(item for item in document["artifacts"] if item["artifact_id"] == "samples")
        self.assertTrue(samples["previewable"])
        text = body.decode("utf-8")
        self.assertNotIn(self.runs_root.as_posix(), text)
        self.assertNotIn("/srv/secret", text)
        self.assertNotIn("output_dir", text)

        status, headers, content = _request(f"{server.base}/api/runs/run_one/artifacts/samples")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/csv")
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertIn(b"sample_id", content)

    def test_head_matches_get_without_body(self) -> None:
        server = self._server()
        get_status, get_headers, get_body = _request(f"{server.base}/api/runs/run_one")
        head_status, head_headers, head_body = _request(f"{server.base}/api/runs/run_one", method="HEAD")
        self.assertEqual(head_status, 200)
        self.assertEqual(head_body, b"")
        self.assertEqual(head_headers["Content-Type"], get_headers["Content-Type"])
        self.assertEqual(head_headers["Content-Length"], str(len(get_body)))

        head_status, head_headers, head_body = _request(
            f"{server.base}/api/runs/run_one/artifacts/samples", method="HEAD"
        )
        self.assertEqual(head_status, 200)
        self.assertEqual(head_body, b"")
        self.assertEqual(head_headers["Content-Type"], "text/csv")

    def test_api_disabled_when_no_runs_root(self) -> None:
        server = self._server(runs_root=False)
        status, _, body = _request(f"{server.base}/api/runs/run_one")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["error"], "api_disabled")
        status, _, _ = _request(f"{server.base}/api/runs/run_one/artifacts/samples")
        self.assertEqual(status, 404)

    def test_static_gzip_and_health_preserved(self) -> None:
        server = self._server()
        status, headers, body = _request(f"{server.base}/health")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])
        status, headers, _ = _request(f"{server.base}/Build/WebGL.framework.js.gz")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Encoding"), "gzip")
        self.assertTrue(headers.get("Content-Type", "").endswith("javascript"))
        status, headers, _ = _request(f"{server.base}/Build/WebGL.wasm.gz")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "application/wasm")

    # ------------------------------------------------------------------ errors
    def test_missing_and_corrupt_metadata(self) -> None:
        server = self._server()
        self.assertEqual(_request(f"{server.base}/api/runs/absent")[0], 404)
        _write(self.runs_root / "broken" / "manifest.json", "{not json")
        self.assertEqual(_request(f"{server.base}/api/runs/broken")[0], 503)
        run_dir = _make_run(self.runs_root, "corrupt_index")
        _write(run_dir / "artifacts.json", "{not json")
        status, _, body = _request(f"{server.base}/api/runs/corrupt_index")
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body)["error"], "run_unreadable")

    def test_incomplete_run_is_flagged_not_faked(self) -> None:
        server = self._server()
        _make_run(self.runs_root, "generating_run", status="generating_data")
        status, _, body = _request(f"{server.base}/api/runs/generating_run")
        self.assertEqual(status, 200)
        document = json.loads(body)
        self.assertFalse(document["complete"])
        self.assertEqual(document["state"], "generating_data")

    # --------------------------------------------------------------- traversal
    def test_traversal_and_encoding_are_rejected(self) -> None:
        server = self._server()
        port = int(server.base.rsplit(":", 1)[1])
        for suffix in (
            "../run_one",
            "..%2frun_one",
            "%2e%2e",
            "%252e%252e",
            "run_one%2f..%2f..",
            "run_one\\..",
            ".%2e",
            "run_one%00",
        ):
            status, _, _ = _request(f"{server.base}/api/runs/{suffix}")
            self.assertIn(status, (400, 404), suffix)

    def test_raw_unnormalized_traversal_is_rejected_by_server(self) -> None:
        server = self._server()
        port = int(server.base.rsplit(":", 1)[1])
        targets = (
            "/api/runs/../run_one",
            "/api/runs/../../etc/passwd",
            "/api/runs/%2e%2e",
            "/api/runs/%252e%252e",
            "/api/runs/run_one%2f..%2f..%2fother_run",
            "/api/runs/..%5c..%5crun_one",
            "/api/runs/run_one/../../other_run/manifest.json",
            "/api/runs/run_one/artifacts/../../../etc/passwd",
        )
        for target in targets:
            status, body = _raw_request(port, target)
            self.assertEqual(status, 404, target)
            self.assertNotIn(b"sample_id", body)
            self.assertNotIn(b"root:", body)

    def test_directory_and_shape_requests_rejected(self) -> None:
        server = self._server()
        for path in (
            "/api/runs",
            "/api/runs/",
            "/api/runs/run_one/",
            "/api/runs/run_one/artifacts",
            "/api/runs/run_one/artifacts/",
            "/api/runs/run_one/data/samples.csv",
            "/api/runs/run_one/artifacts/samples/extra",
        ):
            status, _, _ = _request(f"{server.base}{path}")
            self.assertEqual(status, 404, path)

    def test_unregistered_and_disallowed_artifacts(self) -> None:
        server = self._server()
        self.assertEqual(_request(f"{server.base}/api/runs/run_one/artifacts/missing")[0], 404)
        _make_run(
            self.runs_root,
            "bad_artifacts",
            artifacts=[
                {"artifact_id": "html", "role": "sample_table", "media_type": "text/html", "relative_path": "data/samples.csv", "sha256": "c" * 64},
                {"artifact_id": "script", "role": "arbitrary_file", "media_type": "text/csv", "relative_path": "data/samples.csv", "sha256": "d" * 64},
                {"artifact_id": "secret", "role": "execution_log", "media_type": "application/json", "relative_path": "request.json", "sha256": "e" * 64},
            ],
        )
        status, _, body = _request(f"{server.base}/api/runs/bad_artifacts")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["artifacts"], [])
        for artifact_id in ("html", "script", "secret"):
            self.assertEqual(_request(f"{server.base}/api/runs/bad_artifacts/artifacts/{artifact_id}")[0], 404)

    def test_cross_run_and_traversal_artifacts_rejected(self) -> None:
        server = self._server()
        _make_run(self.runs_root, "other_run")
        _make_run(
            self.runs_root,
            "cross_run",
            artifacts=[
                {"artifact_id": "escape", "role": "sample_table", "media_type": "text/csv", "relative_path": "../other_run/data/samples.csv", "sha256": "f" * 64},
                {"artifact_id": "dotdot", "role": "sample_table", "media_type": "text/csv", "relative_path": "data/../../other_run/data/samples.csv", "sha256": "0" * 64},
            ],
        )
        status, _, body = _request(f"{server.base}/api/runs/cross_run")
        self.assertEqual(json.loads(body)["artifacts"], [])
        self.assertEqual(_request(f"{server.base}/api/runs/cross_run/artifacts/escape")[0], 404)

    def test_run_and_file_symlink_escape_rejected(self) -> None:
        server = self._server()
        import tempfile

        with tempfile.TemporaryDirectory() as outside_name:
            outside = Path(outside_name)
            _write(outside / "manifest.json", json.dumps({"run_id": "linked", "status": "completed"}))
            _write(outside / "samples.csv", "sample_id,fruit_id,batch_id,source_type\nX,X,X,X\n")
            linked = self.runs_root / "linked"
            try:
                linked.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks unsupported")
            self.assertEqual(_request(f"{server.base}/api/runs/linked")[0], 404)

            run_dir = _make_run(self.runs_root, "file_link")
            (run_dir / "data").mkdir(exist_ok=True)
            try:
                (run_dir / "data" / "escape.csv").symlink_to(outside / "samples.csv")
            except OSError:
                self.skipTest("symlinks unsupported")
            _write(
                run_dir / "artifacts.json",
                json.dumps(
                    {
                        "schema_version": 1,
                        "artifacts": [
                            {"artifact_id": "escape", "role": "sample_table", "media_type": "text/csv", "relative_path": "data/escape.csv", "sha256": "1" * 64}
                        ],
                    }
                ),
            )
            status, _, body = _request(f"{server.base}/api/runs/file_link")
            self.assertEqual(json.loads(body)["artifacts"], [])
            self.assertEqual(_request(f"{server.base}/api/runs/file_link/artifacts/escape")[0], 404)

    # ------------------------------------------------- metadata integrity (A)
    def test_metadata_symlinks_are_rejected(self) -> None:
        server = self._server()
        _make_run(self.runs_root, "meta_target")
        targets = {
            "manifest_link": "manifest.json",
            "status_link": "status.json",
            "artifacts_link": "artifacts.json",
        }
        for run_id, filename in targets.items():
            run_dir = _make_run(self.runs_root, run_id)
            try:
                (run_dir / filename).unlink()
                (run_dir / filename).symlink_to(self.runs_root / "meta_target" / filename)
            except OSError:
                self.skipTest("symlinks unsupported")
            self.assertEqual(_request(f"{server.base}/api/runs/{run_id}")[0], 503, run_id)

    def test_metadata_identity_and_schema_are_enforced(self) -> None:
        server = self._server()
        _make_run(self.runs_root, "id_mismatch", manifest_overrides={"run_id": "other"})
        self.assertEqual(_request(f"{server.base}/api/runs/id_mismatch")[0], 503)
        _make_run(self.runs_root, "status_mismatch", status_overrides={"run_id": "other"})
        self.assertEqual(_request(f"{server.base}/api/runs/status_mismatch")[0], 503)
        _make_run(self.runs_root, "bad_schema", manifest_overrides={"schema_version": 2})
        self.assertEqual(_request(f"{server.base}/api/runs/bad_schema")[0], 503)

    def test_missing_run_identity_is_rejected_for_summary_and_download(self) -> None:
        server = self._server()
        for filename in ("manifest.json", "status.json"):
            with self.subTest(filename=filename):
                run_dir = _make_run(self.runs_root, "missing_identity")
                path = run_dir / filename
                document = json.loads(path.read_text(encoding="utf-8"))
                document.pop("run_id")
                path.write_text(json.dumps(document), encoding="utf-8")
                self.assertEqual(_request(f"{server.base}/api/runs/missing_identity")[0], 503)
                self.assertEqual(
                    _request(f"{server.base}/api/runs/missing_identity/artifacts/samples")[0],
                    503,
                )

    def test_missing_status_or_artifacts_is_503_not_success(self) -> None:
        server = self._server()
        _make_run(self.runs_root, "no_status", omit_status=True)
        status, _, body = _request(f"{server.base}/api/runs/no_status")
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body)["error"], "run_unreadable")
        self.assertEqual(_request(f"{server.base}/api/runs/no_status/artifacts/samples")[0], 503)
        _make_run(self.runs_root, "no_artifacts", omit_artifacts=True)
        self.assertEqual(_request(f"{server.base}/api/runs/no_artifacts")[0], 503)

    # ------------------------------------------------------- alias/ids (B)
    def test_blocked_file_alias_symlinks_are_rejected(self) -> None:
        server = self._server()
        run_dir = _make_run(self.runs_root, "alias_run")
        (run_dir / "logs").mkdir(exist_ok=True)
        _write(run_dir / "logs" / "pipeline.jsonl", '{"secret":"pipeline"}\n')
        try:
            (run_dir / "data" / "alias_request.json").symlink_to(run_dir / "request.json")
            (run_dir / "data" / "alias_logs.json").symlink_to(run_dir / "logs" / "pipeline.jsonl")
        except OSError:
            self.skipTest("symlinks unsupported")
        _write(
            run_dir / "artifacts.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "artifacts": [
                        {"artifact_id": "req", "role": "data_provenance", "media_type": "application/json", "relative_path": "data/alias_request.json", "sha256": "2" * 64},
                        {"artifact_id": "logs", "role": "data_provenance", "media_type": "application/json", "relative_path": "data/alias_logs.json", "sha256": "3" * 64},
                    ],
                }
            ),
        )
        status, _, body = _request(f"{server.base}/api/runs/alias_run")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["artifacts"], [])
        text = body.decode("utf-8")
        self.assertNotIn("/srv/secret", text)
        self.assertNotIn("output_dir", text)
        for artifact_id in ("req", "logs"):
            status, _, content = _request(f"{server.base}/api/runs/alias_run/artifacts/{artifact_id}")
            self.assertEqual(status, 404, artifact_id)
            self.assertNotIn(b"secret", content)

    def test_duplicate_and_unsafe_artifact_ids(self) -> None:
        server = self._server()
        _make_run(
            self.runs_root,
            "id_run",
            artifacts=[
                {"artifact_id": "dup", "role": "sample_table", "media_type": "text/csv", "relative_path": "data/samples.csv", "sha256": "4" * 64},
                {"artifact_id": "dup", "role": "sample_table", "media_type": "text/csv", "relative_path": "data/spectra.csv", "sha256": "5" * 64},
                {"artifact_id": "bad%id", "role": "sample_table", "media_type": "text/csv", "relative_path": "data/samples.csv", "sha256": "6" * 64},
                {"artifact_id": "a/b", "role": "sample_table", "media_type": "text/csv", "relative_path": "data/samples.csv", "sha256": "7" * 64},
            ],
        )
        status, _, body = _request(f"{server.base}/api/runs/id_run")
        listed = json.loads(body)["artifacts"]
        self.assertEqual([item["artifact_id"] for item in listed], ["dup"])
        self.assertEqual(listed[0]["url"], "/api/runs/id_run/artifacts/dup")
        self.assertEqual(_request(f"{server.base}/api/runs/id_run/artifacts/dup")[0], 200)
        self.assertEqual(_request(f"{server.base}/api/runs/id_run/artifacts/bad%25id")[0], 404)
        self.assertEqual(_request(f"{server.base}/api/runs/id_run/artifacts/a%2Fb")[0], 404)

    # ------------------------------------------------------- summary/HEAD (C)
    def test_head_artifact_has_headers_without_body(self) -> None:
        server = self._server()
        get_status, get_headers, get_body = _request(f"{server.base}/api/runs/run_one/artifacts/samples")
        head_status, head_headers, head_body = _request(
            f"{server.base}/api/runs/run_one/artifacts/samples", method="HEAD"
        )
        self.assertEqual(head_status, 200)
        self.assertEqual(head_body, b"")
        self.assertEqual(head_headers["Content-Length"], str(len(get_body)))
        self.assertEqual(head_headers["Content-Type"], get_headers["Content-Type"])

    def test_state_flags_and_configuration_hash(self) -> None:
        server = self._server()
        _make_run(self.runs_root, "failed_run", status="failed")
        document = json.loads(_request(f"{server.base}/api/runs/failed_run")[2])
        self.assertTrue(document["complete"])
        self.assertTrue(document["terminal"])
        self.assertFalse(document["succeeded"])
        completed = json.loads(_request(f"{server.base}/api/runs/run_one")[2])
        self.assertTrue(completed["succeeded"])
        self.assertEqual(completed["configuration_hash"], "c" * 64)
        _make_run(self.runs_root, "running_run", status="generating_data")
        running = json.loads(_request(f"{server.base}/api/runs/running_run")[2])
        self.assertFalse(running["complete"])
        self.assertFalse(running["succeeded"])


if __name__ == "__main__":
    unittest.main()
