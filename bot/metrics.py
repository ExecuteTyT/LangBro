"""Prometheus metrics for LangBro bot.

Exposes metrics at :9090/metrics for Grafana scraping.
"""

import logging
from threading import Thread

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    start_http_server,
)

logger = logging.getLogger(__name__)

# --- Registry -----------------------------------------------------------
REGISTRY = CollectorRegistry(auto_describe=True)

# --- Bot info ------------------------------------------------------------
BOT_INFO = Info("langbro", "LangBro bot metadata", registry=REGISTRY)

# --- Telegram metrics ----------------------------------------------------
TELEGRAM_MESSAGES = Counter(
    "langbro_telegram_messages_total",
    "Total Telegram messages processed",
    ["chat_type"],  # private, group, supergroup
    registry=REGISTRY,
)
TELEGRAM_COMMANDS = Counter(
    "langbro_telegram_commands_total",
    "Telegram commands invoked",
    ["command"],  # /start, /report, /check, etc.
    registry=REGISTRY,
)
TELEGRAM_CALLBACKS = Counter(
    "langbro_telegram_callbacks_total",
    "Inline callback queries processed",
    registry=REGISTRY,
)
TELEGRAM_ERRORS = Counter(
    "langbro_telegram_handler_errors_total",
    "Unhandled errors in Telegram handlers",
    ["handler"],
    registry=REGISTRY,
)

# --- LLM metrics --------------------------------------------------------
LLM_REQUESTS = Counter(
    "langbro_llm_requests_total",
    "Total LLM API calls",
    ["feature", "status"],  # status: success / error
    registry=REGISTRY,
)
LLM_TOKENS_INPUT = Counter(
    "langbro_llm_tokens_input_total",
    "Total input tokens sent to LLM",
    ["feature"],
    registry=REGISTRY,
)
LLM_TOKENS_OUTPUT = Counter(
    "langbro_llm_tokens_output_total",
    "Total output tokens received from LLM",
    ["feature"],
    registry=REGISTRY,
)
LLM_LATENCY = Histogram(
    "langbro_llm_latency_seconds",
    "LLM call latency in seconds",
    ["feature"],
    buckets=[0.5, 1, 2, 3, 5, 8, 10, 15, 20, 30],
    registry=REGISTRY,
)
LLM_SEMAPHORE_QUEUE = Gauge(
    "langbro_llm_semaphore_waiting",
    "Number of LLM calls waiting for semaphore",
    registry=REGISTRY,
)

# --- Scheduler metrics ---------------------------------------------------
SCHEDULER_JOB_RUNS = Counter(
    "langbro_scheduler_job_runs_total",
    "Scheduler job executions",
    ["job", "status"],  # status: success / error
    registry=REGISTRY,
)
SCHEDULER_JOB_DURATION = Histogram(
    "langbro_scheduler_job_duration_seconds",
    "Scheduler job execution time",
    ["job"],
    buckets=[1, 5, 10, 30, 60, 120, 300],
    registry=REGISTRY,
)

# --- Database metrics ----------------------------------------------------
DB_QUERIES = Counter(
    "langbro_db_queries_total",
    "Database queries executed",
    registry=REGISTRY,
)
DB_SESSION_ACTIVE = Gauge(
    "langbro_db_sessions_active",
    "Currently active DB sessions",
    registry=REGISTRY,
)

# --- Report metrics ------------------------------------------------------
REPORTS_PROCESSED = Counter(
    "langbro_reports_processed_total",
    "Daily reports processed",
    ["challenge_id"],
    registry=REGISTRY,
)
REPORTS_POINTS = Histogram(
    "langbro_report_points",
    "Points awarded per report",
    buckets=[5, 10, 20, 30, 50, 75, 100, 150, 200],
    registry=REGISTRY,
)

# --- Engagement metrics --------------------------------------------------
ACTIVE_USERS = Gauge(
    "langbro_active_users",
    "Number of active users (reported today)",
    ["challenge_id"],
    registry=REGISTRY,
)
ACTIVE_CHALLENGES = Gauge(
    "langbro_active_challenges",
    "Number of active challenges",
    registry=REGISTRY,
)
QUIZ_ANSWERS = Counter(
    "langbro_quiz_answers_total",
    "Quiz answers submitted",
    ["correct"],  # true / false
    registry=REGISTRY,
)
TTS_GENERATIONS = Counter(
    "langbro_tts_generations_total",
    "TTS audio files generated",
    ["cache_hit"],  # true / false
    registry=REGISTRY,
)


def start_metrics_server(port: int = 9090) -> None:
    """Start the Prometheus metrics HTTP server in a daemon thread."""
    try:
        start_http_server(port, registry=REGISTRY)
        logger.info("Prometheus metrics server started on :%d", port)
    except Exception as e:
        logger.error("Failed to start metrics server: %s", e)
