# Fruitsim Run Contract v1

This document defines the immutable file contract shared by the C++ simulator,
Python analysis pipeline and the canonical Unity viewer in
`apps/fruitsim_unity`.

## Canonical ownership

`apps/fruitsim_unity` is the only Unity application intended for Fruitsim
delivery. `3Dlayzersim/3Dlayzer_unity` remains a migration source and is not a
runtime dependency of the Fruitsim viewer.

## Run directory

Every run is stored under `results/runs/<run_id>/`. The directory contains
`manifest.json`, `status.json`, `artifacts.json` and optional `request.json`.
Large numeric arrays use NPZ in v1; small tables use UTF-8 CSV.

The manifest records the source type, seed, configuration hash, software
versions, backend, coordinate transform, warning state and model status.
Synthetic runs must contain a warning and cannot be marked
`experiment_calibrated`.

## Coordinates and units

Physical artifacts use a right-handed, +Y-up coordinate system and millimetres.
Unity uses metres and receives the explicit `world_to_unity` 4x4 transform from
the manifest. No consumer may apply an additional implicit scale or axis swap.

## Validation

Validate a run with:

```bash
PYTHONPATH=python python -m fruitsim_pipeline validate-run results/runs/<run_id>
```

Validation checks schema version, run identity, state consistency, synthetic
warnings, artifact paths, artifact SHA-256 digests and the required sample
table columns.

The reproducible math demonstration can be generated without Unity:

```bash
PYTHONPATH=python python -m fruitsim_pipeline generate-math \
  --output-root results/runs --run-id math_demo_seed20260819
```

Its target column is `synthetic_ssc_proxy`, deliberately not `ssc_brix`; the
run is suitable for pipeline, visualization and Unity integration experiments,
not for claims about real fruit quality.

This is the first version of the contract. Future incompatible changes must
increment `schema_version`; additive optional fields remain backward compatible.
