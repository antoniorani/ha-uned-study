"""Administrator WebSocket API for content synchronization."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, WS_PREFIX
from .content.sync import ContentSyncError
from .runtime import UNEDStudyRuntime


def _runtime(hass: HomeAssistant) -> UNEDStudyRuntime | None:
    runtime = hass.data.get(DOMAIN)
    return runtime if isinstance(runtime, UNEDStudyRuntime) else None


@callback
def async_register_content_sync_commands(hass: HomeAssistant) -> None:
    """Register content administration WebSocket commands."""
    websocket_api.async_register_command(hass, ws_content_status)
    websocket_api.async_register_command(hass, ws_sync_content)


@websocket_api.websocket_command(
    {vol.Required("type"): f"{WS_PREFIX}/content_status"}
)
@websocket_api.ws_require_user()
def ws_content_status(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return source status without exposing mutable user data."""
    runtime = _runtime(hass)
    if runtime is None:
        connection.send_error(
            msg["id"], "not_loaded", "UNED Study is not loaded"
        )
        return

    connection.send_result(
        msg["id"],
        {
            "source": runtime.synchronizer.source,
            "subject_count": len(runtime.content.subjects),
            "content_errors": (
                runtime.content.errors if connection.user.is_admin else {}
            ),
        },
    )


@websocket_api.websocket_command(
    {vol.Required("type"): f"{WS_PREFIX}/sync_content"}
)
@websocket_api.ws_require_user()
@websocket_api.async_response
async def ws_sync_content(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Download, validate and atomically activate content."""
    runtime = _runtime(hass)
    if runtime is None:
        connection.send_error(
            msg["id"], "not_loaded", "UNED Study is not loaded"
        )
        return
    if not connection.user.is_admin:
        connection.send_error(
            msg["id"], "unauthorized", "Administrator required"
        )
        return

    try:
        report = await runtime.synchronizer.async_sync(hass)
        await runtime.content.async_reload(hass)
    except ContentSyncError as exc:
        connection.send_error(
            msg["id"], "content_sync_failed", str(exc)
        )
        return

    connection.send_result(
        msg["id"],
        {
            "ok": True,
            "report": report.as_dict(),
            "content_errors": runtime.content.errors,
        },
    )
