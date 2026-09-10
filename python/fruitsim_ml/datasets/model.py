from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class DatasetManifest:
    """Typed envelope around a schema-v2 manifest without hiding unknown metadata."""

    raw: dict[str, Any]

    @property
    def schema_version(self) -> int | None:
        return self.raw.get("schema_version")

    @property
    def dataset_id(self) -> str | None:
        return self.raw.get("dataset_id")

    @property
    def source_type(self) -> str | None:
        return self.raw.get("source_type")

    @property
    def status(self) -> str | None:
        return self.raw.get("status")

    @property
    def available_channels(self) -> list[str]:
        return list(self.raw.get("available_channels") or [])


@dataclass
class CanonicalExperimentalDataset:
    """In-memory canonical v2 tables; raw CSV files are never rewritten by loading."""

    root: Path
    manifest: DatasetManifest
    samples: pd.DataFrame
    spectra: pd.DataFrame

    @property
    def dataset_id(self) -> str | None:
        return self.manifest.dataset_id
