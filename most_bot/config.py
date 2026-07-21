from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

from most_bot.openproject.client import OpenProjectError
from most_bot.personality_defaults import (
    DEFAULT_ACCESS_DENIED_REPLIES,
    DEFAULT_BOT_EMOJI,
    DEFAULT_BOT_NAME,
    DEFAULT_EMPTY_PROJECTS_MESSAGE,
    DEFAULT_PROJECTS_INTROS,
    DEFAULT_START_COMMANDS,
    DEFAULT_UNKNOWN_COMMAND_REPLIES,
)

_PLACEHOLDER_TOKENS = {
    "",
    "paste-your-telegram-bot-token-here",
    "paste-your-openproject-api-token-here",
    "your-token",
}


@dataclass
class TelegramProxyConfig:
    enabled: bool = False
    scheme: str = "socks5"
    host: str = ""
    port: int | None = None
    username: str = ""
    password: str = ""

    def build_url(self) -> str | None:
        if not self.enabled:
            return None

        host = self.host.strip()
        if not host:
            raise OpenProjectError(
                "Telegram proxy is enabled but telegram.proxy.host is not configured."
            )
        if self.port is None:
            raise OpenProjectError(
                "Telegram proxy is enabled but telegram.proxy.port is not configured."
            )

        scheme = (self.scheme or "socks5").strip().lower()
        if scheme not in {"socks5", "socks5h"}:
            raise OpenProjectError(
                f"Unsupported Telegram proxy scheme: {scheme}. Use socks5 or socks5h."
            )

        auth = ""
        username = self.username.strip()
        if username:
            auth = f"{quote(username, safe='')}:{quote(self.password, safe='')}@"

        return f"{scheme}://{auth}{host}:{self.port}"


@dataclass
class TelegramConfig:
    token: str = ""
    allowed_user_ids: list[int] = field(default_factory=list)
    proxy: TelegramProxyConfig = field(default_factory=TelegramProxyConfig)


@dataclass
class EmojiConfig:
    default: str = "📋"
    projects: dict[str, str] = field(default_factory=dict)
    departments: dict[str, str] = field(default_factory=dict)
    statuses: dict[str, str] = field(default_factory=dict)
    types: dict[str, str] = field(default_factory=dict)
    priorities: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> EmojiConfig:
        defaults = cls()
        return cls(
            default=str(raw.get("default", defaults.default) or defaults.default),
            projects=_coerce_string_dict(raw.get("projects")),
            departments=_coerce_string_dict(raw.get("departments")),
            statuses=_coerce_string_dict(raw.get("statuses")),
            types=_coerce_string_dict(raw.get("types")),
            priorities=_coerce_string_dict(raw.get("priorities")),
        )


@dataclass
class TranslationsConfig:
    types: dict[str, str] = field(default_factory=dict)
    priorities: dict[str, str] = field(default_factory=dict)
    departments: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> TranslationsConfig:
        defaults = cls()
        return cls(
            types=_coerce_string_dict(raw.get("types")),
            priorities=_coerce_string_dict(raw.get("priorities")),
            departments=_coerce_string_dict(raw.get("departments")),
        )


@dataclass
class DisplayConfig:
    story_points_field: str = "storyPoints"
    department_field: str = "customField2"
    project_departments: dict[str, str] = field(default_factory=dict)
    default_boards: dict[str, str] = field(default_factory=dict)
    # OpenProject display name → Telegram username (без @)
    telegram_users: dict[str, str] = field(default_factory=dict)
    emojis: EmojiConfig = field(default_factory=EmojiConfig)
    translations: TranslationsConfig = field(default_factory=TranslationsConfig)

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> DisplayConfig:
        defaults = cls()
        emojis_raw = raw.get("emojis", {}) if isinstance(raw.get("emojis"), dict) else {}
        translations_raw = raw.get("translations", {}) if isinstance(raw.get("translations"), dict) else {}
        return cls(
            story_points_field=str(
                raw.get("story_points_field", defaults.story_points_field) or defaults.story_points_field
            ),
            department_field=str(raw.get("department_field", defaults.department_field) or defaults.department_field),
            project_departments=_coerce_string_dict(raw.get("project_departments")),
            default_boards=_coerce_string_dict(raw.get("default_boards")),
            telegram_users=_coerce_telegram_users(raw.get("telegram_users")),
            emojis=EmojiConfig.from_mapping(emojis_raw),
            translations=TranslationsConfig.from_mapping(translations_raw),
        )

    def resolve_telegram_username(self, openproject_name: str) -> str | None:
        normalized = _normalize_person_name(openproject_name)
        if not normalized:
            return None
        for name, username in self.telegram_users.items():
            if _normalize_person_name(name) == normalized and username:
                return username.lstrip("@")
        return None


@dataclass
class OpenProjectConnectionConfig:
    scheme: str = "https"
    host: str = ""
    port: int | None = None
    base_path: str = ""
    token: str = ""
    timeout_seconds: int = 30
    display: DisplayConfig = field(default_factory=lambda: DisplayConfig())

    def build_base_url(self) -> str:
        if not self.host:
            raise OpenProjectError("OpenProject host is not configured.")

        host_part = self.host.strip().rstrip("/")
        if self.port:
            host_part = f"{host_part}:{self.port}"

        base_path = self.base_path.strip()
        if base_path and not base_path.startswith("/"):
            base_path = f"/{base_path}"
        base_path = base_path.rstrip("/")
        return f"{self.scheme}://{host_part}{base_path}"


@dataclass
class BotConfig:
    name: str = DEFAULT_BOT_NAME
    emoji: str = DEFAULT_BOT_EMOJI
    projects_intros: list[str] = field(default_factory=lambda: list(DEFAULT_PROJECTS_INTROS))
    unknown_command_replies: list[str] = field(default_factory=lambda: list(DEFAULT_UNKNOWN_COMMAND_REPLIES))
    access_denied_replies: list[str] = field(default_factory=lambda: list(DEFAULT_ACCESS_DENIED_REPLIES))
    start_commands: str = DEFAULT_START_COMMANDS
    empty_projects_message: str = DEFAULT_EMPTY_PROJECTS_MESSAGE

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> BotConfig:
        defaults = cls()
        return cls(
            name=str(raw.get("name", defaults.name) or defaults.name),
            emoji=str(raw.get("emoji", defaults.emoji) or defaults.emoji),
            projects_intros=_coerce_string_list(raw.get("projects_intros")) or defaults.projects_intros,
            unknown_command_replies=_coerce_string_list(raw.get("unknown_command_replies"))
            or defaults.unknown_command_replies,
            access_denied_replies=_coerce_string_list(raw.get("access_denied_replies"))
            or defaults.access_denied_replies,
            start_commands=str(raw.get("start_commands", defaults.start_commands) or defaults.start_commands),
            empty_projects_message=str(
                raw.get("empty_projects_message", defaults.empty_projects_message) or defaults.empty_projects_message
            ),
        )


@dataclass
class AppConfig:
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    openproject: OpenProjectConnectionConfig = field(default_factory=OpenProjectConnectionConfig)
    bot: BotConfig = field(default_factory=BotConfig)

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> AppConfig:
        telegram_raw = raw.get("telegram", {}) if isinstance(raw.get("telegram"), dict) else {}
        openproject_raw = raw.get("openproject", {}) if isinstance(raw.get("openproject"), dict) else {}
        bot_raw = raw.get("bot", {}) if isinstance(raw.get("bot"), dict) else {}

        proxy_raw = telegram_raw.get("proxy", {}) if isinstance(telegram_raw.get("proxy"), dict) else {}
        display_raw = openproject_raw.get("display", {}) if isinstance(openproject_raw.get("display"), dict) else {}

        return cls(
            telegram=TelegramConfig(
                token=str(telegram_raw.get("token", "") or ""),
                allowed_user_ids=_coerce_int_list(telegram_raw.get("allowed_user_ids")),
                proxy=TelegramProxyConfig(
                    enabled=bool(proxy_raw.get("enabled", False)),
                    scheme=str(proxy_raw.get("scheme", "socks5") or "socks5"),
                    host=str(proxy_raw.get("host", "") or ""),
                    port=_coerce_optional_int(proxy_raw.get("port")),
                    username=str(proxy_raw.get("username", "") or ""),
                    password=str(proxy_raw.get("password", "") or ""),
                ),
            ),
            openproject=OpenProjectConnectionConfig(
                scheme=str(openproject_raw.get("scheme", "https") or "https"),
                host=str(openproject_raw.get("host", "") or ""),
                port=_coerce_optional_int(openproject_raw.get("port")),
                base_path=str(openproject_raw.get("base_path", "") or ""),
                token=str(openproject_raw.get("token", "") or ""),
                timeout_seconds=_coerce_optional_int(openproject_raw.get("timeout_seconds")) or 30,
                display=DisplayConfig.from_mapping(display_raw),
            ),
            bot=BotConfig.from_mapping(bot_raw),
        )

    def validate(self) -> None:
        token = (self.telegram.token or "").strip().lower()
        if token in _PLACEHOLDER_TOKENS:
            raise OpenProjectError(
                "Telegram token is not configured. Set telegram.token in config.yaml."
            )

        op_token = (self.openproject.token or "").strip().lower()
        if op_token in _PLACEHOLDER_TOKENS:
            raise OpenProjectError(
                "OpenProject API token is not configured. Set openproject.token in config.yaml."
            )

        if not self.openproject.host:
            raise OpenProjectError(
                "OpenProject host is not configured. Set openproject.host in config.yaml."
            )


class ConfigStore:
    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or Path("config.yaml")

    def load(self) -> AppConfig:
        if not self.config_path.exists():
            raise OpenProjectError(
                f"Config file not found: {self.config_path}. "
                f"Copy config.yaml.example to config.yaml and fill in the values."
            )

        try:
            raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise OpenProjectError(f"Could not parse {self.config_path.name}: {exc}") from exc
        except OSError as exc:
            raise OpenProjectError(f"Could not read {self.config_path.name}: {exc}") from exc

        if not isinstance(raw, dict):
            raise OpenProjectError(f"{self.config_path.name} must contain a YAML object at the top level.")

        config = AppConfig.from_mapping(raw)
        config.validate()
        return config

    def save(self, config: AppConfig) -> None:
        with self.config_path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(asdict(config), handle, sort_keys=False, allow_unicode=True)


def _coerce_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_person_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _coerce_telegram_users(value: Any) -> dict[str, str]:
    raw = _coerce_string_dict(value)
    result: dict[str, str] = {}
    for name, username in raw.items():
        cleaned = username.strip().lstrip("@")
        if cleaned:
            result[name] = cleaned
    return result


def _coerce_string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for key, item in value.items():
        if key in (None, "") or item in (None, ""):
            continue
        result[str(key)] = str(item)
    return result


def _coerce_string_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if item not in (None, "") and str(item).strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return []


def _coerce_int_list(value: Any) -> list[int]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        result: list[int] = []
        for item in value:
            if item in (None, ""):
                continue
            try:
                result.append(int(item))
            except (TypeError, ValueError):
                continue
        return result
    return []
