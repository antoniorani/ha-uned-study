"""Validation and parsing for subject JSON."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import AnswerOption, Flashcard, Subject, SubjectType, TestQuestion, Topic


class ContentValidationError(ValueError):
    """Raised when a subject document is invalid."""


def _required_str(data: Mapping[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContentValidationError(f"{context}.{key} must be a non-empty string")
    return value.strip()


def _optional_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ContentValidationError(f"{key} must be a string")
    return value


def _importance(data: Mapping[str, Any], context: str) -> int:
    value = data.get("importance", 3)
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
        raise ContentValidationError(f"{context}.importance must be an integer from 1 to 5")
    return value


def _string_tuple(value: Any, context: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ContentValidationError(f"{context} must be a list of strings")
    return tuple(value)


def parse_subject(data: Any, *, directory_name: str | None = None) -> Subject:
    """Validate and convert raw JSON data into an immutable Subject."""
    if not isinstance(data, Mapping):
        raise ContentValidationError("subject document must be a JSON object")

    if data.get("schema_version") != 1:
        raise ContentValidationError("schema_version must currently be 1")

    subject_id = _required_str(data, "id", "subject")
    if directory_name is not None and directory_name != subject_id:
        raise ContentValidationError(
            f"subject id '{subject_id}' does not match directory '{directory_name}'"
        )

    title = _required_str(data, "title", "subject")
    content_version = _required_str(data, "content_version", "subject")

    try:
        subject_type = SubjectType(_required_str(data, "type", "subject"))
    except ValueError as exc:
        raise ContentValidationError("subject.type must be 'test' or 'flashcards'") from exc

    raw_topics = data.get("topics")
    if not isinstance(raw_topics, list) or not raw_topics:
        raise ContentValidationError("subject.topics must be a non-empty list")

    topics: list[Topic] = []
    topic_ids: set[str] = set()
    for index, raw_topic in enumerate(raw_topics):
        if not isinstance(raw_topic, Mapping):
            raise ContentValidationError(f"topics[{index}] must be an object")
        topic_id = _required_str(raw_topic, "id", f"topics[{index}]")
        if topic_id in topic_ids:
            raise ContentValidationError(f"duplicate topic id: {topic_id}")
        topic_ids.add(topic_id)
        topics.append(
            Topic(
                id=topic_id,
                title=_required_str(raw_topic, "title", f"topics[{index}]"),
            )
        )

    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raise ContentValidationError("subject.items must be a list")

    item_ids: set[str] = set()
    items: list[TestQuestion | Flashcard] = []
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, Mapping):
            raise ContentValidationError(f"items[{index}] must be an object")
        context = f"items[{index}]"
        item_id = _required_str(raw_item, "id", context)
        if item_id in item_ids:
            raise ContentValidationError(f"duplicate item id: {item_id}")
        item_ids.add(item_id)

        topic = _required_str(raw_item, "topic", context)
        if topic not in topic_ids:
            raise ContentValidationError(f"{context}.topic references unknown topic '{topic}'")

        common = {
            "id": item_id,
            "topic": topic,
            "importance": _importance(raw_item, context),
            "tags": _string_tuple(raw_item.get("tags"), f"{context}.tags"),
            "source": raw_item.get("source") if isinstance(raw_item.get("source"), Mapping) else None,
            "exam_history": _string_tuple(
                raw_item.get("exam_history"), f"{context}.exam_history"
            ),
        }

        if subject_type is SubjectType.TEST:
            raw_answers = raw_item.get("answers")
            if not isinstance(raw_answers, list) or len(raw_answers) < 2:
                raise ContentValidationError(
                    f"{context}.answers must contain at least two options"
                )
            answers: list[AnswerOption] = []
            answer_ids: set[str] = set()
            for answer_index, raw_answer in enumerate(raw_answers):
                if not isinstance(raw_answer, Mapping):
                    raise ContentValidationError(
                        f"{context}.answers[{answer_index}] must be an object"
                    )
                answer_context = f"{context}.answers[{answer_index}]"
                answer_id = _required_str(raw_answer, "id", answer_context)
                if answer_id in answer_ids:
                    raise ContentValidationError(
                        f"duplicate answer id '{answer_id}' in {context}"
                    )
                answer_ids.add(answer_id)
                answers.append(
                    AnswerOption(
                        id=answer_id,
                        text_md=_required_str(raw_answer, "text_md", answer_context),
                    )
                )

            correct_answer = _required_str(raw_item, "correct_answer", context)
            if correct_answer not in answer_ids:
                raise ContentValidationError(
                    f"{context}.correct_answer '{correct_answer}' is not an answer id"
                )
            items.append(
                TestQuestion(
                    **common,
                    question_md=_required_str(raw_item, "question_md", context),
                    answers=tuple(answers),
                    correct_answer=correct_answer,
                    explanation_md=_optional_str(raw_item, "explanation_md"),
                )
            )
        else:
            items.append(
                Flashcard(
                    **common,
                    front_md=_required_str(raw_item, "front_md", context),
                    back_md=_required_str(raw_item, "back_md", context),
                    hint_md=_optional_str(raw_item, "hint_md"),
                    mnemonic_md=_optional_str(raw_item, "mnemonic_md"),
                )
            )

    degree = data.get("degree")
    if degree is not None and not isinstance(degree, str):
        raise ContentValidationError("subject.degree must be a string when present")

    course = data.get("course")
    if course is not None and (
        not isinstance(course, int) or isinstance(course, bool) or course < 1
    ):
        raise ContentValidationError(
            "subject.course must be a positive integer when present"
        )

    exam = data.get("exam", {})
    if not isinstance(exam, Mapping):
        raise ContentValidationError("subject.exam must be an object")

    return Subject(
        schema_version=1,
        id=subject_id,
        title=title,
        type=subject_type,
        content_version=content_version,
        topics=tuple(topics),
        items=tuple(items),
        degree=degree,
        course=course,
        exam=dict(exam),
    )
