from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UploadSession:
    id: str
    label: str
    threshold: float
    source_csv_stem: str
    intermediate_csv_path: str | None = None
