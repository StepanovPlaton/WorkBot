from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from most_bot.bot.handlers import build_application
from most_bot.config import BotConfig, ConfigStore
from most_bot.openproject.client import OpenProjectClient, OpenProjectError
from most_bot.personality import format_projects_message

logger = logging.getLogger(__name__)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def log_startup_projects(client: OpenProjectClient, bot: BotConfig) -> list:
    projects = client.list_projects()
    logger.info("OpenProject connection OK. Projects loaded: %s", len(projects))
    for project in projects:
        logger.info("  - %s (%s)", project.name, project.identifier)
    print(format_projects_message(projects, bot))
    return projects


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Пинг — Telegram-компаньон команды для OpenProject")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    try:
        config = ConfigStore(Path(args.config)).load()
        client = OpenProjectClient(
            base_url=config.openproject.build_base_url(),
            token=config.openproject.token,
            timeout=config.openproject.timeout_seconds,
        )

        logger.info("Starting %s", config.bot.name)
        log_startup_projects(client, config.bot)

        application = build_application(config, client)
        logger.info("Telegram bot is polling...")
        application.run_polling(drop_pending_updates=True)
        return 0

    except KeyboardInterrupt:
        logger.info("Stopped by user.")
        return 130
    except OpenProjectError as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
