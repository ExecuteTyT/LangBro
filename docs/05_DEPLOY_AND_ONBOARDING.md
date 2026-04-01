# LangBro — Онбординг и деплой

---

## Подготовка к запуску

### 1. Создать Telegram-бота
1. Открыть @BotFather в Telegram
2. `/newbot` → имя: `LangBro` (или другое), username: `langbro_english_bot` (или любой свободный)
3. Скопировать токен
4. Настройки бота в BotFather:
   - `/setdescription` — «AI-тренер английского для групповых челленджей 🔥»
   - `/setabouttext` — «Помогаю группе не сливаться в изучении английского. Отчёты, квизы, статистика, AI-коуч.»
   - `/setcommands`:
     ```
     start - Начать работу с ботом
     help - Список команд
     launch - Пригласить участников в челлендж (админ)
     report - Отправить отчёт за день
     mystats - Моя статистика
     leaderboard - Рейтинг участников
     streak - Мой streak
     switch - Переключить активный челлендж
     profile - Обновить уровень и цели
     check - Проверить текст на ошибки
     practice - Практика диалога
     explain - Объяснить слово/фразу
     translate - Перевод с разбором
     members - Участники челленджа
     settings - Настройки (админ)
     pause - Поставить на паузу
     vacation - Взять каникулы
     ```
   - `/setjoingroups` — Enable
   - `/setprivacy` — Disable (чтобы бот видел все сообщения в группе)

### 2. Получить API ключ Google AI Studio
1. Перейти на https://aistudio.google.com/apikey
2. Создать API key
3. Убедиться, что модель `gemini-2.5-flash` доступна

### 3. Настроить сервер
- VPS с Ubuntu 22.04+ или Debian 12+
- Минимум: 1 CPU, 1 GB RAM, 10 GB SSD
- Docker + Docker Compose установлены
- ffmpeg установлен (`apt install ffmpeg`) — для конвертации голосовых
- Или: Python 3.11+ и PostgreSQL 15+ напрямую

---

## Деплой

### Docker (рекомендуется)
```bash
git clone <repo-url> langbro
cd langbro

# Создать .env из шаблона
cp .env.example .env
nano .env  # заполнить TELEGRAM_BOT_TOKEN и GOOGLE_AI_API_KEY

# Запустить
docker-compose up -d

# Проверить логи
docker-compose logs -f bot
```

### Без Docker
```bash
# PostgreSQL
sudo apt install postgresql
sudo -u postgres createdb langbro
sudo -u postgres createuser langbro -P

# Проект
git clone <repo-url> langbro
cd langbro
python -m venv venv
source venv/bin/activate
pip install -e .

# Миграции
cp .env.example .env
nano .env
alembic upgrade head

# Запуск через systemd
sudo cp deploy/langbro.service /etc/systemd/system/
sudo systemctl enable langbro
sudo systemctl start langbro
```

### systemd unit file (deploy/langbro.service)
```ini
[Unit]
Description=LangBro Telegram Bot
After=network.target postgresql.service

[Service]
Type=simple
User=langbro
WorkingDirectory=/opt/langbro
EnvironmentFile=/opt/langbro/.env
ExecStart=/opt/langbro/venv/bin/python -m bot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## Онбординг в существующий челлендж

Бот встраивается в активный чат с ~20 участниками. Сценарий:

### Шаг 1: Добавить бота в группу
- Админ (Айрат) добавляет бота в групповой чат
- Бот отправляет приветствие и краткую инструкцию

### Шаг 2: Создать челлендж
- Айрат отправляет `/create_challenge`
- Задаёт параметры: «Английский до B2», пн-пт, дедлайн 23:59
- Бот генерирует `invite_code` (nanoid 8 символов)

### Шаг 3: Запуск и присоединение участников
- Айрат отправляет `/launch` в группе
- Бот постит красивое сообщение с кнопкой «🚀 Присоединиться»
- Кнопка — deep link: `t.me/langbro_bot?start=join_{invite_code}`
- Каждый участник нажимает кнопку → переходит в личку бота
- Бот проводит анкету (имя, уровень, цель) — ОДИН РАЗ
- После анкеты бот пишет в группу: «Айрат в деле! 🤝»
- Если кто-то не присоединился — Айрат кидает `/launch` повторно

### Шаг 4: Первый день
- Утро: Word of the Day
- День: Pop Quiz
- Вечер: участники шлют отчёты через `/report`
- 22:00: первый Daily Digest

### Шаг 5: Адаптация
- Первую неделю — собирать фидбэк
- Подкрутить баллы, если нужно
- Добавить/убрать фичи через `/settings`

---

## Мониторинг

### Логи
```bash
# Docker
docker-compose logs -f bot

# systemd
journalctl -u langbro -f
```

### Метрики (проверять еженедельно)
```sql
-- Расход LLM за последние 7 дней
SELECT feature, COUNT(*), 
       SUM(input_tokens) as total_input,
       SUM(output_tokens) as total_output,
       SUM(cost_usd) as total_cost
FROM llm_usage_log 
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY feature;

-- Активность участников
SELECT u.display_name, uc.current_streak, uc.total_points, uc.total_reports
FROM user_challenges uc
JOIN users u ON u.id = uc.user_id
WHERE uc.status = 'active'
ORDER BY uc.total_points DESC;

-- % отчётов за последние 7 дней
SELECT report_date, COUNT(*) as reports,
       (SELECT COUNT(*) FROM user_challenges WHERE status = 'active') as total
FROM daily_reports 
WHERE report_date > CURRENT_DATE - 7
GROUP BY report_date ORDER BY report_date;
```

---

## Бэкап

```bash
# Ежедневный бэкап PostgreSQL
pg_dump -U langbro langbro | gzip > /backups/langbro_$(date +%Y%m%d).sql.gz

# Хранить 30 дней
find /backups -name "langbro_*.sql.gz" -mtime +30 -delete

# Очистка кеша голосовых (старше 30 дней)
find /opt/langbro/voice_cache -name "*.ogg" -mtime +30 -delete
```

Добавить в crontab:
```
0 3 * * * pg_dump -U langbro langbro | gzip > /backups/langbro_$(date +\%Y\%m\%d).sql.gz && find /backups -name "langbro_*.sql.gz" -mtime +30 -delete
0 4 * * 0 find /opt/langbro/voice_cache -name "*.ogg" -mtime +30 -delete
```
