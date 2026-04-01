from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False
    )
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    english_level: Mapped[str] = mapped_column(
        String(10), default="A1", server_default="A1"
    )
    learning_goal: Mapped[str | None] = mapped_column(String(50))
    bot_language_mix: Mapped[int] = mapped_column(
        Integer, default=10, server_default="10"
    )
    active_challenge_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("challenges.id", use_alter=True, name="fk_users_active_challenge"),
    )
    onboarding_complete: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    active_challenge: Mapped["Challenge | None"] = relationship(
        "Challenge", foreign_keys=[active_challenge_id]
    )
    user_challenges: Mapped[list["UserChallenge"]] = relationship(
        back_populates="user"
    )
    conversation_history: Mapped[list["ConversationHistory"]] = relationship(
        back_populates="user"
    )

    __table_args__ = (
        Index("idx_users_telegram_id", "telegram_id"),
    )


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    invite_code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active"
    )
    schedule_days: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=[1, 2, 3, 4, 5], server_default="{1,2,3,4,5}"
    )
    timezone: Mapped[str] = mapped_column(
        String(50), default="Europe/Moscow", server_default="Europe/Moscow"
    )
    report_deadline_time: Mapped[time] = mapped_column(
        Time, default=time(23, 59), server_default="23:59"
    )
    digest_time: Mapped[time] = mapped_column(
        Time, default=time(22, 0), server_default="22:00"
    )
    reminder_time: Mapped[time] = mapped_column(
        Time, default=time(20, 0), server_default="20:00"
    )
    wotd_time: Mapped[time] = mapped_column(
        Time, default=time(8, 0), server_default="08:00"
    )
    quiz_window_start: Mapped[time] = mapped_column(
        Time, default=time(12, 0), server_default="12:00"
    )
    quiz_window_end: Mapped[time] = mapped_column(
        Time, default=time(15, 0), server_default="15:00"
    )
    features_enabled: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default='{"daily_digest": true, "reminders": true, "word_of_day": true, "pop_quiz": true, "weekly_battles": true, "weekly_digest": true}',
    )
    scoring_multipliers: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default='{"speaking": 2, "listening": 1, "reading": 1.5, "writing": 2, "vocabulary": 3, "grammar": 5, "app_practice": 10, "other": 5, "wotd_bonus": 20, "quiz_correct": 15, "quiz_speed_bonus": 10}',
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    creator: Mapped["User | None"] = relationship(
        "User", foreign_keys=[created_by]
    )
    user_challenges: Mapped[list["UserChallenge"]] = relationship(
        back_populates="challenge"
    )
    words_of_the_day: Mapped[list["WordOfTheDay"]] = relationship(
        back_populates="challenge"
    )
    quizzes: Mapped[list["Quiz"]] = relationship(back_populates="challenge")
    weekly_battles: Mapped[list["WeeklyBattle"]] = relationship(
        back_populates="challenge"
    )

    __table_args__ = (
        Index(
            "idx_challenges_active_chat",
            "chat_id",
            unique=True,
            postgresql_where=(status == "active"),
        ),
    )


class UserChallenge(Base):
    __tablename__ = "user_challenges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    challenge_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("challenges.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active"
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Streak tracking
    current_streak: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    best_streak: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    last_report_date: Mapped[date | None] = mapped_column(Date)

    # Aggregated stats
    total_points: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    total_reports: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    total_days_in_challenge: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )

    # Vacation
    vacation_until: Mapped[date | None] = mapped_column(Date)
    vacation_days_used: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )

    # Activity distribution
    activity_stats: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default='{"speaking_minutes": 0, "listening_minutes": 0, "reading_minutes": 0, "writing_minutes": 0, "vocabulary_count": 0, "grammar_lessons": 0, "app_lessons": 0}',
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="user_challenges")
    challenge: Mapped["Challenge"] = relationship(
        back_populates="user_challenges"
    )
    daily_reports: Mapped[list["DailyReport"]] = relationship(
        back_populates="user_challenge"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "challenge_id"),
        Index("idx_uc_challenge", "challenge_id"),
        Index("idx_uc_user", "user_id"),
        Index("idx_uc_status", "status"),
        Index("idx_uc_last_report", "last_report_date"),
    )


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_challenge_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("user_challenges.id", ondelete="CASCADE"),
        nullable=False,
    )
    report_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Raw data
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(
        String(20), default="group", server_default="group"
    )

    # Parsed data
    parsed_data: Mapped[dict | None] = mapped_column(JSONB)
    total_points: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    summary: Mapped[str | None] = mapped_column(Text)

    # Word of the Day tracking
    wotd_used: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    wotd_bonus_points: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )

    # LLM metadata
    llm_model: Mapped[str | None] = mapped_column(String(100))
    llm_tokens_used: Mapped[int | None] = mapped_column(Integer)
    llm_parse_time_ms: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user_challenge: Mapped["UserChallenge"] = relationship(
        back_populates="daily_reports"
    )
    activities: Mapped[list["ReportActivity"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("user_challenge_id", "report_date"),
        Index("idx_reports_date", "report_date"),
        Index("idx_reports_uc", "user_challenge_id"),
        Index("idx_reports_date_uc", "user_challenge_id", "report_date"),
        Index("idx_reports_date_points", "report_date", "total_points"),
    )


class ReportActivity(Base):
    __tablename__ = "report_activities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    report_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("daily_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    count: Mapped[int | None] = mapped_column(Integer)
    points: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    details: Mapped[str | None] = mapped_column(Text)

    # Relationships
    report: Mapped["DailyReport"] = relationship(back_populates="activities")

    __table_args__ = (
        Index("idx_activities_report", "report_id"),
        Index("idx_activities_category", "category"),
    )


class WordOfTheDay(Base):
    __tablename__ = "words_of_the_day"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    challenge_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("challenges.id", ondelete="CASCADE"),
        nullable=False,
    )
    word: Mapped[str] = mapped_column(String(255), nullable=False)
    pronunciation: Mapped[str | None] = mapped_column(String(255))
    translation: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str | None] = mapped_column(String(10))
    examples: Mapped[dict | None] = mapped_column(JSONB)
    related_words: Mapped[dict | None] = mapped_column(JSONB)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    posted_date: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    challenge: Mapped["Challenge"] = relationship(
        back_populates="words_of_the_day"
    )

    __table_args__ = (
        UniqueConstraint("challenge_id", "posted_date"),
        Index("idx_wotd_challenge", "challenge_id"),
    )


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    challenge_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("challenges.id", ondelete="CASCADE"),
        nullable=False,
    )
    quiz_type: Mapped[str] = mapped_column(String(30), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict] = mapped_column(JSONB, nullable=False)
    correct_option: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str | None] = mapped_column(String(10))
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    challenge: Mapped["Challenge"] = relationship(back_populates="quizzes")
    answers: Mapped[list["QuizAnswer"]] = relationship(back_populates="quiz")

    __table_args__ = (
        Index("idx_quizzes_challenge", "challenge_id"),
        Index("idx_quizzes_status", "status"),
    )


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("quizzes.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_challenge_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("user_challenges.id", ondelete="CASCADE"),
        nullable=False,
    )
    selected_option: Mapped[int] = mapped_column(Integer, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_first_correct: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    points_earned: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    quiz: Mapped["Quiz"] = relationship(back_populates="answers")

    __table_args__ = (
        UniqueConstraint("quiz_id", "user_challenge_id"),
        Index("idx_qa_quiz", "quiz_id"),
    )


class WeeklyBattle(Base):
    __tablename__ = "weekly_battles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    challenge_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("challenges.id", ondelete="CASCADE"),
        nullable=False,
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    week_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    challenge: Mapped["Challenge"] = relationship(
        back_populates="weekly_battles"
    )
    pairs: Mapped[list["BattlePair"]] = relationship(back_populates="battle")

    __table_args__ = (Index("idx_wb_challenge", "challenge_id"),)


class BattlePair(Base):
    __tablename__ = "battle_pairs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    battle_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("weekly_battles.id", ondelete="CASCADE"),
        nullable=False,
    )
    player1_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_challenges.id"), nullable=False
    )
    player2_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user_challenges.id")
    )
    player1_points: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    player2_points: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    winner_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user_challenges.id")
    )
    loser_penalty_task: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    battle: Mapped["WeeklyBattle"] = relationship(back_populates="pairs")

    __table_args__ = (Index("idx_bp_battle", "battle_id"),)


class ConversationHistory(Base):
    __tablename__ = "conversation_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    feature: Mapped[str | None] = mapped_column(String(30))
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="conversation_history")

    __table_args__ = (
        Index("idx_ch_user", "user_id"),
        Index("idx_ch_created", "created_at"),
    )


class LLMUsageLog(Base):
    __tablename__ = "llm_usage_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    feature: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_llm_log_feature", "feature"),
        Index("idx_llm_log_created", "created_at"),
    )
