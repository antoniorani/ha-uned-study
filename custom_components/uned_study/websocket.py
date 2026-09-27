"""WebSocket API for the UNED Study frontend."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, WS_PREFIX
from .content.models import Flashcard, TestQuestion
from .runtime import UNEDStudyRuntime
from .scheduler import (
    ProgressSnapshot,
    choose_next_item,
    schedule_flashcard,
    schedule_test,
)

STUDY_MODES = ("adaptive", "due", "errors", "new", "important")


def _runtime(hass: HomeAssistant) -> UNEDStudyRuntime | None:
    runtime = hass.data.get(DOMAIN)
    return runtime if isinstance(runtime, UNEDStudyRuntime) else None


def _send_not_loaded(
    connection: websocket_api.ActiveConnection, message_id: int
) -> None:
    connection.send_error(
        message_id, "not_loaded", "UNED Study is not loaded"
    )


def _serialize_item(
    item: TestQuestion | Flashcard, *, reveal: bool = False
) -> dict[str, Any]:
    if isinstance(item, TestQuestion):
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

    return {
        "id": item.id,
        "type": "flashcard",
        "topic": item.topic,
        "importance": item.importance,
        "front_md": item.front_md,
        "back_md": item.back_md,
        "hint_md": item.hint_md,
        "mnemonic_md": item.mnemonic_md,
    }


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register commands when the component loads."""
    for command in (
        ws_dashboard,
        ws_subject,
        ws_start_session,
        ws_resume_session,
        ws_next_item,
        ws_submit_answer,
        ws_rate_card,
        ws_set_favorite,
        ws_reorder_favorites,
        ws_reload_content,
    ):
        websocket_api.async_register_command(hass, command)


@websocket_api.websocket_command(
    {vol.Required("type"): f"{WS_PREFIX}/dashboard"}
)
@websocket_api.ws_require_user()
@websocket_api.async_response
async def ws_dashboard(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    runtime = _runtime(hass)
    if runtime is None:
        _send_not_loaded(connection, msg["id"])
        return

    user_id = connection.user.id
    prefs = await runtime.database.async_get_subject_preferences(hass, user_id)
    aggregates = await runtime.database.async_get_subject_aggregates(
        hass, user_id
    )
    active_sessions = await runtime.database.async_get_active_sessions(
        hass, user_id
    )

    subjects = []
    for subject in runtime.content.subjects.values():
        pref = prefs.get(subject.id, {})
        active = active_sessions.get(subject.id)
        subjects.append(
            {
                "id": subject.id,
                "title": subject.title,
                "type": subject.type.value,
                "content_version": subject.content_version,
                "degree": subject.degree,
                "course": subject.course,
                "item_count": len(subject.items),
                "topic_count": len(subject.topics),
                "favorite": bool(pref.get("favorite", False)),
                "favorite_order": pref.get("favorite_order"),
                "last_studied_at": pref.get("last_studied_at"),
                "progress": aggregates.get(subject.id, {}),
                "active_session": (
                    {
                        "session_id": active["session_id"],
                        "mode": active["mode"],
                        "filters": active["filters"],
                        "current_item_id": active["current_item_id"],
                        "answered_count": active["answered_count"],
                    }
                    if active
                    else None
                ),
            }
        )

    subjects.sort(
        key=lambda item: (
            0 if item["favorite"] else 1,
            item["favorite_order"]
            if item["favorite_order"] is not None else 1_000_000,
            item["title"].casefold(),
        )
    )
    connection.send_result(
        msg["id"],
        {
            "subjects": subjects,
            "content_errors": (
                runtime.content.errors if connection.user.is_admin else {}
            ),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{WS_PREFIX}/subject",
        vol.Required("subject_id"): str,
    }
)
@websocket_api.ws_require_user()
@websocket_api.async_response
async def ws_subject(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    runtime = _runtime(hass)
    if runtime is None:
        _send_not_loaded(connection, msg["id"])
        return

    subject = runtime.content.get_subject(msg["subject_id"])
    if subject is None:
        connection.send_error(
            msg["id"], "not_found", "Subject not found"
        )
        return

    connection.send_result(
        msg["id"],
        {
            "id": subject.id,
            "title": subject.title,
            "type": subject.type.value,
            "content_version": subject.content_version,
            "topics": [asdict(topic) for topic in subject.topics],
            "exam": subject.exam,
            "item_count": len(subject.items),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{WS_PREFIX}/start_session",
        vol.Required("subject_id"): str,
        vol.Optional("mode", default="adaptive"): vol.In(
            STUDY_MODES
        ),
        vol.Optional("topic"): str,
    }
)
@websocket_api.ws_require_user()
@websocket_api.async_response
async def ws_start_session(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    runtime = _runtime(hass)
    if runtime is None:
        _send_not_loaded(connection, msg["id"])
        return

    subject = runtime.content.get_subject(msg["subject_id"])
    if subject is None:
        connection.send_error(
            msg["id"], "not_found", "Subject not found"
        )
        return

    topic = msg.get("topic")
    if topic is not None and topic not in subject.topics_by_id:
        connection.send_error(
            msg["id"], "invalid_topic", "Unknown topic"
        )
        return

    session_id = str(uuid4())
    filters = {"topic": topic} if topic else {}
    await runtime.database.async_create_session(
        hass,
        session_id=session_id,
        user_id=connection.user.id,
        subject_id=subject.id,
        mode=msg["mode"],
        filters=filters,
    )
    connection.send_result(
        msg["id"],
        {
            "session_id": session_id,
            "subject_type": subject.type.value,
            "mode": msg["mode"],
            "filters": filters,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{WS_PREFIX}/resume_session",
        vol.Required("session_id"): str,
    }
)
@websocket_api.ws_require_user()
@websocket_api.async_response
async def ws_resume_session(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Resume the authenticated user's active study session."""
    loaded = await _session_and_subject(
        hass, connection, msg["session_id"]
    )
    if loaded is None:
        connection.send_error(
            msg["id"], "not_found", "Study session is unavailable"
        )
        return
    _runtime_value, session, subject = loaded
    if session["state"] != "active":
        connection.send_error(
            msg["id"], "inactive_session", "Study session is not active"
        )
        return

    current = None
    if session["current_item_id"]:
        item = subject.items_by_id.get(session["current_item_id"])
        if item is not None:
            current = _serialize_item(item)

    connection.send_result(
        msg["id"],
        {
            "session_id": session["session_id"],
            "subject_id": subject.id,
            "subject_type": subject.type.value,
            "mode": session["mode"],
            "filters": session["filters"],
            "item": current,
        },
    )


async def _session_and_subject(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    session_id: str,
) -> tuple[UNEDStudyRuntime, dict[str, Any], Any] | None:
    runtime = _runtime(hass)
    if runtime is None:
        return None
    session = await runtime.database.async_get_session(
        hass, session_id, connection.user.id
    )
    if session is None:
        return None
    subject = runtime.content.get_subject(session["subject_id"])
    if subject is None:
        return None
    return runtime, session, subject


def _eligible_items(
    items: list[TestQuestion | Flashcard],
    session: dict[str, Any],
    progress: dict[str, ProgressSnapshot],
) -> list[TestQuestion | Flashcard]:
    """Apply session topic and study-mode filters."""
    topic = session["filters"].get("topic")
    if topic:
        items = [item for item in items if item.topic == topic]

    mode = session["mode"]
    if mode == "adaptive":
        return items
    if mode == "errors":
        return [
            item
            for item in items
            if (
                (item_progress := progress.get(item.id)) is not None
                and item_progress.incorrect_count > 0
            )
        ]
    if mode == "new":
        return [
            item
            for item in items
            if (
                (item_progress := progress.get(item.id)) is None
                or item_progress.times_seen == 0
            )
        ]
    if mode == "important":
        return [item for item in items if item.importance >= 4]
    if mode == "due":
        now = datetime.now(timezone.utc)
        return [
            item
            for item in items
            if (
                (item_progress := progress.get(item.id)) is not None
                and item_progress.next_review_at is not None
                and item_progress.next_review_at <= now
            )
        ]
    return items


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{WS_PREFIX}/next_item",
        vol.Required("session_id"): str,
    }
)
@websocket_api.ws_require_user()
@websocket_api.async_response
async def ws_next_item(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    loaded = await _session_and_subject(
        hass, connection, msg["session_id"]
    )
    if loaded is None:
        connection.send_error(
            msg["id"], "not_found", "Study session is unavailable"
        )
        return
    runtime, session, subject = loaded
    if session["state"] != "active":
        connection.send_error(
            msg["id"], "inactive_session", "Study session is not active"
        )
        return

    if session["current_item_id"]:
        current = subject.items_by_id.get(session["current_item_id"])
        if current is not None:
            connection.send_result(
                msg["id"],
                {"item": _serialize_item(current)},
            )
            return

    progress = await runtime.database.async_get_progress_map(
        hass, connection.user.id, subject.id
    )
    items = _eligible_items(
        list(subject.items),
        session,
        progress,
    )
    if not items:
        connection.send_error(
            msg["id"], "no_items", "No items match this study mode"
        )
        return

    recent = await runtime.database.async_recent_item_ids(
        hass, session["session_id"], limit=10
    )
    item = choose_next_item(
        items, progress, recent_item_ids=recent
    )
    if item is None:
        connection.send_error(
            msg["id"], "no_items", "No item is available"
        )
        return

    await runtime.database.async_set_current_item(
        hass, session["session_id"], connection.user.id, item.id
    )
    connection.send_result(
        msg["id"], {"item": _serialize_item(item)}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{WS_PREFIX}/submit_answer",
        vol.Required("session_id"): str,
        vol.Required("item_id"): str,
        vol.Required("answer_id"): str,
        vol.Required("request_id"): str,
        vol.Optional("response_ms"): int,
    }
)
@websocket_api.ws_require_user()
@websocket_api.async_response
async def ws_submit_answer(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    loaded = await _session_and_subject(
        hass, connection, msg["session_id"]
    )
    if loaded is None:
        connection.send_error(
            msg["id"], "not_found", "Study session is unavailable"
        )
        return
    runtime, session, subject = loaded

    item = subject.items_by_id.get(msg["item_id"])
    if not isinstance(item, TestQuestion):
        connection.send_error(
            msg["id"], "invalid_item", "This item is not a test question"
        )
        return
    if msg["answer_id"] not in {answer.id for answer in item.answers}:
        connection.send_error(
            msg["id"], "invalid_answer", "Unknown answer"
        )
        return

    previous_request = await runtime.database.async_get_review_request(
        hass,
        msg["request_id"],
        connection.user.id,
    )
    if previous_request is not None:
        if (
            previous_request["subject_id"] != subject.id
            or previous_request["item_id"] != item.id
            or previous_request["session_id"] != session["session_id"]
            or previous_request["answer_id"] != msg["answer_id"]
        ):
            connection.send_error(
                msg["id"],
                "request_conflict",
                "request_id was already used for a different answer",
            )
            return
        progress = await runtime.database.async_get_progress_map(
            hass, connection.user.id, subject.id
        )
        stored = progress.get(item.id)
        connection.send_result(
            msg["id"],
            {
                "duplicate": True,
                "correct": previous_request["result"] == "correct",
                "item": _serialize_item(item, reveal=True),
                "next_review_at": (
                    stored.next_review_at.isoformat()
                    if stored and stored.next_review_at
                    else None
                ),
            },
        )
        return

    if session["state"] != "active":
        connection.send_error(
            msg["id"], "inactive_session", "Study session is not active"
        )
        return
    if session["current_item_id"] != item.id:
        connection.send_error(
            msg["id"], "stale_item", "This is not the current item"
        )
        return

    progress = await runtime.database.async_get_progress_map(
        hass, connection.user.id, subject.id
    )
    previous = progress.get(item.id)
    correct = msg["answer_id"] == item.correct_answer
    decision = schedule_test(
        importance=item.importance,
        was_correct=correct,
        previous_interval_days=(
            previous.interval_days if previous else 0.0
        ),
    )
    committed = await runtime.database.async_record_review(
        hass,
        request_id=msg["request_id"],
        user_id=connection.user.id,
        subject_id=subject.id,
        item_id=item.id,
        session_id=session["session_id"],
        result="correct" if correct else "incorrect",
        answer_id=msg["answer_id"],
        rating=None,
        response_ms=msg.get("response_ms"),
        decision=decision,
    )
    connection.send_result(
        msg["id"],
        {
            "duplicate": not committed,
            "correct": correct,
            "item": _serialize_item(item, reveal=True),
            "next_review_at": decision.next_review_at.isoformat(),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{WS_PREFIX}/rate_card",
        vol.Required("session_id"): str,
        vol.Required("item_id"): str,
        vol.Required("rating"): vol.In(
            ["again", "hard", "good", "easy"]
        ),
        vol.Required("request_id"): str,
        vol.Optional("response_ms"): int,
    }
)
@websocket_api.ws_require_user()
@websocket_api.async_response
async def ws_rate_card(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    loaded = await _session_and_subject(
        hass, connection, msg["session_id"]
    )
    if loaded is None:
        connection.send_error(
            msg["id"], "not_found", "Study session is unavailable"
        )
        return
    runtime, session, subject = loaded

    item = subject.items_by_id.get(msg["item_id"])
    if not isinstance(item, Flashcard):
        connection.send_error(
            msg["id"], "invalid_item", "This item is not a flashcard"
        )
        return

    previous_request = await runtime.database.async_get_review_request(
        hass,
        msg["request_id"],
        connection.user.id,
    )
    if previous_request is not None:
        if (
            previous_request["subject_id"] != subject.id
            or previous_request["item_id"] != item.id
            or previous_request["session_id"] != session["session_id"]
            or previous_request["rating"] != msg["rating"]
        ):
            connection.send_error(
                msg["id"],
                "request_conflict",
                "request_id was already used for a different rating",
            )
            return
        progress = await runtime.database.async_get_progress_map(
            hass, connection.user.id, subject.id
        )
        stored = progress.get(item.id)
        connection.send_result(
            msg["id"],
            {
                "duplicate": True,
                "next_review_at": (
                    stored.next_review_at.isoformat()
                    if stored and stored.next_review_at
                    else None
                ),
            },
        )
        return

    if session["state"] != "active":
        connection.send_error(
            msg["id"], "inactive_session", "Study session is not active"
        )
        return
    if session["current_item_id"] != item.id:
        connection.send_error(
            msg["id"], "stale_item", "This is not the current item"
        )
        return

    progress = await runtime.database.async_get_progress_map(
        hass, connection.user.id, subject.id
    )
    previous = progress.get(item.id)
    decision = schedule_flashcard(
        importance=item.importance,
        rating=msg["rating"],
        previous_interval_days=(
            previous.interval_days if previous else 0.0
        ),
    )
    correct = msg["rating"] in {"good", "easy"}
    committed = await runtime.database.async_record_review(
        hass,
        request_id=msg["request_id"],
        user_id=connection.user.id,
        subject_id=subject.id,
        item_id=item.id,
        session_id=session["session_id"],
        result="correct" if correct else "incorrect",
        answer_id=None,
        rating=msg["rating"],
        response_ms=msg.get("response_ms"),
        decision=decision,
    )
    connection.send_result(
        msg["id"],
        {
            "duplicate": not committed,
            "next_review_at": decision.next_review_at.isoformat(),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{WS_PREFIX}/set_favorite",
        vol.Required("subject_id"): str,
        vol.Required("favorite"): bool,
    }
)
@websocket_api.ws_require_user()
@websocket_api.async_response
async def ws_set_favorite(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    runtime = _runtime(hass)
    if runtime is None:
        _send_not_loaded(connection, msg["id"])
        return
    if runtime.content.get_subject(msg["subject_id"]) is None:
        connection.send_error(
            msg["id"], "not_found", "Subject not found"
        )
        return
    await runtime.database.async_set_favorite(
        hass,
        connection.user.id,
        msg["subject_id"],
        msg["favorite"],
    )
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{WS_PREFIX}/reorder_favorites",
        vol.Required("subject_ids"): [str],
    }
)
@websocket_api.ws_require_user()
@websocket_api.async_response
async def ws_reorder_favorites(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    runtime = _runtime(hass)
    if runtime is None:
        _send_not_loaded(connection, msg["id"])
        return
    valid = set(runtime.content.subjects)
    if any(subject_id not in valid for subject_id in msg["subject_ids"]):
        connection.send_error(
            msg["id"], "invalid_subject", "Unknown subject in order"
        )
        return
    await runtime.database.async_reorder_favorites(
        hass, connection.user.id, msg["subject_ids"]
    )
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command(
    {vol.Required("type"): f"{WS_PREFIX}/reload_content"}
)
@websocket_api.ws_require_user()
@websocket_api.async_response
async def ws_reload_content(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    runtime = _runtime(hass)
    if runtime is None:
        _send_not_loaded(connection, msg["id"])
        return
    if not connection.user.is_admin:
        connection.send_error(
            msg["id"], "unauthorized", "Administrator required"
        )
        return
    await runtime.content.async_reload(hass)
    connection.send_result(
        msg["id"],
        {
            "subjects": len(runtime.content.subjects),
            "errors": runtime.content.errors,
        },
    )
