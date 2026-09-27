"""Runtime state for UNED Study."""

from __future__ import annotations

from dataclasses import dataclass

from .content.manager import ContentManager
from .content.sync import GitHubContentSynchronizer
from .database import StudyDatabase


@dataclass(slots=True)
class UNEDStudyRuntime:
    """Resources owned by one UNED Study config entry."""

    database: StudyDatabase
    content: ContentManager
    synchronizer: GitHubContentSynchronizer
