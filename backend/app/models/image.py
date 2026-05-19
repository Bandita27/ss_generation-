from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Image:
    id: str
    session_id: str
    original_filename: str
    stored_path: str
    matched: bool = False
    confidence: float = 0.0
    label_seen: str = ""
    uid: int = 0
