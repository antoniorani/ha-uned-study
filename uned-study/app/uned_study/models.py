"""Immutable study content models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Topic:
    id: str
    title: str


@dataclass(frozen=True, slots=True)
class AnswerOption:
    id: str
    text_md: str


@dataclass(frozen=True, slots=True)
class StudyItem:
    id: str
    item_type: str
    topic: str
    importance: int
    tags: tuple[str, ...] = ()
    exam_history: tuple[str, ...] = ()
    question_md: str = ""
    answers: tuple[AnswerOption, ...] = ()
    correct_answer: str = ""
    explanation_md: str = ""
    front_md: str = ""
    back_md: str = ""
    hint_md: str = ""
    mnemonic_md: str = ""
    source: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class Subject:
    schema_version: int
    id: str
    title: str
    subject_type: str
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
