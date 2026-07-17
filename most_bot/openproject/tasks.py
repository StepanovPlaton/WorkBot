from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from most_bot.config import DisplayConfig
from most_bot.openproject.boards import resolve_board
from most_bot.openproject.client import OpenProjectClient, OpenProjectError
from most_bot.openproject.status_history import find_last_transition_to_status_at, parse_activity_timestamp


@dataclass(frozen=True)
class TaskSummary:
    work_package_id: str
    display_id: str
    subject: str
    description: str
    task_type: str
    priority_name: str
    status_name: str
    status_duration_text: str
    assignee: str
    assignee_id: str | None
    story_points: float | None
    project_identifier: str
    project_name: str
    department_key: str
    board_id: str | None
    board_name: str | None
    web_url: str


def _link_title(work_package: dict[str, Any], key: str, *, fallback: str = "—") -> str:
    link = work_package.get("_links", {}).get(key, {})
    if isinstance(link, dict):
        title = link.get("title")
        if title:
            return str(title).strip()
    return fallback


def _markdown_raw_to_plain(value: str) -> str:
    text = html.unescape(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = text.replace("\\*", "*")
    return text


def _html_to_plain_text(value: str) -> str:
    text = html.unescape(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>\s*", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</div>\s*", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>\s*", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "• ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def _finalize_description_text(value: str) -> str:
    """Сохраняет переносы строк и абзацы, убирает лишние пробелы."""
    lines = [" ".join(line.split()) for line in value.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_description(work_package: dict[str, Any]) -> str:
    description = work_package.get("description")
    if isinstance(description, dict):
        raw = description.get("raw")
        html_value = description.get("html")

        if isinstance(raw, str) and raw.strip():
            return _finalize_description_text(_markdown_raw_to_plain(raw))
        if isinstance(html_value, str) and html_value.strip():
            return _finalize_description_text(_html_to_plain_text(html_value))
    if isinstance(description, str) and description.strip():
        return _finalize_description_text(_markdown_raw_to_plain(description))
    return "Описание не указано."


def _coerce_story_points(work_package: dict[str, Any], field_name: str) -> float | None:
    value = work_package.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().replace(",", ".")
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _format_duration_largest_unit(delta_seconds: int) -> str:
    if delta_seconds <= 0:
        return "только что"

    days, remainder = divmod(delta_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    if days > 0:
        return _pluralize(days, "день", "дня", "дней")
    if hours > 0:
        return _pluralize(hours, "час", "часа", "часов")
    if minutes > 0:
        return _pluralize(minutes, "минуту", "минуты", "минут")
    return _pluralize(seconds, "секунду", "секунды", "секунд")


def _pluralize(value: int, one: str, few: str, many: str) -> str:
    mod100 = value % 100
    mod10 = value % 10
    if 11 <= mod100 <= 14:
        word = many
    elif mod10 == 1:
        word = one
    elif 2 <= mod10 <= 4:
        word = few
    else:
        word = many
    return f"{value} {word}"


def _status_duration_text(
    *,
    status_name: str,
    activities: list[dict[str, Any]],
    created_at: datetime | None,
) -> str:
    now = datetime.now(timezone.utc)
    entered_at = find_last_transition_to_status_at(activities, status_name)
    if entered_at is None:
        entered_at = created_at

    if entered_at is None:
        return "неизвестно"

    if entered_at.tzinfo is None:
        entered_at = entered_at.replace(tzinfo=timezone.utc)

    delta_seconds = int(max(0, (now - entered_at.astimezone(timezone.utc)).total_seconds()))
    return _format_duration_largest_unit(delta_seconds)


def _extract_project_identifier(work_package: dict[str, Any], client: OpenProjectClient) -> tuple[str, str]:
    project_link = work_package.get("_links", {}).get("project", {})
    href = project_link.get("href", "") if isinstance(project_link, dict) else ""
    title = project_link.get("title", "") if isinstance(project_link, dict) else ""

    if href:
        try:
            project = client.get_json(href)
            identifier = str(project.get("identifier") or "")
            name = str(project.get("name") or title or identifier)
            if identifier:
                return identifier, name
        except OpenProjectError:
            pass

    return "", str(title or "—")


def _extract_link_id(work_package: dict[str, Any], key: str) -> str | None:
    link = work_package.get("_links", {}).get(key, {})
    if not isinstance(link, dict):
        return None
    href = link.get("href")
    if not isinstance(href, str) or not href:
        return None
    link_id = href.rstrip("/").split("/")[-1]
    return link_id if link_id.isdigit() else None


def _extract_department_key(work_package: dict[str, Any], display: DisplayConfig, project_identifier: str) -> str:
    field_name = display.department_field.strip()
    if field_name:
        link = work_package.get("_links", {}).get(field_name, {})
        if isinstance(link, dict):
            title = link.get("title")
            if title:
                return str(title).strip()

        raw_value = work_package.get(field_name)
        if isinstance(raw_value, dict):
            title = raw_value.get("title") or raw_value.get("name")
            if title:
                return str(title).strip()
        elif raw_value not in (None, ""):
            return str(raw_value).strip()

    return display.project_departments.get(project_identifier, "")


def build_work_package_url(base_url: str, project_identifier: str, work_package_id: str) -> str:
    base = base_url.rstrip("/")
    if project_identifier:
        return f"{base}/projects/{project_identifier}/work_packages/{work_package_id}"
    return f"{base}/work_packages/{work_package_id}"


def fetch_task_summary(
    client: OpenProjectClient,
    work_package_id: str,
    *,
    display: DisplayConfig,
    base_url: str,
) -> TaskSummary:
    work_package = client.get_work_package(work_package_id)
    activities = client.list_work_package_activities(work_package_id)

    status_name = _link_title(work_package, "status", fallback="—")
    created_at = parse_activity_timestamp(work_package.get("createdAt"))
    project_identifier, project_name = _extract_project_identifier(work_package, client)
    department_key = _extract_department_key(work_package, display, project_identifier)
    assignee_id = _extract_link_id(work_package, "assignee")
    sprint_id = _extract_link_id(work_package, "sprint")

    wp_id = str(work_package.get("id") or work_package_id)
    display_id = str(work_package.get("displayId") or wp_id)
    base_url = base_url.rstrip("/")

    board_id, board_name = resolve_board(
        client,
        project_identifier=project_identifier,
        sprint_id=sprint_id,
        default_boards=display.default_boards,
    )

    return TaskSummary(
        work_package_id=wp_id,
        display_id=display_id,
        subject=str(work_package.get("subject") or f"Задача #{display_id}").strip(),
        description=_extract_description(work_package),
        task_type=_link_title(work_package, "type", fallback="Задача"),
        priority_name=_link_title(work_package, "priority", fallback="—"),
        status_name=status_name,
        status_duration_text=_status_duration_text(
            status_name=status_name,
            activities=activities,
            created_at=created_at,
        ),
        assignee=_link_title(work_package, "assignee", fallback="Не назначен"),
        assignee_id=assignee_id,
        story_points=_coerce_story_points(work_package, display.story_points_field),
        project_identifier=project_identifier,
        project_name=project_name,
        department_key=department_key,
        board_id=board_id,
        board_name=board_name,
        web_url=build_work_package_url(base_url, project_identifier, wp_id),
    )
