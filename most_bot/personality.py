from __future__ import annotations

import random

from most_bot.config import BotConfig


def _pick(items: list[str], *, fallback: str) -> str:
    return random.choice(items) if items else fallback


def build_start_message(bot: BotConfig) -> str:
    text = bot.start_commands.strip()
    if not text:
        return f"{bot.emoji} {bot.name}".strip() if bot.emoji else bot.name
    prefix = f"{bot.emoji} " if bot.emoji else ""
    return f"{prefix}{text}" if prefix else text


def build_unknown_command_message(bot: BotConfig) -> str:
    return _pick(bot.unknown_command_replies, fallback="Не понял. Напиши #номер задачи или /chatinfo.")


def build_access_denied_message(bot: BotConfig) -> str:
    return _pick(bot.access_denied_replies, fallback="Доступ только для участников команды.")


def build_projects_intro(bot: BotConfig) -> str:
    return _pick(bot.projects_intros, fallback="Проекты в OpenProject:")


def format_projects_message(projects: list, bot: BotConfig) -> str:
    if not projects:
        return bot.empty_projects_message

    lines = [build_projects_intro(bot), ""]
    for index, project in enumerate(projects, start=1):
        lines.append(f"{index}. {project.name} ({project.identifier})")
    lines.append("")
    lines.append(f"Всего: {len(projects)}")
    return "\n".join(lines)
