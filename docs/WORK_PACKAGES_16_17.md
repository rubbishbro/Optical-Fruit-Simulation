# Work Packages 16–17 — WebGL feasibility and low-latency protocol

## Scope

The server demo target is Ubuntu 22.04, x86_64, CPU-only, with Docker allowed.
WebGL is the public/student viewer. Qt remains the local engineering and
diagnostics client. Both clients must use the same versioned protocol and Run
artifacts.

## WP16 delivered

- Unity Editor build entry point `Fruitsim.Editor.FruitsimBuild.BuildWebGL`;
- Linux/WebGL build wrapper `scripts/build_fruitsim_unity_webgl.sh`;
- browser WebSocket bridge in `Assets/Scripts/WebGL/`;
- static WebGL server with health endpoint and compressed-asset support in
  `scripts/serve_webgl_demo.py`;
- browser-safe response headers for a same-origin deployment;
- a documented fallback boundary: WebGL is a viewer, while Python/C++ remain
  server-side workers.

The Unity build is intentionally tested separately from the protocol. If a
machine has no valid Unity Editor license, the source and C# reference compile
can still be checked, but a WebGL binary cannot be claimed as built.

## WP17 delivered

- versioned command, acknowledgement, event and Unity payload schemas;
- standard-library protocol message constructors and validation;
- append-only event journal with monotonically increasing sequence numbers;
- replay after `last_seq` for reconnecting clients;
- command-id idempotency so repeated clicks cannot launch duplicate actions;
- latest-value-wins buffer for high-frequency camera/wavelength interaction;
- a small WebSocket gateway with handshake, text frames, ping/pong and replay;
- protocol tests covering journal replay, duplicate commands, stale interaction
  suppression and a real localhost WebSocket flow.

## Protocol boundary

The browser sends commands and receives pushed state. It never opens a native
socket to C++ and never treats a transient frame as the source of truth. Large
arrays and photon paths remain artifacts or bounded binary/sampled payloads;
the first implementation only enables text control/event frames.

Run the protocol tests with:

```bash
PYTHONPATH=python python -m unittest python/tests/test_protocol.py -v
```

Run the gateway demo with:

```bash
PYTHONPATH=python python -m fruitsim_gateway --bind 127.0.0.1 --port 8765
```

Serve a completed Unity WebGL output with:

```bash
python scripts/serve_webgl_demo.py --root apps/fruitsim_unity/build/WebGL
```

The next package must connect the accepted commands to the real Run
Orchestrator and add the browser shell around the Unity canvas. These packages
do not claim that the full WebGL build is available on a machine without the
Unity WebGL module and a valid editor license.
