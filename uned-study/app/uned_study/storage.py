"""Persistent multi-user SQLite storage for the Home Assistant app."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Any

from .scheduler import Progress, ScheduleDecision

SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class Storage:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
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
                    streak INTEGER NOT NULL DEFAULT 0,
                    mastery REAL NOT NULL DEFAULT 0,
                    difficulty REAL NOT NULL DEFAULT 0.5,
                    interval_days REAL NOT NULL DEFAULT 0,
                    last_seen_at TEXT,
                    next_review_at TEXT,
                    last_result TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, subject_id, item_id)
                );

                CREATE TABLE IF NOT EXISTS study_sessions(
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    topic_id TEXT,
                    state TEXT NOT NULL DEFAULT 'active',
                    current_item_id TEXT,
                    state_json TEXT NOT NULL DEFAULT '{}',
                    answered_count INTEGER NOT NULL DEFAULT 0,
                    correct_count INTEGER NOT NULL DEFAULT 0,
                    incorrect_count INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS review_history(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    session_id TEXT,
                    result TEXT NOT NULL,
                    answer_id TEXT,
                    rating TEXT,
                    response_ms INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS ix_progress_user_subject
                    ON item_progress(user_id, subject_id);
                CREATE INDEX IF NOT EXISTS ix_sessions_user_subject
                    ON study_sessions(user_id, subject_id, state);
                CREATE INDEX IF NOT EXISTS ix_reviews_session
                    ON review_history(session_id, id DESC);
                """
            )
            row = db.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO meta(key,value) VALUES('schema_version',?)",
                    (str(SCHEMA_VERSION),),
                )
            elif int(row["value"]) != SCHEMA_VERSION:
                raise RuntimeError(
                    f"Unsupported UNED Study database schema {row['value']}"
                )

    def checkpoint(self) -> None:
        with self._lock, self.connect() as db:
            db.execute("PRAGMA wal_checkpoint(FULL)")

    def preferences(self, user_id: str) -> dict[str, dict[str, Any]]:
        with self._lock, self.connect() as db:
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

    def set_favorite(
        self,
        user_id: str,
        subject_id: str,
        favorite: bool,
    ) -> None:
        with self._lock, self.connect() as db:
            order = None
            if favorite:
                row = db.execute(
                    """SELECT COALESCE(MAX(favorite_order),0)+1 AS next_order
                       FROM user_subjects
                       WHERE user_id=? AND favorite=1""",
                    (user_id,),
                ).fetchone()
                order = int(row["next_order"])

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
                         ELSE NULL
                       END""",
                (user_id, subject_id, int(favorite), order),
            )

    def progress_map(
        self,
        user_id: str,
        subject_id: str,
    ) -> dict[str, Progress]:
        with self._lock, self.connect() as db:
            rows = db.execute(
                """SELECT * FROM item_progress
                   WHERE user_id=? AND subject_id=?""",
                (user_id, subject_id),
            ).fetchall()

        return {
            row["item_id"]: Progress(
                item_id=row["item_id"],
                times_seen=row["times_seen"],
                correct_count=row["correct_count"],
                incorrect_count=row["incorrect_count"],
                streak=row["streak"],
                mastery=float(row["mastery"]),
                difficulty=float(row["difficulty"]),
                interval_days=float(row["interval_days"]),
                last_seen_at=_dt(row["last_seen_at"]),
                next_review_at=_dt(row["next_review_at"]),
            )
            for row in rows
        }

    def recent_item_ids(
        self,
        user_id: str,
        subject_id: str,
        limit: int = 10,
    ) -> set[str]:
        with self._lock, self.connect() as db:
            rows = db.execute(
                """SELECT item_id FROM review_history
                   WHERE user_id=? AND subject_id=?
                   ORDER BY id DESC LIMIT ?""",
                (user_id, subject_id, limit),
            ).fetchall()
        return {row["item_id"] for row in rows}

    def active_session(
        self,
        user_id: str,
        subject_id: str,
    ) -> dict[str, Any] | None:
        with self._lock, self.connect() as db:
            row = db.execute(
                """SELECT * FROM study_sessions
                   WHERE user_id=? AND subject_id=? AND state='active'
                   ORDER BY updated_at DESC LIMIT 1""",
                (user_id, subject_id),
            ).fetchone()
        return self._session_dict(row) if row else None

    def get_session(
        self,
        user_id: str,
        session_id: str,
    ) -> dict[str, Any] | None:
        with self._lock, self.connect() as db:
            row = db.execute(
                """SELECT * FROM study_sessions
                   WHERE user_id=? AND session_id=?""",
                (user_id, session_id),
            ).fetchone()
        return self._session_dict(row) if row else None

    @staticmethod
    def _session_dict(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        try:
            value["data"] = json.loads(value.pop("state_json"))
        except json.JSONDecodeError:
            value["data"] = {}
        return value

    def create_session(
        self,
        *,
        session_id: str,
        user_id: str,
        subject_id: str,
        kind: str,
        topic_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _now()
        with self._lock, self.connect() as db:
            db.execute(
                """UPDATE study_sessions
                   SET state='paused',updated_at=?
                   WHERE user_id=? AND subject_id=? AND state='active'""",
                (now, user_id, subject_id),
            )
            db.execute(
                """INSERT INTO study_sessions(
                       session_id,user_id,subject_id,kind,topic_id,state,
                       current_item_id,state_json,started_at,updated_at
                   ) VALUES(?,?,?,?,?,'active',NULL,?,?,?)""",
                (
                    session_id,
                    user_id,
                    subject_id,
                    kind,
                    topic_id,
                    json.dumps(data or {}),
                    now,
                    now,
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
        session = self.get_session(user_id, session_id)
        assert session is not None
        return session

    def set_current_item(
        self,
        user_id: str,
        session_id: str,
        item_id: str | None,
    ) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                """UPDATE study_sessions
                   SET current_item_id=?,updated_at=?
                   WHERE user_id=? AND session_id=?""",
                (item_id, _now(), user_id, session_id),
            )

    def update_session_data(
        self,
        user_id: str,
        session_id: str,
        data: dict[str, Any],
    ) -> None:
        with self._lock, self.connect() as db:
            db.execute(
                """UPDATE study_sessions
                   SET state_json=?,updated_at=?
                   WHERE user_id=? AND session_id=?""",
                (
                    json.dumps(data),
                    _now(),
                    user_id,
                    session_id,
                ),
            )

    def complete_session(
        self,
        user_id: str,
        session_id: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> None:
        with self._lock, self.connect() as db:
            if data is None:
                db.execute(
                    """UPDATE study_sessions
                       SET state='completed',current_item_id=NULL,updated_at=?
                       WHERE user_id=? AND session_id=?""",
                    (_now(), user_id, session_id),
                )
            else:
                db.execute(
                    """UPDATE study_sessions
                       SET state='completed',current_item_id=NULL,
                           state_json=?,updated_at=?
                       WHERE user_id=? AND session_id=?""",
                    (
                        json.dumps(data),
                        _now(),
                        user_id,
                        session_id,
                    ),
                )

    def review_request(
        self,
        user_id: str,
        request_id: str,
    ) -> dict[str, Any] | None:
        with self._lock, self.connect() as db:
            row = db.execute(
                """SELECT request_id,user_id,subject_id,item_id,session_id,
                          result,answer_id,rating,response_ms,created_at
                   FROM review_history
                   WHERE user_id=? AND request_id=?""",
                (user_id, request_id),
            ).fetchone()
        return dict(row) if row else None

    def record_review(
        self,
        *,
        request_id: str,
        user_id: str,
        subject_id: str,
        item_id: str,
        session_id: str,
        result: str,
        answer_id: str | None,
        rating: str | None,
        response_ms: int | None,
        decision: ScheduleDecision,
    ) -> bool:
        now = _now()
        correct = result == "correct"

        with self._lock, self.connect() as db:
            existing = db.execute(
                "SELECT 1 FROM review_history WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if existing:
                return False

            previous = db.execute(
                """SELECT times_seen,correct_count,incorrect_count,streak
                   FROM item_progress
                   WHERE user_id=? AND subject_id=? AND item_id=?""",
                (user_id, subject_id, item_id),
            ).fetchone()

            seen = (previous["times_seen"] if previous else 0) + 1
            good = (previous["correct_count"] if previous else 0) + int(correct)
            bad = (previous["incorrect_count"] if previous else 0) + int(not correct)
            streak = (
                (previous["streak"] if previous else 0) + 1
                if correct
                else 0
            )

            db.execute(
                """INSERT INTO item_progress(
                       user_id,subject_id,item_id,times_seen,correct_count,
                       incorrect_count,streak,mastery,difficulty,
                       interval_days,last_seen_at,next_review_at,last_result,
                       updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(user_id,subject_id,item_id) DO UPDATE SET
                       times_seen=excluded.times_seen,
                       correct_count=excluded.correct_count,
                       incorrect_count=excluded.incorrect_count,
                       streak=excluded.streak,
                       mastery=excluded.mastery,
                       difficulty=excluded.difficulty,
                       interval_days=excluded.interval_days,
                       last_seen_at=excluded.last_seen_at,
                       next_review_at=excluded.next_review_at,
                       last_result=excluded.last_result,
                       updated_at=excluded.updated_at""",
                (
                    user_id,
                    subject_id,
                    item_id,
                    seen,
                    good,
                    bad,
                    streak,
                    decision.mastery,
                    decision.difficulty,
                    decision.interval_days,
                    now,
                    decision.next_review_at.isoformat(),
                    result,
                    now,
                ),
            )

            db.execute(
                """INSERT INTO review_history(
                       request_id,user_id,subject_id,item_id,session_id,
                       result,answer_id,rating,response_ms,created_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    request_id,
                    user_id,
                    subject_id,
                    item_id,
                    session_id,
                    result,
                    answer_id,
                    rating,
                    response_ms,
                    now,
                ),
            )

            db.execute(
                """UPDATE study_sessions SET
                       answered_count=answered_count+1,
                       correct_count=correct_count+?,
                       incorrect_count=incorrect_count+?,
                       current_item_id=NULL,
                       updated_at=?
                   WHERE user_id=? AND session_id=?""",
                (
                    int(correct),
                    int(not correct),
                    now,
                    user_id,
                    session_id,
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
