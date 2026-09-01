# fruitsim engineering guide

## Product goal

`fruitsim` is a C++17 research platform for steady-state photon transport in strongly scattering
fruit tissue. The first application is a Golden Delicious apple demonstration over 500–1000 nm,
followed by calibration against measured spectra and destructive SSC reference values.

The physics simulator and SSC model are deliberately separate:

```text
optical properties -> ring illumination -> layered Monte Carlo -> surface escape
                   -> detector geometry/NA -> detected spectrum/path statistics
                   -> future experimental calibration and SSC modeling
```

Synthetic data is only a method demonstration. It must never be presented as a calibrated apple
quality model.

The exact code path, file-level implementation map, output semantics and literature/reference
boundaries are maintained in [`docs/TECHNICAL_CHAIN.md`](docs/TECHNICAL_CHAIN.md).

## Current architecture

- `core`: vector/ray primitives and counter-based Philox random streams.
- `geometry`: analytic layered spheres, plus `StatisticalFujiShape`, a mean radial mesh and PCA
  deformation modes learned offline from registered point clouds. The latter is not yet a Monte
  Carlo boundary backend.
- `optics`: validated optical properties, HG scattering, Snell refraction and unpolarized Fresnel.
- `transport`: photon state, deterministic batches, absorption and detector tallies.
- `runtime`: CPU backend with scheduling-independent photon paths and deterministic reduction.
- `io`: versioned JSON input and CSV/JSON output.
- `python/fruitsim_ml`: synthetic data, spectral preprocessing and SSC model comparison.
- `apps`: CLI and optional Dear ImGui/ImPlot research workbench.

All distances use mm, optical coefficients use mm^-1, wavelengths use nm, and SSC uses degree Brix.
`mu_s_prime_mm_inv` is converted using `mu_s=mu_s_prime/(1-g)`. A configuration must provide exactly
one of `mu_s_mm_inv` and `mu_s_prime_mm_inv`.

## Physical model

The scalar Monte Carlo kernel launches a pencil, Gaussian or annular beam, samples optical depth, preserves residual
optical depth across region boundaries, deposits absorption at collisions, samples the
Henyey–Greenstein phase function, applies stochastic Fresnel reflection/refraction, and terminates
low-weight packets with Russian roulette. Results include R/T/A, layer absorption, radial
reflectance, an optional absorption grid, all-photon penetration quantiles, standard errors and sampled tracks.
An optional circular detector filters reflected surface escapes by its physical disk and acceptance cone, and
reports specular/diffuse detected weight, geometry-defined detected depth and generic per-region
detector-weighted path statistics without changing R/T/A.

Polarization, fluorescence, time-of-flight, voxel geometry and tetrahedral meshes are versioned
future transport modes. They must not enlarge the scalar `PhotonState`.

## Data policy

Every optical record carries dataset, cultivar, tissue, wavelength, measurement method, source DOI,
uncertainty and synthetic/experimental status. Missing values are not inferred silently. Values from
different cultivars or measurement methods are not merged and described as one measured fruit.

Reference baselines:

- Cen, Lu and Mendoza, Golden Delicious optical properties and SSC, 500–1000 nm.
- Qin and Lu, Monte Carlo light transport in 600 Golden Delicious apples.
- Qin, Lu and Peng, absorption/reduced-scattering spectra and SSC prediction in 600 Golden
  Delicious apples.
- Askoura, Vaudelle and L'Huillier, two-layer spherical apple Monte Carlo model.

## SSC modeling

The Python package compares MLR, PLSR, RBF-SVR and Random Forest across absorption, reduced
scattering, combined, product, effective attenuation, reflectance and augmented MC feature sets.
Preprocessing is fitted inside each training fold. `paper_compatible` uses a reproducible 75/25
split; `research` holds out complete batches and uses grouped CV.

The model artifact always records its feature schema, wavelength axis, split, metrics and data
status. Only models validated on independent experimental batches may be marked calibrated.

## Validated local environment (updated 2026-08-30)

The workstation has an NVIDIA GeForce RTX 4060 Laptop GPU (compute capability 8.9). Host-side
validation found the following environments:

| Environment | Python | PyTorch CUDA | GPU runtime | `nvcc` | Intended use |
| --- | ---: | ---: | --- | --- | --- |
| `mamba-torch311` | 3.11.15 | 12.4 | verified | absent | Python SSC workflow |
| `mamba-torch38` | 3.8.20 | 12.1 | verified | 13.0.48 | C++/CUDA configure and build |

`mamba-torch38` is not used to install `fruitsim_ml`, because the package requires Python 3.10 or
newer. It is only the source of the CUDA toolkit for the C++ build. The CUDA-enabled project builds,
all CPU/CUDA tests pass, and `fruitsim_cli devices` reports the RTX 4060. The CUDA scalar kernel now
implements source launch, layered boundaries with residual optical depth, absorption, HG scattering,
Fresnel/Snell handling, roulette, R/T/A, radial response, penetration depth, 3D absorption grids and
bounded debug trajectories. Ring launch, circular-detector acceptance and detected path statistics
are implemented on both CPU and CUDA. It uses float photon state, double tallies, bounded photon batches and a
fixed host reduction order for repeatable scalar results.

Some managed or containerized shells hide `/dev/nvidia*`; in that case PyTorch can report
`cuda.is_available() == false` even though the host GPU is working. Confirm from a normal host shell.

## Start and validation commands

Run all commands from the repository root.

### CPU reference simulator

```bash
cmake -S . -B build-cpu \
  -DFRUITSIM_BUILD_TESTS=ON \
  -DFRUITSIM_BUILD_GUI=OFF \
  -DFRUITSIM_ENABLE_CUDA=OFF
cmake --build build-cpu --parallel
ctest --test-dir build-cpu --output-on-failure

./build-cpu/apps/fruitsim_cli/fruitsim_cli validate \
  --config configs/golden_delicious_demo.json
./build-cpu/apps/fruitsim_cli/fruitsim_cli run \
  --config configs/golden_delicious_demo.json \
  --output results/golden_delicious_demo \
  --photons 100000 --threads 8 --seed 20260819 --backend cpu
```

For a quick smoke test, reduce `--photons` to `1000`. Scientific runs must report convergence versus
photon count and should not use the smoke-test count.

### Ring source and central detector

```bash
./build-cpu/apps/fruitsim_cli/fruitsim_cli validate \
  --config configs/ring_sensor_demo.json
./build-cpu/apps/fruitsim_cli/fruitsim_cli run \
  --config configs/ring_sensor_demo.json \
  --output results/ring_sensor_demo \
  --photons 20000 --threads 8 --seed 20260819 --backend cpu

./build-cpu/apps/fruitsim_cli/fruitsim_cli scan-ring \
  --config configs/ring_sensor_demo.json \
  --ring-radii 1,2,3,5,8,10,12,15 \
  --output results/ring_radius_scan \
  --photons 10000 --threads 8 --seed 20260819 --backend cpu
```

The scan writes long-form `ring_scan.csv` plus `ring_scan_manifest.json`. It is a forward parameter
scan only and does not label any radius optimal.

Detector NA is defined in the exterior medium, `NA=n_exterior*sin(theta_max)`; it never uses a tissue
index. The detector axis points from detector to sample, so accepted escape directions lie around
`-axis`. Maximum penetration is `outer_radius-|point-center|` along the path. Entry-surface Fresnel
and post-entry return are emitted separately as specular and diffuse weights. Generic per-region path
statistics are detector-arrival-weighted; skin/flesh fields are compatibility projections by name.

### Python SSC demonstration

```bash
export FRUITSIM_ML_PYTHON=/home/rubbishbro/miniforge3/envs/mamba-torch311/bin/python

env PYTHONNOUSERSITE=1 PYTHONPATH=python "$FRUITSIM_ML_PYTHON" \
  -m fruitsim_ml generate-demo \
  --output data/synthetic/synthetic_golden_delicious_v1.csv \
  --samples 600 --seed 20260819

env PYTHONNOUSERSITE=1 PYTHONPATH=python "$FRUITSIM_ML_PYTHON" \
  -m fruitsim_ml validate-data \
  --input data/synthetic/synthetic_golden_delicious_v1.csv

env PYTHONNOUSERSITE=1 PYTHONPATH=python "$FRUITSIM_ML_PYTHON" \
  -m fruitsim_ml train --config configs/ml_golden_demo.json
```

The full demo evaluates many feature/preprocessing/model combinations and can take several minutes.
Use `configs/ml_smoke_test.json` for a short end-to-end validation. Every generated artifact remains
marked synthetic and is not valid for real apple SSC prediction.

### GUI workbench

```bash
cmake -S . -B build-gui \
  -DFRUITSIM_BUILD_GUI=ON \
  -DFRUITSIM_BUILD_TESTS=ON
cmake --build build-gui --parallel
./build-gui/apps/fruitsim_gui/fruitsim_gui
```

The first configure downloads pinned GUI dependencies. Start the GUI from the repository root so its
default relative config and result paths resolve correctly. Enter the full `mamba-torch311` Python
path in the GUI before launching an ML job.

### CUDA toolchain and device check

```bash
export FRUITSIM_CUDA_ROOT=/home/rubbishbro/miniforge3/envs/mamba-torch38

"$FRUITSIM_CUDA_ROOT/bin/nvcc" --version
env PYTHONNOUSERSITE=1 "$FRUITSIM_CUDA_ROOT/bin/python" -c \
  "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

cmake -S . -B build-cuda \
  -DFRUITSIM_ENABLE_CUDA=ON \
  -DFRUITSIM_BUILD_TESTS=ON \
  -DCMAKE_CUDA_COMPILER="$FRUITSIM_CUDA_ROOT/bin/nvcc" \
  -DCUDAToolkit_ROOT="$FRUITSIM_CUDA_ROOT"
cmake --build build-cuda --parallel
ctest --test-dir build-cuda --output-on-failure
./build-cuda/apps/fruitsim_cli/fruitsim_cli devices

./build-cuda/apps/fruitsim_cli/fruitsim_cli run \
  --config configs/ring_sensor_demo.json \
  --output results/ring_sensor_cuda \
  --photons 2000 --seed 20260819 --backend cuda
```

`ctest` runs a 12,000-photon CPU/GPU statistical comparison when a GPU is visible and reports the
test as skipped otherwise. `summary.csv` includes `boundary_failures` and
`max_event_terminations`; both must remain zero in accepted validation cases. `manifest.json`
records device, compute capability, CUDA driver/runtime/toolkit versions, precision, block size,
boundary nudge and reduction method. The backend is suitable for engineering validation, but the
synthetic apple inputs still prevent real SSC claims.

### Reproducible ring-detector benchmark

Use the single-wavelength smoke/benchmark configuration without assuming a device runtime:

```bash
./build-cuda/apps/fruitsim_cli/fruitsim_cli run --backend cuda \
  --config configs/ring_sensor_benchmark.json --photons 20000 \
  --output results/ring_benchmark_cuda_20k
./build-cuda/apps/fruitsim_cli/fruitsim_cli run --backend cuda \
  --config configs/ring_sensor_benchmark.json --photons 100000 \
  --output results/ring_benchmark_cuda_100k
./build-cuda/apps/fruitsim_cli/fruitsim_cli run --backend cuda \
  --config configs/ring_sensor_benchmark.json --photons 1000000 \
  --output results/ring_benchmark_cuda_1m
```

Repeat with `--backend cpu` and the CPU executable for comparison. `performance.csv` and
`manifest.json` record wavelength count, total photons, elapsed seconds and photons/s.

## Remaining work and improvement priorities

### P0: required before publication-grade GPU results

1. Extend CPU/CUDA equivalence coverage from the current R/T/A, radial and penetration checks to
   multilayer refractive mismatch, Gaussian sources, 3D grid similarity, roulette extremes and
   photon-count convergence with predefined confidence criteria.
2. Add an independent MCML-style reference corpus and analytical Beer-Lambert/Fresnel regression
   tables. The current unit tests cover core cases but are not yet a publication-grade verification
   package.
3. Replace per-photon device-to-host scalar copies with a validated block/device reduction for large
   runs, retain double tally precision and deterministic reduction, overlap batches with CUDA streams,
   and benchmark throughput/memory against the CPU reference.
4. Add CUDA compile-only CI plus a real GPU CI runner. The current hosted CI is CPU-only; in a CUDA
   build the runtime test cleanly skips without a visible GPU, but hosted CI does not yet configure
   that build and therefore cannot detect CUDA compiler, driver or kernel regressions.
5. Resolve the conda CUDA 13 `nvlink` warnings about incompatible sysroot static libraries or provide
   a pinned native CUDA toolchain file; the current executable links and tests successfully, but a
   clean reproducible build is preferable.
6. Replace synthetic optical curves with precisely extracted, citable Golden Delicious skin, flesh
   and core measurements. Keep cultivar, method, units, uncertainty and interpolation provenance;
   never fill missing spectral ranges by unlabelled extrapolation.

### P1: required before real SSC measurement claims

1. Add instrument import for dark/white reference correction, probe geometry, temperature,
   acquisition position, repeated spectra, refractometer SSC, `sample_id` and `batch_id`.
2. Connect sample-specific Monte Carlo detector spectra to ML rows. The current synthetic
   reflectance/augmented features are method-demo proxies, not a validated simulator-to-instrument
   transfer function.
3. Implement batch/orchard/harvest external validation and compare direct literature priors,
   low-sample calibration, residual correction and full experimental retraining. Only an external
   test set can change status to `experiment_calibrated`.
4. Add prediction-time artifact loading with strict checks for schema version, wavelength axis,
   units, feature ordering and supported software versions, plus uncertainty intervals and
   out-of-distribution warnings.
5. Complete GUI task control: JSONL progress parsing, cancellation, logs, result history and cache;
   editable source/detector/tissue parameters; radial plots, heatmaps, penetration plots and sampled
   trajectories; persistent synthetic/experimental provenance on every view.
6. Extend the implemented ring/circular-detector geometry with mechanical occlusion, lens/fiber
   transfer functions, spectrometer response, dark/white correction and physical probe calibration.

### P2: capability and engineering extensions

1. Add measured apple shape, voxel and tetrahedral mesh backends while retaining versioned config
   migration and the analytic layered sphere as the reference geometry.
2. Add multi-GPU scheduling, wavelength/parameter-sweep orchestration, checkpointable batches,
   performance benchmarks and memory/throughput reports.
3. Add time-resolved transport, then a separate `PolarizedPhotonState`/Mueller transport kernel, and
   finally fluorescence. These modes must not increase scalar-photon memory cost.
4. Harden packaging and CI: locked dependency artifacts, CUDA build runners, sanitizers, larger
   numerical regression tests, JSON Schema validation, install/export targets and reproducible model
   environment manifests.

## Roadmap status

1. CPU scalar reference and Golden Delicious synthetic demo — implemented, convergence validation
   still needs expansion.
2. SSC comparison pipeline — implemented for synthetic method demonstrations.
3. GUI result visualization — initial optional workbench implemented; full task control and plots are
   pending.
4. CUDA scalar photon transport — implemented and statistically smoke-tested on RTX 4060; broader
   reference validation, device reduction optimization and GPU CI remain pending.
5. Ring illumination, central circular detector and detected path statistics — implemented on CPU
   and CUDA for simulation-demo geometry; physical probe calibration remains pending.
6. Experimental import, batch-aware calibration and simulation-to-measurement residual correction —
   pending measured data.
7. Voxel/mesh geometry, time-resolved transport, polarization and fluorescence — future work.
