from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import settings


def ensure_session_dirs(session_id: str | uuid.UUID) -> Path:
    storage_root = Path(settings.STORAGE_ROOT)
    storage_root.mkdir(parents=True, exist_ok=True)

    session_root = storage_root / str(session_id)
    session_root.mkdir(parents=True, exist_ok=True)
    (session_root / "unmatched").mkdir(parents=True, exist_ok=True)
    return session_root
