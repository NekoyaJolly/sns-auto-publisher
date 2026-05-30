import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.config.settings import Settings
from app.db.session import create_app_engine, create_session_factory, init_db
from app.inputs.telegram_input import TelegramInput
from app.storage.local_storage import LocalStorage


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, object | None]] = []

    async def send_message(self, chat_id: str, text: str, reply_markup: object | None = None) -> None:
        self.messages.append((chat_id, text, reply_markup))


def test_whoami_returns_chat_id_and_user_id_even_when_not_allowed(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'app.sqlite3'}",
        storage_root=tmp_path / "storage",
        telegram_allowed_chat_ids=["99999"],
    )
    engine = create_app_engine(settings)
    init_db(engine)
    telegram_input = TelegramInput(
        settings=settings,
        session_factory=create_session_factory(engine),
        storage=LocalStorage(settings=settings),
    )
    bot = FakeBot()
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=12345), effective_user=SimpleNamespace(id=67890))

    asyncio.run(telegram_input.handle_whoami_command(update, SimpleNamespace(bot=bot)))

    assert bot.messages == [("12345", "chat_id=12345\nuser_id=67890", None)]
