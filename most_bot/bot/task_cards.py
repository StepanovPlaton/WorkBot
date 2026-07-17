from __future__ import annotations

import html

from most_bot.bot.labels import LabelResolver
from most_bot.config import DisplayConfig
from most_bot.openproject.tasks import TaskSummary

MAX_DESCRIPTION_LENGTH = 1200
BOARD_EMOJI = "🗂️"


class EmojiResolver:
    def __init__(self, display: DisplayConfig) -> None:
        self.display = display

    def project(self, project_identifier: str) -> str:
        return self._lookup(self.display.emojis.projects, project_identifier)

    def department(self, department_key: str) -> str:
        if not department_key:
            return ""
        return self._lookup_optional(self.display.emojis.departments, department_key)

    def status(self, status_name: str) -> str:
        return self._lookup(self.display.emojis.statuses, status_name)

    def task_type(self, task_type: str) -> str:
        return self._lookup(self.display.emojis.types, task_type)

    def priority(self, priority_name: str) -> str:
        return self._lookup(self.display.emojis.priorities, priority_name)

    def _lookup(self, mapping: dict[str, str], key: str) -> str:
        if not key:
            return self.display.emojis.default
        emoji = self._lookup_optional(mapping, key)
        return emoji or self.display.emojis.default

    @staticmethod
    def _lookup_optional(mapping: dict[str, str], key: str) -> str:
        normalized = _normalize_key(key)
        for map_key, emoji in mapping.items():
            if _normalize_key(map_key) == normalized:
                return emoji
        return ""


def _normalize_key(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _escape(value: str) -> str:
    return html.escape(value, quote=False)


def _truncate_description(value: str, *, limit: int = MAX_DESCRIPTION_LENGTH) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _format_points(value: float | None) -> str:
    if value is None:
        return "—"
    if value.is_integer():
        return str(int(value))
    return str(value).rstrip("0").rstrip(".")


def _format_assignee(task: TaskSummary, display: DisplayConfig) -> str:
    if task.assignee == "Не назначен":
        return _escape(task.assignee)

    username = display.resolve_telegram_username(task.assignee)
    if not username:
        return _escape(task.assignee)

    url = html.escape(f"https://t.me/{username}", quote=True)
    return f'<a href="{url}">{_escape(task.assignee)}</a>'


def _join_parts(parts: list[str]) -> str:
    return " · ".join(part for part in parts if part)


def _format_context_line(task: TaskSummary, display: DisplayConfig) -> str:
    """Проект · Доска · Отдел"""
    emojis = EmojiResolver(display)
    labels = LabelResolver(display)

    parts = [f"{emojis.project(task.project_identifier)} {_escape(task.project_name)}"]

    if task.board_name:
        parts.append(f"{BOARD_EMOJI} {_escape(task.board_name)}")

    department_name = labels.department(task.department_key)
    if department_name:
        department_emoji = emojis.department(task.department_key)
        prefix = f"{department_emoji} " if department_emoji else ""
        parts.append(f"{prefix}{_escape(department_name)}")

    return _join_parts(parts)


def _format_meta_line(task: TaskSummary, display: DisplayConfig) -> str:
    """Тип · Приоритет · Столбец (срок)"""
    emojis = EmojiResolver(display)
    labels = LabelResolver(display)

    return _join_parts(
        [
            f"{emojis.task_type(task.task_type)} {_escape(labels.task_type(task.task_type))}",
            f"{emojis.priority(task.priority_name)} {_escape(labels.priority(task.priority_name))}",
            (
                f"{emojis.status(task.status_name)} {_escape(task.status_name)} "
                f"({_escape(task.status_duration_text)})"
            ),
        ]
    )


def _format_people_line(task: TaskSummary, display: DisplayConfig) -> str:
    """👤 Назначенный · 📊 Очки — только иконки, без подписей."""
    return _join_parts(
        [
            f"👤 {_format_assignee(task, display)}",
            f"📊 {_format_points(task.story_points)}",
        ]
    )


def format_task_card(task: TaskSummary, display: DisplayConfig) -> str:
    task_url = html.escape(task.web_url, quote=True)
    title_link = f'<a href="{task_url}">{_escape(task.subject)}</a>'
    description = _truncate_description(task.description)

    lines = [
        f"<b>#{_escape(task.display_id)} · {title_link}</b>",
        _format_context_line(task, display),
        _format_meta_line(task, display),
        _format_people_line(task, display),
    ]
    if description:
        lines.extend(["", f"<blockquote expandable>{_escape(description)}</blockquote>"])
    return "\n".join(lines)


def format_task_summary_block(task: TaskSummary, display: DisplayConfig) -> str:
    """Компактный блок задачи (для нескольких в одном сообщении) — с описанием."""
    return format_task_card(task, display)


def format_task_cards(tasks: list[TaskSummary], display: DisplayConfig) -> str:
    if not tasks:
        return ""
    if len(tasks) == 1:
        return format_task_card(tasks[0], display)
    return "\n\n".join(format_task_summary_block(task, display) for task in tasks)
