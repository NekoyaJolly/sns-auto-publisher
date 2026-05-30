from io import StringIO
from pathlib import Path

from app.tools.check_env import check_env, run


def test_check_env_allows_dry_run_without_x_keys(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "POSTING_MODE=dry_run",
                "TELEGRAM_BOT_TOKEN=telegram-secret",
                "OPENAI_API_KEY=openai-secret",
                "X_API_KEY=",
                "X_API_SECRET=",
                "X_ACCESS_TOKEN=",
                "X_ACCESS_TOKEN_SECRET=",
            ]
        ),
        encoding="utf-8",
    )

    result = check_env(env_path)

    assert result.is_success is True
    assert result.posting_mode == "dry_run"


def test_check_env_requires_x_keys_for_approval(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "POSTING_MODE=approval",
                "TELEGRAM_BOT_TOKEN=telegram-secret",
                "OPENAI_API_KEY=openai-secret",
                "X_API_KEY=",
                "X_API_SECRET=x-secret",
                "X_ACCESS_TOKEN=x-token",
                "X_ACCESS_TOKEN_SECRET=x-token-secret",
            ]
        ),
        encoding="utf-8",
    )

    result = check_env(env_path)

    assert result.is_success is False
    assert any(item.key == "X_API_KEY" and item.is_required and not item.is_set for item in result.items)


def test_check_env_requires_x_keys_for_auto(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "POSTING_MODE=auto",
                "TELEGRAM_BOT_TOKEN=telegram-secret",
                "OPENAI_API_KEY=openai-secret",
                "X_API_KEY=x-key",
                "X_API_SECRET=x-secret",
                "X_ACCESS_TOKEN=x-token",
                "X_ACCESS_TOKEN_SECRET=",
            ]
        ),
        encoding="utf-8",
    )

    result = check_env(env_path)

    assert result.is_success is False
    assert any(item.key == "X_ACCESS_TOKEN_SECRET" and item.is_required and not item.is_set for item in result.items)


def test_check_env_output_masks_secret_values(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "POSTING_MODE=dry_run",
                "TELEGRAM_BOT_TOKEN=telegram-secret",
                "OPENAI_API_KEY=openai-secret",
                "X_API_KEY=x-key",
            ]
        ),
        encoding="utf-8",
    )
    output = StringIO()

    exit_code = run(["--env-file", str(env_path)], output=output)
    text = output.getvalue()

    assert exit_code == 0
    assert "TELEGRAM_BOT_TOKEN: 設定済み" in text
    assert "OPENAI_API_KEY: 設定済み" in text
    assert "telegram-secret" not in text
    assert "openai-secret" not in text
    assert "x-key" not in text


def test_check_env_reports_missing_env_file(tmp_path: Path):
    output = StringIO()

    exit_code = run(["--env-file", str(tmp_path / ".env")], output=output)

    assert exit_code == 1
    assert ".env が見つかりません" in output.getvalue()


def test_check_env_rejects_invalid_posting_mode(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "POSTING_MODE=invalid",
                "TELEGRAM_BOT_TOKEN=telegram-secret",
                "OPENAI_API_KEY=openai-secret",
            ]
        ),
        encoding="utf-8",
    )

    result = check_env(env_path)

    assert result.is_success is False
    assert result.error_message is not None
    assert "POSTING_MODE" in result.error_message
