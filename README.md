# 🏓 Most Bot

> **Most Bot** — Telegram-бот для команды разработки: карточки задач из OpenProject и напоминания по спринту.

---

## 🚀 О проекте

- **Карточки задач из OpenProject** по `#номер`, `№номер` или ссылке на work package
- **Напоминания по расписанию спринта** (2 недели): Daily, планирование, релиз, ретро, конец рабочего дня
- **Теги команды** в напоминаниях (кроме конца дня) — после указания `schedule.chat_id`
- **SOCKS5-прокси** для Telegram API, если прямой доступ недоступен
- **Персонализация** имени, эмодзи и текстов через секцию `bot` (или дефолты из кода)
- **Оформление карточек** через `openproject.display`: эмодзи, переводы, маппинг пользователей в Telegram
- Запуск **локально** или через **Docker Compose**

> 💡 **Важно:** Секреты и боевой конфиг живут только в `config.yaml` (он в `.gitignore`). В репозитории — шаблон `config.yaml.example` без токенов, IP и персональных данных.

---

## 📝 Подготовка

Перед запуском выполните шаги:

1. **Создайте Telegram-бота** у [@BotFather](https://t.me/BotFather)
   - `/newbot` → display name и username (должен заканчиваться на `bot`)
   - Сохраните токен — это `telegram.token`
   - По желанию: `/setdescription`, `/setabouttext`, `/setcommands`
2. **Создайте API-токен OpenProject**
   - My account → Access tokens → + API token
   - Токен кладите в `openproject.token`
3. **Скопируйте конфиг и заполните**

```bash
cp config.yaml.example config.yaml
```

Заполните как минимум:

- `telegram.token`
- `openproject.host` / `openproject.port` / `openproject.scheme`
- `openproject.token`
- при необходимости — `telegram.proxy` и `schedule.*`

4. **(Опционально)** Узнайте свой Telegram user id у [@userinfobot](https://t.me/userinfobot) и добавьте в `telegram.allowed_user_ids`

### Команды для BotFather (`/setcommands`)

```
start - Кратко, что умею
chatinfo - Chat id и топик для напоминаний
upcoming - 3 ближайших напоминания с датой
```

> После заполнения конфига можно запускать бота локально или в Docker.

---

## ⚙️ Конфигурация

### SOCKS5-прокси для Telegram

Если Telegram API недоступен напрямую:

```yaml
telegram:
  proxy:
    enabled: true
    scheme: socks5   # или socks5h
    host: 127.0.0.1
    port: 1080
    username: ""
    password: ""
```

- `socks5` — DNS резолвится на стороне бота
- `socks5h` — DNS резолвится через прокси

В Docker `127.0.0.1` — это контейнер. Если прокси на хосте: `host.docker.internal` (Windows/macOS) или IP хоста.

> Прокси используется только для Telegram. OpenProject ходит напрямую.

### Расписание и рабочий чат

1. Добавьте бота в рабочий чат / топик
2. Вызовите `/chatinfo` в нужном месте
3. Пропишите `schedule.chat_id` и при необходимости `schedule.message_thread_id`
4. Задайте `sprint_anchor_date` — понедельник недели 1 двухнедельного спринта

Пока `chat_id` пустой, теги команды в напоминания не добавляются.

### Карточки задач

Напишите в чат `#41`, `№41` или ссылку на задачу — бот ответит карточкой.

Оформление — в `openproject.display`:

- `telegram_users` — имя в OpenProject → Telegram username (без `@`)
- `emojis` / `translations` — эмодзи и подписи статусов, типов, отделов
- `default_boards` — доски проектов по умолчанию

---

## 🎯 Использование

### Команды

| Команда | Что делает |
|---------|------------|
| `/start` | Краткая справка |
| `/chatinfo` | `chat_id` и `message_thread_id` для `schedule` |
| `/upcoming` | Текущее время (TZ компании) и 3 ближайших напоминания |

### Задачи

- `#132` / `№132` / ссылка OpenProject → карточка задачи
- Если в тексте есть слово `daily` / `daili` — бот **не** отвечает карточкой (чтобы не мешать стендапу)

### Напоминания

События из `schedule.events` уходят в указанный чат в заданное время:

- Daily
- Планирование
- Релиз
- Ретроспектива
- Конец рабочего дня

---

## 💻 Запуск локально

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m most_bot
```

При старте бот подключится к OpenProject и выведет список проектов в консоль.

---

## 🐳 Запуск через Docker Compose

```bash
docker compose up --build -d
docker compose logs -f most-bot
```

Конфиг монтируется из `./config.yaml`.

---

## 📁 Структура проекта

```
most-bot/
├── config.yaml.example      # шаблон конфигурации
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── most_bot/
    ├── __main__.py          # точка входа
    ├── config.py            # загрузка config.yaml
    ├── schedule.py          # расписание напоминаний
    ├── schedule_defaults.py # дефолтные тексты событий
    ├── personality.py       # сборка сообщений бота
    ├── personality_defaults.py
    ├── bot/
    │   ├── handlers.py      # команды Telegram
    │   └── task_cards.py    # карточки задач
    └── openproject/
        ├── client.py
        ├── task_refs.py     # парсинг # / № / ссылок
        ├── tasks.py
        └── status_history.py
```

---

## 📎 Полезные ссылки

- [BotFather](https://t.me/BotFather) — создание бота
- [userinfobot](https://t.me/userinfobot) — узнать свой Telegram user id
- Стиль документации вдохновлён [HomeServerServices](https://github.com/StepanovPlaton/HomeServerServices)
