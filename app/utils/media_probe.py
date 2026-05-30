from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError


@dataclass(frozen=True)
class ImageInfo:
    width: int
    height: int
    format: str | None


def probe_image(path: Path | str) -> ImageInfo:
    image_path = Path(path)
    try:
        with Image.open(image_path) as image:
            image.verify()
        with Image.open(image_path) as image:
            width, height = image.size
            return ImageInfo(width=width, height=height, format=image.format)
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError("画像ファイルを読み取れません") from exc
