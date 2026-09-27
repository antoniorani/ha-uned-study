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
from .content.sync import parse_github_repository


def _content_schema(
    repository: str,
    branch: str,
) -> probatio.Schema:
    """Build the content source form schema."""
    return probatio.Schema(
        {
            probatio.Required(
                CONF_CONTENT_REPOSITORY,
                default=repository,
            ): str,
            probatio.Required(
                CONF_CONTENT_BRANCH,
                default=branch,
            ): str,
        }
    )


def _validate_content_source(
    user_input: dict[str, Any],
) -> dict[str, str]:
    """Validate content repository and branch fields."""
    errors: dict[str, str] = {}
    try:
        parse_github_repository(
            user_input[CONF_CONTENT_REPOSITORY]
        )
    except ValueError:
        errors["base"] = "invalid_repository"

    if not user_input[CONF_CONTENT_BRANCH].strip():
        errors["base"] = "invalid_branch"
    return errors


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

        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_content_source(user_input)
            if not errors:
                user_input[CONF_CONTENT_BRANCH] = (
                    user_input[CONF_CONTENT_BRANCH].strip()
                )
                return self.async_create_entry(
                    title=NAME,
                    data=user_input,
                )

        schema = _content_schema(
            (
                user_input.get(
                    CONF_CONTENT_REPOSITORY,
                    DEFAULT_CONTENT_REPOSITORY,
                )
                if user_input
                else DEFAULT_CONTENT_REPOSITORY
            ),
            (
                user_input.get(
                    CONF_CONTENT_BRANCH,
                    DEFAULT_CONTENT_BRANCH,
                )
                if user_input
                else DEFAULT_CONTENT_BRANCH
            ),
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Change the GitHub content source without losing local progress."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_content_source(user_input)
            if not errors:
                user_input[CONF_CONTENT_BRANCH] = (
                    user_input[CONF_CONTENT_BRANCH].strip()
                )
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_CONTENT_REPOSITORY:
                            user_input[CONF_CONTENT_REPOSITORY],
                        CONF_CONTENT_BRANCH:
                            user_input[CONF_CONTENT_BRANCH],
                    },
                    reload_even_if_entry_is_unchanged=False,
                )

        schema = _content_schema(
            (
                user_input.get(
                    CONF_CONTENT_REPOSITORY,
                    entry.data[CONF_CONTENT_REPOSITORY],
                )
                if user_input
                else entry.data[CONF_CONTENT_REPOSITORY]
            ),
            (
                user_input.get(
                    CONF_CONTENT_BRANCH,
                    entry.data[CONF_CONTENT_BRANCH],
                )
                if user_input
                else entry.data[CONF_CONTENT_BRANCH]
            ),
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )
