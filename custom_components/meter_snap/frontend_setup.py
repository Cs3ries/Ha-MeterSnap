"""Register the card resource without editing dashboard layouts or YAML files."""
from __future__ import annotations

import logging
from urllib.parse import urlsplit

from .const import VERSION

_LOGGER = logging.getLogger(__name__)
CARD_URL = f"/meter_snap_frontend/meter-snap-card.js?v={VERSION}"


def _is_meter_snap_url(url: str) -> bool:
    """Match only local MeterSnap card resources, including old manual paths."""
    parsed = urlsplit(url)
    return (
        not parsed.scheme
        and not parsed.netloc
        and parsed.path.startswith(("/meter_snap_frontend/", "/local/", "/hacsfiles/"))
        and parsed.path.rsplit("/", 1)[-1] == "meter-snap-card.js"
    )


async def async_register_card(hass) -> None:
    """Create or update a storage resource; leave YAML resources user-managed."""
    lovelace = hass.data.get("lovelace")
    resources = (
        lovelace.get("resources") if isinstance(lovelace, dict)
        else getattr(lovelace, "resources", None)
    )
    if resources is None:
        _LOGGER.warning("Dashboard resources unavailable; register %s manually", CARD_URL)
        return
    if not hasattr(resources, "async_create_item"):
        _LOGGER.warning("YAML dashboard resources: configure %s as type module", CARD_URL)
        return

    try:
        if not resources.loaded:
            await resources.async_load()
            resources.loaded = True
        matches = [item for item in resources.async_items()
                   if _is_meter_snap_url(item.get("url", ""))]
        updates = {"url": CARD_URL, "res_type": "module"}
        if matches:
            first = matches[0]
            if first.get("url") != CARD_URL or first.get("type") != "module":
                await resources.async_update_item(first["id"], updates)
            for duplicate in matches[1:]:
                await resources.async_delete_item(duplicate["id"])
        else:
            await resources.async_create_item(updates)
    except Exception:
        # A frontend registration failure must not prevent meter data from loading.
        _LOGGER.exception("Could not register dashboard resource %s", CARD_URL)
