"""WebSocket API for persistent mock exams."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, WS_PREFIX
from .content.models import SubjectType, TestQuestion
from .exam import (
    ExamConfigurationError,
    build_exam_filters,
    exam_expired,
    exam_payload,
    score_exam,
)
from .runtime import UNEDStudyRuntime
from .scheduler import schedule_test


def _runtime(hass: HomeAssistant) -> UNEDStudyRuntime | None:
    runtime = hass.data.get(DOMAIN)
    return runtime if isinstance(runtime, UNEDStudyRuntime) else None


def _serialize_question(
    item: TestQuestion,
    *,
    reveal: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": item.id,
        "type": "test",
        "topic": item.topic,
        "importance": item.importance,
        "question_md": item.question_md,
        "answers": [asdict(answer) for answer in item.answers],
    }
    if reveal:
        payload["correct_answer"] = item.correct_answer
        payload["explanation_md"] = item.explanation_md
    return payload


def _exam_state(
    session: dict[str, Any],
    *,
    subject_id: str,
) -> dict[str, Any]:
    exam = exam_payload(session["filters"])
    item_ids = exam["item_ids"]
    answers = exam["answers"]
    current_index = exam.get("current_index", 0)
    if not isinstance(current_index, int):
        current_index = 0

    return {
        "session_id": session["session_id"],
        "subject_id": subject_id,
        "state": session["state"],
        "question_count": len(item_ids),
        "answered_count": len(answers),
        "current_index": max(0, min(current_index, max(len(item_ids) - 1, 0))),
        "started_at": exam.get("started_at"),
        "expires_at": exam.get("expires_at"),
        "duration_minutes": exam.get("duration_minutes"),
        "wrong_answer_penalty": exam.get("wrong_answer_penalty", 0.0),
        "expired": exam_expired(session["filters"]),
    }


async def _load_exam(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    session_id: str,
) -> tuple[UNEDStudyRuntime, dict[str, Any], Any] | None:
    runtime = _runtime(hass)
    if runtime is None:
        return None

    session = await runtime.database.async_get_session(
        hass,
        session_id,
        connection.user.id,
    )
    if session is None or session["mode"] != "exam":
        return None

    subject = runtime.content.get_subject(session["subject_id"])
    if subject is None or subject.type is not SubjectType.TEST:
        return None
    return runtime, session, subject


@callback
def async_register_exam_commands(hass: HomeAssistant) -> None:
    """Register mock-exam commands."""
    for command in (
        ws_start_exam,
        ws_exam_state,
        ws_exam_question,
        ws_exam_answer,
        ws_finish_exam,
    ):
        websocket_api.async_register_command(hass, command)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{WS_PREFIX}/start_exam",
        vol.Required("subject_id"): str,
    }
)
@websocket_api.ws_require_user()
@websocket_api.async_response
async def ws_start_exam(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Create a stable mock exam using subject exam metadata."""
    runtime = _runtime(hass)
    if runtime is None:
        connection.send_error(
            msg["id"], "not_loaded", "UNED Study is not loaded"
        )
        return

    subject = runtime.content.get_subject(msg["subject_id"])
    if subject is None:
        connection.send_error(
            msg["id"], "not_found", "Subject not found"
        )
        return
    if subject.type is not SubjectType.TEST:
        connection.send_error(
            msg["id"],
            "unsupported_subject",
            "Mock exams are available only for test subjects",
        )
        return

    try:
        filters = build_exam_filters(subject)
    except ExamConfigurationError as exc:
        connection.send_error(
            msg["id"], "invalid_exam_configuration", str(exc)
        )
        return

    session_id = str(uuid4())
    await runtime.database.async_create_session(
        hass,
        session_id=session_id,
        user_id=connection.user.id,
        subject_id=subject.id,
        mode="exam",
        filters=filters,
    )
    session = await runtime.database.async_get_session(
        hass,
        session_id,
        connection.user.id,
    )
    if session is None:
        connection.send_error(
            msg["id"], "session_error", "Could not create mock exam"
        )
        return

    connection.send_result(
        msg["id"],
        _exam_state(session, subject_id=subject.id),
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{WS_PREFIX}/exam_state",
        vol.Required("session_id"): str,
    }
)
@websocket_api.ws_require_user()
@websocket_api.async_response
async def ws_exam_state(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return durable exam progress and server-side deadline."""
    loaded = await _load_exam(hass, connection, msg["session_id"])
    if loaded is None:
        connection.send_error(
            msg["id"], "not_found", "Mock exam is unavailable"
        )
        return

    _runtime_value, session, subject = loaded
    connection.send_result(
        msg["id"],
        _exam_state(session, subject_id=subject.id),
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{WS_PREFIX}/exam_question",
        vol.Required("session_id"): str,
        vol.Required("index"): vol.All(int, vol.Range(min=0)),
    }
)
@websocket_api.ws_require_user()
@websocket_api.async_response
async def ws_exam_question(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return one question from the stable exam order without correction."""
    loaded = await _load_exam(hass, connection, msg["session_id"])
    if loaded is None:
        connection.send_error(
            msg["id"], "not_found", "Mock exam is unavailable"
        )
        return

    runtime, session, subject = loaded
    if session["state"] != "active":
        connection.send_error(
            msg["id"], "inactive_exam", "Mock exam is not active"
        )
        return

    try:
        exam = exam_payload(session["filters"])
    except ExamConfigurationError as exc:
        connection.send_error(
            msg["id"], "invalid_exam_state", str(exc)
        )
        return

    item_ids = exam["item_ids"]
    index = msg["index"]
    if index >= len(item_ids):
        connection.send_error(
            msg["id"], "invalid_index", "Question index is out of range"
        )
        return

    item = subject.items_by_id.get(item_ids[index])
    if not isinstance(item, TestQuestion):
        connection.send_error(
            msg["id"],
            "content_changed",
            "A mock-exam question is no longer available",
        )
        return

    filters = await runtime.database.async_set_exam_index(
        hass,
        session["session_id"],
        connection.user.id,
        index,
    )
    exam = exam_payload(filters)
    answers = exam["answers"]

    connection.send_result(
        msg["id"],
        {
            "index": index,
            "question_count": len(item_ids),
            "selected_answer": answers.get(item.id),
            "item": _serialize_question(item),
            "expired": exam_expired(filters),
            "expires_at": exam.get("expires_at"),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{WS_PREFIX}/exam_answer",
        vol.Required("session_id"): str,
        vol.Required("item_id"): str,
        vol.Required("answer_id"): str,
    }
)
@websocket_api.ws_require_user()
@websocket_api.async_response
async def ws_exam_answer(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Persist an answer without revealing whether it is correct."""
    loaded = await _load_exam(hass, connection, msg["session_id"])
    if loaded is None:
        connection.send_error(
            msg["id"], "not_found", "Mock exam is unavailable"
        )
        return

    runtime, session, subject = loaded
    if session["state"] != "active":
        connection.send_error(
            msg["id"], "inactive_exam", "Mock exam is not active"
        )
        return
    if exam_expired(session["filters"]):
        connection.send_error(
            msg["id"], "exam_expired", "Mock exam time has expired"
        )
        return

    exam = exam_payload(session["filters"])
    if msg["item_id"] not in exam["item_ids"]:
        connection.send_error(
            msg["id"], "invalid_item", "Question is not part of this exam"
        )
        return

    item = subject.items_by_id.get(msg["item_id"])
    if not isinstance(item, TestQuestion):
        connection.send_error(
            msg["id"], "content_changed", "Question is unavailable"
        )
        return
    if msg["answer_id"] not in {answer.id for answer in item.answers}:
        connection.send_error(
            msg["id"], "invalid_answer", "Unknown answer"
        )
        return

    filters = await runtime.database.async_set_exam_answer(
        hass,
        session["session_id"],
        connection.user.id,
        item.id,
        msg["answer_id"],
    )
    exam = exam_payload(filters)
    connection.send_result(
        msg["id"],
        {
            "ok": True,
            "answered_count": len(exam["answers"]),
            "question_count": len(exam["item_ids"]),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{WS_PREFIX}/finish_exam",
        vol.Required("session_id"): str,
    }
)
@websocket_api.ws_require_user()
@websocket_api.async_response
async def ws_finish_exam(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Correct the whole exam, then commit answered items to study progress."""
    loaded = await _load_exam(hass, connection, msg["session_id"])
    if loaded is None:
        connection.send_error(
            msg["id"], "not_found", "Mock exam is unavailable"
        )
        return

    runtime, session, subject = loaded
    try:
        exam = exam_payload(session["filters"])
    except ExamConfigurationError as exc:
        connection.send_error(
            msg["id"], "invalid_exam_state", str(exc)
        )
        return

    item_ids = exam["item_ids"]
    answers = exam["answers"]
    penalty = exam.get("wrong_answer_penalty", 0.0)
    try:
        penalty_value = float(penalty)
        score = score_exam(
            subject,
            item_ids,
            answers,
            wrong_answer_penalty=penalty_value,
        )
    except (TypeError, ValueError, ExamConfigurationError) as exc:
        connection.send_error(
            msg["id"], "invalid_exam_state", str(exc)
        )
        return

    progress = await runtime.database.async_get_progress_map(
        hass,
        connection.user.id,
        subject.id,
    )
    review: list[dict[str, Any]] = []

    for item_id in item_ids:
        item = subject.items_by_id.get(item_id)
        if not isinstance(item, TestQuestion):
            connection.send_error(
                msg["id"],
                "content_changed",
                "A mock-exam question is no longer available",
            )
            return

        answer_id = answers.get(item.id)
        correct: bool | None = None
        if isinstance(answer_id, str):
            correct = answer_id == item.correct_answer
            previous = progress.get(item.id)
            decision = schedule_test(
                importance=item.importance,
                was_correct=correct,
                previous_interval_days=(
                    previous.interval_days if previous else 0.0
                ),
                previous_mastery=(
                    previous.mastery if previous else 0.0
                ),
                previous_difficulty=(
                    previous.difficulty if previous else 0.5
                ),
            )
            await runtime.database.async_record_review(
                hass,
                request_id=f"exam:{session['session_id']}:{item.id}",
                user_id=connection.user.id,
                subject_id=subject.id,
                item_id=item.id,
                session_id=session["session_id"],
                result="correct" if correct else "incorrect",
                answer_id=answer_id,
                rating=None,
                response_ms=None,
                decision=decision,
            )

        review.append(
            {
                "item": _serialize_question(item, reveal=True),
                "answer_id": answer_id,
                "correct": correct,
            }
        )

    await runtime.database.async_complete_session(
        hass,
        session["session_id"],
        connection.user.id,
    )

    connection.send_result(
        msg["id"],
        {
            "session_id": session["session_id"],
            "expired": exam_expired(session["filters"]),
            "score": score.as_dict(),
            "review": review,
        },
    )
