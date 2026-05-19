from __future__ import annotations

import io
import logging
import shutil
import traceback
import uuid
import zipfile
from pathlib import Path
from threading import Lock, Thread

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.extraction import process_video
from app.core.storage import ensure_session_dirs
from app.models.image import Image as ImageModel
from app.models.upload_session import UploadSession

log = logging.getLogger(__name__)


# ─── job registry (in-memory) ──────────────────────────────────────
_JOBS: dict[str, dict] = {}
_LOCK = Lock()


def _set(job_id: str, **fields) -> None:
    with _LOCK:
        _JOBS.setdefault(job_id, {}).update(fields)


def _get(job_id: str) -> dict | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        return dict(job)


def jobs_dir() -> Path:
    d = Path(settings.STORAGE_ROOT) / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def job_dir(job_id: str) -> Path:
    return jobs_dir() / job_id


# ─── start a job ───────────────────────────────────────────────────
def start_extraction_job(
    video_bytes: bytes,
    video_filename: str,
    csv_bytes: bytes,
    csv_filename: str,
    *,
    conf_threshold: float,
    sample_every: int,
    track_col: str,
    frame_col: str,
    conf_col: str,
    bbox_format: str,
    bbox_cols: tuple[str, str, str, str],
) -> str:
    job_id = uuid.uuid4().hex[:12]
    jd = job_dir(job_id)
    jd.mkdir(parents=True, exist_ok=True)

    safe_video_name = Path(video_filename or "video.mp4").name
    safe_csv_name = Path(csv_filename or "tracks.csv").name
    csv_stem = Path(safe_csv_name).stem

    video_path = jd / safe_video_name
    csv_path = jd / safe_csv_name
    video_path.write_bytes(video_bytes)
    csv_path.write_bytes(csv_bytes)

    _set(
        job_id,
        status="queued",
        progress=0,
        total=0,
        results=[],
        error=None,
        video_name=safe_video_name,
        csv_name=safe_csv_name,
        csv_stem=csv_stem,
    )

    kwargs = dict(
        conf_threshold=conf_threshold,
        sample_every=sample_every,
        track_col=track_col,
        frame_col=frame_col,
        conf_col=conf_col,
        bbox_format=bbox_format,
        bbox_cols=bbox_cols,
    )

    Thread(
        target=_run_job,
        daemon=True,
        args=(job_id, video_path, csv_path, jd, kwargs),
    ).start()

    return job_id


def _run_job(job_id: str, video_path: Path, csv_path: Path, out_dir: Path, kwargs: dict) -> None:
    try:
        _set(job_id, status="processing", progress=0, total=0)

        def cb(i: int, total: int) -> None:
            _set(job_id, progress=i, total=total)

        results, _intermediate_csv = process_video(
            video_path, csv_path, out_dir, progress_cb=cb, **kwargs
        )
        _set(job_id, status="done", results=results, progress=len(results), total=len(results))
    except Exception as e:
        traceback.print_exc()
        _set(job_id, status="error", error=str(e))


def get_job_status(job_id: str) -> dict | None:
    return _get(job_id)


def get_job_preview(job_id: str) -> dict | None:
    job = _get(job_id)
    if job is None:
        return None

    crops = []
    for r in job.get("results", []):
        crops.append({
            "uid": r["uid"],
            "track_id": r["track_id"],
            "frame": r["frame"],
            "confidence": r["confidence"],
            "class_name": r.get("class_name", ""),
            "image_url": f"/storage/jobs/{job_id}/crops/{r['image']}",
        })

    return {
        "job_id": job_id,
        "status": job["status"],
        "progress": job.get("progress", 0),
        "total": job.get("total", 0),
        "crops": crops,
        "source_video_name": job.get("video_name", ""),
        "source_csv_name": job.get("csv_name", ""),
    }


# ─── job zip (preview step download) ──────────────────────────────
def build_job_zip(job_id: str) -> tuple[io.BytesIO, str] | None:
    """Bundle the intermediate CSV + generated crops into a single zip.

    Used by the page-2 'Download' button so the user can grab a copy of the
    extraction artefacts (screenshots + CSV) before moving on to the review
    step. Only available once status is 'done'.
    """
    job = _get(job_id)
    if job is None or job["status"] != "done":
        return None

    jd = job_dir(job_id)
    if not jd.exists():
        return None

    results = job.get("results", [])
    if not results:
        return None

    csv_stem = job.get("csv_stem") or "extracted"
    intermediate_csv = jd / "intermediate.csv"
    crops_dir = jd / "crops"

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Filtered CSV at the top of the archive, named after the source.
        if intermediate_csv.exists():
            zf.write(intermediate_csv, arcname=f"{csv_stem}.csv")
        else:
            log.warning("Job %s: intermediate.csv missing on disk", job_id)

        # Annotated crops under images/<uid>.webp
        if crops_dir.exists():
            for r in results:
                src = crops_dir / r["image"]
                if not src.exists():
                    log.warning("Job %s: crop %s missing on disk, skipping", job_id, r["image"])
                    continue
                zf.write(src, arcname=f"images/{r['image']}")

    buffer.seek(0)
    safe_stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in csv_stem)[:40]
    filename = f"{safe_stem}_preview.zip"
    return buffer, filename


# ─── promote job → permanent session ──────────────────────────────
def save_job_as_session(db: Session, job_id: str, label: str | None = None) -> UploadSession | None:
    job = _get(job_id)
    if job is None or job["status"] != "done":
        return None

    results = job.get("results", [])
    if not results:
        return None

    jd = job_dir(job_id)
    if not jd.exists():
        return None

    csv_stem = job.get("csv_stem") or "extracted"
    session_label = label or f"{csv_stem} — {len(results)} crops"

    session = UploadSession(
        label=session_label,
        threshold=settings.DEFAULT_THRESHOLD,
        source_csv_stem=csv_stem,
    )
    db.add(session)
    db.flush()

    session_id: uuid.UUID = session.id  # type: ignore[assignment]
    ensure_session_dirs(session_id)

    storage_root = Path(settings.STORAGE_ROOT)
    session_root = storage_root / str(session_id)

    intermediate_src = jd / "intermediate.csv"
    intermediate_dst = session_root / "intermediate.csv"
    if intermediate_src.exists():
        shutil.copy2(intermediate_src, intermediate_dst)
        session.intermediate_csv_path = str(intermediate_dst.relative_to(storage_root).as_posix())  # type: ignore[assignment]

    crops_src_dir = jd / "crops"
    unmatched_dir = session_root / "unmatched"
    unmatched_dir.mkdir(parents=True, exist_ok=True)

    for r in results:
        uid = int(r["uid"])
        src_image = crops_src_dir / r["image"]
        if not src_image.exists():
            log.warning("Job %s: crop %s missing on disk, skipping", job_id, r["image"])
            continue

        image_id = uuid.uuid4()
        dst_filename = f"{image_id}.webp"
        dst_path = unmatched_dir / dst_filename
        shutil.copy2(src_image, dst_path)

        rel_path = dst_path.relative_to(storage_root).as_posix()
        db.add(ImageModel(
            id=image_id,
            session_id=session_id,
            original_filename=f"{uid}.webp",
            stored_path=rel_path,
            matched=False,
            confidence=float(r.get("confidence", 0.0)),
            label_seen=str(r.get("class_name", "")),
            uid=uid,
        ))

    db.commit()
    db.refresh(session)

    try:
        shutil.rmtree(jd)
    except Exception as e:
        log.warning("Failed to clean job dir %s: %s", jd, e)
    with _LOCK:
        _JOBS.pop(job_id, None)

    return session


# ─── header sniff ─────────────────────────────────────────────────
def read_csv_headers(csv_bytes: bytes) -> list[str]:
    import io as _io
    try:
        df = pd.read_csv(_io.BytesIO(csv_bytes), nrows=0)
        return [str(c).strip() for c in df.columns]
    except Exception as e:
        raise ValueError(f"CSV parse error: {e}")