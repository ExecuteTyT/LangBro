# LangBro — Схема базы данных
## PostgreSQL Schema v1.0

---

## ER-диаграмма (текстовая)

```
User 1──N UserChallenge N──1 Challenge
                │
                │ 1
                │
                N
          DailyReport 1──N ReportActivity
                
Challenge 1──N Quiz 1──N QuizAnswer
Challenge 1──N WordOfTheDay
Challenge 1──N WeeklyBattle 1──N BattlePair
Challenge 1──N ScheduledMessage
```

---

## Таблицы

### users
Участники бота (все пользователи, которые когда-либо взаимодействовали).

```sql
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,       -- Telegram user ID
    username VARCHAR(255),                     -- @username (может быть NULL)
    first_name VARCHAR(255) NOT NULL,          -- Имя в Telegram
    display_name VARCHAR(255),                 -- Как обращается бот (заполняется при онбординге)
    english_level VARCHAR(10) DEFAULT 'A1',    -- A1, A2, B1, B1+, B2
    learning_goal VARCHAR(50),                 -- speaking, work, exam, general
    bot_language_mix INTEGER DEFAULT 10,       -- % английского в ответах бота (10-50)
    active_challenge_id BIGINT,               -- Активный челлендж для контекста в личке (FK → challenges)
    onboarding_complete BOOLEAN DEFAULT FALSE, -- Прошёл ли анкету (имя, уровень, цель)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_telegram_id ON users(telegram_id);
```

### challenges
Челленджи. Один чат может иметь один активный челлендж.

```sql
CREATE TABLE challenges (
    id BIGSERIAL PRIMARY KEY,
    invite_code VARCHAR(20) UNIQUE NOT NULL,   -- Короткий код для deep link (nanoid, 8 символов)
    chat_id BIGINT NOT NULL,                   -- Telegram chat ID группы
    title VARCHAR(255) NOT NULL,               -- Название челленджа
    status VARCHAR(20) DEFAULT 'active',       -- active, paused, completed
    schedule_days INTEGER[] DEFAULT '{1,2,3,4,5}',  -- 1=пн, 7=вс
    timezone VARCHAR(50) DEFAULT 'Europe/Moscow',
    report_deadline_time TIME DEFAULT '23:59',
    digest_time TIME DEFAULT '22:00',
    reminder_time TIME DEFAULT '20:00',
    wotd_time TIME DEFAULT '08:00',            -- Word of the Day
    quiz_window_start TIME DEFAULT '12:00',
    quiz_window_end TIME DEFAULT '15:00',
    features_enabled JSONB DEFAULT '{
        "daily_digest": true,
        "reminders": true,
        "word_of_day": true,
        "pop_quiz": true,
        "weekly_battles": true,
        "weekly_digest": true
    }',
    scoring_multipliers JSONB DEFAULT '{
        "speaking": 2,
        "listening": 1,
        "reading": 1.5,
        "writing": 2,
        "vocabulary": 3,
        "grammar": 5,
        "app_practice": 10,
        "other": 5,
        "wotd_bonus": 20,
        "quiz_correct": 15,
        "quiz_speed_bonus": 10
    }',
    created_by BIGINT REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_challenges_active_chat ON challenges(chat_id) 
    WHERE status = 'active';
```

### user_challenges
Связь участников с челленджами. Содержит streak и общую статистику.

```sql
CREATE TABLE user_challenges (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    challenge_id BIGINT REFERENCES challenges(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'active',       -- active, paused, left, kicked
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Streak tracking
    current_streak INTEGER DEFAULT 0,
    best_streak INTEGER DEFAULT 0,
    last_report_date DATE,                     -- дата последнего отчёта
    
    -- Aggregated stats (обновляются при каждом отчёте)
    total_points INTEGER DEFAULT 0,
    total_reports INTEGER DEFAULT 0,
    total_days_in_challenge INTEGER DEFAULT 0,
    
    -- Vacation
    vacation_until DATE,                       -- NULL если не на каникулах
    vacation_days_used INTEGER DEFAULT 0,      -- за текущий месяц
    
    -- Activity distribution (обновляется при каждом отчёте)
    activity_stats JSONB DEFAULT '{
        "speaking_minutes": 0,
        "listening_minutes": 0,
        "reading_minutes": 0,
        "writing_minutes": 0,
        "vocabulary_count": 0,
        "grammar_lessons": 0,
        "app_lessons": 0
    }',
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_id, challenge_id)
);

CREATE INDEX idx_uc_challenge ON user_challenges(challenge_id);
CREATE INDEX idx_uc_user ON user_challenges(user_id);
CREATE INDEX idx_uc_status ON user_challenges(status);
```

### daily_reports
Ежедневные отчёты участников.

```sql
CREATE TABLE daily_reports (
    id BIGSERIAL PRIMARY KEY,
    user_challenge_id BIGINT REFERENCES user_challenges(id) ON DELETE CASCADE,
    report_date DATE NOT NULL,
    
    -- Raw data
    raw_text TEXT NOT NULL,                    -- Исходный текст отчёта
    message_id BIGINT,                        -- Telegram message ID
    source VARCHAR(20) DEFAULT 'group',       -- group, private
    
    -- Parsed data
    parsed_data JSONB,                        -- Полный JSON от LLM
    total_points INTEGER DEFAULT 0,
    summary TEXT,                             -- Краткое саммари от LLM
    
    -- Word of the Day tracking
    wotd_used BOOLEAN DEFAULT FALSE,          -- Использовал ли WotD
    wotd_bonus_points INTEGER DEFAULT 0,
    
    -- LLM metadata
    llm_model VARCHAR(100),
    llm_tokens_used INTEGER,
    llm_parse_time_ms INTEGER,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_challenge_id, report_date)    -- один отчёт в день (перезапись)
);

CREATE INDEX idx_reports_date ON daily_reports(report_date);
CREATE INDEX idx_reports_uc ON daily_reports(user_challenge_id);
```

### report_activities
Разбитые активности из отчёта (денормализация для аналитики).

```sql
CREATE TABLE report_activities (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT REFERENCES daily_reports(id) ON DELETE CASCADE,
    category VARCHAR(30) NOT NULL,            -- speaking, listening, etc.
    description TEXT,
    duration_minutes INTEGER,                 -- для timed-активностей
    count INTEGER,                            -- для counted-активностей (слова, уроки)
    points INTEGER DEFAULT 0,
    details TEXT                              -- дополнительные детали
);

CREATE INDEX idx_activities_report ON report_activities(report_id);
CREATE INDEX idx_activities_category ON report_activities(category);
```

### words_of_the_day
История слов дня.

```sql
CREATE TABLE words_of_the_day (
    id BIGSERIAL PRIMARY KEY,
    challenge_id BIGINT REFERENCES challenges(id) ON DELETE CASCADE,
    word VARCHAR(255) NOT NULL,
    pronunciation VARCHAR(255),
    translation TEXT,
    level VARCHAR(10),                        -- A1-C2
    examples JSONB,                           -- ["example1", "example2"]
    related_words JSONB,                      -- ["word1", "word2"]
    message_id BIGINT,                        -- Telegram message ID
    posted_date DATE NOT NULL,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(challenge_id, posted_date)
);

CREATE INDEX idx_wotd_challenge ON words_of_the_day(challenge_id);
```

### quizzes
Pop Quiz вопросы.

```sql
CREATE TABLE quizzes (
    id BIGSERIAL PRIMARY KEY,
    challenge_id BIGINT REFERENCES challenges(id) ON DELETE CASCADE,
    quiz_type VARCHAR(30) NOT NULL,           -- translation, grammar, fill_blank, phrasal_verb, find_error, synonym
    question TEXT NOT NULL,
    options JSONB NOT NULL,                   -- ["option1", "option2", "option3", "option4"]
    correct_option INTEGER NOT NULL,          -- индекс правильного ответа (0-3)
    explanation TEXT,                         -- объяснение правильного ответа
    level VARCHAR(10),
    message_id BIGINT,                        -- Telegram message ID
    posted_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,                    -- когда квиз закрылся
    status VARCHAR(20) DEFAULT 'pending',     -- pending, active, closed
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_quizzes_challenge ON quizzes(challenge_id);
CREATE INDEX idx_quizzes_status ON quizzes(status);
```

### quiz_answers
Ответы участников на квизы.

```sql
CREATE TABLE quiz_answers (
    id BIGSERIAL PRIMARY KEY,
    quiz_id BIGINT REFERENCES quizzes(id) ON DELETE CASCADE,
    user_challenge_id BIGINT REFERENCES user_challenges(id) ON DELETE CASCADE,
    selected_option INTEGER NOT NULL,
    is_correct BOOLEAN NOT NULL,
    is_first_correct BOOLEAN DEFAULT FALSE,    -- первый правильный ответ
    points_earned INTEGER DEFAULT 0,
    answered_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(quiz_id, user_challenge_id)
);

CREATE INDEX idx_qa_quiz ON quiz_answers(quiz_id);
```

### weekly_battles
Еженедельные баттлы.

```sql
CREATE TABLE weekly_battles (
    id BIGSERIAL PRIMARY KEY,
    challenge_id BIGINT REFERENCES challenges(id) ON DELETE CASCADE,
    week_start DATE NOT NULL,                  -- понедельник
    week_end DATE NOT NULL,                    -- пятница
    status VARCHAR(20) DEFAULT 'active',       -- active, completed
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_wb_challenge ON weekly_battles(challenge_id);
```

### battle_pairs
Пары участников в батле.

```sql
CREATE TABLE battle_pairs (
    id BIGSERIAL PRIMARY KEY,
    battle_id BIGINT REFERENCES weekly_battles(id) ON DELETE CASCADE,
    player1_id BIGINT REFERENCES user_challenges(id),
    player2_id BIGINT REFERENCES user_challenges(id),  -- NULL = bye
    player1_points INTEGER DEFAULT 0,
    player2_points INTEGER DEFAULT 0,
    winner_id BIGINT REFERENCES user_challenges(id),    -- NULL пока не завершён
    loser_penalty_task TEXT,                             -- сгенерированное задание для проигравшего
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_bp_battle ON battle_pairs(battle_id);
```

### conversation_history
История диалогов с AI Coach (личка) для контекста.

```sql
CREATE TABLE conversation_history (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,                -- user, assistant
    content TEXT NOT NULL,
    feature VARCHAR(30),                      -- check, practice, explain, translate
    tokens_used INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ch_user ON conversation_history(user_id);
CREATE INDEX idx_ch_created ON conversation_history(created_at);

-- Автоочистка: хранить только последние 30 дней
-- Реализовать через cron job или pg_cron
```

### llm_usage_log
Лог использования LLM для контроля расходов.

```sql
CREATE TABLE llm_usage_log (
    id BIGSERIAL PRIMARY KEY,
    feature VARCHAR(50) NOT NULL,              -- report_parse, digest, quiz_gen, wotd, coach, bot_reply
    model VARCHAR(100) NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    latency_ms INTEGER,
    cost_usd DECIMAL(10, 6),                   -- примерная стоимость
    error TEXT,                                -- если был error
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_llm_log_feature ON llm_usage_log(feature);
CREATE INDEX idx_llm_log_created ON llm_usage_log(created_at);
```

---

## Миграции

Использовать `alembic` для управления миграциями.

```
alembic/
├── versions/
│   ├── 001_initial_schema.py
│   ├── 002_add_quiz_tables.py
│   └── ...
├── env.py
└── alembic.ini
```

---

## Индексы для частых запросов

```sql
-- "Кто сегодня не отчитался?" (для напоминаний)
-- JOIN user_challenges + daily_reports WHERE report_date = today AND report IS NULL
CREATE INDEX idx_reports_date_uc ON daily_reports(user_challenge_id, report_date);

-- "Рейтинг за неделю" 
CREATE INDEX idx_reports_date_points ON daily_reports(report_date, total_points);

-- "Streak вычисление" — по last_report_date в user_challenges
CREATE INDEX idx_uc_last_report ON user_challenges(last_report_date);
```
