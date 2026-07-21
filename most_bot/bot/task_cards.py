from __future__ import annotations

import html
import re

from most_bot.bot.labels import LabelResolver
from most_bot.config import DisplayConfig
from most_bot.openproject.tasks import TaskSummary

MAX_DESCRIPTION_LENGTH = 1200
BOARD_EMOJI = "🗂️"
_IMAGE_PLACEHOLDER_RE = re.compile(r"⟦IMG:(\d+)⟧")


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


def _render_description_html(
    description: str,
    image_urls: tuple[str, ...],
    *,
    attached_indices: set[int],
) -> str:
    """Экранирует текст.

    Успешно вложенные в Telegram картинки убираются.
    Остальные (скачать не удалось) — текст «изображение» без API-ссылки
    (ссылка /api/v3/... без авторизации не открывается).
    """
    parts: list[str] = []
    last = 0
    for match in _IMAGE_PLACEHOLDER_RE.finditer(description):
        parts.append(_escape(description[last:match.start()]))
        idx = int(match.group(1))
        if idx in attached_indices:
            pass
        elif 0 <= idx < len(image_urls):
            parts.append("изображение")
        last = match.end()
    parts.append(_escape(description[last:]))

    text = "".join(parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def format_task_card(
    task: TaskSummary,
    display: DisplayConfig,
    *,
    attached_image_indices: set[int] | None = None,
    expandable_description: bool = True,
) -> str:
    task_url = html.escape(task.web_url, quote=True)
    title_link = f'<a href="{task_url}">{_escape(task.subject)}</a>'
    attached = attached_image_indices or set()
    description = _render_description_html(
        _truncate_description(task.description),
        task.description_image_urls,
        attached_indices=attached,
    )

    lines = [
        f"<b>#{_escape(task.display_id)} · {title_link}</b>",
        _format_context_line(task, display),
        _format_meta_line(task, display),
        _format_people_line(task, display),
    ]
    if description:
        tag = "blockquote expandable" if expandable_description else "blockquote"
        lines.extend(["", f"<{tag}>{description}</{tag.split()[0]}>"])
    return "\n".join(lines)


def format_task_summary_block(
    task: TaskSummary,
    display: DisplayConfig,
    *,
    attached_image_indices: set[int] | None = None,
    expandable_description: bool = True,
) -> str:
    """Компактный блок задачи (для нескольких в одном сообщении) — с описанием."""
    return format_task_card(
        task,
        display,
        attached_image_indices=attached_image_indices,
        expandable_description=expandable_description,
    )


def format_task_cards(
    tasks: list[TaskSummary],
    display: DisplayConfig,
    *,
    attached_image_indices: set[int] | None = None,
    expandable_description: bool = True,
) -> str:
    if not tasks:
        return ""
    if len(tasks) == 1:
        return format_task_card(
            tasks[0],
            display,
            attached_image_indices=attached_image_indices,
            expandable_description=expandable_description,
        )
    return "\n\n".join(
        format_task_summary_block(
            task,
            display,
            expandable_description=expandable_description,
        )
        for task in tasks
    )
