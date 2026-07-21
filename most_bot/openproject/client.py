from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

DEFAULT_TIMEOUT = 30
PAGE_SIZE = 100


class OpenProjectError(RuntimeError):
    """Ошибка API или конфигурации OpenProject."""


@dataclass(frozen=True)
class ProjectInfo:
    id: str
    identifier: str
    name: str


class OpenProjectClient:
    def __init__(self, base_url: str, token: str, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/hal+json, application/json",
            "Content-Type": "application/json",
            "User-Agent": "ping-bot/0.1",
        }

    def _build_url(self, path: str, query: dict[str, Any] | None = None) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            if not path.startswith("/"):
                path = f"/{path}"
            url = f"{self.base_url}{path}"

        if not query:
            return url

        encoded = urllib.parse.urlencode(query, doseq=True)
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}{encoded}"

    def get_json(self, path: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._build_url(path, query)
        request = urllib.request.Request(url, headers=self.headers, method="GET")

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                body = response.read().decode(charset)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OpenProjectError(self._format_http_error(exc.code, body, url)) from exc
        except urllib.error.URLError as exc:
            raise OpenProjectError(
                f"Could not connect to OpenProject at {url}: {exc.reason}"
            ) from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise OpenProjectError(f"OpenProject returned invalid JSON at {url}") from exc

    def get_bytes(self, path: str) -> tuple[bytes, str | None]:
        """Скачивает бинарный контент (вложения). Возвращает (data, content_type)."""
        url = self._build_url(path)
        headers = {key: value for key, value in self.headers.items() if key.lower() != "content-type"}
        request = urllib.request.Request(url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = response.read()
                content_type = response.headers.get_content_type()
                return data, content_type
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OpenProjectError(self._format_http_error(exc.code, body, url)) from exc
        except urllib.error.URLError as exc:
            raise OpenProjectError(
                f"Could not connect to OpenProject at {url}: {exc.reason}"
            ) from exc

    def _format_http_error(self, status: int, body: str, url: str) -> str:
        detail = ""
        try:
            data = json.loads(body)
            detail = data.get("message") or data.get("errorIdentifier") or ""
        except json.JSONDecodeError:
            detail = body.strip().splitlines()[0] if body.strip() else ""

        message = f"OpenProject API error: HTTP {status} for {url}"
        if detail:
            message += f": {detail}"
        return message

    def get_collection(self, path: str, query: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        query = dict(query or {})
        query.setdefault("offset", 1)
        query.setdefault("pageSize", PAGE_SIZE)

        items: list[dict[str, Any]] = []
        while True:
            data = self.get_json(path, query)
            page_items = data.get("_embedded", {}).get("elements", [])
            if not isinstance(page_items, list):
                raise OpenProjectError(f"Unexpected collection format in response for {path}")

            items.extend(page_items)

            count = int(data.get("count", len(page_items)) or 0)
            total = int(data.get("total", len(items)) or 0)
            offset = int(data.get("offset", query["offset"]) or query["offset"])
            page_size = int(data.get("pageSize", query["pageSize"]) or query["pageSize"])

            if count == 0 or len(items) >= total or count < page_size:
                break

            query["offset"] = offset + 1

        return items

    def list_projects(self) -> list[ProjectInfo]:
        projects = self.get_collection("/api/v3/projects")
        items = [
            ProjectInfo(
                id=str(project.get("id")),
                identifier=str(project.get("identifier") or project.get("id")),
                name=str(
                    project.get("name")
                    or project.get("identifier")
                    or f"Project {project.get('id')}"
                ),
            )
            for project in projects
        ]
        items.sort(key=lambda item: item.name.lower())
        return items

    def get_work_package(self, work_package_id: str) -> dict[str, Any]:
        return self.get_json(f"/api/v3/work_packages/{work_package_id}")

    def list_work_package_activities(self, work_package_id: str) -> list[dict[str, Any]]:
        return self.get_collection(f"/api/v3/work_packages/{work_package_id}/activities")
