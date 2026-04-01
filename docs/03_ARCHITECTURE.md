# LangBro — Архитектура и структура проекта

---

## Структура проекта

```
langbro/
├── CLAUDE.md                      # Инструкции для Claude Code
├── README.md
├── .env.example                   # Шаблон переменных окружения
├── .gitignore
├── pyproject.toml                 # Poetry / pip конфигурация
├── docker-compose.yml             # Postgres + Bot
├── Dockerfile
│
├── alembic/                       # Миграции БД
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
│
├── bot/                           # Основной пакет бота
│   ├── __init__.py
│   ├── __main__.py                # Точка входа (python -m bot)
│   ├── config.py                  # Pydantic Settings (загрузка .env)
│   ├── app.py                     # Инициализация бота, диспатчера, middleware
│   │
│   ├── db/                        # Работа с базой данных
│   │   ├── __init__.py
│   │   ├── engine.py              # SQLAlchemy async engine + session
│   │   ├── models.py              # SQLAlchemy ORM модели
│   │   └── repositories/         # Паттерн Repository
│   │       ├── __init__.py
│   │       ├── user_repo.py
│   │       ├── challenge_repo.py
│   │       ├── report_repo.py
│   │       ├── quiz_repo.py
│   │       └── stats_repo.py
│   │
│   ├── llm/                       # Работа с Gemini API
│   │   ├── __init__.py
│   │   ├── client.py              # GeminiClient (обёртка API)
│   │   ├── prompts/               # Системные промпты
│   │   │   ├── __init__.py
│   │   │   ├── report_parser.py   # Промпт для парсинга отчётов
│   │   │   ├── bot_persona.py     # Промпт персоны бота
│   │   │   ├── quiz_generator.py  # Промпт генерации квизов
│   │   │   ├── wotd_generator.py  # Промпт Word of the Day
│   │   │   ├── digest_generator.py # Промпт для сводок
│   │   │   └── coach.py           # Промпт AI Coach
│   │   └── schemas.py             # Pydantic-модели для LLM-ответов
│   │
│   ├── handlers/                  # Telegram обработчики команд
│   │   ├── __init__.py
│   │   ├── start.py               # /start, /help
│   │   ├── challenge.py           # /create_challenge, /join, /members
│   │   ├── report.py              # /report, обработка отчётов
│   │   ├── stats.py               # /mystats, /leaderboard, /streak
│   │   ├── quiz.py                # Обработка ответов на квиз (callback)
│   │   ├── admin.py               # /settings, /kick, /pause
│   │   ├── coach.py               # /check, /practice, /explain, /translate
│   │   └── common.py              # Общие фильтры и утилиты
│   │
│   ├── services/                  # Бизнес-логика
│   │   ├── __init__.py
│   │   ├── report_service.py      # Логика обработки отчётов
│   │   ├── streak_service.py      # Вычисление и обновление streak
│   │   ├── scoring_service.py     # Подсчёт баллов
│   │   ├── digest_service.py      # Генерация сводок
│   │   ├── quiz_service.py        # Создание и обработка квизов
│   │   ├── wotd_service.py        # Word of the Day
│   │   ├── battle_service.py      # Weekly Battles
│   │   ├── coach_service.py       # AI Coach (личка)
│   │   └── tts_service.py         # Text-to-Speech (Edge TTS + ffmpeg + кеш)
│   │
│   ├── scheduler/                 # Планировщик задач
│   │   ├── __init__.py
│   │   ├── setup.py               # Инициализация APScheduler
│   │   └── jobs.py                # Определения задач (digest, reminder, wotd, quiz)
│   │
│   ├── middlewares/               # aiogram middlewares
│   │   ├── __init__.py
│   │   ├── db_session.py          # Инжекция DB сессии в handler
│   │   ├── user_registration.py   # Авто-регистрация пользователей
│   │   ├── challenge_context.py   # Определение активного челленджа (группа → по chat_id, личка → по active_challenge_id)
│   │   └── throttling.py          # Rate limiting
│   │
│   └── utils/                     # Утилиты
│       ├── __init__.py
│       ├── formatting.py          # Форматирование сообщений (Markdown)
│       ├── keyboards.py           # InlineKeyboard билдеры
│       └── timezone.py            # Работа с часовыми поясами
│
└── tests/                         # Тесты
    ├── __init__.py
    ├── conftest.py                # Fixtures
    ├── test_report_parser.py      # Тесты парсинга отчётов
    ├── test_scoring.py            # Тесты подсчёта баллов
    ├── test_streak.py             # Тесты streak логики
    └── test_digest.py             # Тесты генерации сводок
```

---

## Архитектура (компоненты)

```
┌──────────────────────────────────────────────┐
│                 Telegram API                  │
└───────────────────┬──────────────────────────┘
                    │
         ┌──────────▼──────────┐
         │   aiogram 3 Bot     │
         │   (Dispatcher)      │
         └──┬───────┬───────┬──┘
            │       │       │
   ┌────────▼──┐ ┌──▼─────┐ ┌▼──────────┐
   │ Handlers  │ │Middlew.│ │ Scheduler  │
   │ (команды) │ │(auth,  │ │(APScheduler│
   │           │ │ db,    │ │ cron jobs) │
   │           │ │ rate)  │ │            │
   └─────┬─────┘ └────────┘ └─────┬──────┘
         │                        │
    ┌────▼────────────────────────▼────┐
    │          Services Layer          │
    │  (report, streak, scoring,       │
    │   digest, quiz, wotd, coach)     │
    └──┬──────────────────────────┬────┘
       │                          │
  ┌────▼─────┐            ┌──────▼──────┐
  │ DB Layer │            │  LLM Layer  │
  │(Postgres │            │  (Gemini    │
  │ +SQLAlch)│            │   2.5 Flash)│
  └──────────┘            └─────────────┘
```

---

## Поток данных: приём отчёта

```
1. Участник → /report "Сегодня учил 20 слов и смотрел TED Talk"
2. Handler (report.py) → получает message
3. Middleware → инжектирует db session, проверяет user
4. ReportService.process_report():
   a. Проверяет: есть ли отчёт за сегодня (если да — перезаписывает)
   b. GeminiClient.parse_report(raw_text) → JSON с активностями
   c. ScoringService.calculate_points(activities, multipliers)
   d. StreakService.update_streak(user_challenge)
   e. ReportRepo.save(report, activities)
   f. Генерирует ответ с персоной бота через LLM
5. Handler → отправляет ответ в чат
```

---

## Конфигурация (.env)

```env
# Telegram
TELEGRAM_BOT_TOKEN=<token from @BotFather>

# Database
DATABASE_URL=postgresql+asyncpg://langbro:password@localhost:5432/langbro

# Google AI Studio
GOOGLE_AI_API_KEY=<key from AI Studio>
GOOGLE_AI_MODEL=gemini-2.5-flash

# App settings
DEFAULT_TIMEZONE=Europe/Moscow
LOG_LEVEL=INFO
DEBUG=false
```

---

## Docker Compose

```yaml
version: '3.8'

services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: langbro
      POSTGRES_USER: langbro
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-langbro_dev}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U langbro"]
      interval: 5s
      timeout: 3s
      retries: 5

  bot:
    build: .
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped
    command: python -m bot

volumes:
  pgdata:
```

---

## Ключевые технические решения

### Streak-вычисление

**Маршрутизация челленджа (ChallengeContextMiddleware)**

Ключевой middleware — определяет, к какому челленджу привязать действие:

```python
class ChallengeContextMiddleware:
    async def resolve_challenge(self, event) -> Challenge | None:
        if event.chat.type != "private":
            # ГРУППА: однозначно по chat_id
            return await challenge_repo.get_active_by_chat(event.chat.id)
        
        # ЛИЧКА: по active_challenge_id пользователя
        user = await user_repo.get_by_telegram_id(event.from_user.id)
        active_challenges = await challenge_repo.get_user_active_challenges(user.id)
        
        if len(active_challenges) == 0:
            return None  # Не в челлендже
        elif len(active_challenges) == 1:
            return active_challenges[0]  # Автопривязка
        elif user.active_challenge_id:
            return await challenge_repo.get_by_id(user.active_challenge_id)
        else:
            return None  # Нужен выбор → handler покажет InlineKeyboard
```

**Deep link onboarding**

```python
# Участник нажимает кнопку t.me/bot?start=join_abc123
@router.message(CommandStart(deep_link=True))
async def cmd_start_deeplink(message, command: CommandObject):
    payload = command.args  # "join_abc123"
    if payload.startswith("join_"):
        invite_code = payload[5:]  # "abc123"
        challenge = await challenge_repo.get_by_invite_code(invite_code)
        if not challenge:
            await message.answer("Челлендж не найден 🤷")
            return
        # Запустить анкету (FSM) или сразу добавить если onboarding_complete
        ...
```

### Streak-вычисление
```python
# Streak обновляется при каждом отчёте, не пересчитывается из истории
# Это O(1) вместо O(N)

def update_streak(user_challenge, report_date, schedule_days):
    last = user_challenge.last_report_date
    
    if last is None:
        # Первый отчёт
        user_challenge.current_streak = 1
    elif is_next_scheduled_day(last, report_date, schedule_days):
        # Следующий запланированный день — streak продолжается
        user_challenge.current_streak += 1
    elif last == report_date:
        # Повторный отчёт за тот же день — streak не меняется
        pass
    else:
        # Пропуск — streak сбрасывается
        user_challenge.current_streak = 1
    
    user_challenge.best_streak = max(
        user_challenge.best_streak, 
        user_challenge.current_streak
    )
    user_challenge.last_report_date = report_date
```

### LLM-вызовы: retry + cost tracking
```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def call_gemini(prompt, system, response_schema=None):
    start = time.monotonic()
    response = await model.generate_content_async(...)
    latency = (time.monotonic() - start) * 1000
    
    # Логируем использование
    await log_llm_usage(
        feature=current_feature,
        model="gemini-2.5-flash",
        input_tokens=response.usage_metadata.prompt_token_count,
        output_tokens=response.usage_metadata.candidates_token_count,
        latency_ms=latency
    )
    return response
```

### Rate limiting для LLM
- Не больше 1 LLM-вызова на пользователя в 5 секунд
- Глобальный лимит: 60 RPM (requests per minute) для Gemini
- Для массовых операций (digest, quiz gen) — очередь через asyncio.Semaphore

### TTS Service (Edge TTS + ffmpeg)
```python
# bot/services/tts_service.py
import edge_tts
import hashlib
import asyncio
from pathlib import Path

VOICE_CACHE_DIR = Path("voice_cache")
VOICES = {
    "us_male": "en-US-GuyNeural",
    "us_female": "en-US-AriaNeural",
    "uk_male": "en-GB-RyanNeural",
    "uk_female": "en-GB-SoniaNeural",
    "au_male": "en-AU-WilliamNeural",
}

class TTSService:
    async def generate_voice(
        self, text: str, voice: str = "us_male", rate: str = "+0%"
    ) -> Path:
        """Генерирует голосовое в OGG Opus. Возвращает путь к файлу."""
        voice_id = VOICES[voice]
        # Кеш по хешу параметров
        cache_key = hashlib.md5(f"{text}:{voice_id}:{rate}".encode()).hexdigest()
        ogg_path = VOICE_CACHE_DIR / f"{cache_key}.ogg"
        
        if ogg_path.exists():
            return ogg_path  # Кешированный файл
        
        # Генерация MP3 через Edge TTS
        mp3_path = VOICE_CACHE_DIR / f"{cache_key}.mp3"
        communicate = edge_tts.Communicate(text=text, voice=voice_id, rate=rate)
        await communicate.save(str(mp3_path))
        
        # Конвертация MP3 → OGG Opus для Telegram
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", str(mp3_path),
            "-c:a", "libopus", "-b:a", "64k",
            str(ogg_path), "-y",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        mp3_path.unlink()  # Удаляем MP3, храним только OGG
        
        return ogg_path
    
    async def generate_wotd_voice(self, word: str, example: str, voice: str) -> Path:
        """Слово (медленно) + пауза + пример (нормально)."""
        # Генерируем две части и склеиваем через ffmpeg
        word_path = await self.generate_voice(word, voice, rate="-30%")
        example_path = await self.generate_voice(example, voice, rate="+0%")
        # Склейка с паузой
        combined = VOICE_CACHE_DIR / f"wotd_{hashlib.md5(word.encode()).hexdigest()}.ogg"
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i", str(word_path),
            "-i", str(example_path),
            "-filter_complex",
            "[0]apad=pad_dur=1[a];[a][1]concat=n=2:v=0:a=1",
            "-c:a", "libopus", "-b:a", "64k",
            str(combined), "-y",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return combined
```

**Отправка в Telegram (в handler):**
```python
from aiogram.types import FSInputFile

voice_path = await tts_service.generate_voice("Great job, keep it up!", voice="us_male")
await message.answer_voice(FSInputFile(voice_path))
```

---

## Зависимости (pyproject.toml)

```toml
[tool.poetry]
name = "langbro"
version = "1.0.0"
python = "^3.11"

[tool.poetry.dependencies]
aiogram = "^3.4"
sqlalchemy = {extras = ["asyncio"], version = "^2.0"}
asyncpg = "^0.29"
alembic = "^1.13"
google-generativeai = "^0.8"
apscheduler = "^3.10"
pydantic = "^2.6"
pydantic-settings = "^2.2"
tenacity = "^8.2"              # retry logic
python-dotenv = "^1.0"
edge-tts = "^7.0"              # Microsoft Edge TTS (бесплатно, без API-ключа)

# Системные зависимости (apt install):
# ffmpeg — конвертация MP3 → OGG Opus для Telegram voice

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-asyncio = "^0.23"
```
