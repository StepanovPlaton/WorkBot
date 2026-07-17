# Пинг

Telegram-бот-компаньон веб-студии: задачи в OpenProject, напоминания о встречах и лёгкий юмор.

**Пинг** — бодрый напарник, который «пингует» в нужный момент: подскажет по задаче и напомнит о созвоне.

## Быстрый старт

### 1. Получить Telegram-токен

1. Откройте Telegram и найдите [@BotFather](https://t.me/BotFather).
2. Отправьте команду `/newbot`.
3. Укажите **display name** — как бот будет называться в списке чатов (например, `Пинг`).
4. Укажите **username** — должен заканчиваться на `bot` (например, `most_ping_bot`).
5. BotFather пришлёт сообщение с токеном вида `1234567890:AAH...`. Сохраните его — это `telegram.token` в конфиге.

Дополнительно (по желанию):

- `/setdescription` — например: «Пингую по задачам и созвонам. OpenProject, напоминания, zero drama.»
- `/setabouttext` — короткий текст «О боте», например: «🏓 Пинг — компаньон команды разработки»
- `/setcommands` — список команд для меню в Telegram:

```
start - Кратко, что умею
chatinfo - Chat id и топик для напоминаний
upcoming - 3 ближайших напоминания с датой
```

Узнать свой Telegram user id можно у [@userinfobot](https://t.me/userinfobot) — пригодится для `allowed_user_ids`.

### 2. Настроить config.yaml

```bash
cp config.yaml.example config.yaml
```

Заполните:

- `telegram.token` — токен от BotFather
- `telegram.proxy` — SOCKS5-прокси, если Telegram недоступен напрямую (см. ниже)
- `openproject.host`, `openproject.token` — как в проекте [auto_op](../auto_op)

#### SOCKS5-прокси для Telegram

Если Telegram API недоступен в вашем регионе, включите прокси:

```yaml
telegram:
  proxy:
    enabled: true
    scheme: socks5
    host: 127.0.0.1
    port: 1080
    username: ''
    password: ''
```

- `socks5` — DNS резолвится на стороне клиента (бота)
- `socks5h` — DNS резолвится через прокси (удобнее, если прокси за границей)

В Docker `127.0.0.1` указывает на контейнер, а не на хост. Если прокси крутится на машине с Docker, используйте `host.docker.internal` (Windows/macOS) или IP хоста в сети.

Прокси используется только для Telegram API. OpenProject ходит напрямую.

#### Персонализация бота

Тексты и характер настраиваются в секции `bot` в `config.yaml`. Если поле не указано — подставляются дефолты Пинга.

| Поле | Описание |
|------|----------|
| `name` | Имя бота |
| `emoji` | Эмодзи в `/start` |
| `unknown_command_replies` | Ответ на неизвестную команду |
| `access_denied_replies` | Ответ при отказе в доступе |
| `start_commands` | Текст `/start` |

#### Карточки задач и эмодзи

Напишите в чат `#41` или ссылку на задачу — Пинг ответит карточкой с типом, статусом, временем в колонке, ответственным и story points.

Пример ссылки: `http://host:8081/projects/zor/boards/37/details/41`

Оформление настраивается в `openproject.display`:

```yaml
openproject:
  display:
    story_points_field: storyPoints
    project_departments:
      zor: backend
    emojis:
      default: '📋'
      projects:
        zor: '⚡'
      departments:
        backend: '⚙️'
        frontend: '🎨'
      statuses:
        New: '🆕'
        'In progress': '🔧'
      types:
        Task: '📝'
        Bug: '🐛'
```

- `statuses` — колонки/статусы на доске
- `projects` — смайлик проекта
- `departments` + `project_departments` — смайлик отдела для проекта
- `types` — тип задачи (Bug, Task, Feature…)

### 3. Запуск локально

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m most_bot
```

При старте бот подключится к OpenProject и выведет в консоль список проектов. В Telegram: `/start`, `/chatinfo`, `/upcoming`, а также карточки задач по `#номер` или ссылке.

### 4. Запуск через Docker Compose

```bash
docker compose up --build -d
docker compose logs -f most-bot
```

Конфиг монтируется из `./config.yaml`.

## Структура проекта

```
most-bot/
├── config.yaml.example   # шаблон конфигурации
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── most_bot/
    ├── __main__.py       # точка входа
    ├── config.py              # загрузка config.yaml
    ├── personality.py         # сборка сообщений из конфига
    ├── personality_defaults.py # дефолтные тексты Пинга
    ├── bot/
    │   ├── handlers.py   # команды Telegram
    │   └── task_cards.py # карточки задач
    └── openproject/
        ├── client.py
        ├── task_refs.py  # парсинг #41 и ссылок
        ├── tasks.py      # загрузка сводки по задаче
        └── status_history.py
```

## OpenProject API-токен

Создайте персональный API-токен в OpenProject:

**My account → Access tokens → + API token**

Токен кладите в `openproject.token` в `config.yaml`.
