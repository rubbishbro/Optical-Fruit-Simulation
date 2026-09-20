# File-based Run Viewer

The viewer reads the versioned `Run` directory without importing Python or the
C++ simulator. `FruitsimRunDebugPanel` shows the run identity, state, source,
sample counts, artifacts, backend and synthetic-data warnings. It polls
`status.json`, so a separate pipeline process can be observed while it runs.

The default development path is:

```text
<project-root>/results/runs/wp3_math_demo_seed20260919
```

Set `RunDirectory` from another component or type a different absolute path in
the runtime panel. The panel is intended for the Development Build; the same
scene can be built without changing the data contract for a demo build.

For headless/Linux smoke tests or a fixed demo entry point, pass either:

```bash
FRUITSIM_RUN_DIR=/absolute/path/to/results/runs/<run_id> ./Fruitsim.x86_64
```

or:

```bash
./Fruitsim.x86_64 -fruitsim-run /absolute/path/to/results/runs/<run_id>
```

The panel shows an explicit `Empty`, `Ready`, `RecoverableError` or
`BlockingError` state. It probes the `status.json` file metadata first and only
reloads the full contract when that metadata changes.
