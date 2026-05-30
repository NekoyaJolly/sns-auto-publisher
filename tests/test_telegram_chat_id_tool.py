from io import StringIO
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError

from app.tools.telegram_chat_id import (
    ChatIdentity,
    TelegramChatIdToolError,
    TelegramApiClient,
    extract_chat_identity,
    load_telegram_bot_token,
    run,
    update_allowed_chat_ids,
)


class FakeTelegramApi:
    def __init__(self, updates: list[Mapping[str, Any]] | None = None, *, fail_get_me: bool = False) -> None:
        self.updates = updates or []
        self.fail_get_me = fail_get_me
        self.delete_webhook_called = False

    def get_me(self) -> Mapping[str, Any]:
        if self.fail_get_me:
            raise TelegramChatIdToolError("Telegram Bot APIがエラーを返しました: Unauthorized")
        return {"ok": True, "result": {"id": 1, "is_bot": True}}

    def delete_webhook(self) -> Mapping[str, Any]:
        self.delete_webhook_called = True
        return {"ok": True, "result": True}

    def get_updates(self, *, offset: int | None = None) -> list[Mapping[str, Any]]:
        return self.updates


def test_load_telegram_bot_token_from_env(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("TELEGRAM_BOT_TOKEN=secret-token\n", encoding="utf-8")

    assert load_telegram_bot_token(env_path) == "secret-token"


def test_run_returns_safe_error_when_token_missing(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("TELEGRAM_BOT_TOKEN=\n", encoding="utf-8")
    output = StringIO()

    exit_code = run([], env_path=env_path, client_factory=lambda token: FakeTelegramApi(), output=output)

    assert exit_code == 1
    assert "TELEGRAM_BOT_TOKEN" in output.getvalue()
    assert "secret" not in output.getvalue()


def test_extract_chat_identity_from_update_json():
    update = {
        "update_id": 100,
        "message": {
            "chat": {"id": 123456789},
            "from": {"id": 987654321},
            "text": "/start",
        },
    }

    identity = extract_chat_identity(update)

    assert identity == ChatIdentity(chat_id="123456789", user_id="987654321")


def test_run_write_env_updates_allowed_chat_ids(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("TELEGRAM_BOT_TOKEN=secret-token\nTELEGRAM_ALLOWED_CHAT_IDS=\n", encoding="utf-8")
    output = StringIO()
    updates = [
        {
            "update_id": 1,
            "message": {
                "chat": {"id": 123456789},
                "from": {"id": 987654321},
                "text": "test",
            },
        }
    ]

    exit_code = run(
        ["--write-env", "--timeout", "1", "--poll-interval", "0"],
        env_path=env_path,
        client_factory=lambda token: FakeTelegramApi(updates),
        output=output,
        sleep_fn=lambda seconds: None,
    )

    assert exit_code == 0
    assert "TELEGRAM_ALLOWED_CHAT_IDS=123456789" in env_path.read_text(encoding="utf-8")
    assert "chat_id=123456789" in output.getvalue()
    assert "user_id=987654321" in output.getvalue()
    assert "secret-token" not in output.getvalue()


def test_update_allowed_chat_ids_does_not_duplicate_existing_values(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "TELEGRAM_BOT_TOKEN=secret-token\nTELEGRAM_ALLOWED_CHAT_IDS=111,123456789,111\n",
        encoding="utf-8",
    )

    updated_value = update_allowed_chat_ids(env_path, "123456789")

    assert updated_value == "111,123456789"
    assert "TELEGRAM_ALLOWED_CHAT_IDS=111,123456789\n" in env_path.read_text(encoding="utf-8")


def test_run_does_not_print_token_when_api_fails(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("TELEGRAM_BOT_TOKEN=secret-token\n", encoding="utf-8")
    output = StringIO()

    exit_code = run([], env_path=env_path, client_factory=lambda token: FakeTelegramApi(fail_get_me=True), output=output)

    assert exit_code == 1
    assert "Unauthorized" in output.getvalue()
    assert "secret-token" not in output.getvalue()


def test_api_client_reports_http_error_without_token(monkeypatch):
    def fake_urlopen(url: str, timeout: int, context):
        raise HTTPError(
            url=url,
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=FakeHttpErrorBody(b'{"ok":false,"description":"Unauthorized"}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    try:
        TelegramApiClient("secret-token").get_me()
    except TelegramChatIdToolError as exc:
        message = str(exc)
    else:
        raise AssertionError("HTTPErrorはTelegramChatIdToolErrorに変換する必要があります")

    assert "HTTP 401" in message
    assert "Unauthorized" in message
    assert "secret-token" not in message


def test_api_client_reports_network_error_without_token(monkeypatch):
    def fake_urlopen(url: str, timeout: int, context):
        raise URLError("temporary failure in name resolution")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    try:
        TelegramApiClient("secret-token").get_me()
    except TelegramChatIdToolError as exc:
        message = str(exc)
    else:
        raise AssertionError("URLErrorはTelegramChatIdToolErrorに変換する必要があります")

    assert "temporary failure" in message
    assert "secret-token" not in message


class FakeHttpErrorBody:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def close(self) -> None:
        pass
