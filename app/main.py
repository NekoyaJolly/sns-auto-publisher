from __future__ import annotations

import logging

from app.config.settings import get_settings
from app.db.session import create_app_engine, create_session_factory, init_db
from app.inputs.telegram_input import TelegramInput
from app.storage.local_storage import LocalStorage
from app.utils.logger import configure_logging

logger = logging.getLogger(__name__)


def bootstrap() -> tuple[LocalStorage, object]:
    settings = get_settings()
    storage = LocalStorage(settings=settings)
    storage.ensure_directories()

    engine = create_app_engine(settings)
    session_factory = create_session_factory(engine)
    init_db(engine)
    logger.info("アプリ基盤の起動確認が完了しました")
    return storage, session_factory


def main() -> None:
    configure_logging()
    settings = get_settings()
    storage, session_factory = bootstrap()
    if not settings.telegram_bot_token:
        logger.info("TELEGRAM_BOT_TOKENが未設定のため、Telegram Botは起動しません")
        return
    TelegramInput(settings=settings, session_factory=session_factory, storage=storage).run_polling()


if __name__ == "__main__":
    main()
