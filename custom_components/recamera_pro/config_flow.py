"""Config flow for reCamera Pro."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PORT

from .const import (
    CONF_DEVICE_NAME,
    CONF_DEVICE_PASSWORD,
    CONF_DEVICE_USERNAME,
    CONF_HOST,
    DEFAULT_BROKER_HOST,
    DEFAULT_BROKER_PORT,
    DEFAULT_EVENT_TOPIC,
    DOMAIN,
)
from .device_api import RecameraAuthenticationError, async_validate_device

CONF_BROKER = "broker"
CONF_TOPIC_IN = "topic_in"


class RecameraProConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create reCamera Pro device entries."""

    VERSION = 1

    async def async_step_import(self, import_config):
        """Import the existing configuration.yaml settings."""
        existing_entries = self.hass.config_entries.async_entries(DOMAIN)
        if existing_entries:
            existing = existing_entries[0]
            self.hass.config_entries.async_update_entry(
                existing,
                data={**dict(import_config), **existing.data},
            )
            return self.async_abort(reason="already_configured")
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured(updates=dict(import_config))
        return self.async_create_entry(title="reCamera Pro", data=dict(import_config))

    async def async_step_user(self, user_input=None):
        """Allow setup from Settings > Devices & services."""
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip().lower()
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            try:
                await async_validate_device(
                    host,
                    user_input[CONF_DEVICE_USERNAME],
                    user_input[CONF_DEVICE_PASSWORD],
                )
            except RecameraAuthenticationError:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                data = {
                    **user_input,
                    CONF_HOST: host,
                    CONF_BROKER: DEFAULT_BROKER_HOST,
                    CONF_PORT: DEFAULT_BROKER_PORT,
                    CONF_TOPIC_IN: DEFAULT_EVENT_TOPIC,
                }
                return self.async_create_entry(
                    title=user_input[CONF_DEVICE_NAME], data=data
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_NAME, default="reCamera Pro"): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_DEVICE_USERNAME, default="admin"): str,
                vol.Optional(CONF_DEVICE_PASSWORD, default=""): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )
