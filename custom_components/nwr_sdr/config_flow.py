"""Config flow for HA-NWR-SDR."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_TEST_EFFECTIVE_SEVERITY,
    CONF_TOPIC_ROOT,
    DEFAULT_TEST_EFFECTIVE_SEVERITY,
    DEFAULT_TOPIC_ROOT,
    DOMAIN,
)


def _schema(
    *,
    topic_root: str = DEFAULT_TOPIC_ROOT,
    test_effective_severity: int = DEFAULT_TEST_EFFECTIVE_SEVERITY,
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_TOPIC_ROOT, default=topic_root): str,
            vol.Optional(
                CONF_TEST_EFFECTIVE_SEVERITY, default=test_effective_severity
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=5,
                    step=1,
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
        }
    )


def _options_schema(
    *, test_effective_severity: int = DEFAULT_TEST_EFFECTIVE_SEVERITY
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_TEST_EFFECTIVE_SEVERITY, default=test_effective_severity
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=5,
                    step=1,
                    mode=selector.NumberSelectorMode.SLIDER,
                )
            ),
        }
    )


class NwrSdrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HA-NWR-SDR."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Create the integration entry."""
        if user_input is not None:
            await self.async_set_unique_id("nwr_sdr")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="HA-NWR-SDR",
                data={
                    CONF_TOPIC_ROOT: user_input[CONF_TOPIC_ROOT],
                    CONF_TEST_EFFECTIVE_SEVERITY: int(
                        user_input[CONF_TEST_EFFECTIVE_SEVERITY]
                    ),
                },
            )

        return self.async_show_form(step_id="user", data_schema=_schema())

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return NwrSdrOptionsFlow(config_entry)


class NwrSdrOptionsFlow(config_entries.OptionsFlow):
    """Handle HA-NWR-SDR options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_TEST_EFFECTIVE_SEVERITY: int(
                        user_input[CONF_TEST_EFFECTIVE_SEVERITY]
                    )
                },
            )

        test_effective_severity = self.config_entry.options.get(
            CONF_TEST_EFFECTIVE_SEVERITY,
            self.config_entry.data.get(
                CONF_TEST_EFFECTIVE_SEVERITY, DEFAULT_TEST_EFFECTIVE_SEVERITY
            ),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(
                test_effective_severity=int(test_effective_severity)
            ),
        )
