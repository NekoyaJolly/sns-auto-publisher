from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from app.config.settings import Settings, get_settings


class StorageArea(StrEnum):
    RAW = "raw"
    PROCESSED = "processed"
    THUMBNAILS = "thumbnails"


class LocalStorage:
    def __init__(self, storage_root: Path | str | None = None, settings: Settings | None = None) -> None:
        resolved_settings = settings or get_settings()
        self.root = Path(storage_root) if storage_root is not None else resolved_settings.storage_root

    def ensure_directories(self) -> None:
        for area in StorageArea:
            (self.root / area.value).mkdir(parents=True, exist_ok=True)

    def job_directory(self, area: StorageArea | str, job_id: int, *, create: bool = False) -> Path:
        area_value = self._area_value(area)
        directory = self.root / area_value / str(job_id)
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        return directory

    def raw_path(self, job_id: int, filename: str, *, create_parent: bool = True) -> Path:
        return self.build_path(StorageArea.RAW, job_id, filename, create_parent=create_parent)

    def processed_path(self, job_id: int, filename: str, *, create_parent: bool = True) -> Path:
        return self.build_path(StorageArea.PROCESSED, job_id, filename, create_parent=create_parent)

    def thumbnail_path(self, job_id: int, filename: str, *, create_parent: bool = True) -> Path:
        return self.build_path(StorageArea.THUMBNAILS, job_id, filename, create_parent=create_parent)

    def build_path(
        self,
        area: StorageArea | str,
        job_id: int,
        filename: str,
        *,
        create_parent: bool = True,
    ) -> Path:
        safe_name = Path(filename).name
        if not safe_name:
            raise ValueError("filenameは空にできません")
        directory = self.job_directory(area, job_id, create=create_parent)
        return directory / safe_name

    def save_bytes(
        self,
        area: StorageArea | str,
        job_id: int,
        filename: str,
        content: bytes,
    ) -> Path:
        path = self.unique_path(area, job_id, filename)
        path.write_bytes(content)
        return path

    def unique_path(self, area: StorageArea | str, job_id: int, filename: str) -> Path:
        path = self.build_path(area, job_id, filename, create_parent=True)
        if not path.exists():
            return path

        stem = path.stem
        suffix = path.suffix
        for index in range(1, 10_000):
            candidate = path.with_name(f"{stem}-{index}{suffix}")
            if not candidate.exists():
                return candidate
        raise FileExistsError("保存先ファイル名の重複を解決できませんでした")

    @staticmethod
    def _area_value(area: StorageArea | str) -> str:
        try:
            return StorageArea(area).value
        except ValueError as exc:
            allowed = ", ".join(item.value for item in StorageArea)
            raise ValueError(f"storage areaは {allowed} のいずれかを指定してください") from exc
