"""Optional integration-managed, editable Lovelace energy dashboard.

Use a dedicated LovelaceStorage instance and panel; never rewrite HA's dashboard
collection, existing dashboards, or energy preferences. The integration owns the
panel lifecycle, while Lovelace owns and persists user edits to its contents.
"""
from __future__ import annotations

from .const import CONF_ELEC_ENABLED, CONF_GAS_ENABLED

DASHBOARD_URL = "meter-snap-energy"
DASHBOARD_ID = "meter_snap_energy"
DASHBOARD_TITLE = "MeterSnap Energie"


def dashboard_config(config: dict) -> dict:
    """Build the initial layout only; later changes belong to the user."""
    electricity = config.get(CONF_ELEC_ENABLED, True)
    gas = config.get(CONF_GAS_ENABLED, True)
    cards = []
    if electricity or gas:
        cards.append({
            "type": "custom:meter-snap-card",
            "title": "Zähler ablesen",
            "meter": "switchable" if electricity and gas else "electricity" if electricity else "gas",
            "sections": ["header", "capture"],
            "compact": True,
        })
    cards.extend([
        {
            "type": "markdown",
            "content": (
                "Foto hochladen oder Zählerstand manuell eintragen – oben direkt auf dieser Seite.\n\n"
                "Die Diagramme verwenden deine in Home Assistant eingerichteten Energiequellen. "
                "[Energiequellen einrichten](/config/energy) · "
                "[Eingebautes Energie-Dashboard öffnen](/energy)\n\n"
                "**Bei Foto-Ablesungen:** Verbrauch wird erst mit neuen Ablesungen bekannt. "
                "Es entsteht kein gemessener Tages- oder Stundenverlauf; nachgetragene "
                "Ablesungen werden nicht rückwirkend in die Energie-Statistik verteilt."
            ),
        },
        {"type": "energy-date-selection"},
    ])
    if electricity:
        cards.append({"type": "energy-usage-graph"})
    if gas:
        cards.append({"type": "energy-gas-graph"})
    cards.append({"type": "energy-sources-table"})
    return {"title": DASHBOARD_TITLE, "views": [{
        "title": "Zusammenfassung", "path": "summary", "icon": "mdi:lightning-bolt",
        "type": "masonry", "cards": cards,
    }]}


async def async_setup_dashboard(hass, config: dict):
    """Register our panel, seed missing contents, and return an unload callback.

    An occupied URL is an error, never permission to replace another dashboard.
    Stored content survives disabling/removing the integration and is reused.
    """
    from homeassistant.components import frontend
    from homeassistant.components.lovelace.const import ConfigNotFound
    from homeassistant.components.lovelace.dashboard import LovelaceStorage

    lovelace = hass.data.get("lovelace")
    dashboards = lovelace.get("dashboards") if isinstance(lovelace, dict) else getattr(lovelace, "dashboards", None)
    if dashboards is None:
        raise RuntimeError("Home Assistant Lovelace dashboards are not available")
    if DASHBOARD_URL in dashboards or frontend.async_panel_exists(hass, DASHBOARD_URL):
        raise RuntimeError(f"Dashboard URL /{DASHBOARD_URL} is already in use")

    dashboard = LovelaceStorage(hass, {
        "id": DASHBOARD_ID, "url_path": DASHBOARD_URL,
        "title": DASHBOARD_TITLE, "mode": "storage",
        "icon": "mdi:camera-metering-center", "show_in_sidebar": True,
        "require_admin": False,
    })
    try:
        await dashboard.async_load(False)
    except ConfigNotFound:
        await dashboard.async_save(dashboard_config(config))

    dashboards[DASHBOARD_URL] = dashboard
    try:
        frontend.async_register_built_in_panel(
            hass, "lovelace", sidebar_title=DASHBOARD_TITLE,
            sidebar_icon="mdi:camera-metering-center", frontend_url_path=DASHBOARD_URL,
            config={"mode": "storage"}, require_admin=False,
        )
    except Exception:
        dashboards.pop(DASHBOARD_URL, None)
        raise

    def unload():
        # Only remove what this setup registered; retain all saved card edits.
        if dashboards.get(DASHBOARD_URL) is dashboard:
            dashboards.pop(DASHBOARD_URL)
            frontend.async_remove_panel(hass, DASHBOARD_URL)

    return unload
