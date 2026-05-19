from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

import pandas as pd
import av
from av.video.frame import VideoFrame
from PIL import Image, ImageDraw, ImageFont


# Colors (RGB)
CLASS_COLORS = [
    (66, 165, 245),
    (102, 187, 106),
    (255, 167, 38),
    (239, 83, 80),
    (171, 71, 188),
    (38, 198, 218),
    (255, 202, 40),
    (236, 64, 122),
    (141, 110, 99),
    (120, 144, 156),
]


def _color_for(class_name: str) -> tuple[int, int, int]:
    if not class_name:
        return (158, 158, 158)
    h = int(hashlib.md5(str(class_name).encode("utf-8")).hexdigest(), 16)
    return CLASS_COLORS[h % len(CLASS_COLORS)]


def _detect_class_col(columns: list[str]) -> str | None:
    for cand in ("class_name", "class", "label", "category", "cls"):
        for c in columns:
            if c.lower() == cand:
                return c
    return None


def process_video(
    video_path: Path,
    csv_path: Path,
    output_dir: Path,
    *,
    conf_threshold: float = 0.5,
    sample_every: int = 10,
    track_col: str = "track_id",
    frame_col: str = "frame",
    conf_col: str = "confidence",
    timestamp_col: str = "timestamp_seconds",
    bbox_format: str = "xywh",
    bbox_cols: tuple[str, str, str, str] = ("x", "y", "w", "h"),
    progress_cb: Callable[[int, int], None] | None = None,
) -> tuple[list[dict], Path]:
    """Run the extraction pipeline.

    Returns (results, intermediate_csv_path). Each result dict carries uid,
    track_id, frame, timestamp_seconds, confidence, bbox, class_name, image.
    The intermediate CSV (with `uid` column injected) is written to
    `output_dir / "intermediate.csv"`.
    """
    df = pd.read_csv(csv_path)
    df.columns = [str(c).strip() for c in df.columns]

    column_aliases = {
        "x": ["bbox_x1", "bbox_x"],
        "y": ["bbox_y1", "bbox_y"],
        "w": ["bbox_width", "width"],
        "h": ["bbox_height", "height"],
    }

    def resolve_alias(canonical: str) -> str | None:
        if canonical in df.columns:
            return canonical
        for alias in column_aliases[canonical]:
            if alias in df.columns:
                return alias
        return None

    bbox_source: dict[str, str | tuple[str, str] | None] = {
        "x": resolve_alias("x"),
        "y": resolve_alias("y"),
        "w": resolve_alias("w"),
        "h": resolve_alias("h"),
    }

    if bbox_source["w"] is None and {"bbox_x1", "bbox_x2"}.issubset(df.columns):
        bbox_source["w"] = ("bbox_x1", "bbox_x2")
    if bbox_source["h"] is None and {"bbox_y1", "bbox_y2"}.issubset(df.columns):
        bbox_source["h"] = ("bbox_y1", "bbox_y2")

    if frame_col not in df.columns and "frame_number" in df.columns:
        df[frame_col] = df["frame_number"]

    required = [track_col, frame_col, conf_col]
    missing: list[str] = []
    for canonical in ("x", "y", "w", "h"):
        source = bbox_source[canonical]
        if source is None:
            missing.append(canonical)
        elif isinstance(source, tuple):
            required.extend(source)
        else:
            required.append(source)

    missing += [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"CSV missing columns: {missing}. "
            f"Available columns are: {list(df.columns)}"
        )

    x_src = bbox_source["x"]
    y_src = bbox_source["y"]
    w_src = bbox_source["w"]
    h_src = bbox_source["h"]
    assert x_src is not None and y_src is not None
    assert w_src is not None and h_src is not None

    class_col = _detect_class_col(list(df.columns))
    has_timestamp = timestamp_col in df.columns

    # --- Step 1: Confidence filter ---
    df[conf_col] = pd.to_numeric(df[conf_col], errors="coerce")
    df = df.dropna(subset=[conf_col])
    df = df[df[conf_col] >= conf_threshold].copy()
    if len(df) == 0:
        raise ValueError(f"No detections remain after confidence ≥ {conf_threshold}.")

    # --- Step 2: Validate track_id and frame ---
    df[track_col] = pd.to_numeric(df[track_col], errors="coerce")
    df = df.dropna(subset=[track_col])
    df[track_col] = df[track_col].astype(int)

    df[frame_col] = pd.to_numeric(df[frame_col], errors="coerce")
    df = df.dropna(subset=[frame_col])
    df[frame_col] = df[frame_col].astype(int)

    # --- Step 3: Sort by track_id then frame ---
    df = df.sort_values(by=[track_col, frame_col], kind="stable").reset_index(drop=True)

    # --- Step 4: Per-track 1-in-N sampling ---
    if sample_every < 1:
        sample_every = 1
    within_track_idx = df.groupby(track_col).cumcount()
    df = df[within_track_idx % sample_every == 0].reset_index(drop=True)
    if len(df) == 0:
        raise ValueError("No rows remain after per-track sampling.")

    # --- Step 5: Serial UID (1, 2, 3, ..., N) ---
    df["uid"] = range(1, len(df) + 1)

    # --- Step 6: Open video (PyAV) ---
    try:
        container = av.open(str(video_path))
    except Exception as e:
        raise RuntimeError(f"Could not open video: {video_path} ({e})")

    # Find the first video stream
    video_stream = next((s for s in container.streams if s.type == "video"), None)
    if video_stream is None:
        container.close()
        raise RuntimeError(f"No video stream found: {video_path}")

    # Use codec_context attributes to satisfy static type checkers
    cc = video_stream.codec_context
    vw = int(getattr(cc, "width", 0))
    vh = int(getattr(cc, "height", 0))
    try:
        n_frames = int(video_stream.frames) if video_stream.frames is not None else 0
    except Exception:
        n_frames = 0
    fps = None
    avg = getattr(video_stream, "average_rate", None)
    if avg is not None:
        try:
            fps = float(avg)
        except Exception:
            fps = None
    else:
        fr = getattr(cc, "framerate", None)
        if fr is not None:
            try:
                fps = float(fr)
            except Exception:
                fps = None

    crops_dir = output_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    kept_uids: list[int] = []
    total = len(df)

    if progress_cb is not None:
        progress_cb(0, total)

    try:
        for i, (_, row) in enumerate(df.iterrows()):
            uid = int(row["uid"])
            try:
                # Seek to requested timestamp or frame
                if has_timestamp and pd.notna(row[timestamp_col]):
                    ts_sec = float(row[timestamp_col])
                    timestamp_us = int(ts_sec * 1_000_000)
                    container.seek(timestamp_us, any_frame=False, backward=True, stream=video_stream)
                else:
                    fn = int(row[frame_col])
                    if n_frames and fn >= n_frames:
                        fn = n_frames - 1
                    fn = max(0, fn)
                    if fps:
                        timestamp_us = int(fn / fps * 1_000_000)
                        container.seek(timestamp_us, any_frame=False, backward=True, stream=video_stream)

                # Decode the next available frame
                frame = None
                for f in container.decode(video=video_stream):
                    frame = f
                    break
                if frame is None:
                    print(f"uid {uid}: frame unreadable, skipped")
                    continue

                if not isinstance(frame, VideoFrame):
                    # skip non-video frames (audio frames, etc.)
                    print(f"uid {uid}: non-video frame, skipped")
                    continue

                img_pil: Image.Image = frame.to_image()

                if bbox_format == "xywh":
                    def get_bbox_value(source):
                        if isinstance(source, tuple):
                            return float(row[source[1]]) - float(row[source[0]])
                        return float(row[source])

                    x = get_bbox_value(x_src)
                    y = get_bbox_value(y_src)
                    w = get_bbox_value(w_src)
                    h = get_bbox_value(h_src)
                else:
                    v = [float(row[c]) for c in bbox_cols]
                    x, y, w, h = v[0], v[1], v[2] - v[0], v[3] - v[1]

                if all(abs(c) <= 1.0001 for c in (x, y, w, h)):
                    x *= vw; y *= vh; w *= vw; h *= vh

                x = max(0, int(x))
                y = max(0, int(y))
                w = max(1, min(int(w), vw - x))
                h = max(1, min(int(h), vh - y))

                cls_name = str(row[class_col]).strip() if class_col else ""
                color = _color_for(cls_name)
                thickness = max(2, int(round(min(vw, vh) / 400)))

                annotated = img_pil.copy()
                draw = ImageDraw.Draw(annotated)

                # Draw rectangle
                draw.rectangle([x, y, x + w, y + h], outline=color, width=thickness)

                parts: list[str] = []
                if cls_name:
                    parts.append(cls_name)
                parts.append(f"#{int(row[track_col])}")
                parts.append(f"{float(row[conf_col]):.2f}")
                label = "  ".join(parts)

                # Font handling (fall back to default)
                try:
                    font_size = max(10, int(max(12, min(vw, vh) / 55)))
                    font = ImageFont.truetype("arial.ttf", font_size)
                except Exception:
                    font = ImageFont.load_default()

                # Text size and label background
                bbox = draw.textbbox((0, 0), label, font=font)
                lw = bbox[2] - bbox[0]
                lh = bbox[3] - bbox[1]
                baseline = 0
                pad_x, pad_y = 8, 6

                if y - lh - baseline - pad_y * 2 >= 0:
                    ly_top = y - lh - baseline - pad_y * 2
                    ly_bot = y
                else:
                    ly_top = y
                    ly_bot = y + lh + baseline + pad_y * 2

                label_right = min(vw - 1, x + lw + pad_x * 2)
                draw.rectangle((x, ly_top, label_right, ly_bot), fill=color)
                text_x = x + pad_x
                text_y = ly_bot - pad_y - baseline // 2 - lh
                if text_y < ly_top:
                    text_y = ly_top
                draw.text((text_x, ly_bot - pad_y - baseline // 2 - lh + (lh // 8)), label, font=font, fill=(255, 255, 255))

                out_path = crops_dir / f"{uid}.webp"
                annotated.save(str(out_path), "WEBP", quality=88)

                kept_uids.append(uid)
                results.append({
                    "uid": uid,
                    "track_id": int(row[track_col]),
                    "frame": int(row[frame_col]),
                    "timestamp_seconds": float(row[timestamp_col]) if has_timestamp else None,
                    "confidence": float(row[conf_col]),
                    "bbox": [x, y, w, h],
                    "class_name": cls_name,
                    "image": f"{uid}.webp",
                })
            except Exception as e:
                print(f"uid {uid} skipped: {e}")
                continue

            if progress_cb is not None:
                progress_cb(int(i) + 1, total)
    finally:
        try:
            container.close()
        except Exception:
            pass

    # Intermediate CSV — only rows that produced an image, with uid column.
    intermediate_df = df[df["uid"].isin(kept_uids)].copy()
    intermediate_csv = output_dir / "intermediate.csv"
    intermediate_df.to_csv(intermediate_csv, index=False)

    return results, intermediate_csv