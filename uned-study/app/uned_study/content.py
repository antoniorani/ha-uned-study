"""Content validation, local cache and atomic GitHub synchronization."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
from urllib.parse import quote, urlparse

from aiohttp import ClientSession, ClientTimeout

from .models import AnswerOption, StudyItem, Subject, Topic

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_EXPANDED_BYTES = 300 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 30 * 1024 * 1024
SAFE_ASSET_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}


class ContentError(ValueError):
    """Raised when content cannot be safely used."""


def _required_str(data: Mapping[str, object], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContentError(f"{context}.{key} must be a non-empty string")
    return value.strip()


def _optional_str(data: Mapping[str, object], key: str) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ContentError(f"{key} must be a string")
    return value


def _string_tuple(value: object, context: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ContentError(f"{context} must be a list of strings")
    return tuple(value)


def parse_subject(data: object, *, directory_name: str) -> Subject:
    if not isinstance(data, Mapping):
        raise ContentError("subject document must be an object")
    if data.get("schema_version") != 1:
        raise ContentError("schema_version must be 1")

    subject_id = _required_str(data, "id", "subject")
    if subject_id != directory_name:
        raise ContentError(
            f"subject id {subject_id!r} does not match folder {directory_name!r}"
        )

    subject_type = _required_str(data, "type", "subject")
    if subject_type not in {"test", "flashcards"}:
        raise ContentError("subject.type must be test or flashcards")

    raw_topics = data.get("topics")
    if not isinstance(raw_topics, list) or not raw_topics:
        raise ContentError("subject.topics must be a non-empty list")

    topics: list[Topic] = []
    topic_ids: set[str] = set()
    for index, raw in enumerate(raw_topics):
        if not isinstance(raw, Mapping):
            raise ContentError(f"topics[{index}] must be an object")
        topic_id = _required_str(raw, "id", f"topics[{index}]")
        if topic_id in topic_ids:
            raise ContentError(f"duplicate topic id {topic_id!r}")
        topic_ids.add(topic_id)
        topics.append(
            Topic(
                id=topic_id,
                title=_required_str(raw, "title", f"topics[{index}]"),
            )
        )

    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raise ContentError("subject.items must be a list")

    seen_ids: set[str] = set()
    items: list[StudyItem] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, Mapping):
            raise ContentError(f"items[{index}] must be an object")
        context = f"items[{index}]"
        item_id = _required_str(raw, "id", context)
        if item_id in seen_ids:
            raise ContentError(f"duplicate item id {item_id!r}")
        seen_ids.add(item_id)

        topic = _required_str(raw, "topic", context)
        if topic not in topic_ids:
            raise ContentError(f"{context}.topic references unknown topic {topic!r}")

        importance = raw.get("importance", 3)
        if (
            not isinstance(importance, int)
            or isinstance(importance, bool)
            or not 1 <= importance <= 5
        ):
            raise ContentError(f"{context}.importance must be from 1 to 5")

        common = dict(
            id=item_id,
            topic=topic,
            importance=importance,
            tags=_string_tuple(raw.get("tags"), f"{context}.tags"),
            exam_history=_string_tuple(
                raw.get("exam_history"),
                f"{context}.exam_history",
            ),
            source=dict(raw["source"]) if isinstance(raw.get("source"), Mapping) else None,
        )

        if subject_type == "test":
            raw_answers = raw.get("answers")
            if not isinstance(raw_answers, list) or len(raw_answers) < 2:
                raise ContentError(f"{context}.answers must contain at least two options")
            answers: list[AnswerOption] = []
            answer_ids: set[str] = set()
            for answer_index, answer in enumerate(raw_answers):
                if not isinstance(answer, Mapping):
                    raise ContentError(
                        f"{context}.answers[{answer_index}] must be an object"
                    )
                answer_id = _required_str(
                    answer,
                    "id",
                    f"{context}.answers[{answer_index}]",
                )
                if answer_id in answer_ids:
                    raise ContentError(f"duplicate answer id {answer_id!r}")
                answer_ids.add(answer_id)
                answers.append(
                    AnswerOption(
                        id=answer_id,
                        text_md=_required_str(
                            answer,
                            "text_md",
                            f"{context}.answers[{answer_index}]",
                        ),
                    )
                )
            correct = _required_str(raw, "correct_answer", context)
            if correct not in answer_ids:
                raise ContentError(f"{context}.correct_answer is not an answer id")
            items.append(
                StudyItem(
                    **common,
                    item_type="mcq",
                    question_md=_required_str(raw, "question_md", context),
                    answers=tuple(answers),
                    correct_answer=correct,
                    explanation_md=_optional_str(raw, "explanation_md"),
                )
            )
        else:
            items.append(
                StudyItem(
                    **common,
                    item_type="flashcard",
                    front_md=_required_str(raw, "front_md", context),
                    back_md=_required_str(raw, "back_md", context),
                    hint_md=_optional_str(raw, "hint_md"),
                    mnemonic_md=_optional_str(raw, "mnemonic_md"),
                )
            )

    exam = data.get("exam", {})
    if not isinstance(exam, Mapping):
        raise ContentError("subject.exam must be an object")

    degree = data.get("degree")
    if degree is not None and not isinstance(degree, str):
        raise ContentError("subject.degree must be a string")
    course = data.get("course")
    if course is not None and (
        not isinstance(course, int) or isinstance(course, bool) or course < 1
    ):
        raise ContentError("subject.course must be a positive integer")

    return Subject(
        schema_version=1,
        id=subject_id,
        title=_required_str(data, "title", "subject"),
        subject_type=subject_type,
        content_version=_required_str(data, "content_version", "subject"),
        topics=tuple(topics),
        items=tuple(items),
        degree=degree,
        course=course,
        exam=dict(exam),
    )


def _load_subject(path: Path) -> Subject:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContentError(f"cannot read {path.name}: {exc}") from exc
    return parse_subject(raw, directory_name=path.parent.name)


def scan_subjects(root: Path) -> tuple[dict[str, Subject], dict[str, str]]:
    subjects: dict[str, Subject] = {}
    errors: dict[str, str] = {}
    if not root.exists():
        return subjects, errors

    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        path = directory / "subject.json"
        if not path.is_file():
            continue
        try:
            subject = _load_subject(path)
        except ContentError as exc:
            errors[directory.name] = str(exc)
            continue
        subjects[subject.id] = subject
    return subjects, errors


def _repo_coordinates(repository: str) -> tuple[str, str]:
    parsed = urlparse(repository)
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"github.com", "www.github.com"}
        or len(parts) != 2
    ):
        raise ContentError("only public github.com repositories are supported")
    return parts[0], parts[1].removesuffix(".git")


class ContentManager:
    def __init__(
        self,
        *,
        data_dir: Path,
        repository: str,
        branch: str,
    ) -> None:
        self.data_dir = data_dir
        self.content_dir = data_dir / "content"
        self.repository = repository
        self.branch = branch
        self.state_path = data_dir / "content-sync-state.json"
        self.subjects: dict[str, Subject] = {}
        self.errors: dict[str, str] = {}
        self.last_sync: str | None = None
        self.last_error: str | None = None
        self._sync_lock = asyncio.Lock()

    async def load(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.content_dir.mkdir(parents=True, exist_ok=True)
        self.subjects, self.errors = await asyncio.to_thread(
            scan_subjects,
            self.content_dir,
        )
        await asyncio.to_thread(self._load_state)

    def _load_state(self) -> None:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(value, dict):
            return
        self.last_sync = value.get("last_sync") if isinstance(value.get("last_sync"), str) else None
        self.last_error = value.get("last_error") if isinstance(value.get("last_error"), str) else None

    def _save_state(self) -> None:
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(
                {
                    "repository": self.repository,
                    "branch": self.branch,
                    "last_sync": self.last_sync,
                    "last_error": self.last_error,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temp, self.state_path)

    async def sync(self) -> bool:
        async with self._sync_lock:
            owner, name = _repo_coordinates(self.repository)
            ref = quote(self.branch, safe="")
            url = f"https://codeload.github.com/{owner}/{name}/tar.gz/{ref}"

            try:
                timeout = ClientTimeout(total=90)
                async with ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            raise ContentError(
                                f"GitHub returned HTTP {response.status}"
                            )
                        if (
                            response.content_length is not None
                            and response.content_length > MAX_ARCHIVE_BYTES
                        ):
                            raise ContentError("content archive is too large")
                        archive = await response.read()
                if not archive:
                    raise ContentError("GitHub returned an empty archive")
                if len(archive) > MAX_ARCHIVE_BYTES:
                    raise ContentError("content archive is too large")

                subjects = await asyncio.to_thread(
                    self._install_archive,
                    archive,
                )
            except Exception as exc:
                self.last_error = str(exc)
                await asyncio.to_thread(self._save_state)
                return False

            self.subjects = subjects
            self.errors = {}
            self.last_sync = datetime.now(timezone.utc).isoformat()
            self.last_error = None
            await asyncio.to_thread(self._save_state)
            return True

    def _install_archive(self, archive: bytes) -> dict[str, Subject]:
        staging_parent = Path(
            tempfile.mkdtemp(prefix=".content-staging-", dir=self.data_dir)
        )
        staged = staging_parent / "content"
        staged.mkdir()
        backup = self.data_dir / ".content-backup"
        active_moved = False

        try:
            self._extract(archive, staged)
            subjects, errors = scan_subjects(staged)
            if errors:
                detail = "; ".join(f"{key}: {value}" for key, value in errors.items())
                raise ContentError(f"downloaded content is invalid: {detail}")
            if not subjects:
                raise ContentError("downloaded repository contains no valid subjects")

            if backup.exists():
                shutil.rmtree(backup)
            if self.content_dir.exists():
                os.replace(self.content_dir, backup)
                active_moved = True

            try:
                os.replace(staged, self.content_dir)
            except Exception:
                if active_moved and backup.exists():
                    os.replace(backup, self.content_dir)
                    active_moved = False
                raise

            active_moved = False
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
            return subjects
        finally:
            if active_moved and not self.content_dir.exists() and backup.exists():
                os.replace(backup, self.content_dir)
            shutil.rmtree(staging_parent, ignore_errors=True)

    def _extract(self, archive: bytes, destination: Path) -> None:
        expanded = 0
        entries = 0
        seen: set[PurePosixPath] = set()
        found_subject = False

        with tarfile.open(fileobj=BytesIO(archive), mode="r:gz") as tar:
            for member in tar:
                entries += 1
                if entries > 20_000:
                    raise ContentError("content archive contains too many entries")
                if not member.isfile():
                    continue
                if member.size < 0 or member.size > MAX_SINGLE_FILE_BYTES:
                    raise ContentError(f"archive member is too large: {member.name}")

                parts = PurePosixPath(member.name).parts
                try:
                    index = parts.index("subjects")
                except ValueError:
                    continue
                relative_parts = parts[index + 1 :]
                if len(relative_parts) < 2:
                    continue

                relative = PurePosixPath(*relative_parts)
                if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
                    raise ContentError(f"unsafe archive path: {member.name}")
                if relative in seen:
                    raise ContentError(f"duplicate archive path: {relative}")
                seen.add(relative)

                expanded += member.size
                if expanded > MAX_EXPANDED_BYTES:
                    raise ContentError("expanded content is too large")

                target = destination.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    raise ContentError(f"cannot read archive member: {member.name}")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)

                if target.name == "subject.json":
                    found_subject = True

        if not found_subject:
            raise ContentError("archive contains no subjects/*/subject.json")

    def asset_path(self, subject_id: str, asset_path: str) -> Path | None:
        relative = PurePosixPath(asset_path)
        if (
            relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
            or "." in relative.parts
            or relative.suffix.lower() not in SAFE_ASSET_SUFFIXES
        ):
            return None

        root = self.content_dir / subject_id / "assets"
        requested = root.joinpath(*relative.parts)
        try:
            resolved_root = root.resolve(strict=True)
            resolved = requested.resolve(strict=True)
        except OSError:
            return None
        if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
            return None
        if resolved.stat().st_size > MAX_SINGLE_FILE_BYTES:
            return None
        return resolved
