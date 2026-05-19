from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.controller.extraction import (
    build_job_zip,
    get_job_preview,
    get_job_status,
    read_csv_headers,
    save_job_as_session,
    start_extraction_job,
)
from app.schemas.extraction import (
    ExtractionPreview,
    ExtractionStartResponse,
    ExtractionStatus,
)
from app.schemas.upload_session import UploadSessionResponse


router = APIRouter(prefix="/extract", tags=["extract"])


@router.post("/headers")
async def headers(csv: UploadFile = File(...)) -> dict:
    csv_bytes = await csv.read()
    try:
        return {"headers": read_csv_headers(csv_bytes)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("", response_model=ExtractionStartResponse)
async def start_job(
    video: UploadFile = File(...),
    csv: UploadFile = File(...),
    conf_threshold: float = Form(0.5),
    sample_every: int = Form(10),
    track_col: str = Form("track_id"),
    frame_col: str = Form("frame"),
    conf_col: str = Form("confidence"),
    bbox_format: str = Form("xywh"),
    bbox_x: str = Form("x"),
    bbox_y: str = Form("y"),
    bbox_w: str = Form("w"),
    bbox_h: str = Form("h"),
):
    video_bytes = await video.read()
    csv_bytes = await csv.read()
    if not video_bytes or not csv_bytes:
        raise HTTPException(400, "Both video and CSV are required")

    job_id = start_extraction_job(
        video_bytes=video_bytes,
        video_filename=video.filename or "video.mp4",
        csv_bytes=csv_bytes,
        csv_filename=csv.filename or "tracks.csv",
        conf_threshold=conf_threshold,
        sample_every=sample_every,
        track_col=track_col,
        frame_col=frame_col,
        conf_col=conf_col,
        bbox_format=bbox_format,
        bbox_cols=(bbox_x, bbox_y, bbox_w, bbox_h),
    )
    return ExtractionStartResponse(job_id=job_id)


@router.get("/{job_id}/status", response_model=ExtractionStatus)
def job_status(job_id: str):
    job = get_job_status(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return ExtractionStatus(
        status=job["status"],
        progress=job.get("progress", 0),
        total=job.get("total", 0),
        error=job.get("error"),
    )


@router.get("/{job_id}/preview", response_model=ExtractionPreview)
def job_preview(job_id: str):
    preview = get_job_preview(job_id)
    if preview is None:
        raise HTTPException(404, "Job not found")
    return preview


@router.get("/{job_id}/zip")
def download_job_zip(job_id: str):
    """Download the generated screenshots + intermediate CSV as one zip.

    Available between Step 2 (preview) and Step 3 (review) — lets the user
    grab a copy of the extraction artefacts before promoting to a session.
    """
    result = build_job_zip(job_id)
    if result is None:
        raise HTTPException(
            400,
            "Cannot download: job not found, not done yet, or has no crops",
        )
    buffer, filename = result
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{job_id}/save", response_model=UploadSessionResponse)
def save_job(job_id: str):
    session = save_job_as_session(job_id)
    if session is None:
        raise HTTPException(
            400,
            "Cannot save: job not found, not done yet, or has no crops",
        )
    return UploadSessionResponse.model_validate(session)