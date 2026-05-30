from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from dotenv import dotenv_values

from app.db.models import PostingMode


SECRET_KEYS = {
    "TELEGRAM_BOT_TOKEN",
    "OPENAI_API_KEY",
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
    "X_BEARER_TOKEN",
}

COMMON_REQUIRED_KEYS = [
    "TELEGRAM_BOT_TOKEN",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
]

X_REQUIRED_KEYS = [
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
]


@dataclass(frozen=True)
class EnvCheckItem:
    key: str
    is_required: bool
    is_set: bool
    reason: str | None = None


@dataclass(frozen=True)
class EnvCheckResult:
    env_path: Path
    posting_mode: str
    items: list[EnvCheckItem]
    error_message: str | None = None

    @property
    def is_success(self) -> bool:
        if self.error_message is not None:
            return False
        return all(item.is_set for item in self.items if item.is_required)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=".env のMVP検収向け設定を安全に確認します。")
    parser.add_argument("--env-file", default=".env", help="確認する.envファイルのパスです。")
    return parser


def check_env(env_path: Path) -> EnvCheckResult:
    if not env_path.exists():
        return EnvCheckResult(
            env_path=env_path,
            posting_mode=PostingMode.APPROVAL.value,
            items=[],
            error_message=".env が見つかりません。先に cp .env.example .env を実行してください。",
        )

    values = dotenv_values(env_path)
    posting_mode = str(values.get("POSTING_MODE") or PostingMode.APPROVAL.value).strip()
    allowed_modes = {mode.value for mode in PostingMode}
    if posting_mode not in allowed_modes:
        return EnvCheckResult(
            env_path=env_path,
            posting_mode=posting_mode,
            items=[],
            error_message="POSTING_MODE は approval / auto / dry_run のいずれかを指定してください。",
        )

    required_keys = list(COMMON_REQUIRED_KEYS)
    items: list[EnvCheckItem] = [
        EnvCheckItem(key=key, is_required=True, is_set=_is_set(values.get(key)))
        for key in required_keys
    ]

    if posting_mode in {PostingMode.APPROVAL.value, PostingMode.AUTO.value}:
        items.extend(
            EnvCheckItem(key=key, is_required=True, is_set=_is_set(values.get(key)))
            for key in X_REQUIRED_KEYS
        )
    else:
        items.extend(
            EnvCheckItem(
                key=key,
                is_required=False,
                is_set=_is_set(values.get(key)),
                reason="dry_runでは任意です",
            )
            for key in X_REQUIRED_KEYS
        )

    items.append(
        EnvCheckItem(
            key="TELEGRAM_ALLOWED_CHAT_IDS",
            is_required=False,
            is_set=_is_set(values.get("TELEGRAM_ALLOWED_CHAT_IDS")),
            reason="未設定の場合はすべてのchat_idを許可します",
        )
    )
    return EnvCheckResult(env_path=env_path, posting_mode=posting_mode, items=items)


def print_result(result: EnvCheckResult, output: IO[str]) -> None:
    if result.error_message:
        print(result.error_message, file=output)
        return

    print(".env を確認しました。", file=output)
    print(f"POSTING_MODE={result.posting_mode}", file=output)
    print("秘密情報の値は表示しません。設定済み/未設定のみ表示します。", file=output)
    for item in result.items:
        label = "必須" if item.is_required else "任意"
        state = "設定済み" if item.is_set else "未設定"
        suffix = f" ({item.reason})" if item.reason else ""
        print(f"- {item.key}: {state} / {label}{suffix}", file=output)

    if result.is_success:
        print("MVP検収に必要な環境変数は揃っています。", file=output)
    else:
        print("必須の環境変数が不足しています。.env を更新してください。", file=output)


def run(argv: list[str] | None = None, *, output: IO[str] = sys.stdout) -> int:
    args = build_parser().parse_args(argv)
    result = check_env(Path(args.env_file))
    print_result(result, output)
    return 0 if result.is_success else 1


def _is_set(value: object) -> bool:
    return bool(str(value or "").strip())


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
