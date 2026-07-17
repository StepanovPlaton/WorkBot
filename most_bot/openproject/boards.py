from __future__ import annotations

from typing import Any

from most_bot.openproject.client import OpenProjectClient, OpenProjectError


def _extract_id_from_href(href: str) -> str | None:
    parts = [part for part in href.rstrip("/").split("/") if part]
    return parts[-1] if parts and parts[-1].isdigit() else None


def _grid_matches_project(grid: dict[str, Any], project_identifier: str) -> bool:
    links = grid.get("_links", {})
    project_link = links.get("project", {})
    scope_link = links.get("scope", {})

    project_href = project_link.get("href", "") if isinstance(project_link, dict) else ""
    scope_href = scope_link.get("href", "") if isinstance(scope_link, dict) else ""

    if "/boards" not in scope_href:
        return False

    if project_href.endswith(f"/{project_identifier}") or f"/projects/{project_identifier}" in project_href:
        return True

    return f"/projects/{project_identifier}/boards" in scope_href


def _grid_sprint_id(grid: dict[str, Any]) -> str | None:
    options = grid.get("options", {})
    if not isinstance(options, dict):
        return None

    filters = options.get("filters")
    if not isinstance(filters, list):
        return None

    for filter_item in filters:
        if not isinstance(filter_item, dict):
            continue
        sprint_config = filter_item.get("sprint_id")
        if not isinstance(sprint_config, dict):
            continue
        values = sprint_config.get("values")
        if isinstance(values, list) and values:
            return str(values[0])
    return None


def resolve_board(
    client: OpenProjectClient,
    *,
    project_identifier: str,
    sprint_id: str | None,
    default_boards: dict[str, str],
) -> tuple[str | None, str | None]:
    """Возвращает (board_id, board_name)."""
    grids = client.get_collection("/api/v3/grids")
    project_grids = [grid for grid in grids if _grid_matches_project(grid, project_identifier)]

    if sprint_id:
        for grid in project_grids:
            if _grid_sprint_id(grid) == sprint_id:
                board_id = str(grid.get("id") or "")
                board_name = str(grid.get("name") or grid.get("title") or f"Доска {board_id}")
                if board_id:
                    return board_id, board_name

    fallback_id = default_boards.get(project_identifier, "").strip()
    if not fallback_id:
        return None, None

    for grid in project_grids:
        if str(grid.get("id") or "") == fallback_id:
            board_name = str(grid.get("name") or grid.get("title") or f"Доска {fallback_id}")
            return fallback_id, board_name

    try:
        grid = client.get_json(f"/api/v3/grids/{fallback_id}")
        board_name = str(grid.get("name") or grid.get("title") or f"Доска {fallback_id}")
        return fallback_id, board_name
    except OpenProjectError:
        return fallback_id, f"Доска {fallback_id}"


def resolve_board_id(
    client: OpenProjectClient,
    *,
    project_identifier: str,
    sprint_id: str | None,
    default_boards: dict[str, str],
) -> str | None:
    board_id, _ = resolve_board(
        client,
        project_identifier=project_identifier,
        sprint_id=sprint_id,
        default_boards=default_boards,
    )
    return board_id


def build_assignee_board_url(
    base_url: str,
    *,
    project_identifier: str,
    board_id: str,
    assignee_id: str,
) -> str:
    """Ссылка на задачи проекта с фильтром по исполнителю.

    Раньше использовали ``/boards/{id}?query_props=...``, но на досках
    OpenProject неполный/чужой ``query_props`` даёт
    ``no implicit conversion of String into Integer`` при загрузке колонок.

    Надёжный вариант UI — список work packages с API-фильтром ``filters``.
    ``board_id`` оставляем в сигнатуре для совместимости вызовов.
    """
    import json
    from urllib.parse import quote

    _ = board_id  # доска в URL не используется — см. docstring
    filters = json.dumps(
        [{"assignee": {"operator": "=", "values": [str(assignee_id)]}}],
        separators=(",", ":"),
    )
    return (
        f"{base_url.rstrip('/')}/projects/{project_identifier}/work_packages"
        f"?filters={quote(filters)}"
    )
