"""Config Flow and Options Flow for MeterSnap."""
from __future__ import annotations

import logging
from typing import Any
import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_ENERGY_DASHBOARD,
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
    DEFAULT_CUSTOM_ENDPOINT,
    DEFAULT_CUSTOM_MODEL,
    DEFAULT_ELEC_BASE_PRICE,
    DEFAULT_ELEC_MONTHLY_PAYMENT,
    DEFAULT_ELEC_UNIT_PRICE,
    DEFAULT_GAS_BASE_PRICE,
    DEFAULT_GAS_CALORIFIC_VALUE,
    DEFAULT_GAS_CONVERSION_FACTOR,
    DEFAULT_GAS_MONTHLY_PAYMENT,
    DEFAULT_GAS_UNIT_PRICE,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_OPENROUTER_MODEL,
    DOMAIN,
    NAME,
    OPENROUTER_API_URL,
    OPENROUTER_MODELS_URL,
    PROVIDER_CUSTOM,
    PROVIDER_GEMINI,
    PROVIDER_NONE,
    PROVIDER_OPENAI,
    PROVIDER_OPENROUTER,
)

_LOGGER = logging.getLogger(__name__)


class MeterSnapConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MeterSnap."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 1: Choose AI service or manual mode."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        return self.async_show_menu(
            step_id="user",
            menu_options=["openrouter", "custom", "gemini", "openai", "none"],
        )

    async def async_step_none(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Setup without AI (manual reading & photo archive)."""
        self._data[CONF_OCR_PROVIDER] = PROVIDER_NONE
        self._data[CONF_API_KEY] = ""
        self._data[CONF_CUSTOM_ENDPOINT] = ""
        self._data[CONF_CUSTOM_MODEL] = ""
        return await self.async_step_electricity()

    async def async_step_openrouter(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step: OpenRouter API key entry."""
        if user_input is not None:
            self._data[CONF_OCR_PROVIDER] = PROVIDER_OPENROUTER
            self._data[CONF_API_KEY] = user_input.get(CONF_API_KEY, "").strip()
            self._data[CONF_CUSTOM_ENDPOINT] = OPENROUTER_API_URL
            return await self.async_step_openrouter_model()

        schema = vol.Schema(
            {
                vol.Optional(CONF_API_KEY, default=""): cv.string,
            }
        )
        return self.async_show_form(step_id="openrouter", data_schema=schema)

    async def async_step_openrouter_model(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step: OpenRouter model selection (free models on top)."""
        if user_input is not None:
            chosen_model = user_input.get("openrouter_model_select")
            custom_text = user_input.get(CONF_CUSTOM_MODEL, "").strip()
            if chosen_model == "custom_manual" and custom_text:
                self._data[CONF_CUSTOM_MODEL] = custom_text
            elif chosen_model and chosen_model != "custom_manual":
                self._data[CONF_CUSTOM_MODEL] = chosen_model
            elif custom_text:
                self._data[CONF_CUSTOM_MODEL] = custom_text
            else:
                self._data[CONF_CUSTOM_MODEL] = DEFAULT_OPENROUTER_MODEL

            return await self.async_step_electricity()

        model_options = await self._async_get_openrouter_models(self._data.get(CONF_API_KEY, ""))
        default_choice = next(iter(model_options.keys())) if model_options else DEFAULT_OPENROUTER_MODEL

        schema = vol.Schema(
            {
                vol.Required("openrouter_model_select", default=default_choice): vol.In(model_options),
                vol.Optional(CONF_CUSTOM_MODEL, default=""): cv.string,
            }
        )
        return self.async_show_form(step_id="openrouter_model", data_schema=schema)

    async def _async_get_openrouter_models(self, api_key: str = "") -> dict[str, str]:
        """Fetch vision-capable models from OpenRouter, placing free models first."""
        fallback_models: dict[str, str] = {
            "inclusionai/ling-3.0-flash-vl:free": "✨ Ling 3.0 Flash VL (Kostenlos / Free)",
            "google/gemma-4-26b-a4b-it:free": "✨ Google Gemma 4 26B (Kostenlos / Free)",
            "qwen/qwen3.8-27b:free": "✨ Qwen 3.8 27B (Kostenlos / Free)",
            "nex-agi/nex-n2.5-mini:free": "✨ Nex AGI Mini (Kostenlos / Free)",
            "meta-llama/llama-3.2-11b-vision-instruct:free": "✨ Llama 3.2 11B Vision (Kostenlos / Free)",
            "google/gemini-2.0-flash-exp:free": "✨ Gemini 2.0 Flash Exp (Kostenlos / Free)",
            "openai/gpt-4o-mini": "OpenAI GPT-4o-mini",
            "google/gemini-flash-1.5": "Google Gemini Flash 1.5",
            "custom_manual": "✍️ Anderes Modell manuell eingeben...",
        }

        session = async_get_clientsession(self.hass)
        headers = {
            "HTTP-Referer": "https://github.com/Cs3ries/Ha-MeterSnap",
            "X-Title": "MeterSnap",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with session.get(
                OPENROUTER_MODELS_URL,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    raw_list = data.get("data", [])

                    free_models: dict[str, str] = {}
                    other_models: dict[str, str] = {}

                    for m in raw_list:
                        mid = m.get("id", "")
                        name = m.get("name", mid)
                        arch = m.get("architecture", {})
                        modality = arch.get("modality", "") if isinstance(arch, dict) else ""

                        is_vision = (
                            "image" in modality
                            or "vl" in mid.lower()
                            or "vision" in mid.lower()
                        )
                        if not is_vision:
                            continue

                        if ":free" in mid:
                            free_models[mid] = f"✨ {name} (Kostenlos / Free)"
                        else:
                            other_models[mid] = name

                    if free_models or other_models:
                        result: dict[str, str] = {}
                        result.update(free_models)
                        count = 0
                        for k, v in other_models.items():
                            result[k] = v
                            count += 1
                            if count >= 30:
                                break
                        result["custom_manual"] = "✍️ Anderes Modell manuell eingeben..."
                        return result
        except Exception as err:
            _LOGGER.warning("Could not fetch OpenRouter models (%s), using fallback list", err)

        return fallback_models

    async def async_step_custom(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step: Local / Custom OpenAI-compatible endpoint."""
        if user_input is not None:
            self._data[CONF_OCR_PROVIDER] = PROVIDER_CUSTOM
            self._data[CONF_CUSTOM_ENDPOINT] = user_input.get(CONF_CUSTOM_ENDPOINT, DEFAULT_CUSTOM_ENDPOINT).strip()
            self._data[CONF_CUSTOM_MODEL] = user_input.get(CONF_CUSTOM_MODEL, DEFAULT_CUSTOM_MODEL).strip()
            self._data[CONF_API_KEY] = user_input.get(CONF_API_KEY, "").strip()
            return await self.async_step_electricity()

        schema = vol.Schema(
            {
                vol.Required(CONF_CUSTOM_ENDPOINT, default=DEFAULT_CUSTOM_ENDPOINT): cv.string,
                vol.Required(CONF_CUSTOM_MODEL, default=DEFAULT_CUSTOM_MODEL): cv.string,
                vol.Optional(CONF_API_KEY, default=""): cv.string,
            }
        )
        return self.async_show_form(step_id="custom", data_schema=schema)

    async def async_step_gemini(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step: Google Gemini configuration."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            if not api_key:
                errors[CONF_API_KEY] = "empty_api_key"
            else:
                self._data[CONF_OCR_PROVIDER] = PROVIDER_GEMINI
                self._data[CONF_API_KEY] = api_key
                self._data[CONF_CUSTOM_ENDPOINT] = ""
                self._data[CONF_CUSTOM_MODEL] = DEFAULT_GEMINI_MODEL
                return await self.async_step_electricity()

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY, default=""): cv.string,
            }
        )
        return self.async_show_form(step_id="gemini", data_schema=schema, errors=errors)

    async def async_step_openai(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step: OpenAI configuration."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            if not api_key:
                errors[CONF_API_KEY] = "empty_api_key"
            else:
                self._data[CONF_OCR_PROVIDER] = PROVIDER_OPENAI
                self._data[CONF_API_KEY] = api_key
                self._data[CONF_CUSTOM_ENDPOINT] = ""
                self._data[CONF_CUSTOM_MODEL] = DEFAULT_OPENAI_MODEL
                return await self.async_step_electricity()

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY, default=""): cv.string,
            }
        )
        return self.async_show_form(step_id="openai", data_schema=schema, errors=errors)

    async def async_step_electricity(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step: Electricity tariff settings."""
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
        """Step: Gas tariff settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_dashboard()

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

    async def async_step_dashboard(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Offer an optional energy dashboard with meter capture."""
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title=NAME, data=self._data)
        return self.async_show_form(
            step_id="dashboard",
            data_schema=vol.Schema({vol.Required(CONF_ENERGY_DASHBOARD, default=False): cv.boolean}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Get the options flow handler."""
        return MeterSnapOptionsFlow(config_entry)


class MeterSnapOptionsFlow(config_entries.OptionsFlow):
    """Handle options (editing tariffs & AI keys after installation)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._options: dict[str, Any] = {**config_entry.data, **config_entry.options}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Main options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["provider_select", "electricity", "gas", "dashboard"],
        )

    async def async_step_provider_select(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Choose provider to configure in options."""
        return self.async_show_menu(
            step_id="provider_select",
            menu_options=["opt_openrouter", "opt_custom", "opt_gemini", "opt_openai", "opt_none"],
        )

    async def async_step_opt_none(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Disable AI in options."""
        self._options[CONF_OCR_PROVIDER] = PROVIDER_NONE
        self._options[CONF_API_KEY] = ""
        self._options[CONF_CUSTOM_ENDPOINT] = ""
        self._options[CONF_CUSTOM_MODEL] = ""
        return self.async_create_entry(title="", data=self._options)

    async def async_step_opt_openrouter(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure OpenRouter in options."""
        if user_input is not None:
            self._options[CONF_OCR_PROVIDER] = PROVIDER_OPENROUTER
            self._options[CONF_API_KEY] = user_input.get(CONF_API_KEY, "").strip()
            self._options[CONF_CUSTOM_ENDPOINT] = OPENROUTER_API_URL
            model_text = user_input.get(CONF_CUSTOM_MODEL, "").strip()
            chosen_select = user_input.get("openrouter_model_select")
            if chosen_select == "custom_manual" and model_text:
                self._options[CONF_CUSTOM_MODEL] = model_text
            elif chosen_select and chosen_select != "custom_manual":
                self._options[CONF_CUSTOM_MODEL] = chosen_select
            elif model_text:
                self._options[CONF_CUSTOM_MODEL] = model_text
            else:
                self._options[CONF_CUSTOM_MODEL] = DEFAULT_OPENROUTER_MODEL
            return self.async_create_entry(title="", data=self._options)

        model_options = await self._async_get_openrouter_models(self._options.get(CONF_API_KEY, ""))
        curr_model = self._options.get(CONF_CUSTOM_MODEL, DEFAULT_OPENROUTER_MODEL)
        default_choice = curr_model if curr_model in model_options else "custom_manual"

        schema = vol.Schema(
            {
                vol.Optional(CONF_API_KEY, default=self._options.get(CONF_API_KEY, "")): cv.string,
                vol.Required("openrouter_model_select", default=default_choice): vol.In(model_options),
                vol.Optional(CONF_CUSTOM_MODEL, default=curr_model if default_choice == "custom_manual" else ""): cv.string,
            }
        )
        return self.async_show_form(step_id="opt_openrouter", data_schema=schema)

    async def _async_get_openrouter_models(self, api_key: str = "") -> dict[str, str]:
        """Fetch vision-capable models from OpenRouter."""
        fallback_models: dict[str, str] = {
            "inclusionai/ling-3.0-flash-vl:free": "✨ Ling 3.0 Flash VL (Kostenlos / Free)",
            "google/gemma-4-26b-a4b-it:free": "✨ Google Gemma 4 26B (Kostenlos / Free)",
            "qwen/qwen3.8-27b:free": "✨ Qwen 3.8 27B (Kostenlos / Free)",
            "nex-agi/nex-n2.5-mini:free": "✨ Nex AGI Mini (Kostenlos / Free)",
            "meta-llama/llama-3.2-11b-vision-instruct:free": "✨ Llama 3.2 11B Vision (Kostenlos / Free)",
            "google/gemini-2.0-flash-exp:free": "✨ Gemini 2.0 Flash Exp (Kostenlos / Free)",
            "openai/gpt-4o-mini": "OpenAI GPT-4o-mini",
            "google/gemini-flash-1.5": "Google Gemini Flash 1.5",
            "custom_manual": "✍️ Anderes Modell manuell eingeben...",
        }
        session = async_get_clientsession(self.hass)
        headers = {"HTTP-Referer": "https://github.com/Cs3ries/Ha-MeterSnap", "X-Title": "MeterSnap"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            async with session.get(OPENROUTER_MODELS_URL, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    free_models: dict[str, str] = {}
                    other_models: dict[str, str] = {}
                    for m in data.get("data", []):
                        mid = m.get("id", "")
                        name = m.get("name", mid)
                        arch = m.get("architecture", {})
                        modality = arch.get("modality", "") if isinstance(arch, dict) else ""
                        if not ("image" in modality or "vl" in mid.lower() or "vision" in mid.lower()):
                            continue
                        if ":free" in mid:
                            free_models[mid] = f"✨ {name} (Kostenlos / Free)"
                        else:
                            other_models[mid] = name
                    if free_models or other_models:
                        res: dict[str, str] = {}
                        res.update(free_models)
                        count = 0
                        for k, v in other_models.items():
                            res[k] = v
                            count += 1
                            if count >= 30:
                                break
                        res["custom_manual"] = "✍️ Anderes Modell manuell eingeben..."
                        return res
        except Exception as err:
            _LOGGER.warning("Could not fetch OpenRouter models (%s), using fallback", err)
        return fallback_models

    async def async_step_opt_custom(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure local / custom endpoint in options."""
        if user_input is not None:
            self._options[CONF_OCR_PROVIDER] = PROVIDER_CUSTOM
            self._options[CONF_CUSTOM_ENDPOINT] = user_input.get(CONF_CUSTOM_ENDPOINT, DEFAULT_CUSTOM_ENDPOINT).strip()
            self._options[CONF_CUSTOM_MODEL] = user_input.get(CONF_CUSTOM_MODEL, DEFAULT_CUSTOM_MODEL).strip()
            self._options[CONF_API_KEY] = user_input.get(CONF_API_KEY, "").strip()
            return self.async_create_entry(title="", data=self._options)

        schema = vol.Schema(
            {
                vol.Required(CONF_CUSTOM_ENDPOINT, default=self._options.get(CONF_CUSTOM_ENDPOINT, DEFAULT_CUSTOM_ENDPOINT)): cv.string,
                vol.Required(CONF_CUSTOM_MODEL, default=self._options.get(CONF_CUSTOM_MODEL, DEFAULT_CUSTOM_MODEL)): cv.string,
                vol.Optional(CONF_API_KEY, default=self._options.get(CONF_API_KEY, "")): cv.string,
            }
        )
        return self.async_show_form(step_id="opt_custom", data_schema=schema)

    async def async_step_opt_gemini(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure Gemini in options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            if not api_key:
                errors[CONF_API_KEY] = "empty_api_key"
            else:
                self._options[CONF_OCR_PROVIDER] = PROVIDER_GEMINI
                self._options[CONF_API_KEY] = api_key
                self._options[CONF_CUSTOM_ENDPOINT] = ""
                self._options[CONF_CUSTOM_MODEL] = DEFAULT_GEMINI_MODEL
                return self.async_create_entry(title="", data=self._options)

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY, default=self._options.get(CONF_API_KEY, "")): cv.string,
            }
        )
        return self.async_show_form(step_id="opt_gemini", data_schema=schema, errors=errors)

    async def async_step_opt_openai(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure OpenAI in options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input.get(CONF_API_KEY, "").strip()
            if not api_key:
                errors[CONF_API_KEY] = "empty_api_key"
            else:
                self._options[CONF_OCR_PROVIDER] = PROVIDER_OPENAI
                self._options[CONF_API_KEY] = api_key
                self._options[CONF_CUSTOM_ENDPOINT] = ""
                self._options[CONF_CUSTOM_MODEL] = DEFAULT_OPENAI_MODEL
                return self.async_create_entry(title="", data=self._options)

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY, default=self._options.get(CONF_API_KEY, "")): cv.string,
            }
        )
        return self.async_show_form(step_id="opt_openai", data_schema=schema, errors=errors)

    async def async_step_electricity(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Edit electricity tariffs in options."""
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)

        schema = vol.Schema(
            {
                vol.Required(CONF_ELEC_ENABLED, default=self._options.get(CONF_ELEC_ENABLED, True)): cv.boolean,
                vol.Required(CONF_ELEC_UNIT_PRICE, default=self._options.get(CONF_ELEC_UNIT_PRICE, DEFAULT_ELEC_UNIT_PRICE)): vol.Coerce(float),
                vol.Required(CONF_ELEC_BASE_PRICE, default=self._options.get(CONF_ELEC_BASE_PRICE, DEFAULT_ELEC_BASE_PRICE)): vol.Coerce(float),
                vol.Required(CONF_ELEC_MONTHLY_PAYMENT, default=self._options.get(CONF_ELEC_MONTHLY_PAYMENT, DEFAULT_ELEC_MONTHLY_PAYMENT)): vol.Coerce(float),
            }
        )
        return self.async_show_form(step_id="electricity", data_schema=schema)

    async def async_step_gas(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Edit gas tariffs in options."""
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)

        schema = vol.Schema(
            {
                vol.Required(CONF_GAS_ENABLED, default=self._options.get(CONF_GAS_ENABLED, True)): cv.boolean,
                vol.Required(CONF_GAS_UNIT_PRICE, default=self._options.get(CONF_GAS_UNIT_PRICE, DEFAULT_GAS_UNIT_PRICE)): vol.Coerce(float),
                vol.Required(CONF_GAS_BASE_PRICE, default=self._options.get(CONF_GAS_BASE_PRICE, DEFAULT_GAS_BASE_PRICE)): vol.Coerce(float),
                vol.Required(CONF_GAS_MONTHLY_PAYMENT, default=self._options.get(CONF_GAS_MONTHLY_PAYMENT, DEFAULT_GAS_MONTHLY_PAYMENT)): vol.Coerce(float),
                vol.Required(CONF_GAS_CALORIFIC_VALUE, default=self._options.get(CONF_GAS_CALORIFIC_VALUE, DEFAULT_GAS_CALORIFIC_VALUE)): vol.Coerce(float),
                vol.Required(CONF_GAS_CONVERSION_FACTOR, default=self._options.get(CONF_GAS_CONVERSION_FACTOR, DEFAULT_GAS_CONVERSION_FACTOR)): vol.Coerce(float),
            }
        )
        return self.async_show_form(step_id="gas", data_schema=schema)

    async def async_step_dashboard(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Enable or hide the managed dashboard without deleting its layout."""
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)
        return self.async_show_form(
            step_id="dashboard",
            data_schema=vol.Schema({
                vol.Required(CONF_ENERGY_DASHBOARD, default=self._options.get(CONF_ENERGY_DASHBOARD, False)): cv.boolean,
            }),
        )
