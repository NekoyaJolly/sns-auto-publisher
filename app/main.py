from __future__ import annotations

import logging

from app.config.settings import get_settings
from app.db.session import create_app_engine, create_session_factory, init_db
from app.storage.local_storage import LocalStorage
from app.utils.logger import configure_logging

logger = logging.getLogger(__name__)


def bootstrap() -> None:
    settings = get_settings()
    storage = LocalStorage(settings=settings)
    storage.ensure_directories()

    engine = create_app_engine(settings)
    create_session_factory(engine)
    init_db(engine)
    logger.info("アプリ基盤の起動確認が完了しました")


def main() -> None:
    configure_logging()
    bootstrap()


if __name__ == "__main__":
    main()
