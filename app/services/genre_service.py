from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.db.models import PostJob


@dataclass(frozen=True)
class GenreHashtagRules:
    max_count: int
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class CaptionGenre:
    key: str
    label: str
    purpose: str
    caption_style: tuple[str, ...]
    cta: bool
    hashtags: GenreHashtagRules
    avoid: tuple[str, ...] = ()


@dataclass(frozen=True)
class GenreSelection:
    genres: tuple[CaptionGenre, ...]

    @property
    def genre_keys(self) -> list[str]:
        return [genre.key for genre in self.genres]

    @property
    def genre_labels(self) -> list[str]:
        return [genre.label for genre in self.genres]

    @property
    def genre_key(self) -> str:
        return ",".join(self.genre_keys)

    @property
    def genre_label(self) -> str:
        return " / ".join(self.genre_labels)


class UnknownGenreError(ValueError):
    def __init__(self, unknown_values: list[str]) -> None:
        self.unknown_values = unknown_values
        super().__init__(f"不明なジャンルです: {', '.join(unknown_values)}")


class GenreService:
    separator_pattern = re.compile(r"[\s,、/]+")
    prefix_pattern = re.compile(r"^\s*(?:genre|g)\s*=\s*(.+)\s*$", re.IGNORECASE | re.DOTALL)

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or Path(__file__).resolve().parents[2] / "config" / "caption_genres.yaml"
        self._settings = self._load_settings()

    @property
    def default_genre(self) -> str:
        return str(self._settings["default_genre"])

    @property
    def aliases(self) -> dict[str, str]:
        return dict(self._settings["aliases"])

    @property
    def common_rules(self) -> dict[str, Any]:
        return dict(self._settings["common_rules"])

    @property
    def genres(self) -> dict[str, CaptionGenre]:
        return dict(self._settings["genres"])

    def resolve_from_text(self, caption_text: str | None) -> GenreSelection:
        tokens = self.extract_genre_tokens(caption_text)
        if not tokens:
            tokens = [self.default_genre]
        return self.resolve_tokens(tokens)

    def resolve_for_post_job(self, post_job: PostJob) -> GenreSelection:
        return self.resolve_from_text(post_job.genre_key)

    def extract_genre_tokens(self, caption_text: str | None) -> list[str]:
        text = (caption_text or "").strip()
        if not text:
            return []
        match = self.prefix_pattern.match(text)
        value = match.group(1) if match else text
        return [token.strip() for token in self.separator_pattern.split(value) if token.strip()]

    def resolve_tokens(self, tokens: list[str]) -> GenreSelection:
        selected: list[CaptionGenre] = []
        unknown: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            genre_key = self.aliases.get(token, token)
            genre = self.genres.get(genre_key)
            if genre is None:
                unknown.append(token)
                continue
            if genre.key in seen:
                continue
            selected.append(genre)
            seen.add(genre.key)
        if unknown:
            raise UnknownGenreError(unknown)
        return GenreSelection(genres=tuple(selected))

    def build_caption_instruction(self, selection: GenreSelection) -> str:
        lines = [
            "ジャンル指定:",
            f"- genre_key: {selection.genre_key}",
            f"- genre_label: {selection.genre_label}",
            "",
            "共通ルール:",
            f"- language: {self.common_rules.get('language', 'ja')}",
            f"- platform: {self.common_rules.get('platform', 'x')}",
            f"- max_hashtags: {self.max_hashtags_for_selection(selection)}",
            "- avoid:",
            *[f"  - {item}" for item in self.common_rules.get("avoid", [])],
            "- style:",
            *[f"  - {item}" for item in self.common_rules.get("style", [])],
            "",
            "選択ジャンル別ルール:",
        ]
        for genre in selection.genres:
            lines.extend(
                [
                    f"- key: {genre.key}",
                    f"  label: {genre.label}",
                    f"  purpose: {genre.purpose}",
                    f"  cta: {str(genre.cta).lower()}",
                    "  caption_style:",
                    *[f"    - {item}" for item in genre.caption_style],
                    "  hashtag_candidates:",
                    *[f"    - {candidate}" for candidate in genre.hashtags.candidates],
                    f"  hashtag_max_count: {genre.hashtags.max_count}",
                ]
            )
            if genre.avoid:
                lines.extend(["  avoid:", *[f"    - {item}" for item in genre.avoid]])
        lines.extend(
            [
                "",
                "生成ルール:",
                "- 選択ジャンルが複数ある場合は、すべてのpurposeとcaption_styleを自然に統合する",
                "- ハッシュタグ候補は固定挿入ではなく、画像/動画内容に合う場合だけ優先候補として扱う",
                "- hashtagsはmax_hashtagsを超えない",
                "- 勝てる、稼げる、確実、鉄板、保証などの断定表現は禁止",
                "- 設定投入や高設定を根拠なく断定しない",
                "- 過度に射幸心を煽らない",
                "- 画像/動画にない内容を断定しない",
            ]
        )
        return "\n".join(lines)

    def build_caption_instruction_for_post_job(self, post_job: PostJob) -> str:
        return self.build_caption_instruction(self.resolve_for_post_job(post_job))

    def max_hashtags_for_selection(self, selection: GenreSelection) -> int:
        common_max = int(self.common_rules.get("max_hashtags", 4))
        if not selection.genres:
            return common_max
        genre_max = max(genre.hashtags.max_count for genre in selection.genres)
        return min(common_max, genre_max)

    def max_hashtags_for_post_job(self, post_job: PostJob) -> int:
        return self.max_hashtags_for_selection(self.resolve_for_post_job(post_job))

    def available_genres_text(self) -> str:
        lines: list[str] = []
        for alias, genre_key in sorted(self.aliases.items(), key=lambda item: self._alias_sort_key(item[0])):
            genre = self.genres.get(genre_key)
            if genre is None:
                continue
            lines.append(f"{alias} = {genre.key} / {genre.label}")
        return "\n".join(lines)

    def unknown_genre_message(self, error: UnknownGenreError) -> str:
        unknown = ", ".join(error.unknown_values)
        return f"不明なジャンルです: {unknown}\n\n利用可能ジャンル:\n{self.available_genres_text()}"

    def _load_settings(self) -> dict[str, Any]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"captionジャンル設定が見つかりません: {self.config_path}")
        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        aliases = {str(key): str(value) for key, value in dict(raw.get("aliases") or {}).items()}
        genres = {
            key: self._parse_genre(key, value)
            for key, value in dict(raw.get("genres") or {}).items()
        }
        default_genre = str(raw.get("default_genre") or "")
        if default_genre not in genres:
            raise ValueError("default_genreがgenresに存在しません")
        for alias, genre_key in aliases.items():
            if genre_key not in genres:
                raise ValueError(f"aliasesの参照先genreが存在しません: {alias}={genre_key}")
        return {
            "default_genre": default_genre,
            "aliases": aliases,
            "common_rules": dict(raw.get("common_rules") or {}),
            "genres": genres,
        }

    @staticmethod
    def _parse_genre(key: str, raw: dict[str, Any]) -> CaptionGenre:
        hashtag_raw = dict(raw.get("hashtags") or {})
        return CaptionGenre(
            key=key,
            label=str(raw.get("label") or key),
            purpose=str(raw.get("purpose") or ""),
            caption_style=tuple(str(item) for item in raw.get("caption_style") or []),
            cta=bool(raw.get("cta", False)),
            hashtags=GenreHashtagRules(
                max_count=int(hashtag_raw.get("max_count", 0)),
                candidates=tuple(str(item) for item in hashtag_raw.get("candidates") or []),
            ),
            avoid=tuple(str(item) for item in raw.get("avoid") or []),
        )

    @staticmethod
    def _alias_sort_key(alias: str) -> tuple[int, int | str]:
        return (0, int(alias)) if alias.isdigit() else (1, alias)
