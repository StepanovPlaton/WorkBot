from __future__ import annotations

import logging
import re
from io import BytesIO

from telegram import InputMediaPhoto, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
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
_MAX_TELEGRAM_PHOTOS = 10

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


def _download_description_images(
    client: OpenProjectClient,
    summaries: list[TaskSummary],
) -> tuple[set[int], list[BytesIO]]:
    """Скачивает картинки из описания одной задачи. Возвращает (индексы, файлы)."""
    if len(summaries) != 1 or not summaries[0].description_image_urls:
        return set(), []

    attached_indices: set[int] = set()
    photos: list[BytesIO] = []

    for index, image_url in enumerate(summaries[0].description_image_urls[:_MAX_TELEGRAM_PHOTOS]):
        try:
            data, content_type = client.get_bytes(image_url)
        except OpenProjectError as exc:
            logger.warning("Failed to download description image %s: %s", image_url, exc)
            continue

        if not data:
            continue

        photo = BytesIO(data)
        photo.name = _image_filename(content_type, image_url)
        photos.append(photo)
        attached_indices.add(index)

    return attached_indices, photos


def _photo_caption(text: str) -> str:
    if len(text) <= _TELEGRAM_CAPTION_LIMIT:
        return text
    return text[: _TELEGRAM_CAPTION_LIMIT - 1].rstrip() + "…"


async def _reply_task_cards(
    message,
    text: str,
    *,
    photos: list[BytesIO] | None = None,
) -> None:
    photos = photos or []

    if not photos:
        await message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_to_message_id=message.message_id,
        )
        return

    caption = _photo_caption(text)

    try:
        if len(photos) == 1:
            photos[0].seek(0)
            await message.reply_photo(
                photo=photos[0],
                caption=caption,
                parse_mode=ParseMode.HTML,
                show_caption_above_media=True,
                reply_to_message_id=message.message_id,
            )
            return

        for photo in photos:
            photo.seek(0)
        media: list[InputMediaPhoto] = [
            InputMediaPhoto(
                media=photos[0],
                caption=caption,
                parse_mode=ParseMode.HTML,
                show_caption_above_media=True,
            )
        ]
        # В sendMediaGroup show_caption_above_media должен совпадать у всех элементов альбома.
        media.extend(
            InputMediaPhoto(media=photo, show_caption_above_media=True) for photo in photos[1:]
        )
        await message.reply_media_group(media=media, reply_to_message_id=message.message_id)
    except TelegramError:
        logger.exception("Failed to send task card with photos")
        if len(photos) == 1:
            await message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_to_message_id=message.message_id,
            )
            return
        try:
            for photo in photos:
                photo.seek(0)
            media_fallback: list[InputMediaPhoto] = [
                InputMediaPhoto(
                    media=photos[0],
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    show_caption_above_media=False,
                )
            ]
            media_fallback.extend(
                InputMediaPhoto(media=photo, show_caption_above_media=False) for photo in photos[1:]
            )
            await message.reply_media_group(media=media_fallback, reply_to_message_id=message.message_id)
        except TelegramError:
            logger.exception("Failed to send task card media group fallback")
            await message.reply_text(
                text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_to_message_id=message.message_id,
            )


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
    photos: list[BytesIO] = []
    attached_indices: set[int] = set()

    if summaries:
        attached_indices, photos = _download_description_images(bot_context.openproject, summaries)
        parts.append(
            format_task_cards(
                summaries,
                openproject.display,
                attached_image_indices=attached_indices or None,
                expandable_description=not photos,
            )
        )
    if errors:
        parts.append("\n".join(errors))

    if not parts:
        return

    await _reply_task_cards(message, "\n\n".join(parts), photos=photos)


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
