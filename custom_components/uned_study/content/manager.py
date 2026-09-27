"""Content manager for active subject data."""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant

from .loader import scan_subjects
from .models import Subject


class ContentManager:
    """Keep the validated content snapshot currently active in Home Assistant."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._subjects: dict[str, Subject] = {}
        self._errors: dict[str, str] = {}

    @property
    def subjects(self) -> dict[str, Subject]:
        return self._subjects

    @property
    def errors(self) -> dict[str, str]:
        return self._errors

    async def async_reload(self, hass: HomeAssistant) -> None:
        """Atomically replace the active content snapshot after a filesystem scan."""
        subjects, errors = await hass.async_add_executor_job(scan_subjects, self.root)
        self._subjects = subjects
        self._errors = errors

    def get_subject(self, subject_id: str) -> Subject | None:
        return self._subjects.get(subject_id)
