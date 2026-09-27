"""UNED Study integration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .assets import async_register_asset_view
from .const import (
    CONF_CONTENT_BRANCH,
    CONF_CONTENT_REPOSITORY,
    CONTENT_DIRECTORY,
    DATA_DIRECTORY,
    DATABASE_FILENAME,
    DOMAIN,
)
from .content.manager import ContentManager
from .content.sync import ContentSyncError, GitHubContentSynchronizer
from .database import StudyDatabase
from .panel import (
    async_register_panel,
    async_register_static_assets,
    async_remove_panel,
)
from .runtime import UNEDStudyRuntime
from .sync_api import async_register_content_sync_commands
from .websocket import async_register_websocket_commands

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up integration-wide resources."""
    content_dir = (
        Path(hass.config.path(DATA_DIRECTORY)) / CONTENT_DIRECTORY
    )
    async_register_websocket_commands(hass)
    async_register_content_sync_commands(hass)
    async_register_asset_view(hass, content_dir)
    await async_register_static_assets(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up UNED Study from a config entry."""
    data_dir = Path(hass.config.path(DATA_DIRECTORY))
    content_dir = data_dir / CONTENT_DIRECTORY
    database_path = data_dir / DATABASE_FILENAME

    await hass.async_add_executor_job(
        data_dir.mkdir, parents=True, exist_ok=True
    )
    await hass.async_add_executor_job(
        content_dir.mkdir, parents=True, exist_ok=True
    )

    database = StudyDatabase(database_path)
    await database.async_initialize(hass)

    content = ContentManager(content_dir)
    await content.async_reload(hass)

    synchronizer = GitHubContentSynchronizer(
        data_dir=data_dir,
        content_dir=content_dir,
        repository=entry.data[CONF_CONTENT_REPOSITORY],
        branch=entry.data[CONF_CONTENT_BRANCH],
    )

    runtime = UNEDStudyRuntime(
        database=database,
        content=content,
        synchronizer=synchronizer,
    )
    entry.runtime_data = runtime
    hass.data[DOMAIN] = runtime

    # An empty local cache may be bootstrapped from the configured repository.
    # Failure is non-fatal: the integration remains usable and an administrator
    # can retry synchronization from the panel later.
    if not content.subjects:
        try:
            await synchronizer.async_sync(hass)
        except ContentSyncError as exc:
            _LOGGER.info(
                "Initial content synchronization unavailable: %s", exc
            )
        else:
            await content.async_reload(hass)

    await async_register_panel(hass)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Unload a UNED Study config entry."""
    await async_remove_panel(hass)
    hass.data.pop(DOMAIN, None)
    return True


async def async_migrate_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Migrate config entry data when its schema changes."""
    return entry.version == 1
