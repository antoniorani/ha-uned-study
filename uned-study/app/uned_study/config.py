"""Runtime configuration read from the Home Assistant app data volume."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from urllib.parse import urlparse

DATA_DIR = Path(os.environ.get("UNED_STUDY_DATA", "/data"))
OPTIONS_PATH = DATA_DIR / "options.json"


@dataclass(frozen=True, slots=True)
class AppConfig:
    content_repository: str
    content_branch: str
    sync_interval_hours: int
    dev_mode: bool = False


def _valid_github_repository(value: str) -> bool:
    parsed = urlparse(value)
    parts = [part for part in parsed.path.split("/") if part]
    return (
        parsed.scheme == "https"
        and parsed.hostname in {"github.com", "www.github.com"}
        and len(parts) == 2
    )


def load_config() -> AppConfig:
    data: dict[str, object] = {}
    try:
        data = json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    repository = str(
        data.get(
            "content_repository",
            "https://github.com/antoniorani/uned-study-content",
        )
    ).strip()
    if not _valid_github_repository(repository):
        raise ValueError("content_repository must be a public github.com repository")

    branch = str(data.get("content_branch", "main")).strip()
    if not branch:
        raise ValueError("content_branch cannot be empty")

    interval = int(data.get("sync_interval_hours", 6))
    interval = max(1, min(interval, 168))

    return AppConfig(
        content_repository=repository,
        content_branch=branch,
        sync_interval_hours=interval,
        dev_mode=os.environ.get("UNED_STUDY_DEV") == "1",
    )
