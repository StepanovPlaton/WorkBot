from __future__ import annotations

import re
from datetime import datetime
from typing import Any

STATUS_CHANGED_RE = re.compile(
    r"^(?:Статус|Status)\s+(?:изменён|изменено|changed)\s+(?:с|from)\s+(.+?)\s+(?:на|to)\s+(.+)$",
    re.IGNORECASE,
)
STATUS_SET_RE = re.compile(
    r"^(?:Статус|Status)\s+(?:установлен(?:о)?|set)\s+(?:на|to)\s+(.+)$",
    re.IGNORECASE,
)
STATUS_ASSIGNED_RE = re.compile(
    r"^(?:Статус|Status)\s+присвоено\s+значение\s+(.+)$",
    re.IGNORECASE,
)


def normalize_status_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def parse_status_transition(raw: str) -> tuple[str | None, str | None]:
    text = raw.strip()
    if not text:
        return None, None

    match = STATUS_CHANGED_RE.match(text)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    match = STATUS_SET_RE.match(text)
    if match:
        return None, match.group(1).strip()

    match = STATUS_ASSIGNED_RE.match(text)
    if match:
        return None, match.group(1).strip()

    return None, None


def parse_activity_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None

    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def find_last_transition_to_status_at(
    activities: list[dict[str, Any]],
    target_status_name: str,
) -> datetime | None:
    target = normalize_status_name(target_status_name)
    last_at: datetime | None = None

    sorted_activities = sorted(
        activities,
        key=lambda item: (
            parse_activity_timestamp(item.get("createdAt")) or datetime.min.replace(tzinfo=None),
            int(item.get("version") or 0),
        ),
    )

    for activity in sorted_activities:
        created_at = parse_activity_timestamp(activity.get("createdAt"))
        if not created_at:
            continue

        details = activity.get("details")
        if not isinstance(details, list):
            continue

        for detail in details:
            if not isinstance(detail, dict):
                continue
            raw = detail.get("raw")
            if not isinstance(raw, str):
                continue

            _, to_status = parse_status_transition(raw)
            if to_status and normalize_status_name(to_status) == target:
                last_at = created_at

    return last_at
