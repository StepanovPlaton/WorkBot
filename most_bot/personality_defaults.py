"""Тексты персонализации бота по умолчанию (Пинг)."""

DEFAULT_BOT_NAME = "Пинг"
DEFAULT_BOT_EMOJI = "🏓"

DEFAULT_PROJECTS_INTROS = [
    "Проекты в OpenProject:",
]

DEFAULT_UNKNOWN_COMMAND_REPLIES = [
    "Не понял. Напиши #номер задачи или /chatinfo.",
]

DEFAULT_ACCESS_DENIED_REPLIES = [
    "Пинг! Этот бот только для своих.",
]

DEFAULT_START_COMMANDS = (
    "Напиши #132 или ссылку на задачу — пришлю карточку.\n"
    "/chatinfo — chat_id и топик для напоминаний\n"
    "/upcoming — 3 ближайших напоминания с датой публикации"
)

DEFAULT_EMPTY_PROJECTS_MESSAGE = (
    "Проектов пока нет. Либо OpenProject пуст, либо у токена нет доступа."
)
