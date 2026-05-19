from pydantic import BaseModel


class ExtractionStartResponse(BaseModel):
    job_id: str


class ExtractionStatus(BaseModel):
    status: str
    progress: int
    total: int
    error: str | None = None


class CropItem(BaseModel):
    uid: int
    track_id: int
    frame: int
    confidence: float
    class_name: str
    image_url: str


class ExtractionPreview(BaseModel):
    job_id: str
    status: str
    progress: int
    total: int
    crops: list[CropItem]
    source_video_name: str
    source_csv_name: str
