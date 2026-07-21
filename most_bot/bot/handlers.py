from __future__ import annotations

import logging
import re
from io import BytesIO

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from most_bot.bot.task_cards import format_task_cards
from most_bot.config import AppConfig
from most_bot.openproject.client import OpenProjectClient, OpenProjectError
from most_bot.openproject.task_refs import extract_task_references
from most_bot.openproject.tasks import TaskSummary, fetch_task_summary
from most_bot.personality import (
    build_access_denied_message,
    build_start_message,
    build_unknown_command_message,
)

logger = logging.getLogger(__name__)

# В сообщениях про daily бот не отвечает карточками задач
_IGNORE_TASK_REPLY_RE = re.compile(r"\bdail[yi]\b", re.IGNORECASE)
_TELEGRAM_CAPTION_LIMIT = 1024

_CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _image_filename(content_type: str | None, url: str) -> str:
    if content_type:
        ext = _CONTENT_TYPE_EXTENSIONS.get(content_type.lower())
        if ext:
            return f"image{ext}"
    lower = url.lower().split("?", 1)[0]
    for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        if lower.endswith(ext):
            return f"image{ext if ext != '.jpeg' else '.jpg'}"
    return "image.jpg"


async def _reply_task_cards(
    message,
    text: str,
    *,
    photo: BytesIO | None = None,
) -> None:
    if photo is None:
        await message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_to_message_id=message.message_id,
        )
        return

    if len(text) <= _TELEGRAM_CAPTION_LIMIT:
        await message.reply_photo(
            photo=photo,
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=message.message_id,
        )
        return

    await message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_to_message_id=message.message_id,
    )
    await message.reply_photo(photo=photo, reply_to_message_id=message.message_id)


def _prepare_attachable_image(
    client: OpenProjectClient,
    summaries: list[TaskSummary],
) -> tuple[set[int], BytesIO | None]:
    """Для одной задачи: скачивает первую картинку. Остальные останутся ссылками."""
    if len(summaries) != 1 or not summaries[0].description_image_urls:
        return set(), None

    image_url = summaries[0].description_image_urls[0]
    try:
        data, content_type = client.get_bytes(image_url)
    except OpenProjectError as exc:
        logger.warning("Failed to download description image %s: %s", image_url, exc)
        return set(), None

    if not data:
        return set(), None

    photo = BytesIO(data)
    photo.name = _image_filename(content_type, image_url)
    return {0}, photo


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
    photo: BytesIO | None = None
    attached_indices: set[int] = set()

    if summaries:
        attached_indices, photo = _prepare_attachable_image(bot_context.openproject, summaries)
        parts.append(
            format_task_cards(
                summaries,
                openproject.display,
                attached_image_indices=attached_indices or None,
            )
        )
    if errors:
        parts.append("\n".join(errors))

    if not parts:
        return

    await _reply_task_cards(message, "\n\n".join(parts), photo=photo)


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
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, task_reference_handler))

    return application
