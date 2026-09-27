"""In-memory content models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SubjectType(StrEnum):
    """Supported study subject types."""

    TEST = "test"
    FLASHCARDS = "flashcards"


@dataclass(frozen=True, slots=True)
class Topic:
    id: str
    title: str


@dataclass(frozen=True, slots=True)
class AnswerOption:
    id: str
    text_md: str


@dataclass(frozen=True, slots=True)
class TestQuestion:
    id: str
    topic: str
    importance: int
    question_md: str
    answers: tuple[AnswerOption, ...]
    correct_answer: str
    explanation_md: str = ""
    tags: tuple[str, ...] = ()
    source: dict[str, Any] | None = None
    exam_history: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Flashcard:
    id: str
    topic: str
    importance: int
    front_md: str
    back_md: str
    hint_md: str = ""
    mnemonic_md: str = ""
    tags: tuple[str, ...] = ()
    source: dict[str, Any] | None = None
    exam_history: tuple[str, ...] = ()


StudyItem = TestQuestion | Flashcard


@dataclass(frozen=True, slots=True)
class Subject:
    schema_version: int
    id: str
    title: str
    type: SubjectType
    content_version: str
    topics: tuple[Topic, ...]
    items: tuple[StudyItem, ...]
    degree: str | None = None
    course: int | None = None
    exam: dict[str, Any] = field(default_factory=dict)

    @property
    def items_by_id(self) -> dict[str, StudyItem]:
        return {item.id: item for item in self.items}

    @property
    def topics_by_id(self) -> dict[str, Topic]:
        return {topic.id: topic for topic in self.topics}
