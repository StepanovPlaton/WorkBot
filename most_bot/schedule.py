from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from telegram.ext import ContextTypes

from most_bot.config import AppConfig, ScheduleConfig, ScheduleEventConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReminderFire:
    event_key: str
    title: str
    message: str


@dataclass(frozen=True)
class UpcomingReminder:
    fire_at: datetime
    event_key: str
    title: str
    message: str


def _parse_hhmm(value: str) -> time:
    hours, minutes = value.strip().split(":", 1)
    return time(hour=int(hours), minute=int(minutes))


def sprint_week_number(today: date, anchor: date) -> int:
    """1 или 2 в двухнедельном цикле. anchor — понедельник недели планирования."""
    delta_days = (today - anchor).days
    cycle_day = delta_days % 14
    if cycle_day < 0:
        cycle_day += 14
    return 1 if cycle_day < 7 else 2


def _weekday_matches(today: date, weekdays: list[str]) -> bool:
    names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    today_name = names[today.weekday()]
    return today_name in {day.strip().lower() for day in weekdays}


def _event_applies_today(event: ScheduleEventConfig, today: date, week_number: int) -> bool:
    if event.sprint_weeks and week_number not in event.sprint_weeks:
        return False
    if event.weekdays and not _weekday_matches(today, event.weekdays):
        return False
    for rule in event.exclude:
        if rule.sprint_week == week_number and _weekday_matches(today, [rule.weekday]):
            return False
    return True


def _pick_message(event: ScheduleEventConfig, bot_name: str) -> str:
    pool = event.messages or ["{title} {when}."]
    template = random.choice(pool)
    return template.format(
        when="прямо сейчас",
        title=event.title,
        name=bot_name,
        gap=0,
    )


def format_team_mentions(
    telegram_users: dict[str, str],
    *,
    exclude: list[str] | None = None,
) -> str:
    """@username всех из telegram_users, кроме exclude (по умолчанию seregatot)."""
    excluded = {name.strip().lstrip("@").lower() for name in (exclude or []) if name and name.strip()}
    seen: set[str] = set()
    mentions: list[str] = []
    for username in telegram_users.values():
        cleaned = username.strip().lstrip("@")
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in excluded or key in seen:
            continue
        seen.add(key)
        mentions.append(f"@{cleaned}")
    return " ".join(mentions)


def _build_reminder_message(
    event_key: str,
    event: ScheduleEventConfig,
    *,
    bot_name: str,
    telegram_users: dict[str, str],
    mention_exclude: list[str],
    mentions_enabled: bool,
) -> str:
    message = _pick_message(event, bot_name)
    if not mentions_enabled or event_key == "workday_end":
        return message
    mentions = format_team_mentions(telegram_users, exclude=mention_exclude)
    if not mentions:
        return message
    return f"{message}\n\n{mentions}"


def collect_due_reminders(
    schedule: ScheduleConfig,
    *,
    now: datetime,
    bot_name: str,
    telegram_users: dict[str, str] | None = None,
) -> list[ReminderFire]:
    if not schedule.enabled:
        return []

    local_now = now.astimezone(ZoneInfo(schedule.timezone))
    today = local_now.date()
    current_time = local_now.replace(second=0, microsecond=0).time()
    week_number = sprint_week_number(today, schedule.sprint_anchor_date)
    users = telegram_users or {}
    mentions_enabled = schedule.chat_id is not None

    due: list[ReminderFire] = []

    for event_key, event in schedule.events.items():
        if not event.enabled:
            continue
        if not _event_applies_today(event, today, week_number):
            continue

        fire_at = _parse_hhmm(event.time)
        if fire_at.hour != current_time.hour or fire_at.minute != current_time.minute:
            continue

        due.append(
            ReminderFire(
                event_key=event_key,
                title=event.title,
                message=_build_reminder_message(
                    event_key,
                    event,
                    bot_name=bot_name,
                    telegram_users=users,
                    mention_exclude=schedule.mention_exclude,
                    mentions_enabled=mentions_enabled,
                ),
            )
        )

    return due


def collect_upcoming_reminders(
    schedule: ScheduleConfig,
    *,
    now: datetime,
    bot_name: str,
    telegram_users: dict[str, str] | None = None,
    limit: int = 3,
    max_days: int = 28,
) -> list[UpcomingReminder]:
    """Ближайшие напоминания после now."""
    if not schedule.enabled or limit <= 0:
        return []

    tz = ZoneInfo(schedule.timezone)
    local_now = now.astimezone(tz)
    users = telegram_users or {}
    mentions_enabled = schedule.chat_id is not None
    candidates: list[UpcomingReminder] = []

    for day_offset in range(max_days + 1):
        day = (local_now + timedelta(days=day_offset)).date()
        week_number = sprint_week_number(day, schedule.sprint_anchor_date)

        for event_key, event in schedule.events.items():
            if not event.enabled:
                continue
            if not _event_applies_today(event, day, week_number):
                continue

            fire_at = datetime.combine(day, _parse_hhmm(event.time), tzinfo=tz)
            if fire_at <= local_now:
                continue

            candidates.append(
                UpcomingReminder(
                    fire_at=fire_at,
                    event_key=event_key,
                    title=event.title,
                    message=_build_reminder_message(
                        event_key,
                        event,
                        bot_name=bot_name,
                        telegram_users=users,
                        mention_exclude=schedule.mention_exclude,
                        mentions_enabled=mentions_enabled,
                    ),
                )
            )

    candidates.sort(key=lambda item: item.fire_at)
    return candidates[:limit]


async def schedule_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    config: AppConfig = context.application.bot_data["bot_context"].config
    schedule = config.schedule

    if not schedule.enabled:
        return
    if schedule.chat_id is None:
        return

    now = datetime.now(tz=ZoneInfo(schedule.timezone))
    due = collect_due_reminders(
        schedule,
        now=now,
        bot_name=config.bot.name,
        telegram_users=config.openproject.display.telegram_users,
    )
    if not due:
        return

    fired: set[str] = context.application.bot_data.setdefault("schedule_fired", set())
    stamp = now.strftime("%Y-%m-%d %H:%M")

    for reminder in due:
        fire_key = f"{stamp}:{reminder.event_key}"
        if fire_key in fired:
            continue
        fired.add(fire_key)

        # Не раздуваем set бесконечно
        if len(fired) > 500:
            context.application.bot_data["schedule_fired"] = {fire_key}

        kwargs: dict = {
            "chat_id": schedule.chat_id,
            "text": f"🏓 <b>{reminder.title}</b>\n{reminder.message}",
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if schedule.message_thread_id is not None:
            kwargs["message_thread_id"] = schedule.message_thread_id

        try:
            await context.bot.send_message(**kwargs)
            logger.info(
                "Reminder sent: %s -> chat=%s thread=%s",
                reminder.event_key,
                schedule.chat_id,
                schedule.message_thread_id,
            )
        except Exception:
            logger.exception("Failed to send reminder %s", reminder.event_key)
            fired.discard(fire_key)


def setup_schedule_jobs(application) -> None:
    config: AppConfig = application.bot_data["bot_context"].config
    schedule = config.schedule

    if not schedule.enabled:
        logger.info("Schedule reminders disabled in config.")
        return

    if schedule.chat_id is None:
        logger.warning(
            "Schedule enabled, but schedule.chat_id is empty. "
            "Add the bot to the work chat and set chat_id / message_thread_id "
            "(use /chatinfo in the target topic)."
        )
        return

    if application.job_queue is None:
        logger.error(
            "JobQueue is unavailable. Install: pip install \"python-telegram-bot[job-queue]\""
        )
        return

    application.job_queue.run_repeating(
        schedule_tick,
        interval=30,
        first=5,
        name="schedule_tick",
    )
    logger.info(
        "Schedule reminders armed: tz=%s chat=%s thread=%s anchor=%s",
        schedule.timezone,
        schedule.chat_id,
        schedule.message_thread_id,
        schedule.sprint_anchor_date.isoformat(),
    )
