from __future__ import annotations

import numpy as np
import pandas as pd


def _pivot(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    return frame.pivot(index="sample_id", columns="wavelength_nm", values=column).sort_index(axis=1)


def build_feature_matrix(frame: pd.DataFrame, feature_set: str):
    mua = _pivot(frame, "mu_a_mm_inv")
    musp = _pivot(frame, "mu_s_prime_mm_inv")
    if feature_set == "mu_a":
        matrix, names = mua, [f"mu_a_{x:g}" for x in mua.columns]
    elif feature_set == "mu_s_prime":
        matrix, names = musp, [f"mu_s_prime_{x:g}" for x in musp.columns]
    elif feature_set == "combined":
        matrix = pd.concat([mua, musp], axis=1)
        names = [f"mu_a_{x:g}" for x in mua.columns] + [f"mu_s_prime_{x:g}" for x in musp.columns]
    elif feature_set == "product":
        matrix = mua * musp
        names = [f"mu_a_x_mu_s_prime_{x:g}" for x in mua.columns]
    elif feature_set == "mu_eff":
        matrix = np.sqrt(3.0 * mua * (mua + musp))
        names = [f"mu_eff_{x:g}" for x in mua.columns]
    elif feature_set == "reflectance":
        matrix = _pivot(frame, "reflectance")
        names = [f"reflectance_{x:g}" for x in matrix.columns]
    elif feature_set == "mc_augmented":
        pieces = [_pivot(frame, column) for column in ("reflectance", "penetration_depth_mm", "radial_decay")]
        matrix = pd.concat(pieces, axis=1)
        names = [f"{column}_{x:g}" for column, piece in zip(
            ("reflectance", "penetration_depth_mm", "radial_decay"), pieces
        ) for x in piece.columns]
    else:
        raise ValueError(f"Unknown feature set: {feature_set}")

    labels = frame.groupby("sample_id", sort=True)["ssc_brix"].first().reindex(matrix.index)
    groups = frame.groupby("sample_id", sort=True)["batch_id"].first().reindex(matrix.index)
    if matrix.isna().any().any() or labels.isna().any():
        raise ValueError("Feature table has missing wavelength or SSC values")
    return matrix.to_numpy(dtype=float), labels.to_numpy(dtype=float), groups.to_numpy(), matrix.index.to_numpy(), names
