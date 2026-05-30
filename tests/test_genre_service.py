from pathlib import Path

import pytest

from app.services.genre_service import GenreService, UnknownGenreError


def test_genre_service_resolves_numeric_aliases():
    service = GenreService()

    assert service.resolve_from_text("1").genre_key == "slot_daily"
    assert service.resolve_from_text("2").genre_key == "slot_result"


def test_genre_service_resolves_key_and_assignment_forms():
    service = GenreService()

    assert service.resolve_from_text("slot_result").genre_key == "slot_result"
    assert service.resolve_from_text("genre=slot_result").genre_key == "slot_result"
    assert service.resolve_from_text("g=2").genre_key == "slot_result"


def test_genre_service_uses_default_when_not_specified():
    service = GenreService()

    selection = service.resolve_from_text(None)

    assert selection.genre_key == "slot_daily"
    assert selection.genre_label == "稼働日記"


def test_genre_service_rejects_unknown_genre():
    service = GenreService()

    with pytest.raises(UnknownGenreError) as exc_info:
        service.resolve_from_text("abc")

    assert exc_info.value.unknown_values == ["abc"]


def test_genre_service_builds_available_genre_list():
    service = GenreService()

    text = service.available_genres_text()

    assert "1 = slot_daily / 稼働日記" in text
    assert "10 = announcement / 告知" in text


def test_genre_service_resolves_multiple_genres_without_duplicates():
    service = GenreService()

    selection = service.resolve_from_text("1 2,slot_moment/2")

    assert selection.genre_keys == ["slot_daily", "slot_result", "slot_moment"]
    assert selection.genre_label == "稼働日記 / 実戦結果 / 出目・演出"


def test_genre_service_resolves_multiple_assignment_values():
    service = GenreService()

    assert service.resolve_from_text("g=2,3").genre_keys == ["slot_result", "slot_moment"]
    assert service.resolve_from_text("genre=slot_result,slot_moment").genre_keys == [
        "slot_result",
        "slot_moment",
    ]


def test_genre_service_reads_custom_config(tmp_path: Path):
    config_path = tmp_path / "caption_genres.yaml"
    config_path.write_text(
        """
version: 1
default_genre: custom
aliases:
  "1": custom
common_rules:
  language: ja
  platform: x
  max_hashtags: 2
genres:
  custom:
    label: カスタム
    purpose: テスト用
    caption_style:
      - 短く
    cta: false
    hashtags:
      max_count: 2
      candidates:
        - "#test"
""",
        encoding="utf-8",
    )

    service = GenreService(config_path)

    assert service.resolve_from_text("1").genre_key == "custom"
    assert service.available_genres_text() == "1 = custom / カスタム"
