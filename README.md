# fruitsim

`fruitsim` is a modular C++17 Monte Carlo photon-transport platform for fruit optics, with a Python
workflow for comparing SSC regression models. The bundled Golden Delicious configuration is
synthetic and is **not valid for real SSC prediction**.

## Build and test

```bash
cmake -S . -B build -DFRUITSIM_BUILD_TESTS=ON
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

The first configure downloads pinned nlohmann/json 3.12.0. CUDA, the GUI and practice example are
off by default.

## Run the apple simulation

```bash
./build/apps/fruitsim_cli/fruitsim_cli validate \
  --config configs/golden_delicious_demo.json

./build/apps/fruitsim_cli/fruitsim_cli run \
  --config configs/golden_delicious_demo.json \
  --output results/golden_delicious_demo
```

Outputs include `summary.csv`, radial `detectors.csv`, instrument `instrument.csv`, optional
`absorption_grid.csv`, `trajectories.csv` and `manifest.json`. Use `--photons`, `--seed`, `--threads`
and `--backend` for controlled overrides.

## Ring illumination and central sensor

The instrument demo uses a formal annular source, a two-layer flesh/skin sphere and a coaxial
circular detector with an aperture and acceptance cone:

```text
ring illumination -> layered skin/flesh transport -> surface escape
                  -> detector disk/acceptance filtering -> detected spectrum/path statistics
```

```bash
./build/apps/fruitsim_cli/fruitsim_cli run \
  --config configs/ring_sensor_demo.json \
  --output results/ring_sensor_demo --photons 20000 --backend cpu

./build/apps/fruitsim_cli/fruitsim_cli scan-ring \
  --config configs/ring_sensor_demo.json \
  --ring-radii 1,2,3,5,8,10,12,15 \
  --output results/ring_radius_scan --photons 10000 --backend cpu
```

`ring_scan.csv` is long-form in `(ring_radius_mm, wavelength_nm)` for direct `R(lambda, r)` analysis;
`ring_scan_manifest.json` records the seed, photon count, radii and demo assumptions.
`detection_efficiency = detected_weight / launched_photons`; detector collection observes escaped
weight and is never subtracted from R/T/A. Detected penetration/path statistics describe only light
accepted by this instrument geometry and are not interchangeable with all-photon penetration depth.
All bundled instrument dimensions and optical properties are simulation assumptions, not calibrated
hardware data.

## Generate data and compare SSC models

Use an environment containing NumPy, pandas, SciPy, scikit-learn and joblib:

```bash
PYTHONPATH=python python -m fruitsim_ml generate-demo \
  --output data/synthetic/synthetic_golden_delicious_v1.csv \
  --samples 600 --seed 20260819

PYTHONPATH=python python -m fruitsim_ml train \
  --config configs/ml_golden_demo.json
```

Training emits JSONL progress and writes a leaderboard, predictions, split assignments, metrics,
feature schema and serialized pipelines under `results/ml_golden_demo`.

## Optional components

```bash
cmake -S . -B build-gui -DFRUITSIM_BUILD_GUI=ON
cmake --build build-gui --parallel
./build-gui/apps/fruitsim_gui/fruitsim_gui

export FRUITSIM_CUDA_ROOT=/home/rubbishbro/miniforge3/envs/mamba-torch38
cmake -S . -B build-cuda \
  -DFRUITSIM_ENABLE_CUDA=ON \
  -DCMAKE_CUDA_COMPILER="$FRUITSIM_CUDA_ROOT/bin/nvcc" \
  -DCUDAToolkit_ROOT="$FRUITSIM_CUDA_ROOT"
cmake --build build-cuda --parallel
ctest --test-dir build-cuda --output-on-failure
./build-cuda/apps/fruitsim_cli/fruitsim_cli run \
  --config configs/ring_sensor_demo.json \
  --output results/ring_sensor_cuda --photons 2000 --backend cuda
```

The GUI uses pinned Dear ImGui, ImPlot and GLFW sources. The CUDA scalar backend implements the same
layered-sphere photon lifecycle as the CPU reference, uses bounded batches, float propagation state,
double tallies and fixed-order host reduction. CUDA tests are skipped when no device is visible.

See [GUIDE.md](GUIDE.md) for startup commands, architecture, assumptions and roadmap. See
[docs/TECHNICAL_CHAIN.md](docs/TECHNICAL_CHAIN.md) for the current end-to-end chain, source-file
mapping, implementation details and literature/reference boundaries.
