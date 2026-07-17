from __future__ import annotations

from most_bot.config import DisplayConfig


def _normalize_key(value: str) -> str:
    return " ".join(value.strip().lower().split())


class LabelResolver:
    def __init__(self, display: DisplayConfig) -> None:
        self.display = display

    def task_type(self, task_type: str) -> str:
        return self._translate(self.display.translations.types, task_type, task_type)

    def priority(self, priority_name: str) -> str:
        return self._translate(self.display.translations.priorities, priority_name, priority_name)

    def department(self, department_key: str) -> str:
        if not department_key:
            return ""
        return self._translate(self.display.translations.departments, department_key, department_key)

    @staticmethod
    def _translate(mapping: dict[str, str], key: str, fallback: str) -> str:
        normalized = _normalize_key(key)
        for map_key, label in mapping.items():
            if _normalize_key(map_key) == normalized:
                return label
        return fallback
