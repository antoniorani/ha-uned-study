"""Home Assistant sidebar panel registration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel as ha_async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import (
    PANEL_ELEMENT_NAME,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL_PATH,
    STATIC_URL_PATH,
    VERSION,
)


async def async_register_static_assets(hass: HomeAssistant) -> None:
    """Serve bundled frontend files through Home Assistant."""
    frontend_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL_PATH, str(frontend_dir), False)]
    )


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register the sidebar panel if it is not already present."""
    if PANEL_URL_PATH in hass.data.get("frontend_panels", {}):
        return
    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_URL_PATH,
        config={
            "_panel_custom": {
                "name": PANEL_ELEMENT_NAME,
                "embed_iframe": False,
                "trust_external": False,
                "js_url": f"{STATIC_URL_PATH}/uned-study.js?v={VERSION}",
            }
        },
        require_admin=False,
    )


async def async_remove_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar panel during a config-entry unload."""
    if PANEL_URL_PATH in hass.data.get("frontend_panels", {}):
        ha_async_remove_panel(hass, PANEL_URL_PATH)
