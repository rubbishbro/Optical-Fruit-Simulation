# Data provenance and dataset contracts

`literature/` contains source metadata and only values that can be traced to a cited table.
`synthetic/` is generated locally and is ignored as scientific evidence. The Golden Delicious demo
is a method demonstration; it is not a calibrated SSC predictor.

The legacy schema v1 long table remains the compatibility format for the synthetic Golden Delicious
workflow and for existing `fruitsim_ml.data.validate_dataset()` callers. It requires optical and IAD
columns in every row because that was the original demonstration contract; it must not be used to
force missing values into real author data.

Experimental data uses schema v2 under [`experimental/`](experimental/). Its canonical tables are:

- `processed/samples.csv`: `dataset_id`, `sample_id`, optional `measurement_id`, apple metadata,
  storage metadata, SSC in degree Brix, firmness in N, thickness and notes;
- `processed/spectra.csv`: `dataset_id`, `sample_id`, optional `measurement_id`, tissue,
  `wavelength_nm`, and any available subset of reflectance, transmittance, `mu_a_mm_inv` and
  `mu_s_prime_mm_inv`.

The v2 manifest records provenance, redistribution restrictions, channel availability and units.
Global IAD settings such as `g` or refractive index are assumptions/settings, not per-sample
experimental observations. They remain null when unknown. No missing channel is filled with zero,
an average, a literature value or an implicit interpolation.

The Hu LWT 2024 directory is only a requested/pending placeholder. It contains no fabricated data.
Use the loader/validator with:

```bash
PYTHONPATH=python python -m fruitsim_ml validate-experimental \
  --input data/experimental/hu_lwt_2024
```

Future author files should be converted with an explicit column mapping and every unit conversion
should be written into manifest provenance before validation. Keep restricted raw files local when
redistribution is not permitted.

The end-to-end data and implementation mapping is documented in
[`docs/TECHNICAL_CHAIN.md`](../docs/TECHNICAL_CHAIN.md).
