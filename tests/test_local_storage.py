from pathlib import Path

from app.storage.local_storage import LocalStorage


def test_storage_directories_can_be_initialized(tmp_path: Path):
    storage = LocalStorage(storage_root=tmp_path / "storage")

    storage.ensure_directories()

    assert (tmp_path / "storage" / "raw").is_dir()
    assert (tmp_path / "storage" / "processed").is_dir()
    assert (tmp_path / "storage" / "thumbnails").is_dir()


def test_storage_paths_can_be_generated_by_area(tmp_path: Path):
    storage = LocalStorage(storage_root=tmp_path / "storage")

    raw_path = storage.raw_path(12, "photo.jpg")
    processed_path = storage.processed_path(12, "photo.webp")
    thumbnail_path = storage.thumbnail_path(12, "photo-thumb.jpg")

    assert raw_path == tmp_path / "storage" / "raw" / "12" / "photo.jpg"
    assert processed_path == tmp_path / "storage" / "processed" / "12" / "photo.webp"
    assert thumbnail_path == tmp_path / "storage" / "thumbnails" / "12" / "photo-thumb.jpg"
    assert raw_path.parent.is_dir()
    assert processed_path.parent.is_dir()
    assert thumbnail_path.parent.is_dir()
