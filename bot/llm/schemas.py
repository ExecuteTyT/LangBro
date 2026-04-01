from pydantic import BaseModel, Field


class ParsedActivity(BaseModel):
    category: str
    description: str | None = None
    duration_minutes: int | None = None
    count: int | None = None
    details: str | None = None


class ReportParseResult(BaseModel):
    activities: list[ParsedActivity] = Field(default_factory=list)
    word_of_day_used: bool = False
    raw_summary: str = ""


class WotdResult(BaseModel):
    word: str
    pronunciation: str = ""
    translation: str = ""
    level: str = "B1"
    part_of_speech: str = ""
    examples: list[dict[str, str]] = Field(default_factory=list)
    related_words: list[str] = Field(default_factory=list)
    usage_tip: str = ""
    challenge_task: str = ""


class QuizResult(BaseModel):
    quiz_type: str
    question: str
    options: list[str] = Field(min_length=4, max_length=4)
    correct_option: int = Field(ge=0, le=3)
    explanation: str = ""
    level: str = "B1"
