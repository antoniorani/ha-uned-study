"""Filesystem content loader."""

from __future__ import annotations

import json
from pathlib import Path

from .models import Subject
from .validator import ContentValidationError, parse_subject


def load_subject_file(path: Path) -> Subject:
    """Load and validate one subject.json file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContentValidationError(f"cannot read valid JSON from {path}: {exc}") from exc
    return parse_subject(raw, directory_name=path.parent.name)


def scan_subjects(root: Path) -> tuple[dict[str, Subject], dict[str, str]]:
    """Scan the content root and return valid subjects plus per-folder errors."""
    subjects: dict[str, Subject] = {}
    errors: dict[str, str] = {}
    if not root.exists():
        return subjects, errors

    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        subject_path = directory / "subject.json"
        if not subject_path.exists():
            continue
        try:
            subject = load_subject_file(subject_path)
        except ContentValidationError as exc:
            errors[directory.name] = str(exc)
            continue
        subjects[subject.id] = subject
    return subjects, errors
