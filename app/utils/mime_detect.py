from __future__ import annotations

import mimetypes
from pathlib import Path


def detect_mime_type(path: Path | str, fallback: str | None = None) -> str:
    guessed, _ = mimetypes.guess_type(Path(path).name)
    return guessed or fallback or "application/octet-stream"


def media_type_from_mime(mime_type: str) -> str | None:
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    return None
