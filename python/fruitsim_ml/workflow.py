"""Typed, stage-constrained ML workflow for Fruitsim.

This module is deliberately independent from the GUI.  Algorithms return
structured objects and intermediate states; renderers may later turn those
states into PNGs, HTML, ImPlot views, or teaching animations.
"""

from __future__ import annotations

import csv
import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
from sklearn.cross_decomposition import PLSRegression
from sklearn.decomposition import PCA
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GroupKFold, KFold
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler
from scipy.signal import savgol_filter


class Stage(str, Enum):
    DATA_INSPECTION = "data_inspection"
    PREPROCESSING = "preprocessing"
    FEATURE_ANALYSIS = "feature_analysis"
    FEATURE_SELECTION = "feature_selection"
    MODELING = "modeling"
    RESULTS = "results"


class DataKind(str, Enum):
    SPECTRUM_SET = "spectrum_set"
    LATENT_FEATURE_SET = "latent_feature_set"
    FEATURE_ANALYSIS = "feature_analysis"
    SELECTED_FEATURE_SET = "selected_feature_set"
    MODEL_RESULT = "model_result"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, np.ndarray):
        return {
            "__ndarray__": value.tolist(),
            "dtype": str(value.dtype),
            "shape": list(value.shape),
        }
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _from_json_value(value: Any) -> Any:
    if isinstance(value, dict) and "__ndarray__" in value:
        return np.asarray(value["__ndarray__"], dtype=value.get("dtype"))
    if isinstance(value, dict):
        return {key: _from_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_from_json_value(item) for item in value]
    return value


def _matrix_shape(matrix: np.ndarray, names: Sequence[str], sample_ids: Sequence[str]) -> None:
    if matrix.ndim != 2:
        raise ValueError("feature matrix must be two-dimensional")
    if matrix.shape[1] != len(names):
        raise ValueError("feature name count does not match matrix width")
    if matrix.shape[0] != len(sample_ids):
        raise ValueError("sample id count does not match matrix height")
    if not np.isfinite(matrix).all():
        raise ValueError("feature matrix contains non-finite values")


@dataclass
class SpectrumSet:
    X: np.ndarray
    wavelengths: np.ndarray
    sample_ids: tuple[str, ...]
    y: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    kind: DataKind = field(default=DataKind.SPECTRUM_SET, init=False)

    def __post_init__(self) -> None:
        self.X = np.asarray(self.X, dtype=float)
        self.wavelengths = np.asarray(self.wavelengths, dtype=float)
        self.sample_ids = tuple(str(item) for item in self.sample_ids)
        if self.X.ndim != 2 or self.X.shape[1] != len(self.wavelengths):
            raise ValueError("SpectrumSet X must have one column per wavelength")
        if self.X.shape[0] != len(self.sample_ids):
            raise ValueError("SpectrumSet X must have one row per sample id")
        if not np.isfinite(self.X).all() or not np.isfinite(self.wavelengths).all():
            raise ValueError("SpectrumSet contains non-finite values")
        if self.y is not None:
            self.y = np.asarray(self.y, dtype=float)
            if self.y.shape != (self.X.shape[0],):
                raise ValueError("SpectrumSet y must have one value per sample")
        self.metadata = dict(self.metadata)

    @property
    def feature_names(self) -> tuple[str, ...]:
        return tuple(f"wavelength_{value:g}nm" for value in self.wavelengths)

    def copy(self, X: np.ndarray | None = None, **metadata: Any) -> "SpectrumSet":
        merged = dict(self.metadata)
        merged.update(metadata)
        return SpectrumSet(
            self.X.copy() if X is None else np.asarray(X),
            self.wavelengths.copy(),
            self.sample_ids,
            None if self.y is None else self.y.copy(),
            merged,
        )

    @property
    def computational_metadata(self) -> dict[str, Any]:
        """Metadata that is allowed to affect numerical execution and caching.

        ``metadata["display"]`` is deliberately excluded.  Existing top-level
        fields remain computational for backward compatibility, while new
        callers should put presentation-only labels under ``display``.
        """
        return {key: value for key, value in self.metadata.items() if key != "display"}

    @property
    def display_metadata(self) -> dict[str, Any]:
        value = self.metadata.get("display", {})
        return dict(value) if isinstance(value, Mapping) else {}


@dataclass
class LatentFeatureSet:
    X: np.ndarray
    feature_names: tuple[str, ...]
    sample_ids: tuple[str, ...]
    y: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    loadings: np.ndarray | None = None

    kind: DataKind = field(default=DataKind.LATENT_FEATURE_SET, init=False)

    def __post_init__(self) -> None:
        self.X = np.asarray(self.X, dtype=float)
        self.feature_names = tuple(str(item) for item in self.feature_names)
        self.sample_ids = tuple(str(item) for item in self.sample_ids)
        _matrix_shape(self.X, self.feature_names, self.sample_ids)
        if self.y is not None:
            self.y = np.asarray(self.y, dtype=float)
            if self.y.shape != (self.X.shape[0],):
                raise ValueError("LatentFeatureSet y must have one value per sample")
        if self.loadings is not None:
            self.loadings = np.asarray(self.loadings, dtype=float)
        self.metadata = dict(self.metadata)


@dataclass
class SelectedFeatureSet:
    X: np.ndarray
    feature_names: tuple[str, ...]
    selected_indices: np.ndarray
    sample_ids: tuple[str, ...]
    y: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    kind: DataKind = field(default=DataKind.SELECTED_FEATURE_SET, init=False)

    def __post_init__(self) -> None:
        self.X = np.asarray(self.X, dtype=float)
        self.feature_names = tuple(str(item) for item in self.feature_names)
        self.selected_indices = np.asarray(self.selected_indices, dtype=int)
        self.sample_ids = tuple(str(item) for item in self.sample_ids)
        _matrix_shape(self.X, self.feature_names, self.sample_ids)
        if len(self.selected_indices) != self.X.shape[1]:
            raise ValueError("selected_indices must match selected matrix width")
        if self.y is not None:
            self.y = np.asarray(self.y, dtype=float)
            if self.y.shape != (self.X.shape[0],):
                raise ValueError("SelectedFeatureSet y must have one value per sample")
        self.metadata = dict(self.metadata)


@dataclass
class FeatureAnalysisResult:
    method_id: str
    source: SpectrumSet | LatentFeatureSet
    feature_names: tuple[str, ...]
    selected_indices: np.ndarray | None = None
    scores: np.ndarray | None = None
    loadings: np.ndarray | None = None
    statistics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    kind: DataKind = field(default=DataKind.FEATURE_ANALYSIS, init=False)

    def __post_init__(self) -> None:
        self.feature_names = tuple(str(item) for item in self.feature_names)
        if self.selected_indices is not None:
            self.selected_indices = np.asarray(self.selected_indices, dtype=int)
        if self.scores is not None:
            self.scores = np.asarray(self.scores, dtype=float)
        if self.loadings is not None:
            self.loadings = np.asarray(self.loadings, dtype=float)
        self.statistics = dict(self.statistics)
        self.metadata = dict(self.metadata)


@dataclass
class PredictionSet:
    sample_ids: tuple[str, ...]
    y_true: np.ndarray
    y_pred: np.ndarray
    residuals: np.ndarray
    split: tuple[str, ...]
    fold_ids: tuple[int, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.sample_ids = tuple(str(item) for item in self.sample_ids)
        self.y_true = np.asarray(self.y_true, dtype=float)
        self.y_pred = np.asarray(self.y_pred, dtype=float)
        self.residuals = np.asarray(self.residuals, dtype=float)
        self.split = tuple(str(item) for item in self.split)
        if not (len(self.sample_ids) == len(self.y_true) == len(self.y_pred) == len(self.residuals) == len(self.split)):
            raise ValueError("PredictionSet columns must have equal length")
        if not self.fold_ids:
            self.fold_ids = tuple(-1 for _ in self.sample_ids)
        if len(self.fold_ids) != len(self.sample_ids):
            raise ValueError("fold_ids must match prediction rows")
        self.metadata = dict(self.metadata)

    def view(self, split_name: str) -> "PredictionSet":
        indices = np.asarray([index for index, name in enumerate(self.split) if name == split_name], dtype=int)
        return PredictionSet(
            tuple(self.sample_ids[index] for index in indices),
            self.y_true[indices],
            self.y_pred[indices],
            self.residuals[indices],
            tuple(self.split[index] for index in indices),
            tuple(self.fold_ids[index] for index in indices),
            {**self.metadata, "view_split": split_name},
        )

    def calibration_view(self) -> "PredictionSet":
        return self.view("calibration")

    def validation_view(self) -> "PredictionSet":
        return self.view("validation")


@dataclass
class EvaluationResult:
    rmse: float
    mae: float
    r2: float
    sample_count: int
    feature_count: int
    cv_rmse: float | None = None
    bias: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _json_value({
            "rmse": self.rmse,
            "mae": self.mae,
            "r2": self.r2,
            "sample_count": self.sample_count,
            "feature_count": self.feature_count,
            "cv_rmse": self.cv_rmse,
            "bias": self.bias,
            "metadata": self.metadata,
        })


@dataclass
class ModelResult:
    method_id: str
    predictions: PredictionSet
    evaluation: EvaluationResult
    model_metadata: dict[str, Any] = field(default_factory=dict)

    kind: DataKind = field(default=DataKind.MODEL_RESULT, init=False)


@dataclass
class IntermediateState:
    name: str
    kind: str
    event: str
    arrays: dict[str, np.ndarray] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _json_value({
            "name": self.name,
            "kind": self.kind,
            "event": self.event,
            "arrays": self.arrays,
            "values": self.values,
        })

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "IntermediateState":
        return cls(
            str(document["name"]),
            str(document["kind"]),
            str(document["event"]),
            {key: _from_json_value(value) for key, value in document.get("arrays", {}).items()},
            _from_json_value(document.get("values", {})),
        )


@dataclass
class MethodExecutionResult:
    output: Any
    metrics: dict[str, Any] = field(default_factory=dict)
    intermediate_states: list[IntermediateState] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


MethodExecutor = Callable[[Any, Mapping[str, Any], int], MethodExecutionResult]
ParameterValidator = Callable[[Mapping[str, Any]], None]


@dataclass(frozen=True)
class ParameterDefinition:
    default: Any
    value_type: type | tuple[type, ...]
    minimum: float | None = None
    maximum: float | None = None

    def validate(self, name: str, value: Any) -> Any:
        # bool is an int subclass but is never a useful numerical method value.
        if isinstance(value, bool) or not isinstance(value, self.value_type):
            expected = self.value_type if isinstance(self.value_type, tuple) else (self.value_type,)
            names = "/".join(item.__name__ for item in expected)
            raise ValueError(f"parameter {name} must be {names}")
        if self.minimum is not None and value < self.minimum:
            raise ValueError(f"parameter {name} must be >= {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise ValueError(f"parameter {name} must be <= {self.maximum}")
        return value


@dataclass(frozen=True)
class MethodSpec:
    method_id: str
    parameters: dict[str, Any] = field(default_factory=dict)
    resolved_parameters: dict[str, Any] = field(default_factory=dict)
    invocation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "method_id", str(self.method_id))
        object.__setattr__(self, "parameters", copy.deepcopy(dict(self.parameters)))
        object.__setattr__(self, "resolved_parameters", copy.deepcopy(dict(self.resolved_parameters)))
        invocation_id = self.method_id if self.invocation_id is None else str(self.invocation_id)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", invocation_id):
            raise ValueError(
                "invocation_id must start with an alphanumeric character and contain only "
                "letters, numbers, '.', '_' or '-'"
            )
        object.__setattr__(self, "invocation_id", invocation_id)

    @property
    def node_id(self) -> str:
        """Graph/UI alias for the stable invocation identity."""
        return str(self.invocation_id)

    def computational_dict(self) -> dict[str, Any]:
        """Return fields that affect output, excluding graph-node identity."""
        return {
            "method_id": self.method_id,
            "parameters": _json_value(self.parameters),
            "resolved_parameters": _json_value(self.resolved_parameters),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_id": self.method_id,
            "invocation_id": self.invocation_id,
            "parameters": _json_value(self.parameters),
            "resolved_parameters": _json_value(self.resolved_parameters),
        }

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "MethodSpec":
        return cls(
            str(document["method_id"]),
            _from_json_value(document.get("parameters", {})),
            _from_json_value(document.get("resolved_parameters", {})),
            document.get("invocation_id", document.get("node_id")),
        )


def _method_spec(value: str | MethodSpec | Mapping[str, Any]) -> MethodSpec:
    if isinstance(value, MethodSpec):
        return value
    if isinstance(value, str):
        return MethodSpec(value)
    if isinstance(value, Mapping):
        return MethodSpec.from_dict(value)
    raise TypeError(f"invalid method specification: {type(value).__name__}")


@dataclass(frozen=True)
class FeatureSelectionSpec:
    method: MethodSpec = field(default_factory=lambda: MethodSpec("cars.select"))
    source_invocation_id: str = "cars"

    def __post_init__(self) -> None:
        object.__setattr__(self, "method", _method_spec(self.method))
        object.__setattr__(self, "source_invocation_id", str(self.source_invocation_id))

    @property
    def source_analysis_id(self) -> str:
        """Backward-compatible alias; the value now identifies an invocation."""
        return self.source_invocation_id

    def to_dict(self) -> dict[str, Any]:
        return {"method": self.method.to_dict(), "source_invocation_id": self.source_invocation_id}

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "FeatureSelectionSpec":
        source = document.get("source_invocation_id", document.get("source_analysis_id"))
        if source is None:
            raise ValueError("feature selection requires source_invocation_id")
        return cls(_method_spec(document["method"]), str(source))


@dataclass
class Method:
    id: str
    name: str
    stage: Stage
    input_type: DataKind
    output_type: DataKind
    parameter_schema: dict[str, ParameterDefinition]
    execute: MethodExecutor
    metadata: dict[str, Any] = field(default_factory=dict)
    runtime_parameters: tuple[str, ...] = ()
    seed_sensitive: bool = False
    parameter_validator: ParameterValidator | None = None

    def resolve_parameters(
        self,
        explicit: Mapping[str, Any],
        runtime: Mapping[str, Any] | None = None,
        saved_resolved: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        unknown = set(explicit) - set(self.parameter_schema)
        if unknown:
            raise ValueError(f"unknown parameters for {self.id}: {sorted(unknown)}")
        resolved = {name: copy.deepcopy(rule.default) for name, rule in self.parameter_schema.items()}
        if saved_resolved:
            saved_user = {key: value for key, value in saved_resolved.items() if key in self.parameter_schema}
            resolved.update(copy.deepcopy(saved_user))
        resolved.update(copy.deepcopy(dict(explicit)))
        for name, rule in self.parameter_schema.items():
            resolved[name] = rule.validate(name, resolved[name])
        runtime = dict(runtime or {})
        disallowed_runtime = set(runtime) - set(self.runtime_parameters)
        if disallowed_runtime:
            raise ValueError(f"runtime parameters not accepted by {self.id}: {sorted(disallowed_runtime)}")
        resolved.update(copy.deepcopy(runtime))
        if self.parameter_validator is not None:
            self.parameter_validator(resolved)
        return resolved


class MethodRegistry:
    def __init__(self) -> None:
        self._methods: dict[str, Method] = {}

    def register(self, method: Method) -> None:
        if method.id in self._methods:
            raise ValueError(f"method already registered: {method.id}")
        self._methods[method.id] = method

    def get(self, method_id: str) -> Method:
        try:
            return self._methods[method_id]
        except KeyError as exc:
            raise ValueError(f"unknown method: {method_id}") from exc

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._methods))


def _copy_spectrum(values: SpectrumSet, *, method_id: str, X: np.ndarray | None = None) -> SpectrumSet:
    return values.copy(
        X=X,
        preprocessing_chain=[*values.metadata.get("preprocessing_chain", []), method_id],
    )


def _fit_indices(parameters: Mapping[str, Any], count: int) -> np.ndarray:
    indices = np.asarray(parameters.get("fit_indices", np.arange(count)), dtype=int)
    if indices.ndim != 1 or len(indices) == 0 or np.any(indices < 0) or np.any(indices >= count):
        raise ValueError("fit_indices must contain valid non-empty row indices")
    return indices


def _validation_indices(parameters: Mapping[str, Any], count: int, fit: np.ndarray) -> np.ndarray:
    indices = np.asarray(parameters.get("validation_indices", np.setdiff1d(np.arange(count), fit)), dtype=int)
    if indices.ndim != 1 or len(indices) == 0 or np.any(indices < 0) or np.any(indices >= count):
        raise ValueError("validation_indices must contain valid non-empty row indices")
    overlap = np.intersect1d(fit, indices)
    if len(overlap):
        raise ValueError("fit_indices and validation_indices must be disjoint")
    return indices


def _raw(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, SpectrumSet):
        raise TypeError("Raw expects SpectrumSet")
    output = _copy_spectrum(values, method_id="raw")
    return MethodExecutionResult(
        output,
        metrics={"sample_count": len(output.sample_ids), "feature_count": output.X.shape[1]},
        intermediate_states=[IntermediateState("raw", "spectrum", "morph_curve", {"spectrum": output.X.copy()})],
    )


def _snv(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, SpectrumSet):
        raise TypeError("SNV expects SpectrumSet")
    means = values.X.mean(axis=1, keepdims=True)
    scales = values.X.std(axis=1, keepdims=True)
    scales[scales == 0.0] = 1.0
    normalized = (values.X - means) / scales
    output = _copy_spectrum(values, X=normalized, method_id="snv")
    return MethodExecutionResult(
        output,
        metrics={"mean_before": float(np.mean(means)), "std_before": float(np.mean(scales))},
        intermediate_states=[IntermediateState(
            "snv_normalization", "spectrum", "show_formula",
            {"raw": values.X.copy(), "sample_mean": means.reshape(-1), "sample_std": scales.reshape(-1), "normalized": normalized.copy()},
            {"formula": "(x - mean(x)) / std(x)"},
        )],
    )


def _savgol(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, SpectrumSet):
        raise TypeError("Savitzky-Golay expects SpectrumSet")
    requested = int(parameters.get("window_length", 9))
    if requested > values.X.shape[1]:
        raise ValueError("Savitzky-Golay window_length exceeds feature count")
    window = requested
    polyorder = int(parameters.get("polyorder", 2))
    smoothed = savgol_filter(values.X, window_length=window, polyorder=polyorder, axis=1)
    output = _copy_spectrum(values, X=smoothed, method_id="savgol")
    return MethodExecutionResult(
        output,
        metrics={"window_length": window, "polyorder": polyorder},
        intermediate_states=[IntermediateState(
            "savgol_smoothing", "spectrum", "morph_curve",
            {"raw": values.X.copy(), "smoothed": smoothed.copy()},
            {"window_length": window, "polyorder": polyorder},
        )],
    )


def _pca(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, SpectrumSet):
        raise TypeError("PCA expects SpectrumSet")
    fit = _fit_indices(parameters, values.X.shape[0])
    n_components = max(1, min(
        int(parameters.get("n_components", 3)),
        values.X.shape[1],
        len(fit),
    ))
    center = StandardScaler(with_std=False)
    centered_fit = center.fit_transform(values.X[fit])
    centered_all = center.transform(values.X)
    model = PCA(n_components=n_components, random_state=seed)
    model.fit(centered_fit)
    scores = model.transform(centered_all)
    names = tuple(f"PC{index + 1}" for index in range(n_components))
    output = LatentFeatureSet(scores, names, values.sample_ids, values.y, dict(values.metadata), model.components_.T)
    output.metadata.update({"source_method": "pca", "fit_indices": fit.tolist()})
    analysis = FeatureAnalysisResult(
        "pca", output, names, scores=scores, loadings=model.components_.T,
        statistics={"explained_variance_ratio": model.explained_variance_ratio_.tolist()},
        metadata={"fit_indices": fit.tolist(), "source_feature_count": values.X.shape[1]},
    )
    return MethodExecutionResult(
        analysis,
        metrics={"component_count": n_components, "explained_variance": float(np.sum(model.explained_variance_ratio_))},
        intermediate_states=[IntermediateState(
            "pca_projection", "latent_features", "project_points",
            {"centered_X": centered_all.copy(), "scores": scores.copy(), "loadings": model.components_.T.copy()},
            {"explained_variance_ratio": model.explained_variance_ratio_.tolist()},
        )],
    )


def _splitter(X: np.ndarray, groups: np.ndarray | None, seed: int) -> Iterable[tuple[np.ndarray, np.ndarray]]:
    if groups is not None and len(np.unique(groups)) >= 2:
        splitter = GroupKFold(n_splits=min(5, len(np.unique(groups))))
        yield from splitter.split(X, groups=groups)
    else:
        splitter = KFold(n_splits=min(5, len(X)), shuffle=True, random_state=seed)
        yield from splitter.split(X)


def _safe_pls_components(features: int, samples: int, requested: int) -> int:
    return max(1, min(int(requested), features, max(1, samples - 1)))


def _validate_savgol_parameters(parameters: Mapping[str, Any]) -> None:
    window = int(parameters["window_length"])
    polyorder = int(parameters["polyorder"])
    if window % 2 == 0:
        raise ValueError("parameter window_length must be odd")
    if polyorder >= window:
        raise ValueError("parameter polyorder must be smaller than window_length")


def _validate_cars_parameters(parameters: Mapping[str, Any]) -> None:
    if not 0.0 < float(parameters["decay"]) <= 1.0:
        raise ValueError("parameter decay must be in (0, 1]")


def _cars(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, SpectrumSet):
        raise TypeError("CARS analysis expects SpectrumSet")
    fit = _fit_indices(parameters, values.X.shape[0])
    X_fit = values.X[fit]
    y_fit = values.y[fit] if values.y is not None else None
    if y_fit is None:
        raise ValueError("CARS requires a target y")
    iterations = max(1, int(parameters.get("iterations", 6)))
    min_features = max(1, min(int(parameters.get("min_features", 8)), values.X.shape[1]))
    decay = float(parameters.get("decay", 0.72))
    current = np.arange(values.X.shape[1], dtype=int)
    best_indices = current.copy()
    best_rmse = float("inf")
    states: list[IntermediateState] = []
    progression: list[float] = []
    rng = np.random.default_rng(seed)
    groups = values.metadata.get("groups")
    group_fit = None if groups is None else np.asarray(groups)[fit]
    for iteration in range(iterations):
        components = _safe_pls_components(len(current), len(fit), int(parameters.get("pls_components", 5)))
        model = PLSRegression(n_components=components, scale=True, max_iter=1000)
        fold_predictions = np.empty(len(fit), dtype=float)
        for train_fold, valid_fold in _splitter(X_fit[:, current], group_fit, seed + iteration):
            fold_model = PLSRegression(n_components=_safe_pls_components(len(current), len(train_fold), components), scale=True, max_iter=1000)
            fold_model.fit(X_fit[train_fold][:, :], y_fit[train_fold])
            fold_predictions[valid_fold] = np.asarray(fold_model.predict(X_fit[valid_fold][:, :])).reshape(-1)
        # This coefficient ranking is fitted on the complete calibration set,
        # while fold predictions evaluate the already-chosen reduced matrix.
        # Therefore RMSECV is an internal selection heuristic, not an unbiased
        # nested-CV estimate of the full CARS selection procedure.
        ranking_count = min(len(fit), max(2, int(np.ceil(len(fit) * 0.8))))
        ranking_rows = np.sort(rng.choice(len(fit), size=ranking_count, replace=False))
        model.fit(X_fit[ranking_rows][:, current], y_fit[ranking_rows])
        coefficients = np.abs(np.asarray(model.coef_).reshape(-1))
        rmsecv = float(np.sqrt(mean_squared_error(y_fit, fold_predictions)))
        progression.append(rmsecv)
        if rmsecv <= best_rmse:
            best_rmse = rmsecv
            best_indices = current.copy()
        if len(current) <= min_features:
            retained = current.copy()
        else:
            retained_count = max(min_features, int(np.ceil(len(current) * decay)))
            ranking = np.argsort(-coefficients, kind="stable")
            retained = np.sort(current[ranking[:retained_count]])
        states.append(IntermediateState(
            f"cars_iteration_{iteration + 1}", "feature_selection", "remove_features",
            {
                # ``coefficients[j]`` is fitted for ``current_indices[j]``.
                # Keeping both arrays makes this identity explicit after a
                # non-prefix feature removal.
                "current_indices": current.copy(),
                "retained_indices": retained.copy(),
                "coefficients": coefficients.copy(),
            },
            {
                "iteration": iteration + 1,
                "rmsecv": rmsecv,
                "feature_count": len(retained),
                "ranking_fit_indices": fit[ranking_rows].tolist(),
            },
        ))
        current = retained
        if len(current) <= min_features:
            break
    analysis = FeatureAnalysisResult(
        "cars", values, values.feature_names, selected_indices=best_indices,
        statistics={"rmsecv_progression": progression, "best_rmsecv": best_rmse},
        metadata={
            "fit_indices": fit.tolist(),
            "iterations": len(states),
            "min_features": min_features,
            "rmsecv_semantics": "internal_selection_heuristic_not_nested_cv",
        },
    )
    return MethodExecutionResult(
        analysis,
        metrics={"selected_features": int(len(best_indices)), "best_rmsecv": best_rmse},
        intermediate_states=states,
    )


def _cars_select(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, FeatureAnalysisResult) or values.method_id != "cars":
        raise TypeError("CARS selection expects a CARS FeatureAnalysisResult")
    if values.selected_indices is None:
        raise ValueError("CARS analysis did not provide selected indices")
    source = values.source
    indices = values.selected_indices
    if isinstance(source, SpectrumSet):
        names = tuple(source.feature_names[index] for index in indices)
        output = SelectedFeatureSet(source.X[:, indices], names, indices, source.sample_ids, source.y, dict(source.metadata))
    elif isinstance(source, LatentFeatureSet):
        names = tuple(source.feature_names[index] for index in indices)
        output = SelectedFeatureSet(source.X[:, indices], names, indices, source.sample_ids, source.y, dict(source.metadata))
    else:
        raise TypeError("unsupported CARS source type")
    output.metadata.update({"selection_method": "cars", "selection_statistics": values.statistics})
    return MethodExecutionResult(
        output,
        metrics={"original_features": len(values.feature_names), "selected_features": len(indices)},
        intermediate_states=[IntermediateState(
            "selected_wavelengths", "feature_selection", "select_features",
            {"selected_indices": indices.copy()},
            {"selected_feature_names": list(output.feature_names)},
        )],
    )


def _plsr(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, SelectedFeatureSet):
        raise TypeError("PLSR expects SelectedFeatureSet")
    if values.y is None:
        raise ValueError("PLSR requires a target y")
    fit = _fit_indices(parameters, values.X.shape[0])
    validation = _validation_indices(parameters, len(values.sample_ids), fit)
    components = _safe_pls_components(values.X.shape[1], len(fit), int(parameters.get("n_components", 5)))
    model = PLSRegression(n_components=components, scale=True, max_iter=1000)
    model.fit(values.X[fit], values.y[fit])
    prediction = np.asarray(model.predict(values.X)).reshape(-1)
    split = np.asarray(["unused"] * len(values.sample_ids), dtype=object)
    split[fit] = "calibration"
    split[validation] = "validation"
    residual = prediction - values.y
    validation_prediction = prediction[validation]
    validation_y = values.y[validation]
    evaluation = EvaluationResult(
        rmse=float(np.sqrt(mean_squared_error(validation_y, validation_prediction))),
        mae=float(mean_absolute_error(validation_y, validation_prediction)),
        r2=float(r2_score(validation_y, validation_prediction)) if len(validation) > 1 else 0.0,
        sample_count=int(len(validation)),
        feature_count=int(values.X.shape[1]),
        bias=float(np.mean(validation_prediction - validation_y)),
        metadata={"split": "validation", "fit_sample_count": int(len(fit))},
    )
    cv_scores: list[float] = []
    groups = values.metadata.get("groups")
    group_fit = None if groups is None else np.asarray(groups)[fit]
    for train_fold, valid_fold in _splitter(values.X[fit], group_fit, seed):
        fold_model = PLSRegression(n_components=_safe_pls_components(values.X.shape[1], len(train_fold), components), scale=True, max_iter=1000)
        fold_model.fit(values.X[fit][train_fold], values.y[fit][train_fold])
        fold_prediction = np.asarray(fold_model.predict(values.X[fit][valid_fold])).reshape(-1)
        cv_scores.append(float(np.sqrt(mean_squared_error(values.y[fit][valid_fold], fold_prediction))))
    evaluation.cv_rmse = float(np.mean(cv_scores)) if cv_scores else None
    predictions = PredictionSet(
        values.sample_ids, values.y, prediction, residual, tuple(split),
        metadata={"model": "PLSR", "validation_indices": validation.tolist()},
    )
    x_scores_all = np.asarray(model.transform(values.X))
    x_scores_calibration = x_scores_all[fit]
    coefficient_source_indices = np.asarray(values.selected_indices, dtype=int)
    score_sample_ids_all = tuple(values.sample_ids)
    calibration_sample_ids = tuple(values.sample_ids[index] for index in fit)
    return MethodExecutionResult(
        ModelResult(
            "plsr", predictions, evaluation,
            {
                "n_components": components,
                "coefficients": np.asarray(model.coef_).reshape(-1),
                "coefficient_source_indices": coefficient_source_indices.copy(),
                "x_scores_all": x_scores_all.copy(),
                "x_scores_calibration": x_scores_calibration.copy(),
                "x_score_sample_ids_all": score_sample_ids_all,
                "calibration_sample_ids": calibration_sample_ids,
                "fit_indices": fit.copy(),
                "validation_indices": validation.copy(),
            },
        ),
        metrics=evaluation.to_dict(),
        intermediate_states=[IntermediateState(
            "plsr_fit", "model", "connect_feature_to_prediction",
            {
                "scores": x_scores_all.copy(),
                "scores_calibration": x_scores_calibration.copy(),
                "coefficients": np.asarray(model.coef_).reshape(-1),
                "coefficient_source_indices": coefficient_source_indices.copy(),
                "predictions": prediction.copy(),
                "residuals": residual.copy(),
            },
            {
                "n_components": components,
                "scores_sample_ids": list(score_sample_ids_all),
                "calibration_sample_ids": list(calibration_sample_ids),
                "fit_indices": fit.tolist(),
                "validation_indices": validation.tolist(),
            },
        )],
    )


def evaluate_predictions(predictions: PredictionSet, feature_count: int, cv_rmse: float | None = None) -> EvaluationResult:
    if len(predictions.sample_ids) == 0:
        raise ValueError("cannot evaluate an empty PredictionSet")
    return EvaluationResult(
        rmse=float(np.sqrt(mean_squared_error(predictions.y_true, predictions.y_pred))),
        mae=float(mean_absolute_error(predictions.y_true, predictions.y_pred)),
        r2=float(r2_score(predictions.y_true, predictions.y_pred)) if len(predictions.sample_ids) > 1 else 0.0,
        sample_count=len(predictions.sample_ids),
        feature_count=int(feature_count),
        cv_rmse=cv_rmse,
        bias=float(np.mean(predictions.y_pred - predictions.y_true)),
        metadata={"split": predictions.metadata.get("view_split", "all")},
    )


def _inspect(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, SpectrumSet):
        raise TypeError("Data inspection expects SpectrumSet")
    groups = values.metadata.get("groups", [])
    statistics = {
        "sample_count": len(values.sample_ids),
        "feature_count": int(values.X.shape[1]),
        "wavelength_min_nm": float(values.wavelengths.min()),
        "wavelength_max_nm": float(values.wavelengths.max()),
        "group_count": int(len(set(groups))) if len(groups) else 0,
        "has_target": values.y is not None,
    }
    return MethodExecutionResult(values, metrics=statistics, intermediate_states=[IntermediateState(
        "dataset_snapshot", "data", "highlight_sample", {"spectrum": values.X.copy()}, statistics,
    )])


def _summarize_results(values: Any, parameters: Mapping[str, Any], seed: int) -> MethodExecutionResult:
    if not isinstance(values, ModelResult):
        raise TypeError("Results summary expects ModelResult")
    validation = values.predictions.validation_view()
    summary = evaluate_predictions(validation, values.evaluation.feature_count, values.evaluation.cv_rmse)
    summary.metadata.update(values.evaluation.metadata)
    summary.metadata["split"] = "validation"
    return MethodExecutionResult(
        values,
        metrics=summary.to_dict(),
        intermediate_states=[IntermediateState(
            "experiment_summary", "results", "show_residual",
            {"y_true": validation.y_true.copy(), "y_pred": validation.y_pred.copy(), "residuals": validation.residuals.copy()},
            {**summary.to_dict(), "default_prediction_view": "validation"},
        )],
    )


def build_default_registry() -> MethodRegistry:
    registry = MethodRegistry()
    registry.register(Method("data.inspect", "Data Inspection", Stage.DATA_INSPECTION, DataKind.SPECTRUM_SET, DataKind.SPECTRUM_SET, {}, _inspect))
    registry.register(Method("raw", "Raw passthrough", Stage.PREPROCESSING, DataKind.SPECTRUM_SET, DataKind.SPECTRUM_SET, {}, _raw))
    registry.register(Method("snv", "SNV", Stage.PREPROCESSING, DataKind.SPECTRUM_SET, DataKind.SPECTRUM_SET, {}, _snv))
    registry.register(Method(
        "savgol", "Savitzky–Golay", Stage.PREPROCESSING, DataKind.SPECTRUM_SET, DataKind.SPECTRUM_SET,
        {"window_length": ParameterDefinition(9, int, 3), "polyorder": ParameterDefinition(2, int, 0)},
        _savgol, parameter_validator=_validate_savgol_parameters,
    ))
    registry.register(Method(
        "pca", "PCA", Stage.FEATURE_ANALYSIS, DataKind.SPECTRUM_SET, DataKind.FEATURE_ANALYSIS,
        {"n_components": ParameterDefinition(3, int, 1)}, _pca,
        runtime_parameters=("fit_indices",),
    ))
    registry.register(Method(
        "cars", "CARS stability analysis", Stage.FEATURE_ANALYSIS, DataKind.SPECTRUM_SET, DataKind.FEATURE_ANALYSIS,
        {
            "iterations": ParameterDefinition(6, int, 1),
            "min_features": ParameterDefinition(8, int, 1),
            "decay": ParameterDefinition(0.72, (int, float)),
            "pls_components": ParameterDefinition(5, int, 1),
        },
        _cars,
        metadata={"metric_semantics": "internal_selection_heuristic_not_nested_cv"},
        runtime_parameters=("fit_indices",), seed_sensitive=True,
        parameter_validator=_validate_cars_parameters,
    ))
    registry.register(Method(
        "cars.select", "CARS selected wavelengths", Stage.FEATURE_SELECTION, DataKind.FEATURE_ANALYSIS, DataKind.SELECTED_FEATURE_SET,
        {}, _cars_select, metadata={"accepted_analysis_ids": ["cars"]},
    ))
    registry.register(Method(
        "plsr", "PLSR", Stage.MODELING, DataKind.SELECTED_FEATURE_SET, DataKind.MODEL_RESULT,
        {"n_components": ParameterDefinition(5, int, 1)}, _plsr,
        runtime_parameters=("fit_indices", "validation_indices"), seed_sensitive=True,
    ))
    registry.register(Method("results.summarize", "Experiment results summary", Stage.RESULTS, DataKind.MODEL_RESULT, DataKind.MODEL_RESULT, {}, _summarize_results))
    return registry


@dataclass(frozen=True)
class PipelineDefinition:
    preprocessing: tuple[MethodSpec, ...] = field(default_factory=lambda: (MethodSpec("snv"),))
    feature_analysis: tuple[MethodSpec, ...] = field(default_factory=lambda: (MethodSpec("pca"), MethodSpec("cars")))
    feature_selection: FeatureSelectionSpec = field(default_factory=FeatureSelectionSpec)
    modeling: tuple[MethodSpec, ...] = field(default_factory=lambda: (MethodSpec("plsr"),))

    def __post_init__(self) -> None:
        object.__setattr__(self, "preprocessing", tuple(_method_spec(item) for item in self.preprocessing))
        object.__setattr__(self, "feature_analysis", tuple(_method_spec(item) for item in self.feature_analysis))
        selection = self.feature_selection
        if isinstance(selection, str):
            selection = FeatureSelectionSpec(MethodSpec(selection), selection.rsplit(".", 1)[0])
        elif isinstance(selection, Mapping):
            selection = FeatureSelectionSpec.from_dict(selection)
        elif not isinstance(selection, FeatureSelectionSpec):
            raise TypeError("feature_selection must be FeatureSelectionSpec")
        object.__setattr__(self, "feature_selection", selection)
        object.__setattr__(self, "modeling", tuple(_method_spec(item) for item in self.modeling))

    @staticmethod
    def _validated_spec(spec: MethodSpec, registry: MethodRegistry) -> MethodSpec:
        method = registry.get(spec.method_id)
        resolved = method.resolve_parameters(spec.parameters, saved_resolved=spec.resolved_parameters)
        return MethodSpec(spec.method_id, spec.parameters, resolved, spec.invocation_id)

    def validate(self, registry: MethodRegistry) -> None:
        if not self.preprocessing:
            raise ValueError("pipeline requires at least one preprocessing method")
        if not self.feature_analysis:
            raise ValueError("pipeline requires at least one feature analysis method")
        previous = DataKind.SPECTRUM_SET
        for spec in self.preprocessing:
            method = registry.get(spec.method_id)
            self._validated_spec(spec, registry)
            if method.stage is not Stage.PREPROCESSING or method.input_type is not previous or method.output_type is not DataKind.SPECTRUM_SET:
                raise TypeError(f"incompatible preprocessing method: {spec.method_id}")
            previous = method.output_type
        invocation_specs = (
            *self.preprocessing,
            *self.feature_analysis,
            self.feature_selection.method,
            *self.modeling,
        )
        invocation_ids = [str(spec.invocation_id) for spec in invocation_specs]
        duplicates = sorted({item for item in invocation_ids if invocation_ids.count(item) > 1})
        if duplicates:
            raise ValueError(f"duplicate invocation_id values: {duplicates}")

        analyses_by_invocation: dict[str, MethodSpec] = {}
        for spec in self.feature_analysis:
            method = registry.get(spec.method_id)
            self._validated_spec(spec, registry)
            if method.stage is not Stage.FEATURE_ANALYSIS or method.input_type is not DataKind.SPECTRUM_SET:
                raise TypeError(f"feature analysis must consume SpectrumSet: {spec.method_id}")
            analyses_by_invocation[str(spec.invocation_id)] = spec
        selection_spec = self.feature_selection.method
        selection = registry.get(selection_spec.method_id)
        self._validated_spec(selection_spec, registry)
        if selection.stage is not Stage.FEATURE_SELECTION or selection.input_type is not DataKind.FEATURE_ANALYSIS:
            raise TypeError(f"invalid feature selection method: {selection_spec.method_id}")
        source_invocation_id = self.feature_selection.source_invocation_id
        if source_invocation_id not in analyses_by_invocation:
            raise ValueError(f"feature selection source invocation is not defined: {source_invocation_id}")
        source_method_id = analyses_by_invocation[source_invocation_id].method_id
        accepted = selection.metadata.get("accepted_analysis_ids")
        if accepted is not None and source_method_id not in accepted:
            raise TypeError(
                f"{selection_spec.method_id} cannot consume analysis method {source_method_id} "
                f"from invocation {source_invocation_id}; "
                f"accepted sources: {accepted}"
            )
        if not self.modeling:
            raise ValueError("pipeline requires at least one modeling method")
        for spec in self.modeling:
            method = registry.get(spec.method_id)
            self._validated_spec(spec, registry)
            if method.stage is not Stage.MODELING or method.input_type is not DataKind.SELECTED_FEATURE_SET:
                raise TypeError(f"modeling method must consume SelectedFeatureSet: {spec.method_id}")

    def resolved(self, registry: MethodRegistry) -> "PipelineDefinition":
        self.validate(registry)
        return PipelineDefinition(
            tuple(self._validated_spec(spec, registry) for spec in self.preprocessing),
            tuple(self._validated_spec(spec, registry) for spec in self.feature_analysis),
            FeatureSelectionSpec(self._validated_spec(self.feature_selection.method, registry), self.feature_selection.source_invocation_id),
            tuple(self._validated_spec(spec, registry) for spec in self.modeling),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "preprocessing": [spec.to_dict() for spec in self.preprocessing],
            "feature_analysis": [spec.to_dict() for spec in self.feature_analysis],
            "feature_selection": self.feature_selection.to_dict(),
            "modeling": [spec.to_dict() for spec in self.modeling],
        }

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "PipelineDefinition":
        # Schema-v1 experiments stored plain method ids.  Keep them loadable,
        # then resolve defaults explicitly when replayed.
        preprocessing = tuple(_method_spec(item) for item in document["preprocessing"])
        analyses = tuple(_method_spec(item) for item in document["feature_analysis"])
        selection_document = document["feature_selection"]
        if isinstance(selection_document, str):
            selection = FeatureSelectionSpec(MethodSpec(selection_document), selection_document.rsplit(".", 1)[0])
        else:
            selection = FeatureSelectionSpec.from_dict(selection_document)
        modeling = tuple(_method_spec(item) for item in document["modeling"])
        return cls(preprocessing, analyses, selection, modeling)


@dataclass
class StageRun:
    stage: Stage
    stage_run_id: str
    method_specs: list[MethodSpec]
    input_ref: str
    output_ref: str
    output_kind: DataKind
    output: Any
    intermediate_states: list[IntermediateState]
    statistics: dict[str, Any]
    execution_metadata: dict[str, Any]
    random_seed: int
    computational_fingerprint: str
    created_at: str = field(default_factory=_now)
    cache_hit: bool = False

    @property
    def method_chain(self) -> list[str]:
        return [spec.method_id for spec in self.method_specs]

    @property
    def parameters(self) -> list[dict[str, Any]]:
        return [
            {
                "method_id": spec.method_id,
                "invocation_id": spec.invocation_id,
                "resolved_parameters": copy.deepcopy(spec.resolved_parameters),
            }
            for spec in self.method_specs
        ]

    @property
    def cache_key(self) -> str:
        return self.computational_fingerprint

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 3,
            "stage": self.stage.value,
            "stage_run_id": self.stage_run_id,
            "method_chain": self.method_chain,
            "method_specs": [spec.to_dict() for spec in self.method_specs],
            "input_ref": self.input_ref,
            "output_ref": self.output_ref,
            "parameters": _json_value(self.parameters),
            "output_kind": self.output_kind.value,
            "output": _serialize_output(self.output),
            "intermediate_states": [state.to_dict() for state in self.intermediate_states],
            "statistics": _json_value(self.statistics),
            "execution_metadata": _json_value(self.execution_metadata),
            "random_seed": self.random_seed,
            "computational_fingerprint": self.computational_fingerprint,
            "created_at": self.created_at,
            "cache_hit": self.cache_hit,
        }

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "StageRun":
        if "method_specs" in document:
            method_specs = [MethodSpec.from_dict(item) for item in document["method_specs"]]
        else:
            legacy_parameters = _from_json_value(document.get("parameters", {}))
            method_specs = [MethodSpec(method_id, legacy_parameters, legacy_parameters) for method_id in document["method_chain"]]
        fingerprint = str(
            document.get("computational_fingerprint")
            or document.get("execution_metadata", {}).get("cache_key")
            or hashlib.sha256(json.dumps(_json_value(document), sort_keys=True).encode()).hexdigest()
        )
        return cls(
            Stage(document["stage"]), str(document["stage_run_id"]), method_specs,
            str(document["input_ref"]), str(document["output_ref"]),
            DataKind(document["output_kind"]), _deserialize_output(document["output"]),
            [IntermediateState.from_dict(state) for state in document.get("intermediate_states", [])],
            _from_json_value(document.get("statistics", {})), _from_json_value(document.get("execution_metadata", {})),
            int(document["random_seed"]), fingerprint,
            str(document.get("created_at", _now())), bool(document.get("cache_hit", False)),
        )

    @classmethod
    def load(cls, path: Path) -> "StageRun":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass
class ExperimentRun:
    experiment_id: str
    dataset_id: str
    pipeline_definition: PipelineDefinition
    random_seed: int
    configuration_snapshot: dict[str, Any]
    stage_runs: list[StageRun] = field(default_factory=list)
    final_metrics: EvaluationResult | None = None
    final_model_id: str | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=_now)

    def add_stage_run(self, stage_run: StageRun) -> None:
        self.stage_runs.append(stage_run)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 3,
            "experiment_id": self.experiment_id,
            "dataset_id": self.dataset_id,
            "pipeline_definition": self.pipeline_definition.to_dict(),
            "random_seed": self.random_seed,
            "configuration_snapshot": _json_value(self.configuration_snapshot),
            "stage_runs": [stage.to_dict() for stage in self.stage_runs],
            "final_metrics": None if self.final_metrics is None else self.final_metrics.to_dict(),
            "final_model_id": self.final_model_id,
            "artifacts": _json_value(self.artifacts),
            "created_at": self.created_at,
        }

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "ExperimentRun":
        definition_document = document["pipeline_definition"]
        metrics_document = document.get("final_metrics")
        metrics = None if metrics_document is None else EvaluationResult(**_from_json_value(metrics_document))
        return cls(
            str(document["experiment_id"]), str(document["dataset_id"]),
            PipelineDefinition.from_dict(definition_document),
            int(document["random_seed"]), _from_json_value(document.get("configuration_snapshot", {})),
            [StageRun.from_dict(item) for item in document.get("stage_runs", [])], metrics,
            document.get("final_model_id"), _from_json_value(document.get("artifacts", [])), str(document.get("created_at", _now())),
        )

    @classmethod
    def load(cls, path: Path) -> "ExperimentRun":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _serialize_output(output: Any) -> dict[str, Any]:
    if isinstance(output, SpectrumSet):
        return {"kind": output.kind.value, "X": _json_value(output.X), "wavelengths": _json_value(output.wavelengths), "sample_ids": list(output.sample_ids), "y": _json_value(output.y), "metadata": _json_value(output.metadata)}
    if isinstance(output, LatentFeatureSet):
        return {"kind": output.kind.value, "X": _json_value(output.X), "feature_names": list(output.feature_names), "sample_ids": list(output.sample_ids), "y": _json_value(output.y), "metadata": _json_value(output.metadata), "loadings": _json_value(output.loadings)}
    if isinstance(output, SelectedFeatureSet):
        return {"kind": output.kind.value, "X": _json_value(output.X), "feature_names": list(output.feature_names), "selected_indices": _json_value(output.selected_indices), "sample_ids": list(output.sample_ids), "y": _json_value(output.y), "metadata": _json_value(output.metadata)}
    if isinstance(output, FeatureAnalysisResult):
        return {"kind": output.kind.value, "method_id": output.method_id, "source": _serialize_output(output.source), "feature_names": list(output.feature_names), "selected_indices": _json_value(output.selected_indices), "scores": _json_value(output.scores), "loadings": _json_value(output.loadings), "statistics": _json_value(output.statistics), "metadata": _json_value(output.metadata)}
    if isinstance(output, ModelResult):
        return {"kind": output.kind.value, "method_id": output.method_id, "predictions": _serialize_prediction(output.predictions), "evaluation": output.evaluation.to_dict(), "model_metadata": _json_value(output.model_metadata)}
    raise TypeError(f"cannot serialize workflow output: {type(output).__name__}")


def _serialize_prediction(output: PredictionSet) -> dict[str, Any]:
    return {"sample_ids": list(output.sample_ids), "y_true": _json_value(output.y_true), "y_pred": _json_value(output.y_pred), "residuals": _json_value(output.residuals), "split": list(output.split), "fold_ids": list(output.fold_ids), "metadata": _json_value(output.metadata)}


def _deserialize_output(document: Mapping[str, Any]) -> Any:
    kind = DataKind(document["kind"])
    if kind is DataKind.SPECTRUM_SET:
        return SpectrumSet(_from_json_value(document["X"]), _from_json_value(document["wavelengths"]), tuple(document["sample_ids"]), _from_json_value(document.get("y")), _from_json_value(document.get("metadata", {})))
    if kind is DataKind.LATENT_FEATURE_SET:
        return LatentFeatureSet(_from_json_value(document["X"]), tuple(document["feature_names"]), tuple(document["sample_ids"]), _from_json_value(document.get("y")), _from_json_value(document.get("metadata", {})), _from_json_value(document.get("loadings")))
    if kind is DataKind.SELECTED_FEATURE_SET:
        return SelectedFeatureSet(_from_json_value(document["X"]), tuple(document["feature_names"]), _from_json_value(document["selected_indices"]), tuple(document["sample_ids"]), _from_json_value(document.get("y")), _from_json_value(document.get("metadata", {})))
    if kind is DataKind.FEATURE_ANALYSIS:
        return FeatureAnalysisResult(document["method_id"], _deserialize_output(document["source"]), tuple(document["feature_names"]), _from_json_value(document.get("selected_indices")), _from_json_value(document.get("scores")), _from_json_value(document.get("loadings")), _from_json_value(document.get("statistics", {})), _from_json_value(document.get("metadata", {})))
    if kind is DataKind.MODEL_RESULT:
        prediction = document["predictions"]
        predictions = PredictionSet(tuple(prediction["sample_ids"]), _from_json_value(prediction["y_true"]), _from_json_value(prediction["y_pred"]), _from_json_value(prediction["residuals"]), tuple(prediction["split"]), tuple(prediction.get("fold_ids", [])), _from_json_value(prediction.get("metadata", {})))
        return ModelResult(document["method_id"], predictions, EvaluationResult(**_from_json_value(document["evaluation"])), _from_json_value(document.get("model_metadata", {})))
    raise ValueError(f"unknown workflow output kind: {kind}")


def serialize_workflow_output(output: Any) -> dict[str, Any]:
    return _serialize_output(output)


def deserialize_workflow_output(document: Mapping[str, Any]) -> Any:
    return _deserialize_output(document)


class StageCache:
    """In-memory cache for stage switching; optional disk persistence is explicit."""

    def __init__(self) -> None:
        self._items: dict[str, StageRun] = {}

    def get(self, key: str) -> StageRun | None:
        item = self._items.get(key)
        if item is None:
            return None
        cached = copy.deepcopy(item)
        cached.cache_hit = True
        return cached

    def put(self, item: StageRun) -> None:
        self._items[item.cache_key] = item
        cache_key = item.execution_metadata.get("cache_key")
        if isinstance(cache_key, str):
            self._items[cache_key] = item


def _fingerprint(value: Any) -> str:
    if isinstance(value, SpectrumSet):
        document = {
            "kind": value.kind.value,
            "X": _json_value(value.X),
            "wavelengths": _json_value(value.wavelengths),
            "sample_ids": value.sample_ids,
            "y": _json_value(value.y),
            "computational_metadata": _json_value(value.computational_metadata),
        }
    elif isinstance(value, LatentFeatureSet):
        document = {
            "kind": value.kind.value, "X": _json_value(value.X), "feature_names": value.feature_names,
            "sample_ids": value.sample_ids, "y": _json_value(value.y), "loadings": _json_value(value.loadings),
            "computational_metadata": _json_value({key: item for key, item in value.metadata.items() if key != "display"}),
        }
    elif isinstance(value, SelectedFeatureSet):
        document = {
            "kind": value.kind.value, "X": _json_value(value.X), "feature_names": value.feature_names,
            "selected_indices": _json_value(value.selected_indices), "sample_ids": value.sample_ids,
            "y": _json_value(value.y),
            "computational_metadata": _json_value({key: item for key, item in value.metadata.items() if key != "display"}),
        }
    elif isinstance(value, FeatureAnalysisResult):
        document = {
            "kind": value.kind.value, "method_id": value.method_id, "source": _fingerprint(value.source),
            "feature_names": value.feature_names, "selected_indices": _json_value(value.selected_indices),
            "scores": _json_value(value.scores), "loadings": _json_value(value.loadings),
            "statistics": _json_value(value.statistics),
            "computational_metadata": _json_value({key: item for key, item in value.metadata.items() if key != "display"}),
        }
    elif isinstance(value, ModelResult):
        document = _serialize_output(value)
        document["model_metadata"] = _json_value({key: item for key, item in value.model_metadata.items() if key != "display"})
    else:
        document = _json_value(value)
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def select_final_model_by_cv(model_results: Sequence[tuple[str, ModelResult]]) -> tuple[str, ModelResult]:
    """Select only with calibration-internal CV; validation metrics are ignored."""
    if not model_results:
        raise ValueError("model selection requires at least one model result")
    if len(model_results) == 1:
        return model_results[0]
    missing = [model_id for model_id, result in model_results if result.evaluation.cv_rmse is None]
    if missing:
        raise ValueError(f"multi-model selection requires calibration CV metrics: {missing}")
    return min(model_results, key=lambda item: float(item[1].evaluation.cv_rmse))


class PipelineEngine:
    def __init__(self, registry: MethodRegistry | None = None, cache: StageCache | None = None) -> None:
        self.registry = registry or build_default_registry()
        self.cache = cache or StageCache()

    def _execute_method(self, spec: MethodSpec, value: Any, seed: int, stage: Stage) -> tuple[Any, MethodExecutionResult]:
        method = self.registry.get(spec.method_id)
        if method.stage is not stage:
            raise TypeError(f"{spec.method_id} belongs to stage {method.stage.value}, not {stage.value}")
        actual_kind = getattr(value, "kind", None)
        if actual_kind is not method.input_type:
            raise TypeError(f"{spec.method_id} expects {method.input_type.value}, got {actual_kind}")
        result = method.execute(value, spec.resolved_parameters, seed)
        actual_output_kind = getattr(result.output, "kind", None)
        if actual_output_kind is not method.output_type:
            raise TypeError(f"{spec.method_id} returned {actual_output_kind}, expected {method.output_type.value}")
        return result.output, result

    def _stage_run(
        self,
        stage: Stage,
        method_specs: Sequence[str | MethodSpec | Mapping[str, Any]],
        value: Any,
        runtime_parameters: Mapping[str, Any],
        seed: int,
        input_ref: str,
        stage_run_id: str,
    ) -> tuple[Any, StageRun]:
        resolved_specs: list[MethodSpec] = []
        seed_sensitive = False
        for item in method_specs:
            spec = _method_spec(item)
            method = self.registry.get(spec.method_id)
            runtime = {key: item for key, item in runtime_parameters.items() if key in method.runtime_parameters}
            resolved = method.resolve_parameters(spec.parameters, runtime, spec.resolved_parameters)
            resolved_specs.append(MethodSpec(spec.method_id, spec.parameters, resolved, spec.invocation_id))
            seed_sensitive = seed_sensitive or method.seed_sensitive
        input_fingerprint = _fingerprint(value)
        key_document = {
            "input": input_fingerprint,
            "stage": stage.value,
            "method_specs": [spec.computational_dict() for spec in resolved_specs],
            "seed": seed if seed_sensitive else None,
        }
        key = hashlib.sha256(json.dumps(_json_value(key_document), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        cached = self.cache.get(key)
        if cached is not None:
            previous_specs = cached.method_specs
            remapped_statistics: dict[str, Any] = {}
            for previous, current_spec in zip(previous_specs, resolved_specs):
                previous_key = str(previous.invocation_id)
                fallback_key = previous.method_id
                if previous_key in cached.statistics:
                    remapped_statistics[str(current_spec.invocation_id)] = cached.statistics[previous_key]
                elif fallback_key in cached.statistics:
                    remapped_statistics[str(current_spec.invocation_id)] = cached.statistics[fallback_key]
            if len(remapped_statistics) == len(resolved_specs):
                cached.statistics = remapped_statistics
            methods_metadata = cached.execution_metadata.get("methods")
            if isinstance(methods_metadata, list):
                for metadata, spec in zip(methods_metadata, resolved_specs):
                    if isinstance(metadata, dict):
                        metadata["method_id"] = spec.method_id
                        metadata["invocation_id"] = spec.invocation_id
            cached.stage_run_id = stage_run_id
            cached.input_ref = input_ref
            cached.random_seed = seed
            cached.method_specs = copy.deepcopy(resolved_specs)
            return cached.output, cached
        current = value
        states: list[IntermediateState] = []
        metrics: dict[str, Any] = {}
        method_metadata: list[dict[str, Any]] = []
        for spec in resolved_specs:
            current, result = self._execute_method(spec, current, seed, stage)
            states.extend(result.intermediate_states)
            metrics[str(spec.invocation_id)] = result.metrics
            method_metadata.append({
                "method_id": spec.method_id,
                "invocation_id": spec.invocation_id,
                "resolved_parameters": copy.deepcopy(spec.resolved_parameters),
                "metadata": result.metadata,
            })
        stage_run = StageRun(
            stage, stage_run_id, resolved_specs, input_ref, _fingerprint(current),
            getattr(current, "kind"), current, states, metrics,
            {
                "methods": method_metadata,
                "cache_key": key,
                "input_fingerprint": input_fingerprint,
                "seed_sensitive": seed_sensitive,
            },
            seed, key,
        )
        self.cache.put(stage_run)
        return current, stage_run

    def execute(self, spectrum: SpectrumSet, experiment_id: str, dataset_id: str, seed: int, definition: PipelineDefinition | None = None, output_dir: Path | None = None) -> ExperimentRun:
        definition = (definition or PipelineDefinition()).resolved(self.registry)
        groups = spectrum.metadata.get("groups")
        if groups is not None and len(np.unique(groups)) >= 2:
            unique_groups = np.unique(groups)
            split = max(1, int(np.ceil(len(unique_groups) * 0.25)))
            rng = np.random.default_rng(seed)
            validation_groups = set(rng.choice(unique_groups, size=split, replace=False).tolist())
            validation_indices = np.asarray([index for index, group in enumerate(groups) if group in validation_groups], dtype=int)
        else:
            rng = np.random.default_rng(seed)
            order = rng.permutation(len(spectrum.sample_ids))
            validation_indices = np.sort(order[:max(1, int(len(order) * 0.25))])
        fit_indices = np.setdiff1d(np.arange(len(spectrum.sample_ids)), validation_indices)
        experiment = ExperimentRun(
            experiment_id, dataset_id, definition, seed,
            {
                "stage_order": [stage.value for stage in Stage],
                "fit_indices": fit_indices.tolist(),
                "validation_indices": validation_indices.tolist(),
                "target": spectrum.metadata.get("target_name"),
                "model_selection_metric": "calibration_cv_rmse",
                "final_evaluation_split": "validation",
            },
        )
        current, stage_run = self._stage_run(Stage.DATA_INSPECTION, [MethodSpec("data.inspect")], spectrum, {}, seed, "dataset:" + dataset_id, "data-inspection")
        experiment.add_stage_run(stage_run)
        current, stage_run = self._stage_run(Stage.PREPROCESSING, definition.preprocessing, current, {"fit_indices": fit_indices.tolist()}, seed, f"stage:{stage_run.stage_run_id}", "preprocessing")
        experiment.add_stage_run(stage_run)
        preprocessing_run = stage_run
        analyses: dict[str, tuple[FeatureAnalysisResult, StageRun]] = {}
        for spec in definition.feature_analysis:
            invocation_id = str(spec.invocation_id)
            analysis_output, analysis_run = self._stage_run(
                Stage.FEATURE_ANALYSIS, [spec], current, {"fit_indices": fit_indices.tolist()}, seed,
                f"stage:{preprocessing_run.stage_run_id}", f"feature-analysis-{invocation_id}",
            )
            experiment.add_stage_run(analysis_run)
            analyses[invocation_id] = (analysis_output, analysis_run)
        source_invocation_id = definition.feature_selection.source_invocation_id
        selection_source, source_analysis_run = analyses[source_invocation_id]
        selection_invocation_id = str(definition.feature_selection.method.invocation_id)
        selected, selection_run = self._stage_run(
            Stage.FEATURE_SELECTION, [definition.feature_selection.method], selection_source, {}, seed,
            f"stage:{source_analysis_run.stage_run_id}", f"feature-selection-{selection_invocation_id}",
        )
        experiment.add_stage_run(selection_run)
        model_results: list[tuple[str, ModelResult]] = []
        model_runs: dict[str, StageRun] = {}
        for spec in definition.modeling:
            invocation_id = str(spec.invocation_id)
            model, model_run = self._stage_run(
                Stage.MODELING, [spec], selected,
                {"fit_indices": fit_indices.tolist(), "validation_indices": validation_indices.tolist()}, seed,
                f"stage:{selection_run.stage_run_id}", f"modeling-{invocation_id}",
            )
            experiment.add_stage_run(model_run)
            model_results.append((invocation_id, model))
            model_runs[invocation_id] = model_run
        if model_results:
            final_id, final_model = select_final_model_by_cv(model_results)
            experiment.final_model_id = final_id
            experiment.final_metrics = final_model.evaluation
            _, results_run = self._stage_run(
                Stage.RESULTS,
                ["results.summarize"],
                final_model,
                {},
                seed,
                f"stage:{model_runs[final_id].stage_run_id}",
                "results",
            )
            experiment.add_stage_run(results_run)
        if output_dir is not None:
            output_dir = Path(output_dir)
            experiment.artifacts.append({"type": "experiment", "path": "experiment.json"})
            experiment.save(output_dir / "experiment.json")
            for stage_run in experiment.stage_runs:
                stage_run.save(output_dir / "stages" / f"{stage_run.stage_run_id}.json")
        return experiment

    def replay(self, experiment: ExperimentRun, spectrum: SpectrumSet, output_dir: Path | None = None) -> ExperimentRun:
        return self.execute(
            spectrum,
            experiment.experiment_id,
            experiment.dataset_id,
            experiment.random_seed,
            experiment.pipeline_definition,
            output_dir,
        )


def spectrum_from_run(run_dir: Path) -> SpectrumSet:
    root = Path(run_dir).resolve()
    samples_path = root / "data" / "samples.csv"
    spectra_path = root / "data" / "spectra.csv"
    with samples_path.open(newline="", encoding="utf-8") as stream:
        samples = list(csv.DictReader(stream))
    with spectra_path.open(newline="", encoding="utf-8") as stream:
        spectra = list(csv.DictReader(stream))
    if not samples or not spectra:
        raise ValueError("run must contain non-empty sample and spectra tables")
    sample_ids = [row["sample_id"] for row in samples]
    wavelengths = sorted({float(row["wavelength_nm"]) for row in spectra})
    lookup = {(row["sample_id"], float(row["wavelength_nm"])): row for row in spectra}
    X = np.asarray([[float(lookup[(sample_id, wavelength)]["reflectance"]) for wavelength in wavelengths] for sample_id in sample_ids], dtype=float)
    target_name = "ssc_brix" if "ssc_brix" in samples[0] else "synthetic_ssc_proxy"
    if target_name not in samples[0]:
        target_name = target_name if target_name in spectra[0] else None
    y = None if target_name is None else np.asarray([float(row[target_name]) for row in samples], dtype=float)
    groups = np.asarray([row.get("batch_id", row.get("fruit_id", sample_id)) for row, sample_id in zip(samples, sample_ids)])
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    return SpectrumSet(X, np.asarray(wavelengths), tuple(sample_ids), y, {
        "dataset_id": manifest.get("dataset_id", root.name),
        "source_type": manifest.get("source_type", samples[0].get("source_type", "unknown")),
        "target_name": target_name,
        "groups": groups,
        "run_dir": str(root),
    })


def run_workflow_from_run(run_dir: Path, output_dir: Path, experiment_id: str | None = None, seed: int = 20260920, definition: PipelineDefinition | None = None) -> ExperimentRun:
    spectrum = spectrum_from_run(run_dir)
    experiment_id = experiment_id or f"experiment_{Path(run_dir).name}"
    return PipelineEngine().execute(spectrum, experiment_id, str(spectrum.metadata.get("dataset_id", Path(run_dir).name)), seed, definition, output_dir)


def run_preprocessing_comparison(
    spectrum: SpectrumSet,
    chains: Sequence[Sequence[str | MethodSpec | Mapping[str, Any]]],
    seed: int = 20260920,
    cache: StageCache | None = None,
) -> list[StageRun]:
    """Run comparable preprocessing chains over the same samples and axis."""
    engine = PipelineEngine(cache=cache)
    results: list[StageRun] = []
    for index, chain in enumerate(chains, start=1):
        if not chain:
            raise ValueError("each preprocessing comparison chain must be non-empty")
        specs = tuple(_method_spec(item) for item in chain)
        invocation_ids = [str(spec.invocation_id) for spec in specs]
        if len(invocation_ids) != len(set(invocation_ids)):
            raise ValueError(f"duplicate invocation_id within comparison chain: {invocation_ids}")
        for spec in specs:
            method = engine.registry.get(spec.method_id)
            if method.stage is not Stage.PREPROCESSING:
                raise TypeError(f"comparison method is not preprocessing: {spec.method_id}")
        _, stage_run = engine._stage_run(
            Stage.PREPROCESSING,
            specs,
            spectrum,
            {},
            seed,
            "dataset:" + str(spectrum.metadata.get("dataset_id", "unknown")),
            f"preprocessing-comparison-{index}",
        )
        results.append(stage_run)
    return results


__all__ = [
    "DataKind", "EvaluationResult", "ExperimentRun", "FeatureAnalysisResult", "FeatureSelectionSpec",
    "IntermediateState", "LatentFeatureSet", "Method", "MethodRegistry", "MethodSpec", "ModelResult",
    "ParameterDefinition", "PipelineDefinition", "PipelineEngine", "PredictionSet", "SelectedFeatureSet",
    "SpectrumSet", "Stage", "StageCache", "StageRun", "build_default_registry",
    "deserialize_workflow_output", "evaluate_predictions", "run_preprocessing_comparison",
    "run_workflow_from_run", "select_final_model_by_cv", "serialize_workflow_output", "spectrum_from_run",
]
