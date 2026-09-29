# Work Packages 6/7

## WP6 — C++ Monte Carlo → canonical Run

The adapter in `python/fruitsim_pipeline/physical_run.py` invokes the C++ CLI,
captures its command/stdout/stderr, and packages the result without rewriting
the original C++ files. The canonical Run contains:

- the raw C++ `manifest.json`, `summary.csv`, `instrument.csv`,
  `instrument_regions.csv` and `performance.csv`;
- a sample table explicitly marked `synthetic_physics` with no SSC label;
- a detector spectrum table and pending-label ML input;
- state transitions and artifact SHA-256 entries from the common Run manager.

Example:

```bash
PYTHONPATH=python python -m fruitsim_pipeline simulate-physical \
  --binary build-mesh/apps/fruitsim_cli/fruitsim_cli \
  --config configs/ring_sensor_demo.json \
  --output-root results/runs \
  --run-id physical_ring_demo \
  --photons 256 --seed 20260919 --threads 1 --backend cpu
```

The adapter deliberately does not convert detector response into `ssc_brix`.
That label requires calibration data and remains unavailable in this Run.

## WP7 — end-to-end experiment and QA

`fruitsim-ml visualize-run` now handles both math-synthetic and C++ physical
Runs. Physical Runs produce detector spectrum, detector path statistics and
energy-residual audit figures. Same-seed repeat runs were compared byte-for-byte
for the C++ `summary.csv` and `instrument.csv` outputs.

The current delivered experiment is:

```text
results/runs/wp67_physical_ring_seed20260919
```

It contains six wavelengths, nine validated artifacts and a completed Run
status. The C++ build used for the experiment is the repository-local
`build-mesh` build; the stale historical `build` cache is not used.
