"""SQLite persistence for UNED Study."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Any

from homeassistant.core import HomeAssistant

from .scheduler import ALGORITHM_VERSION, ProgressSnapshot, ScheduleDecision

DB_SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class StudyDatabase:
    """Persistent per-user study state kept outside the integration package."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    async def async_initialize(self, hass: HomeAssistant) -> None:
        await hass.async_add_executor_job(self._initialize)

    def _initialize(self) -> None:
        with self._lock, self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta(
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS user_subjects(
                    user_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    favorite INTEGER NOT NULL DEFAULT 0,
                    favorite_order INTEGER,
                    last_studied_at TEXT,
                    PRIMARY KEY(user_id, subject_id)
                );
                CREATE TABLE IF NOT EXISTS item_progress(
                    user_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    times_seen INTEGER NOT NULL DEFAULT 0,
                    correct_count INTEGER NOT NULL DEFAULT 0,
                    incorrect_count INTEGER NOT NULL DEFAULT 0,
                    current_streak INTEGER NOT NULL DEFAULT 0,
                    mastery REAL NOT NULL DEFAULT 0,
                    difficulty REAL NOT NULL DEFAULT 0.5,
                    last_seen_at TEXT,
                    next_review_at TEXT,
                    interval_days REAL NOT NULL DEFAULT 0,
                    last_result TEXT,
                    algorithm_version INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY(user_id, subject_id, item_id)
                );
                CREATE TABLE IF NOT EXISTS study_sessions(
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    filters_json TEXT NOT NULL DEFAULT '{}',
                    started_at TEXT NOT NULL,
                    last_activity_at TEXT NOT NULL,
                    current_item_id TEXT,
                    answered_count INTEGER NOT NULL DEFAULT 0,
                    correct_count INTEGER NOT NULL DEFAULT 0,
                    incorrect_count INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL DEFAULT 'active'
                );
                CREATE TABLE IF NOT EXISTS review_history(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    session_id TEXT,
                    result TEXT NOT NULL,
                    rating TEXT,
                    response_ms INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_progress_user_subject
                    ON item_progress(user_id, subject_id);
                CREATE INDEX IF NOT EXISTS ix_review_session
                    ON review_history(session_id, id DESC);
                """
            )
            row = db.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO meta(key,value) VALUES('schema_version',?)",
                    (str(DB_SCHEMA_VERSION),),
                )
            elif int(row["value"]) != DB_SCHEMA_VERSION:
                raise RuntimeError(
                    f"Unsupported UNED Study DB schema {row['value']}"
                )

    async def async_checkpoint(self, hass: HomeAssistant) -> None:
        await hass.async_add_executor_job(self._checkpoint)

    def _checkpoint(self) -> None:
        with self._lock, self._connect() as db:
            db.execute("PRAGMA wal_checkpoint(FULL)")

    async def async_get_subject_preferences(
        self, hass: HomeAssistant, user_id: str
    ) -> dict[str, dict[str, Any]]:
        return await hass.async_add_executor_job(
            self._get_subject_preferences, user_id
        )

    def _get_subject_preferences(self, user_id: str) -> dict[str, dict[str, Any]]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                """SELECT subject_id,favorite,favorite_order,last_studied_at
                   FROM user_subjects WHERE user_id=?""",
                (user_id,),
            ).fetchall()
        return {
            row["subject_id"]: {
                "favorite": bool(row["favorite"]),
                "favorite_order": row["favorite_order"],
                "last_studied_at": row["last_studied_at"],
            }
            for row in rows
        }

    async def async_get_subject_aggregates(
        self, hass: HomeAssistant, user_id: str
    ) -> dict[str, dict[str, Any]]:
        return await hass.async_add_executor_job(
            self._get_subject_aggregates, user_id
        )

    def _get_subject_aggregates(self, user_id: str) -> dict[str, dict[str, Any]]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                """SELECT subject_id,COUNT(*) studied_items,
                          SUM(times_seen) reviews,
                          SUM(correct_count) correct,
                          SUM(incorrect_count) incorrect,
                          AVG(mastery) mastery
                   FROM item_progress
                   WHERE user_id=? GROUP BY subject_id""",
                (user_id,),
            ).fetchall()
        return {
            row["subject_id"]: {
                "studied_items": row["studied_items"] or 0,
                "reviews": row["reviews"] or 0,
                "correct": row["correct"] or 0,
                "incorrect": row["incorrect"] or 0,
                "mastery": float(row["mastery"] or 0),
            }
            for row in rows
        }

    async def async_set_favorite(
        self, hass: HomeAssistant, user_id: str, subject_id: str, favorite: bool
    ) -> None:
        await hass.async_add_executor_job(
            self._set_favorite, user_id, subject_id, favorite
        )

    def _set_favorite(
        self, user_id: str, subject_id: str, favorite: bool
    ) -> None:
        with self._lock, self._connect() as db:
            order = None
            if favorite:
                row = db.execute(
                    """SELECT COALESCE(MAX(favorite_order),0)+1 n
                       FROM user_subjects
                       WHERE user_id=? AND favorite=1""",
                    (user_id,),
                ).fetchone()
                order = int(row["n"])
            db.execute(
                """INSERT INTO user_subjects(
                       user_id,subject_id,favorite,favorite_order
                   ) VALUES(?,?,?,?)
                   ON CONFLICT(user_id,subject_id) DO UPDATE SET
                       favorite=excluded.favorite,
                       favorite_order=CASE
                         WHEN excluded.favorite=1
                         THEN COALESCE(user_subjects.favorite_order,
                                       excluded.favorite_order)
                         ELSE NULL END""",
                (user_id, subject_id, int(favorite), order),
            )

    async def async_reorder_favorites(
        self, hass: HomeAssistant, user_id: str, subject_ids: list[str]
    ) -> None:
        await hass.async_add_executor_job(
            self._reorder_favorites, user_id, subject_ids
        )

    def _reorder_favorites(
        self, user_id: str, subject_ids: list[str]
    ) -> None:
        with self._lock, self._connect() as db:
            for order, subject_id in enumerate(subject_ids, 1):
                db.execute(
                    """INSERT INTO user_subjects(
                           user_id,subject_id,favorite,favorite_order
                       ) VALUES(?,?,1,?)
                       ON CONFLICT(user_id,subject_id) DO UPDATE SET
                         favorite=1,favorite_order=excluded.favorite_order""",
                    (user_id, subject_id, order),
                )

    async def async_create_session(
        self,
        hass: HomeAssistant,
        *,
        session_id: str,
        user_id: str,
        subject_id: str,
        mode: str,
        filters: dict[str, Any],
    ) -> None:
        await hass.async_add_executor_job(
            self._create_session,
            session_id, user_id, subject_id, mode, filters,
        )

    def _create_session(
        self,
        session_id: str,
        user_id: str,
        subject_id: str,
        mode: str,
        filters: dict[str, Any],
    ) -> None:
        now = _now()
        with self._lock, self._connect() as db:
            db.execute(
                """UPDATE study_sessions
                   SET state='paused'
                   WHERE user_id=? AND subject_id=? AND state='active'""",
                (user_id, subject_id),
            )
            db.execute(
                """INSERT INTO study_sessions(
                     session_id,user_id,subject_id,mode,filters_json,
                     started_at,last_activity_at
                   ) VALUES(?,?,?,?,?,?,?)""",
                (
                    session_id, user_id, subject_id, mode,
                    json.dumps(filters), now, now,
                ),
            )
            db.execute(
                """INSERT INTO user_subjects(
                     user_id,subject_id,last_studied_at
                   ) VALUES(?,?,?)
                   ON CONFLICT(user_id,subject_id) DO UPDATE SET
                     last_studied_at=excluded.last_studied_at""",
                (user_id, subject_id, now),
            )

    async def async_get_active_sessions(
        self, hass: HomeAssistant, user_id: str
    ) -> dict[str, dict[str, Any]]:
        """Return the newest active session for each subject."""
        return await hass.async_add_executor_job(
            self._get_active_sessions, user_id
        )

    def _get_active_sessions(
        self, user_id: str
    ) -> dict[str, dict[str, Any]]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                """SELECT * FROM study_sessions
                   WHERE user_id=? AND state='active'
                   ORDER BY last_activity_at DESC""",
                (user_id,),
            ).fetchall()

        sessions: dict[str, dict[str, Any]] = {}
        for row in rows:
            subject_id = row["subject_id"]
            if subject_id in sessions:
                continue
            session = dict(row)
            session["filters"] = json.loads(
                session.pop("filters_json")
            )
            sessions[subject_id] = session
        return sessions

    async def async_get_session(
        self, hass: HomeAssistant, session_id: str, user_id: str
    ) -> dict[str, Any] | None:
        return await hass.async_add_executor_job(
            self._get_session, session_id, user_id
        )

    def _get_session(
        self, session_id: str, user_id: str
    ) -> dict[str, Any] | None:
        with self._lock, self._connect() as db:
            row = db.execute(
                """SELECT * FROM study_sessions
                   WHERE session_id=? AND user_id=?""",
                (session_id, user_id),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["filters"] = json.loads(result.pop("filters_json"))
        return result

    async def async_set_current_item(
        self,
        hass: HomeAssistant,
        session_id: str,
        user_id: str,
        item_id: str,
    ) -> None:
        await hass.async_add_executor_job(
            self._set_current_item, session_id, user_id, item_id
        )

    def _set_current_item(
        self, session_id: str, user_id: str, item_id: str
    ) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                """UPDATE study_sessions
                   SET current_item_id=?,last_activity_at=?
                   WHERE session_id=? AND user_id=?""",
                (item_id, _now(), session_id, user_id),
            )

    async def async_get_progress_map(
        self, hass: HomeAssistant, user_id: str, subject_id: str
    ) -> dict[str, ProgressSnapshot]:
        return await hass.async_add_executor_job(
            self._get_progress_map, user_id, subject_id
        )

    def _get_progress_map(
        self, user_id: str, subject_id: str
    ) -> dict[str, ProgressSnapshot]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                """SELECT * FROM item_progress
                   WHERE user_id=? AND subject_id=?""",
                (user_id, subject_id),
            ).fetchall()
        return {
            row["item_id"]: ProgressSnapshot(
                item_id=row["item_id"],
                times_seen=row["times_seen"],
                correct_count=row["correct_count"],
                incorrect_count=row["incorrect_count"],
                current_streak=row["current_streak"],
                interval_days=row["interval_days"],
                last_seen_at=_dt(row["last_seen_at"]),
                next_review_at=_dt(row["next_review_at"]),
            )
            for row in rows
        }

    async def async_recent_item_ids(
        self, hass: HomeAssistant, session_id: str, limit: int = 10
    ) -> set[str]:
        return await hass.async_add_executor_job(
            self._recent_item_ids, session_id, limit
        )

    def _recent_item_ids(self, session_id: str, limit: int) -> set[str]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                """SELECT item_id FROM review_history
                   WHERE session_id=? ORDER BY id DESC LIMIT ?""",
                (session_id, limit),
            ).fetchall()
        return {row["item_id"] for row in rows}

    async def async_request_exists(
        self, hass: HomeAssistant, request_id: str
    ) -> bool:
        return await hass.async_add_executor_job(
            self._request_exists, request_id
        )

    def _request_exists(self, request_id: str) -> bool:
        with self._lock, self._connect() as db:
            return db.execute(
                "SELECT 1 FROM review_history WHERE request_id=?",
                (request_id,),
            ).fetchone() is not None

    async def async_record_review(
        self,
        hass: HomeAssistant,
        *,
        request_id: str,
        user_id: str,
        subject_id: str,
        item_id: str,
        session_id: str,
        result: str,
        rating: str | None,
        response_ms: int | None,
        decision: ScheduleDecision,
    ) -> bool:
        return await hass.async_add_executor_job(
            self._record_review,
            request_id, user_id, subject_id, item_id, session_id,
            result, rating, response_ms, decision,
        )

    def _record_review(
        self,
        request_id: str,
        user_id: str,
        subject_id: str,
        item_id: str,
        session_id: str,
        result: str,
        rating: str | None,
        response_ms: int | None,
        decision: ScheduleDecision,
    ) -> bool:
        now = _now()
        correct = result == "correct"
        with self._lock, self._connect() as db:
            if db.execute(
                "SELECT 1 FROM review_history WHERE request_id=?",
                (request_id,),
            ).fetchone():
                return False

            previous = db.execute(
                """SELECT times_seen,correct_count,incorrect_count,current_streak
                   FROM item_progress
                   WHERE user_id=? AND subject_id=? AND item_id=?""",
                (user_id, subject_id, item_id),
            ).fetchone()

            seen = (previous["times_seen"] if previous else 0) + 1
            good = (previous["correct_count"] if previous else 0) + int(correct)
            bad = (previous["incorrect_count"] if previous else 0) + int(not correct)
            streak = (
                (previous["current_streak"] if previous else 0) + 1
                if correct else 0
            )

            db.execute(
                """INSERT INTO item_progress(
                     user_id,subject_id,item_id,times_seen,correct_count,
                     incorrect_count,current_streak,mastery,difficulty,
                     last_seen_at,next_review_at,interval_days,last_result,
                     algorithm_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(user_id,subject_id,item_id) DO UPDATE SET
                     times_seen=excluded.times_seen,
                     correct_count=excluded.correct_count,
                     incorrect_count=excluded.incorrect_count,
                     current_streak=excluded.current_streak,
                     mastery=excluded.mastery,
                     difficulty=excluded.difficulty,
                     last_seen_at=excluded.last_seen_at,
                     next_review_at=excluded.next_review_at,
                     interval_days=excluded.interval_days,
                     last_result=excluded.last_result,
                     algorithm_version=excluded.algorithm_version""",
                (
                    user_id, subject_id, item_id, seen, good, bad, streak,
                    decision.mastery, decision.difficulty, now,
                    decision.next_review_at.isoformat(),
                    decision.interval_days, result, ALGORITHM_VERSION,
                ),
            )
            db.execute(
                """INSERT INTO review_history(
                     request_id,user_id,subject_id,item_id,session_id,
                     result,rating,response_ms,created_at
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    request_id, user_id, subject_id, item_id, session_id,
                    result, rating, response_ms, now,
                ),
            )
            db.execute(
                """UPDATE study_sessions SET
                     answered_count=answered_count+1,
                     correct_count=correct_count+?,
                     incorrect_count=incorrect_count+?,
                     current_item_id=NULL,last_activity_at=?
                   WHERE session_id=? AND user_id=?""",
                (
                    int(correct), int(not correct), now,
                    session_id, user_id,
                ),
            )
            db.execute(
                """INSERT INTO user_subjects(
                     user_id,subject_id,last_studied_at
                   ) VALUES(?,?,?)
                   ON CONFLICT(user_id,subject_id) DO UPDATE SET
                     last_studied_at=excluded.last_studied_at""",
                (user_id, subject_id, now),
            )
        return True
