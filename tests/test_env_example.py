from pathlib import Path


REQUIRED_KEYS = {
    "APP_ENV",
    "POSTING_MODE",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_CHAT_IDS",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
    "X_BEARER_TOKEN",
    "DATABASE_URL",
    "STORAGE_ROOT",
    "MAX_IMAGE_SIZE_MB",
    "MAX_VIDEO_SIZE_MB",
    "MAX_VIDEO_DURATION_SECONDS",
}

SECRET_KEYS = {
    "TELEGRAM_BOT_TOKEN",
    "OPENAI_API_KEY",
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_TOKEN_SECRET",
    "X_BEARER_TOKEN",
}


def test_env_example_contains_required_keys_and_no_dummy_secrets():
    values = _read_env_example(Path(".env.example"))

    assert REQUIRED_KEYS <= values.keys()
    assert values["APP_ENV"] == "local"
    assert values["POSTING_MODE"] == "approval"
    assert values["OPENAI_MODEL"] == ""
    assert values["DATABASE_URL"] == "sqlite:///data/app.sqlite3"
    assert values["STORAGE_ROOT"] == "storage"
    for key in SECRET_KEYS:
        assert values[key] == ""


def _read_env_example(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, value = stripped.split("=", maxsplit=1)
        values[key] = value
    return values
