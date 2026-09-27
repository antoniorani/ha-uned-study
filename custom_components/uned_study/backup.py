"""Backup hooks for UNED Study."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .runtime import UNEDStudyRuntime


async def async_pre_backup(hass: HomeAssistant) -> None:
    """Checkpoint SQLite WAL before Home Assistant snapshots /config."""
    runtime = hass.data.get(DOMAIN)
    if isinstance(runtime, UNEDStudyRuntime):
        await runtime.database.async_checkpoint(hass)


async def async_post_backup(hass: HomeAssistant) -> None:
    """Resume normal operation after a backup.

    Connections are short-lived, so no explicit resume action is necessary.
    """
