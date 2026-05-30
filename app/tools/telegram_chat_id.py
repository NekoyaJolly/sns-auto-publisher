from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, IO, Protocol

from dotenv import dotenv_values


class TelegramChatIdToolError(Exception):
    pass


@dataclass(frozen=True)
class ChatIdentity:
    chat_id: str
    user_id: str | None = None


class TelegramApi(Protocol):
    def get_me(self) -> Mapping[str, Any]:
        pass

    def delete_webhook(self) -> Mapping[str, Any]:
        pass

    def get_updates(self, *, offset: int | None = None) -> list[Mapping[str, Any]]:
        pass


class TelegramApiClient:
    def __init__(self, token: str, *, base_url: str = "https://api.telegram.org") -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")

    def get_me(self) -> Mapping[str, Any]:
        return self._request("getMe")

    def delete_webhook(self) -> Mapping[str, Any]:
        return self._request("deleteWebhook", {"drop_pending_updates": "false"})

    def get_updates(self, *, offset: int | None = None) -> list[Mapping[str, Any]]:
        params: dict[str, str] = {"timeout": "0"}
        if offset is not None:
            params["offset"] = str(offset)
        payload = self._request("getUpdates", params)
        result = payload.get("result")
        if not isinstance(result, list):
            raise TelegramChatIdToolError("Telegram getUpdatesの応答形式が不正です。")
        return [update for update in result if isinstance(update, Mapping)]

    def _request(self, method: str, params: Mapping[str, str] | None = None) -> Mapping[str, Any]:
        url = f"{self.base_url}/bot{self.token}/{method}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        context = _ssl_context()
        try:
            with urllib.request.urlopen(url, timeout=15, context=context) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            description = _telegram_error_description(body)
            detail = f"HTTP {exc.code}"
            if description:
                detail = f"{detail}: {description}"
            raise TelegramChatIdToolError(f"Telegram Bot APIの呼び出しに失敗しました: {method} ({detail})") from exc
        except URLError as exc:
            reason = str(exc.reason)
            raise TelegramChatIdToolError(f"Telegram Bot APIの呼び出しに失敗しました: {method} ({reason})") from exc
        except Exception as exc:
            raise TelegramChatIdToolError(
                f"Telegram Bot APIの呼び出しに失敗しました: {method} ({exc.__class__.__name__})"
            ) from exc

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise TelegramChatIdToolError("Telegram Bot APIの応答JSONを解析できませんでした。") from exc

        if not isinstance(payload, Mapping):
            raise TelegramChatIdToolError("Telegram Bot APIの応答形式が不正です。")
        if not payload.get("ok"):
            description = payload.get("description") or "TokenまたはBot API応答を確認してください。"
            raise TelegramChatIdToolError(f"Telegram Bot APIがエラーを返しました: {description}")
        return payload


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _telegram_error_description(body: str) -> str | None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping):
        return None
    description = payload.get("description")
    return str(description) if description else None


def load_telegram_bot_token(env_path: Path) -> str:
    if not env_path.exists():
        raise TelegramChatIdToolError(".env が見つかりません。先に cp .env.example .env を実行してください。")
    values = dotenv_values(env_path)
    token = str(values.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise TelegramChatIdToolError(".env に TELEGRAM_BOT_TOKEN を設定してください。")
    return token


def extract_chat_identity(update: Mapping[str, Any]) -> ChatIdentity | None:
    candidates = [
        update.get("message"),
        update.get("edited_message"),
        update.get("channel_post"),
        update.get("edited_channel_post"),
        update.get("my_chat_member"),
    ]
    callback_query = update.get("callback_query")
    if isinstance(callback_query, Mapping):
        candidates.append(callback_query.get("message"))

    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        chat = candidate.get("chat")
        if not isinstance(chat, Mapping) or chat.get("id") is None:
            continue
        user = candidate.get("from")
        if not isinstance(user, Mapping) and isinstance(callback_query, Mapping):
            user = callback_query.get("from")
        user_id = str(user.get("id")) if isinstance(user, Mapping) and user.get("id") is not None else None
        return ChatIdentity(chat_id=str(chat["id"]), user_id=user_id)
    return None


def wait_for_chat_identity(
    api: TelegramApi,
    *,
    timeout_seconds: int,
    poll_interval_seconds: float,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> ChatIdentity | None:
    deadline = monotonic_fn() + timeout_seconds
    offset: int | None = None

    while monotonic_fn() <= deadline:
        updates = api.get_updates(offset=offset)
        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                offset = update_id + 1
            identity = extract_chat_identity(update)
            if identity is not None:
                return identity
        if monotonic_fn() >= deadline:
            break
        sleep_fn(poll_interval_seconds)
    return None


def update_allowed_chat_ids(env_path: Path, chat_id: str) -> str:
    lines = env_path.read_text(encoding="utf-8").splitlines()
    key = "TELEGRAM_ALLOWED_CHAT_IDS"
    updated_lines: list[str] = []
    found = False
    updated_value = chat_id

    for line in lines:
        if line.startswith(f"{key}="):
            found = True
            current_value = line.split("=", maxsplit=1)[1]
            values = []
            for value in [item.strip() for item in current_value.split(",") if item.strip()]:
                if value not in values:
                    values.append(value)
            if chat_id not in values:
                values.append(chat_id)
            updated_value = ",".join(values)
            updated_lines.append(f"{key}={updated_value}")
        else:
            updated_lines.append(line)

    if not found:
        if updated_lines and updated_lines[-1] != "":
            updated_lines.append("")
        updated_lines.append(f"{key}={chat_id}")

    env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    return updated_value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Telegram Botのchat_idを取得します。")
    parser.add_argument("--write-env", action="store_true", help=".env の TELEGRAM_ALLOWED_CHAT_IDS を更新します。")
    parser.add_argument("--timeout", type=int, default=120, help="chat_id検出を待つ最大秒数です。")
    parser.add_argument("--poll-interval", type=float, default=2, help="getUpdatesを確認する間隔秒です。")
    parser.add_argument(
        "--clear-webhook",
        action="store_true",
        help="deleteWebhook?drop_pending_updates=false を実行してからgetUpdatesします。",
    )
    return parser


def run(
    argv: list[str] | None = None,
    *,
    env_path: Path = Path(".env"),
    client_factory: Callable[[str], TelegramApi] = TelegramApiClient,
    output: IO[str] = sys.stdout,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> int:
    args = build_parser().parse_args(argv)

    try:
        token = load_telegram_bot_token(env_path)
        api = client_factory(token)
        api.get_me()
        print("Telegram Bot Tokenを確認しました。", file=output)
        if args.clear_webhook:
            api.delete_webhook()
            print("Webhookを解除しました。", file=output)

        print("Telegramで対象Botに /start または test を送ってください。", file=output)
        print(f"最大{args.timeout}秒待機します...", file=output)
        print("すでに python -m app.main でBotが起動中の場合、updatesが先に消費されることがあります。", file=output)

        identity = wait_for_chat_identity(
            api,
            timeout_seconds=args.timeout,
            poll_interval_seconds=args.poll_interval,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
        )
        if identity is None:
            print("chat_idを検出できませんでした。", file=output)
            print("Botに /start または test を送ってから再実行してください。", file=output)
            print("Botが起動中の場合は停止してから再実行してください。", file=output)
            return 1

        print("chat_id を検出しました。", file=output)
        print(f"chat_id={identity.chat_id}", file=output)
        if identity.user_id is not None:
            print(f"user_id={identity.user_id}", file=output)

        if args.write_env:
            updated_value = update_allowed_chat_ids(env_path, identity.chat_id)
            print(".env を更新しました。", file=output)
            print(f"TELEGRAM_ALLOWED_CHAT_IDS={updated_value}", file=output)

        print("次に python -m app.main でBotを起動してください。", file=output)
        return 0
    except TelegramChatIdToolError as exc:
        print(str(exc), file=output)
        return 1


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
