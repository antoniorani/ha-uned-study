"""UNED Study integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONTENT_DIRECTORY, DATA_DIRECTORY, DATABASE_FILENAME, DOMAIN
from .content.manager import ContentManager
from .database import StudyDatabase
from .panel import async_register_panel, async_register_static_assets, async_remove_panel
from .runtime import UNEDStudyRuntime
from .websocket import async_register_websocket_commands


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up integration-wide resources."""
    async_register_websocket_commands(hass)
    await async_register_static_assets(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UNED Study from a config entry."""
    data_dir = Path(hass.config.path(DATA_DIRECTORY))
    content_dir = data_dir / CONTENT_DIRECTORY
    database_path = data_dir / DATABASE_FILENAME

    await hass.async_add_executor_job(data_dir.mkdir, parents=True, exist_ok=True)
    await hass.async_add_executor_job(content_dir.mkdir, parents=True, exist_ok=True)

    database = StudyDatabase(database_path)
    await database.async_initialize(hass)

    content = ContentManager(content_dir)
    await content.async_reload(hass)

    runtime = UNEDStudyRuntime(database=database, content=content)
    entry.runtime_data = runtime
    hass.data[DOMAIN] = runtime

    await async_register_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a UNED Study config entry."""
    await async_remove_panel(hass)
    hass.data.pop(DOMAIN, None)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry data when its schema changes."""
    return entry.version == 1
