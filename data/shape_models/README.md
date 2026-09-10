# Statistical shape artifacts

Committed or generated statistical apple-shape models use the versioned
`StatisticalFujiShape` JSON schema documented in
[`docs/STATISTICAL_FUJI_SHAPE.md`](../../docs/STATISTICAL_FUJI_SHAPE.md).

`generated/` is ignored because local experiments may use different point-cloud subsets and PCA
settings. A promoted model must record its complete Zenodo provenance, archive checksum, sample list,
coordinate conversion, correspondence parameters and cultivar verification status.

`statistical_fuji_shape_zenodo_v1.json` is the promoted model trained from all 100 point clouds with
2048 common directions and 8 PCA modes. Its Fuji cultivar status remains unverified because the
source record does not state cultivar.
