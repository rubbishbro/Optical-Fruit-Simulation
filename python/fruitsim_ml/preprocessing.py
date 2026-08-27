"""Pickle-safe spectral preprocessing functions."""

from __future__ import annotations

import numpy as np
from scipy.signal import savgol_filter


def snv(values: np.ndarray) -> np.ndarray:
    means = values.mean(axis=1, keepdims=True)
    scales = values.std(axis=1, keepdims=True)
    scales[scales == 0.0] = 1.0
    return (values - means) / scales


def savgol_smooth(values: np.ndarray) -> np.ndarray:
    window = nine_or_largest_odd(values.shape[1])
    if window < 5:
        return values.copy()
    return savgol_filter(values, window_length=window, polyorder=2, axis=1)


def savgol_derivative(values: np.ndarray) -> np.ndarray:
    window = nine_or_largest_odd(values.shape[1])
    if window < 5:
        return np.gradient(values, axis=1)
    return savgol_filter(values, window_length=window, polyorder=2, deriv=1, axis=1)


def nine_or_largest_odd(width: int) -> int:
    return min(9, width if width % 2 else width - 1)
