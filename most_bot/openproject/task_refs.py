from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

HASH_REF_RE = re.compile(r"(?:^|[\s(,])(?:#|№)\s*(\d+)\b")
WORK_PACKAGE_URL_RES = (
    re.compile(r"/projects/[^/]+/boards/\d+/details/(?P<id>\d+)", re.IGNORECASE),
    re.compile(r"/projects/[^/]+/work_packages/(?P<id>\d+)", re.IGNORECASE),
    re.compile(r"/work_packages/(?P<id>\d+)", re.IGNORECASE),
)


@dataclass(frozen=True)
class TaskReference:
    work_package_id: str
    source: str


def extract_task_references(text: str, *, openproject_base_url: str = "") -> list[TaskReference]:
    if not text or not text.strip():
        return []

    found: dict[str, TaskReference] = {}

    for match in HASH_REF_RE.finditer(text):
        work_package_id = match.group(1)
        found.setdefault(
            work_package_id,
            TaskReference(work_package_id=work_package_id, source="hash"),
        )

    for token in re.findall(r"https?://\S+", text):
        url = token.rstrip(").,;]")
        parsed = urlparse(url)
        if openproject_base_url:
            expected = urlparse(openproject_base_url.rstrip("/"))
            if parsed.netloc and expected.netloc and parsed.netloc != expected.netloc:
                continue

        for pattern in WORK_PACKAGE_URL_RES:
            match = pattern.search(parsed.path)
            if not match:
                continue
            work_package_id = match.group("id")
            found.setdefault(
                work_package_id,
                TaskReference(work_package_id=work_package_id, source="url"),
            )
            break

    return list(found.values())
