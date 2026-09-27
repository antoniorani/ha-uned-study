"""Ingress HTTP application for UNED Study."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import mimetypes
from pathlib import Path
import uuid
from typing import Any

from aiohttp import web

from .config import DATA_DIR, AppConfig, load_config
from .content import ContentManager
from .exam import build_exam_state, expired as exam_expired, score as score_exam
from .models import StudyItem, Subject
from .scheduler import choose_next, schedule_flashcard, schedule_test
from .storage import Storage

STATIC_DIR = Path(__file__).parent / "static"
INGRESS_PROXY_IP = "172.30.32.2"


def _user_id(request: web.Request) -> str:
    value = request.headers.get("X-Remote-User-Id")
    if value:
        return value
    config: AppConfig = request.app["config"]
    if config.dev_mode:
        return request.headers.get("X-Debug-User-Id", "dev-user")
    raise web.HTTPUnauthorized(text="Home Assistant user header missing")


def _display_name(request: web.Request) -> str:
    return (
        request.headers.get("X-Remote-User-Display-Name")
        or request.headers.get("X-Remote-User-Name")
        or "Usuario"
    )


@web.middleware
async def ingress_only(request: web.Request, handler):
    config: AppConfig = request.app["config"]
    if request.path != "/health" and not config.dev_mode:
        if request.remote != INGRESS_PROXY_IP:
            raise web.HTTPForbidden(text="Ingress access required")
    return await handler(request)


def _item_payload(item: StudyItem, *, reveal: bool = False) -> dict[str, Any]:
    if item.item_type == "mcq":
        value: dict[str, Any] = {
            "id": item.id,
            "type": "test",
            "topic": item.topic,
            "importance": item.importance,
            "question_md": item.question_md,
            "answers": [
                {"id": answer.id, "text_md": answer.text_md}
                for answer in item.answers
            ],
        }
        if reveal:
            value["correct_answer"] = item.correct_answer
            value["explanation_md"] = item.explanation_md
        return value

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


def _statistics(
    subject: Subject,
    progress: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    overall = {
        "total": len(subject.items),
        "studied": 0,
        "new": 0,
        "due": 0,
        "correct": 0,
        "incorrect": 0,
        "mastery_sum": 0.0,
    }
    topics = {
        topic.id: {
            "id": topic.id,
            "title": topic.title,
            "total": 0,
            "studied": 0,
            "new": 0,
            "due": 0,
            "correct": 0,
            "incorrect": 0,
            "mastery_sum": 0.0,
        }
        for topic in subject.topics
    }

    for item in subject.items:
        stats = topics[item.topic]
        stats["total"] += 1
        item_progress = progress.get(item.id)
        if item_progress is None or item_progress.times_seen == 0:
            overall["new"] += 1
            stats["new"] += 1
            continue

        overall["studied"] += 1
        stats["studied"] += 1
        overall["correct"] += item_progress.correct_count
        overall["incorrect"] += item_progress.incorrect_count
        stats["correct"] += item_progress.correct_count
        stats["incorrect"] += item_progress.incorrect_count
        overall["mastery_sum"] += item_progress.mastery
        stats["mastery_sum"] += item_progress.mastery

        due = item_progress.next_review_at
        if due is not None and due <= now:
            overall["due"] += 1
            stats["due"] += 1

    def finish(value: dict[str, Any]) -> dict[str, Any]:
        attempts = value["correct"] + value["incorrect"]
        total = value["total"]
        result = dict(value)
        result["accuracy"] = value["correct"] / attempts if attempts else None
        result["mastery"] = value["mastery_sum"] / total if total else 0.0
        result.pop("mastery_sum", None)
        return result

    return {
        "overall": finish(overall),
        "topics": [finish(topics[topic.id]) for topic in subject.topics],
    }


async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def static_file(request: web.Request) -> web.FileResponse:
    name = request.match_info["name"]
    if "/" in name or ".." in name:
        raise web.HTTPNotFound
    path = STATIC_DIR / name
    if not path.is_file():
        raise web.HTTPNotFound
    return web.FileResponse(path)


async def dashboard(request: web.Request) -> web.Response:
    user = _user_id(request)
    storage: Storage = request.app["storage"]
    content: ContentManager = request.app["content"]

    preferences, = await asyncio.gather(
        asyncio.to_thread(storage.preferences, user),
    )

    subjects = []
    for subject in content.subjects.values():
        progress, active = await asyncio.gather(
            asyncio.to_thread(storage.progress_map, user, subject.id),
            asyncio.to_thread(storage.active_session, user, subject.id),
        )
        stats = _statistics(subject, progress)["overall"]
        pref = preferences.get(subject.id, {})
        subjects.append(
            {
                "id": subject.id,
                "title": subject.title,
                "type": subject.subject_type,
                "favorite": bool(pref.get("favorite", False)),
                "favorite_order": pref.get("favorite_order"),
                "progress": stats,
                "active_session": (
                    {
                        "session_id": active["session_id"],
                        "kind": active["kind"],
                        "topic_id": active["topic_id"],
                    }
                    if active
                    else None
                ),
                "exam_available": (
                    subject.subject_type == "test"
                    and bool(subject.items)
                ),
            }
        )

    subjects.sort(
        key=lambda item: (
            0 if item["favorite"] else 1,
            item["favorite_order"]
            if item["favorite_order"] is not None
            else 1_000_000,
            item["title"].casefold(),
        )
    )

    return web.json_response(
        {
            "user": {
                "id": user,
                "name": _display_name(request),
            },
            "subjects": subjects,
            "content": {
                "last_sync": content.last_sync,
                "last_error": content.last_error,
            },
        }
    )


async def subject_detail(request: web.Request) -> web.Response:
    user = _user_id(request)
    subject_id = request.match_info["subject_id"]
    storage: Storage = request.app["storage"]
    content: ContentManager = request.app["content"]
    subject = content.subjects.get(subject_id)
    if subject is None:
        raise web.HTTPNotFound(text="Subject not found")

    progress = await asyncio.to_thread(
        storage.progress_map,
        user,
        subject.id,
    )
    stats = _statistics(subject, progress)
    return web.json_response(
        {
            "id": subject.id,
            "title": subject.title,
            "type": subject.subject_type,
            "degree": subject.degree,
            "course": subject.course,
            "content_version": subject.content_version,
            "topics": [
                {"id": topic.id, "title": topic.title}
                for topic in subject.topics
            ],
            "statistics": stats,
            "exam": subject.exam,
        }
    )


async def set_favorite(request: web.Request) -> web.Response:
    user = _user_id(request)
    subject_id = request.match_info["subject_id"]
    content: ContentManager = request.app["content"]
    storage: Storage = request.app["storage"]
    if subject_id not in content.subjects:
        raise web.HTTPNotFound(text="Subject not found")

    body = await request.json()
    favorite = bool(body.get("favorite"))
    await asyncio.to_thread(
        storage.set_favorite,
        user,
        subject_id,
        favorite,
    )
    return web.json_response({"ok": True})


async def continue_subject(request: web.Request) -> web.Response:
    user = _user_id(request)
    subject_id = request.match_info["subject_id"]
    content: ContentManager = request.app["content"]
    storage: Storage = request.app["storage"]
    subject = content.subjects.get(subject_id)
    if subject is None:
        raise web.HTTPNotFound(text="Subject not found")

    active = await asyncio.to_thread(
        storage.active_session,
        user,
        subject_id,
    )
    if active:
        return web.json_response(
            {
                "session_id": active["session_id"],
                "kind": active["kind"],
                "subject_id": subject_id,
            }
        )

    session = await asyncio.to_thread(
        storage.create_session,
        session_id=str(uuid.uuid4()),
        user_id=user,
        subject_id=subject_id,
        kind="adaptive",
    )
    return web.json_response(
        {
            "session_id": session["session_id"],
            "kind": session["kind"],
            "subject_id": subject_id,
        }
    )


async def start_topic(request: web.Request) -> web.Response:
    user = _user_id(request)
    subject_id = request.match_info["subject_id"]
    body = await request.json()
    topic_id = body.get("topic_id")

    content: ContentManager = request.app["content"]
    storage: Storage = request.app["storage"]
    subject = content.subjects.get(subject_id)
    if subject is None:
        raise web.HTTPNotFound(text="Subject not found")
    if not isinstance(topic_id, str) or topic_id not in subject.topics_by_id:
        raise web.HTTPBadRequest(text="Unknown topic")

    session = await asyncio.to_thread(
        storage.create_session,
        session_id=str(uuid.uuid4()),
        user_id=user,
        subject_id=subject_id,
        kind="topic",
        topic_id=topic_id,
    )
    return web.json_response(
        {
            "session_id": session["session_id"],
            "kind": session["kind"],
            "subject_id": subject_id,
            "topic_id": topic_id,
        }
    )


def _study_session(
    request: web.Request,
    user: str,
    session_id: str,
) -> tuple[dict[str, Any], Subject]:
    storage: Storage = request.app["storage"]
    content: ContentManager = request.app["content"]
    session = storage.get_session(user, session_id)
    if (
        session is None
        or session["state"] != "active"
        or session["kind"] not in {"adaptive", "topic"}
    ):
        raise web.HTTPNotFound(text="Active study session not found")
    subject = content.subjects.get(session["subject_id"])
    if subject is None:
        raise web.HTTPConflict(text="Subject content is unavailable")
    return session, subject


async def next_item(request: web.Request) -> web.Response:
    user = _user_id(request)
    session_id = request.match_info["session_id"]
    storage: Storage = request.app["storage"]

    session, subject = await asyncio.to_thread(
        _study_session,
        request,
        user,
        session_id,
    )

    if session["current_item_id"]:
        current = subject.items_by_id.get(session["current_item_id"])
        if current is not None:
            return web.json_response({"item": _item_payload(current)})

    items = list(subject.items)
    if session["kind"] == "topic":
        items = [
            item
            for item in items
            if item.topic == session["topic_id"]
        ]

    progress, recent = await asyncio.gather(
        asyncio.to_thread(storage.progress_map, user, subject.id),
        asyncio.to_thread(storage.recent_item_ids, user, subject.id, 10),
    )
    item = choose_next(
        items,
        progress,
        recent_item_ids=recent,
    )
    if item is None:
        await asyncio.to_thread(
            storage.complete_session,
            user,
            session_id,
        )
        return web.json_response(
            {
                "complete": True,
                "session": {
                    "answered_count": session["answered_count"],
                    "correct_count": session["correct_count"],
                    "incorrect_count": session["incorrect_count"],
                },
            }
        )

    await asyncio.to_thread(
        storage.set_current_item,
        user,
        session_id,
        item.id,
    )
    return web.json_response({"item": _item_payload(item)})


async def finish_study_session(request: web.Request) -> web.Response:
    user = _user_id(request)
    session_id = request.match_info["session_id"]
    storage: Storage = request.app["storage"]
    session = await asyncio.to_thread(
        storage.get_session,
        user,
        session_id,
    )
    if (
        session is None
        or session["state"] != "active"
        or session["kind"] not in {"adaptive", "topic"}
    ):
        raise web.HTTPNotFound(text="Active study session not found")

    await asyncio.to_thread(
        storage.complete_session,
        user,
        session_id,
    )
    return web.json_response({"ok": True})


async def answer_question(request: web.Request) -> web.Response:
    user = _user_id(request)
    session_id = request.match_info["session_id"]
    storage: Storage = request.app["storage"]
    body = await request.json()
    item_id = body.get("item_id")
    answer_id = body.get("answer_id")
    request_id = body.get("request_id")

    if not all(isinstance(value, str) and value for value in (
        item_id,
        answer_id,
        request_id,
    )):
        raise web.HTTPBadRequest(text="Missing answer fields")

    session, subject = await asyncio.to_thread(
        _study_session,
        request,
        user,
        session_id,
    )
    item = subject.items_by_id.get(item_id)
    if item is None or item.item_type != "mcq":
        raise web.HTTPBadRequest(text="Item is not a test question")

    previous_request = await asyncio.to_thread(
        storage.review_request,
        user,
        request_id,
    )
    if previous_request is not None:
        if (
            previous_request["session_id"] != session_id
            or previous_request["item_id"] != item_id
            or previous_request["answer_id"] != answer_id
        ):
            raise web.HTTPConflict(text="request_id already used")
        return web.json_response(
            {
                "duplicate": True,
                "correct": previous_request["result"] == "correct",
                "item": _item_payload(item, reveal=True),
            }
        )

    if session["current_item_id"] != item.id:
        raise web.HTTPConflict(text="Question is no longer current")
    if answer_id not in {answer.id for answer in item.answers}:
        raise web.HTTPBadRequest(text="Unknown answer")

    progress = await asyncio.to_thread(
        storage.progress_map,
        user,
        subject.id,
    )
    correct = answer_id == item.correct_answer
    decision = schedule_test(
        importance=item.importance,
        correct=correct,
        previous=progress.get(item.id),
    )
    await asyncio.to_thread(
        storage.record_review,
        request_id=request_id,
        user_id=user,
        subject_id=subject.id,
        item_id=item.id,
        session_id=session_id,
        result="correct" if correct else "incorrect",
        answer_id=answer_id,
        rating=None,
        response_ms=body.get("response_ms")
        if isinstance(body.get("response_ms"), int)
        else None,
        decision=decision,
    )
    return web.json_response(
        {
            "correct": correct,
            "item": _item_payload(item, reveal=True),
            "next_review_at": decision.next_review_at.isoformat(),
        }
    )


async def rate_card(request: web.Request) -> web.Response:
    user = _user_id(request)
    session_id = request.match_info["session_id"]
    storage: Storage = request.app["storage"]
    body = await request.json()
    item_id = body.get("item_id")
    rating = body.get("rating")
    request_id = body.get("request_id")

    if (
        not isinstance(item_id, str)
        or rating not in {"again", "hard", "good", "easy"}
        or not isinstance(request_id, str)
        or not request_id
    ):
        raise web.HTTPBadRequest(text="Invalid flashcard rating")

    session, subject = await asyncio.to_thread(
        _study_session,
        request,
        user,
        session_id,
    )
    item = subject.items_by_id.get(item_id)
    if item is None or item.item_type != "flashcard":
        raise web.HTTPBadRequest(text="Item is not a flashcard")

    previous_request = await asyncio.to_thread(
        storage.review_request,
        user,
        request_id,
    )
    if previous_request is not None:
        if (
            previous_request["session_id"] != session_id
            or previous_request["item_id"] != item_id
            or previous_request["rating"] != rating
        ):
            raise web.HTTPConflict(text="request_id already used")
        return web.json_response({"duplicate": True})

    if session["current_item_id"] != item.id:
        raise web.HTTPConflict(text="Card is no longer current")

    progress = await asyncio.to_thread(
        storage.progress_map,
        user,
        subject.id,
    )
    decision = schedule_flashcard(
        importance=item.importance,
        rating=rating,
        previous=progress.get(item.id),
    )
    correct = rating in {"good", "easy"}
    await asyncio.to_thread(
        storage.record_review,
        request_id=request_id,
        user_id=user,
        subject_id=subject.id,
        item_id=item.id,
        session_id=session_id,
        result="correct" if correct else "incorrect",
        answer_id=None,
        rating=rating,
        response_ms=body.get("response_ms")
        if isinstance(body.get("response_ms"), int)
        else None,
        decision=decision,
    )
    return web.json_response(
        {"next_review_at": decision.next_review_at.isoformat()}
    )


def _exam_session(
    request: web.Request,
    user: str,
    session_id: str,
    *,
    allow_completed: bool = False,
) -> tuple[dict[str, Any], Subject]:
    storage: Storage = request.app["storage"]
    content: ContentManager = request.app["content"]
    session = storage.get_session(user, session_id)
    if (
        session is None
        or session["kind"] != "exam"
        or (
            not allow_completed
            and session["state"] != "active"
        )
    ):
        raise web.HTTPNotFound(text="Mock exam not found")
    subject = content.subjects.get(session["subject_id"])
    if subject is None:
        raise web.HTTPConflict(text="Subject content is unavailable")
    return session, subject


def _exam_view(
    subject: Subject,
    session: dict[str, Any],
) -> dict[str, Any]:
    state = session["data"]
    item_ids = state.get("item_ids", [])
    answers = state.get("answers", {})
    index = int(state.get("current_index", 0))
    index = max(0, min(index, max(len(item_ids) - 1, 0)))
    item = (
        subject.items_by_id.get(item_ids[index])
        if item_ids
        else None
    )
    if item is None:
        raise web.HTTPConflict(text="Exam question is unavailable")

    return {
        "session_id": session["session_id"],
        "subject_id": subject.id,
        "state": session["state"],
        "index": index,
        "question_count": len(item_ids),
        "answered_count": len(answers),
        "selected_answer": answers.get(item.id),
        "expires_at": state.get("expires_at"),
        "expired": exam_expired(state),
        "item": _item_payload(item),
    }


async def start_exam(request: web.Request) -> web.Response:
    user = _user_id(request)
    subject_id = request.match_info["subject_id"]
    content: ContentManager = request.app["content"]
    storage: Storage = request.app["storage"]
    subject = content.subjects.get(subject_id)
    if subject is None:
        raise web.HTTPNotFound(text="Subject not found")
    if subject.subject_type != "test":
        raise web.HTTPBadRequest(text="Mock exam requires a test subject")

    active = await asyncio.to_thread(
        storage.active_session,
        user,
        subject_id,
    )
    if active and active["kind"] == "exam":
        return web.json_response(_exam_view(subject, active))

    state = build_exam_state(subject)
    session = await asyncio.to_thread(
        storage.create_session,
        session_id=str(uuid.uuid4()),
        user_id=user,
        subject_id=subject_id,
        kind="exam",
        data=state,
    )
    return web.json_response(_exam_view(subject, session))


async def exam_state(request: web.Request) -> web.Response:
    user = _user_id(request)
    session_id = request.match_info["session_id"]
    session, subject = await asyncio.to_thread(
        _exam_session,
        request,
        user,
        session_id,
    )
    return web.json_response(_exam_view(subject, session))


async def exam_navigate(request: web.Request) -> web.Response:
    user = _user_id(request)
    session_id = request.match_info["session_id"]
    body = await request.json()
    index = body.get("index")
    if not isinstance(index, int) or index < 0:
        raise web.HTTPBadRequest(text="Invalid question index")

    storage: Storage = request.app["storage"]
    session, subject = await asyncio.to_thread(
        _exam_session,
        request,
        user,
        session_id,
    )
    state = dict(session["data"])
    item_ids = state.get("item_ids", [])
    if index >= len(item_ids):
        raise web.HTTPBadRequest(text="Question index out of range")
    state["current_index"] = index
    await asyncio.to_thread(
        storage.update_session_data,
        user,
        session_id,
        state,
    )
    session["data"] = state
    return web.json_response(_exam_view(subject, session))


async def exam_answer(request: web.Request) -> web.Response:
    user = _user_id(request)
    session_id = request.match_info["session_id"]
    body = await request.json()
    item_id = body.get("item_id")
    answer_id = body.get("answer_id")
    if not isinstance(item_id, str) or not isinstance(answer_id, str):
        raise web.HTTPBadRequest(text="Invalid answer")

    storage: Storage = request.app["storage"]
    session, subject = await asyncio.to_thread(
        _exam_session,
        request,
        user,
        session_id,
    )
    state = dict(session["data"])
    if exam_expired(state):
        raise web.HTTPConflict(text="Mock exam has expired")

    item_ids = state.get("item_ids", [])
    if item_id not in item_ids:
        raise web.HTTPBadRequest(text="Question is not part of the exam")
    item = subject.items_by_id.get(item_id)
    if item is None or item.item_type != "mcq":
        raise web.HTTPConflict(text="Question is unavailable")
    if answer_id not in {answer.id for answer in item.answers}:
        raise web.HTTPBadRequest(text="Unknown answer")

    answers = dict(state.get("answers", {}))
    answers[item_id] = answer_id
    state["answers"] = answers
    await asyncio.to_thread(
        storage.update_session_data,
        user,
        session_id,
        state,
    )
    return web.json_response(
        {
            "ok": True,
            "answered_count": len(answers),
            "question_count": len(item_ids),
        }
    )


async def finish_exam(request: web.Request) -> web.Response:
    user = _user_id(request)
    session_id = request.match_info["session_id"]
    storage: Storage = request.app["storage"]
    session, subject = await asyncio.to_thread(
        _exam_session,
        request,
        user,
        session_id,
        allow_completed=True,
    )
    state = dict(session["data"])

    if session["state"] == "completed" and isinstance(state.get("result"), dict):
        return web.json_response(state["result"])

    result_score = score_exam(subject, state)
    item_ids = list(state.get("item_ids", []))
    answers = dict(state.get("answers", {}))
    progress = await asyncio.to_thread(
        storage.progress_map,
        user,
        subject.id,
    )

    review = []
    for item_id in item_ids:
        item = subject.items_by_id.get(str(item_id))
        if item is None or item.item_type != "mcq":
            raise web.HTTPConflict(text="Exam content changed during session")
        answer_id = answers.get(item.id)
        correct = None
        if isinstance(answer_id, str):
            correct = answer_id == item.correct_answer
            decision = schedule_test(
                importance=item.importance,
                correct=correct,
                previous=progress.get(item.id),
            )
            await asyncio.to_thread(
                storage.record_review,
                request_id=f"exam:{session_id}:{item.id}",
                user_id=user,
                subject_id=subject.id,
                item_id=item.id,
                session_id=session_id,
                result="correct" if correct else "incorrect",
                answer_id=answer_id,
                rating=None,
                response_ms=None,
                decision=decision,
            )

        review.append(
            {
                "item": _item_payload(item, reveal=True),
                "answer_id": answer_id,
                "correct": correct,
            }
        )

    result = {
        "session_id": session_id,
        "expired": exam_expired(state),
        "score": result_score,
        "review": review,
    }
    state["result"] = result
    await asyncio.to_thread(
        storage.complete_session,
        user,
        session_id,
        data=state,
    )
    return web.json_response(result)


async def asset(request: web.Request) -> web.FileResponse:
    _user_id(request)
    content: ContentManager = request.app["content"]
    path = content.asset_path(
        request.match_info["subject_id"],
        request.match_info["asset_path"],
    )
    if path is None:
        raise web.HTTPNotFound
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    response = web.FileResponse(path)
    response.content_type = content_type
    response.headers["Cache-Control"] = "private, max-age=3600"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    return response


async def sync_loop(app: web.Application) -> None:
    content: ContentManager = app["content"]
    config: AppConfig = app["config"]
    while True:
        await asyncio.sleep(config.sync_interval_hours * 3600)
        await content.sync()


async def on_startup(app: web.Application) -> None:
    storage: Storage = app["storage"]
    content: ContentManager = app["content"]
    await asyncio.to_thread(storage.initialize)
    await content.load()

    # Always check GitHub at startup, but cached valid content remains usable
    # when the network is unavailable.
    await content.sync()
    app["sync_task"] = asyncio.create_task(sync_loop(app))


async def on_cleanup(app: web.Application) -> None:
    task = app.get("sync_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    storage: Storage = app["storage"]
    await asyncio.to_thread(storage.checkpoint)


def create_app(config: AppConfig | None = None) -> web.Application:
    config = config or load_config()
    storage = Storage(DATA_DIR / "uned_study.db")
    content = ContentManager(
        data_dir=DATA_DIR,
        repository=config.content_repository,
        branch=config.content_branch,
    )

    app = web.Application(
        middlewares=[ingress_only],
        client_max_size=2 * 1024 * 1024,
    )
    app["config"] = config
    app["storage"] = storage
    app["content"] = content

    app.router.add_get("/health", health)
    app.router.add_get("/", index)
    app.router.add_get("/static/{name}", static_file)

    app.router.add_get("/api/dashboard", dashboard)
    app.router.add_get("/api/subjects/{subject_id}", subject_detail)
    app.router.add_post("/api/subjects/{subject_id}/favorite", set_favorite)
    app.router.add_post("/api/subjects/{subject_id}/continue", continue_subject)
    app.router.add_post("/api/subjects/{subject_id}/topic", start_topic)

    app.router.add_get("/api/sessions/{session_id}/next", next_item)
    app.router.add_post("/api/sessions/{session_id}/finish", finish_study_session)
    app.router.add_post("/api/sessions/{session_id}/answer", answer_question)
    app.router.add_post("/api/sessions/{session_id}/rate", rate_card)

    app.router.add_post("/api/subjects/{subject_id}/exam", start_exam)
    app.router.add_get("/api/exams/{session_id}", exam_state)
    app.router.add_post("/api/exams/{session_id}/navigate", exam_navigate)
    app.router.add_post("/api/exams/{session_id}/answer", exam_answer)
    app.router.add_post("/api/exams/{session_id}/finish", finish_exam)

    app.router.add_get(
        "/api/assets/{subject_id}/{asset_path:.+}",
        asset,
    )

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def main() -> None:
    web.run_app(
        create_app(),
        host="0.0.0.0",
        port=8099,
        access_log_format='%a "%r" %s %b %Tf',
    )


if __name__ == "__main__":
    main()
