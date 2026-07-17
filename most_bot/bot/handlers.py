from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from most_bot.bot.task_cards import format_task_cards
from most_bot.config import AppConfig
from most_bot.openproject.client import OpenProjectClient, OpenProjectError
from most_bot.openproject.task_refs import extract_task_references
from most_bot.openproject.tasks import fetch_task_summary
from datetime import datetime
from zoneinfo import ZoneInfo

from most_bot.schedule import collect_upcoming_reminders, setup_schedule_jobs
from most_bot.personality import (
    build_access_denied_message,
    build_start_message,
    build_unknown_command_message,
)

logger = logging.getLogger(__name__)

# В сообщениях про daily бот не отвечает карточками задач
_IGNORE_TASK_REPLY_RE = re.compile(r"\bdail[yi]\b", re.IGNORECASE)


class BotContext:
    def __init__(self, config: AppConfig, openproject: OpenProjectClient) -> None:
        self.config = config
        self.openproject = openproject


def _is_user_allowed(config: AppConfig, user_id: int | None) -> bool:
    allowed = config.telegram.allowed_user_ids
    if not allowed:
        return True
    return user_id is not None and user_id in allowed


async def _guard_access(update: Update, config: AppConfig) -> bool:
    user = update.effective_user
    if _is_user_allowed(config, user.id if user else None):
        return True

    if update.message:
        await update.message.reply_text(build_access_denied_message(config.bot))
    return False


def _get_bot_context(context: ContextTypes.DEFAULT_TYPE) -> BotContext:
    bot_context = context.application.bot_data.get("bot_context")
    if not isinstance(bot_context, BotContext):
        raise RuntimeError("Bot context is not initialized.")
    return bot_context


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_context = _get_bot_context(context)
    if not await _guard_access(update, bot_context.config):
        return

    message = update.effective_message
    if not message:
        return

    await message.reply_text(build_start_message(bot_context.config.bot))


async def chatinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает chat_id и message_thread_id топика — для schedule в config.yaml."""
    bot_context = _get_bot_context(context)
    if not await _guard_access(update, bot_context.config):
        return

    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    thread_id = message.message_thread_id
    lines = [
        "Чтобы Пинг писал напоминания сюда, пропиши в config.yaml:",
        "",
        "schedule:",
        f"  chat_id: {chat.id}",
        f"  message_thread_id: {thread_id if thread_id is not None else 'null  # общий чат без топиков'}",
        "",
        f"Чат: {chat.title or chat.id}",
        f"Тип: {chat.type}",
    ]
    if thread_id is not None:
        lines.append(f"Топик (thread): {thread_id}")
    else:
        lines.append("Топик: нет (сообщение не в форум-топике)")

    await message.reply_text("\n".join(lines))


async def upcoming_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает 3 ближайших запланированных напоминания с датой публикации."""
    bot_context = _get_bot_context(context)
    if not await _guard_access(update, bot_context.config):
        return

    message = update.effective_message
    if not message:
        return

    schedule = bot_context.config.schedule
    if not schedule.enabled:
        await message.reply_text("Расписание выключено (schedule.enabled: false).")
        return

    now = datetime.now(tz=ZoneInfo(schedule.timezone))
    now_label = now.strftime("%d.%m.%Y %H:%M")
    upcoming = collect_upcoming_reminders(
        schedule,
        now=now,
        bot_name=bot_context.config.bot.name,
        telegram_users=bot_context.config.openproject.display.telegram_users,
        limit=3,
    )
    if not upcoming:
        await message.reply_text(
            f"Сейчас: <b>{now_label}</b> ({schedule.timezone})\n\n"
            "Ближайших напоминаний не нашлось (проверь events в config).",
            parse_mode=ParseMode.HTML,
        )
        return

    blocks: list[str] = [
        f"Сейчас: <b>{now_label}</b> ({schedule.timezone})",
        "",
        "Ближайшие напоминания:",
    ]
    for index, item in enumerate(upcoming, start=1):
        when = item.fire_at.strftime("%d.%m.%Y %H:%M")
        blocks.append(
            f"\n{index}. <b>{when}</b> — {item.title}\n"
            f"🏓 <b>{item.title}</b>\n{item.message}"
        )

    await message.reply_text(
        "\n".join(blocks),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_context = _get_bot_context(context)
    if not await _guard_access(update, bot_context.config):
        return

    message = update.effective_message
    if not message:
        return

    await message.reply_text(build_unknown_command_message(bot_context.config.bot))


async def task_reference_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_context = _get_bot_context(context)
    if not await _guard_access(update, bot_context.config):
        return

    message = update.effective_message
    if not message or not message.text:
        return

    if _IGNORE_TASK_REPLY_RE.search(message.text):
        return

    openproject = bot_context.config.openproject
    references = extract_task_references(
        message.text,
        openproject_base_url=openproject.build_base_url(),
    )
    if not references:
        return

    summaries = []
    errors: list[str] = []

    for reference in references:
        try:
            summaries.append(
                fetch_task_summary(
                    bot_context.openproject,
                    reference.work_package_id,
                    display=openproject.display,
                    base_url=openproject.build_base_url(),
                )
            )
        except OpenProjectError as exc:
            logger.warning("Failed to load work package %s: %s", reference.work_package_id, exc)
            errors.append(f"#{reference.work_package_id}: {exc}")

    parts: list[str] = []
    if summaries:
        parts.append(format_task_cards(summaries, openproject.display))
    if errors:
        parts.append("\n".join(errors))

    if not parts:
        return

    await message.reply_text(
        "\n\n".join(parts),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_to_message_id=message.message_id,
    )


def _mask_proxy_url(proxy_url: str) -> str:
    if "@" not in proxy_url:
        return proxy_url
    scheme, rest = proxy_url.split("://", 1)
    _, host_part = rest.rsplit("@", 1)
    return f"{scheme}://***:***@{host_part}"


def build_application(config: AppConfig, openproject: OpenProjectClient) -> Application:
    builder = Application.builder().token(config.telegram.token)

    proxy_url = config.telegram.proxy.build_url()
    if proxy_url:
        logger.info("Telegram proxy enabled: %s", _mask_proxy_url(proxy_url))
        builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)

    application = builder.build()

    application.bot_data["bot_context"] = BotContext(config, openproject)

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("chatinfo", chatinfo_command))
    application.add_handler(CommandHandler("upcoming", upcoming_command))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, task_reference_handler))

    setup_schedule_jobs(application)

    return application
