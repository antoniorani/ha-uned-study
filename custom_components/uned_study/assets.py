"""Authenticated HTTP endpoint for subject assets."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path, PurePosixPath
import re

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

_ASSET_SUBJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
MAX_SERVED_ASSET_BYTES = 30 * 1024 * 1024
SAFE_ASSET_TYPES = {
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}


class UNEDStudyAssetView(HomeAssistantView):
    """Serve cached subject assets only to authenticated Home Assistant users."""

    url = "/api/uned_study/assets/{subject_id}/{asset_path:.+}"
    name = "api:uned_study:asset"
    requires_auth = True

    def __init__(self, hass: HomeAssistant, content_dir: Path) -> None:
        self._hass = hass
        self._content_dir = content_dir

    async def get(
        self,
        request: web.Request,
        subject_id: str,
        asset_path: str,
    ) -> web.Response:
        """Return one asset from a subject's assets directory."""
        if not _ASSET_SUBJECT_RE.fullmatch(subject_id):
            raise web.HTTPNotFound

        relative = PurePosixPath(asset_path)
        if (
            relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
            or "." in relative.parts
        ):
            raise web.HTTPNotFound

        root = self._content_dir / subject_id / "assets"
        requested = root.joinpath(*relative.parts)

        result = await self._hass.async_add_executor_job(
            self._read_safe_asset,
            root,
            requested,
        )
        if result is None:
            raise web.HTTPNotFound

        body, content_type = result
        return web.Response(
            status=HTTPStatus.OK,
            body=body,
            content_type=content_type,
            headers={
                "Cache-Control": "private, max-age=3600",
                "Content-Security-Policy": (
                    "sandbox; default-src 'none'; "
                    "img-src data:; style-src 'unsafe-inline'"
                ),
                "Cross-Origin-Resource-Policy": "same-origin",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @staticmethod
    def _read_safe_asset(
        root: Path,
        requested: Path,
    ) -> tuple[bytes, str] | None:
        """Resolve symlinks and read only a regular file below assets/."""
        try:
            resolved_root = root.resolve(strict=True)
            resolved = requested.resolve(strict=True)
        except OSError:
            return None

        if not resolved.is_relative_to(resolved_root):
            return None
        if not resolved.is_file():
            return None

        try:
            size = resolved.stat().st_size
        except OSError:
            return None
        if size < 0 or size > MAX_SERVED_ASSET_BYTES:
            return None

        try:
            body = resolved.read_bytes()
        except OSError:
            return None

        content_type = SAFE_ASSET_TYPES.get(resolved.suffix.lower())
        if content_type is None:
            return None
        return body, content_type


def async_register_asset_view(
    hass: HomeAssistant,
    content_dir: Path,
) -> None:
    """Register the authenticated asset endpoint once at integration setup."""
    hass.http.register_view(UNEDStudyAssetView(hass, content_dir))
