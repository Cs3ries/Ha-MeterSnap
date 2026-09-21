"""The MeterSnap Integration."""
from __future__ import annotations

import logging
import os
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_API_KEY,
    CONF_CUSTOM_ENDPOINT,
    CONF_CUSTOM_MODEL,
    CONF_OCR_PROVIDER,
    DEFAULT_CUSTOM_MODEL,
    DOMAIN,
    PROVIDER_OPENROUTER,
)
from .coordinator import MeterSnapCoordinator
from .frontend_setup import async_register_card
from .ocr_engine import MeterSnapOCREngine
from .views import (
    MeterSnapConfigView,
    MeterSnapReadingView,
    MeterSnapScanView,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]
URL_BASE = "/meter_snap_frontend"


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the MeterSnap component global resources."""
    hass.data.setdefault(DOMAIN, {})

    # Register frontend static path for the Lovelace card
    frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
    if os.path.isdir(frontend_dir):
        if hasattr(hass.http, "async_register_static_paths"):
            from homeassistant.components.http import StaticPathConfig
            await hass.http.async_register_static_paths(
                [
                    StaticPathConfig(
                        URL_BASE,
                        frontend_dir,
                        cache_headers=False,
                    )
                ]
            )
        else:
            hass.http.register_static_path(
                URL_BASE,
                frontend_dir,
                cache_headers=False,
            )
        _LOGGER.debug("Registered MeterSnap frontend static path: %s", frontend_dir)

    await async_register_card(hass)

    # Register API views
    hass.http.register_view(MeterSnapScanView)
    hass.http.register_view(MeterSnapReadingView)
    hass.http.register_view(MeterSnapConfigView)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MeterSnap from a config entry."""
    session = async_get_clientsession(hass)

    # Merge data and options
    cfg = dict(entry.data)
    if entry.options:
        cfg.update(entry.options)

    provider = cfg.get(CONF_OCR_PROVIDER, PROVIDER_OPENROUTER)
    api_key = cfg.get(CONF_API_KEY, "")
    custom_endpoint = cfg.get(CONF_CUSTOM_ENDPOINT, "")
    custom_model = cfg.get(CONF_CUSTOM_MODEL, DEFAULT_CUSTOM_MODEL)

    ocr_engine = MeterSnapOCREngine(
        session=session,
        provider=provider,
        api_key=api_key,
        custom_endpoint=custom_endpoint,
        custom_model=custom_model,
    )

    coordinator = MeterSnapCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "ocr_engine": ocr_engine,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry on options update."""
    await hass.config_entries.async_reload(entry.entry_id)
