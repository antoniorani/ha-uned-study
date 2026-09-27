"""Config flow for UNED Study."""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import (
    CONF_CONTENT_BRANCH,
    CONF_CONTENT_REPOSITORY,
    DEFAULT_CONTENT_BRANCH,
    DEFAULT_CONTENT_REPOSITORY,
    DOMAIN,
    NAME,
)


class UNEDStudyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UNED Study config flow."""

    VERSION = 1
    MINOR_VERSION = 0

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the single UNED Study config entry."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title=NAME, data=user_input)

        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_CONTENT_REPOSITORY,
                    default=DEFAULT_CONTENT_REPOSITORY,
                ): str,
                probatio.Required(
                    CONF_CONTENT_BRANCH,
                    default=DEFAULT_CONTENT_BRANCH,
                ): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)
