from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from uuid import UUID


class UploadSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    threshold: float
    source_csv_stem: str
    intermediate_csv_path: str | None = None
