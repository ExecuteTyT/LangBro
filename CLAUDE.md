# CLAUDE.md — LangBro Bot

## Что это
Telegram-бот «LangBro» — AI-тренер для группового челленджа по изучению английского. Встраивается в активный чат ~20 человек, принимает ежедневные отчёты, ведёт статистику, мотивирует через геймификацию.

## Стек
- **Python 3.11+**, async
- **aiogram 3.x** — Telegram Bot API
- **SQLAlchemy 2.0** (async) + **asyncpg** — ORM и драйвер PostgreSQL
- **Alembic** — миграции
- **google-generativeai** — Gemini 2.5 Flash (Google AI Studio)
- **APScheduler** — cron-задачи (digest, reminders, quiz, WotD)
- **Pydantic v2** — валидация, settings
- **edge-tts** — Microsoft Edge TTS (бесплатно, без API-ключа, нейросетевые голоса)
- **ffmpeg** — конвертация MP3 → OGG Opus для Telegram voice messages
- **tenacity** — retry для LLM API

## Ключевые документы
Перед началом работы прочитай:
- `docs/01_TECHNICAL_SPEC.md` — полное ТЗ с функциональными требованиями (FR-xxx)
- `docs/02_DATABASE_SCHEMA.md` — схема PostgreSQL со всеми таблицами
- `docs/03_ARCHITECTURE.md` — структура проекта и архитектура
- `docs/04_LLM_PROMPTS.md` — все промпты для Gemini

## Структура проекта
```
bot/
├── __main__.py          # Точка входа
├── config.py            # Pydantic Settings (.env)
├── app.py               # Инициализация Bot, Dispatcher, middleware
├── db/                  # models.py, engine.py, repositories/
├── llm/                 # client.py, prompts/, schemas.py
├── handlers/            # Telegram command handlers
├── services/            # Бизнес-логика
├── scheduler/           # APScheduler jobs
├── middlewares/         # DB session injection, throttling
└── utils/               # formatting, keyboards, timezone
```

## Команды

```bash
# Запуск
docker-compose up -d db    # Postgres
python -m bot               # Бот

# Миграции
alembic upgrade head
alembic revision --autogenerate -m "description"

# Тесты
pytest tests/ -v
```

## Правила разработки

### Общие
- Весь async код — через `async/await`, никаких блокирующих вызовов
- Все DB-запросы через Repository-паттерн (`bot/db/repositories/`)
- Все LLM-вызовы через `GeminiClient` (`bot/llm/client.py`) — НЕ напрямую
- Конфигурация — через `bot/config.py` (Pydantic Settings), никаких хардкодов
- Все времена хранятся в UTC, конвертируются при отображении

### LLM (Gemini)
- Модель: `gemini-2.5-flash` — всегда через переменную `settings.GOOGLE_AI_MODEL`
- Все промпты хранятся в `bot/llm/prompts/` — не инлайн в коде
- JSON-ответы парсятся через Pydantic-модели (`bot/llm/schemas.py`)
- Каждый вызов логируется в `llm_usage_log` (feature, tokens, latency, cost)
- Retry: 3 попытки, exponential backoff через tenacity
- Rate limit: asyncio.Semaphore(10) глобально

### TTS (Edge TTS)
- Все голосовые генерируются через `TTSService` (`bot/services/tts_service.py`)
- Пайплайн: text → edge-tts → MP3 → ffmpeg → OGG Opus → Telegram voice
- Кеширование: voice_cache/ с ключом hash(text + voice + rate), TTL 30 дней
- Голоса: настраиваются per-challenge через settings (us_male по умолчанию)
- ffmpeg должен быть установлен на сервере (`apt install ffmpeg`)
- НЕ генерировать TTS в main thread — всегда async

### Telegram
- Используй aiogram 3.x Router-based архитектуру
- Каждый handler-файл создаёт свой `Router()`
- Inline keyboards — через `bot/utils/keyboards.py`
- Форматирование — Markdown V2 (экранирование спецсимволов!)
- Длинные сообщения (>4096 символов) — разбивать на части

### База данных
- SQLAlchemy 2.0 style (mapped_column, DeclarativeBase)
- Async sessions через middleware injection
- Никаких raw SQL — только через ORM/Repository
- Все модели в `bot/db/models.py`

### Error handling
- Все LLM-ошибки ловятся, участник видит: «Сорри, что-то пошло не так. Попробуй через минуту 🔧»
- Все ошибки логируются через стандартный logging
- Unhandled exceptions в handlers не крашат бота

## Порядок разработки (фазы)

### Phase 1 — MVP Core
1. Настроить проект (pyproject.toml, docker-compose, alembic)
2. Реализовать DB модели и миграции
3. GeminiClient с retry и логированием
4. Handlers: /start, /help, /create_challenge, /join, /members
5. Handler: /report + LLM парсинг + scoring + streak
6. Scheduler: daily_digest (22:00), reminder (20:00)
7. Handler: /mystats, /leaderboard

### Phase 2 — Engagement
8. Word of the Day (scheduler + handler)
9. Pop Quiz (scheduler + callback handlers)
10. Weekly Digest (scheduler)
11. Weekly Battles (создание пар + подведение итогов)

### Phase 3 — AI Coach
12. /check — разбор ошибок
13. /practice — ролевой диалог
14. /explain — объяснение слов
15. /translate — перевод с разбором

## Важно
- Бот встраивается в АКТИВНЫЙ челлендж — нужен гладкий онбординг
- **Онбординг через deep link**: `/launch` в группе → кнопка → deep link → анкета в личке. Бот НЕ может первым написать пользователю!
- **Multi-challenge**: один пользователь может быть в нескольких челленджах. В группе — контекст по chat_id. В личке — по active_challenge_id (автовыбор если 1, InlineKeyboard если 2+)
- **invite_code**: каждый челлендж имеет уникальный код (nanoid 8 символов) для deep link: `t.me/bot?start=join_{invite_code}`
- Персона бота: бро-тренер, неформальный, с юмором. НЕ корпоративный робот
- Gemini 2.5 Flash, НЕ Claude, НЕ OpenAI — весь LLM код через Google AI Studio SDK
- Часовой пояс по умолчанию — Europe/Moscow (MSK)
