"""Config Flow and Options Flow for MeterSnap."""
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_API_KEY,
    CONF_CUSTOM_ENDPOINT,
    CONF_CUSTOM_MODEL,
    CONF_ELEC_BASE_PRICE,
    CONF_ELEC_ENABLED,
    CONF_ELEC_MONTHLY_PAYMENT,
    CONF_ELEC_UNIT_PRICE,
    CONF_GAS_BASE_PRICE,
    CONF_GAS_CALORIFIC_VALUE,
    CONF_GAS_CONVERSION_FACTOR,
    CONF_GAS_ENABLED,
    CONF_GAS_MONTHLY_PAYMENT,
    CONF_GAS_UNIT_PRICE,
    CONF_OCR_PROVIDER,
    DEFAULT_CUSTOM_MODEL,
    DEFAULT_ELEC_BASE_PRICE,
    DEFAULT_ELEC_MONTHLY_PAYMENT,
    DEFAULT_ELEC_UNIT_PRICE,
    DEFAULT_GAS_BASE_PRICE,
    DEFAULT_GAS_CALORIFIC_VALUE,
    DEFAULT_GAS_CONVERSION_FACTOR,
    DEFAULT_GAS_MONTHLY_PAYMENT,
    DEFAULT_GAS_UNIT_PRICE,
    DOMAIN,
    NAME,
    OCR_PROVIDERS,
    PROVIDER_GEMINI,
)


class MeterSnapConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MeterSnap."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 1: General and AI settings."""
        # Only allow single instance
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_electricity()

        schema = vol.Schema(
            {
                vol.Required(CONF_OCR_PROVIDER, default=PROVIDER_GEMINI): vol.In(OCR_PROVIDERS),
                vol.Optional(CONF_API_KEY, default=""): cv.string,
                vol.Optional(CONF_CUSTOM_ENDPOINT, default=""): cv.string,
                vol.Optional(CONF_CUSTOM_MODEL, default=DEFAULT_CUSTOM_MODEL): cv.string,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_electricity(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 2: Electricity tariff settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_gas()

        schema = vol.Schema(
            {
                vol.Required(CONF_ELEC_ENABLED, default=True): cv.boolean,
                vol.Required(CONF_ELEC_UNIT_PRICE, default=DEFAULT_ELEC_UNIT_PRICE): vol.Coerce(float),
                vol.Required(CONF_ELEC_BASE_PRICE, default=DEFAULT_ELEC_BASE_PRICE): vol.Coerce(float),
                vol.Required(CONF_ELEC_MONTHLY_PAYMENT, default=DEFAULT_ELEC_MONTHLY_PAYMENT): vol.Coerce(float),
            }
        )

        return self.async_show_form(step_id="electricity", data_schema=schema, errors=errors)

    async def async_step_gas(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 3: Gas tariff settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title=NAME, data=self._data)

        schema = vol.Schema(
            {
                vol.Required(CONF_GAS_ENABLED, default=True): cv.boolean,
                vol.Required(CONF_GAS_UNIT_PRICE, default=DEFAULT_GAS_UNIT_PRICE): vol.Coerce(float),
                vol.Required(CONF_GAS_BASE_PRICE, default=DEFAULT_GAS_BASE_PRICE): vol.Coerce(float),
                vol.Required(CONF_GAS_MONTHLY_PAYMENT, default=DEFAULT_GAS_MONTHLY_PAYMENT): vol.Coerce(float),
                vol.Required(CONF_GAS_CALORIFIC_VALUE, default=DEFAULT_GAS_CALORIFIC_VALUE): vol.Coerce(float),
                vol.Required(CONF_GAS_CONVERSION_FACTOR, default=DEFAULT_GAS_CONVERSION_FACTOR): vol.Coerce(float),
            }
        )

        return self.async_show_form(step_id="gas", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Get the options flow handler."""
        return MeterSnapOptionsFlow(config_entry)


class MeterSnapOptionsFlow(config_entries.OptionsFlow):
    """Handle options (editing tariffs & keys after installation)."""

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        """Initialize options flow."""
        if config_entry is not None:
            try:
                self.config_entry = config_entry
            except AttributeError:
                pass

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage tariffs and configuration."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}

        schema = vol.Schema(
            {
                # AI
                vol.Required(CONF_OCR_PROVIDER, default=current.get(CONF_OCR_PROVIDER, PROVIDER_GEMINI)): vol.In(OCR_PROVIDERS),
                vol.Optional(CONF_API_KEY, default=current.get(CONF_API_KEY, "")): cv.string,
                vol.Optional(CONF_CUSTOM_ENDPOINT, default=current.get(CONF_CUSTOM_ENDPOINT, "")): cv.string,
                vol.Optional(CONF_CUSTOM_MODEL, default=current.get(CONF_CUSTOM_MODEL, DEFAULT_CUSTOM_MODEL)): cv.string,

                # Electricity
                vol.Required(CONF_ELEC_ENABLED, default=current.get(CONF_ELEC_ENABLED, True)): cv.boolean,
                vol.Required(CONF_ELEC_UNIT_PRICE, default=current.get(CONF_ELEC_UNIT_PRICE, DEFAULT_ELEC_UNIT_PRICE)): vol.Coerce(float),
                vol.Required(CONF_ELEC_BASE_PRICE, default=current.get(CONF_ELEC_BASE_PRICE, DEFAULT_ELEC_BASE_PRICE)): vol.Coerce(float),
                vol.Required(CONF_ELEC_MONTHLY_PAYMENT, default=current.get(CONF_ELEC_MONTHLY_PAYMENT, DEFAULT_ELEC_MONTHLY_PAYMENT)): vol.Coerce(float),

                # Gas
                vol.Required(CONF_GAS_ENABLED, default=current.get(CONF_GAS_ENABLED, True)): cv.boolean,
                vol.Required(CONF_GAS_UNIT_PRICE, default=current.get(CONF_GAS_UNIT_PRICE, DEFAULT_GAS_UNIT_PRICE)): vol.Coerce(float),
                vol.Required(CONF_GAS_BASE_PRICE, default=current.get(CONF_GAS_BASE_PRICE, DEFAULT_GAS_BASE_PRICE)): vol.Coerce(float),
                vol.Required(CONF_GAS_MONTHLY_PAYMENT, default=current.get(CONF_GAS_MONTHLY_PAYMENT, DEFAULT_GAS_MONTHLY_PAYMENT)): vol.Coerce(float),
                vol.Required(CONF_GAS_CALORIFIC_VALUE, default=current.get(CONF_GAS_CALORIFIC_VALUE, DEFAULT_GAS_CALORIFIC_VALUE)): vol.Coerce(float),
                vol.Required(CONF_GAS_CONVERSION_FACTOR, default=current.get(CONF_GAS_CONVERSION_FACTOR, DEFAULT_GAS_CONVERSION_FACTOR)): vol.Coerce(float),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
