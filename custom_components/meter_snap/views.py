"""HTTP Views and API Endpoints for MeterSnap."""
from __future__ import annotations

import base64
import logging
import os
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN, METER_ELECTRICITY, METER_TYPES
from .coordinator import MeterSnapCoordinator
from .ocr_engine import MeterSnapOCREngine

_LOGGER = logging.getLogger(__name__)


def get_coordinator_and_ocr(hass: HomeAssistant) -> tuple[MeterSnapCoordinator, MeterSnapOCREngine] | None:
    """Get coordinator and OCR engine from first config entry."""
    domain_data = hass.data.get(DOMAIN, {})
    for entry_id, data in domain_data.items():
        if isinstance(data, dict) and "coordinator" in data and "ocr_engine" in data:
            return data["coordinator"], data["ocr_engine"]
    return None


class MeterSnapScanView(HomeAssistantView):
    """View to accept a photo, run OCR, and return detected meter reading."""

    url = "/api/meter_snap/scan"
    name = "api:meter_snap:scan"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Handle image upload and OCR processing."""
        res = get_coordinator_and_ocr(request.app["hass"])
        if not res:
            return self.json({"success": False, "error": "MeterSnap nicht initialisiert"}, status_code=500)

        _, ocr_engine = res

        try:
            content_type = request.content_type or ""
            image_bytes = None
            meter_type = METER_ELECTRICITY
            mime_type = "image/jpeg"

            if "multipart/form-data" in content_type:
                reader = await request.multipart()
                while True:
                    part = await reader.next()
                    if part is None:
                        break
                    if part.name == "image":
                        image_bytes = await part.read()
                        mime_type = part.headers.get("Content-Type", "image/jpeg")
                    elif part.name == "meter_type":
                        val = await part.text()
                        if val in METER_TYPES:
                            meter_type = val
            else:
                data = await request.json()
                b64_str = data.get("image", "")
                meter_type = data.get("meter_type", METER_ELECTRICITY)
                if "," in b64_str:
                    header, b64_str = b64_str.split(",", 1)
                    if "image/png" in header:
                        mime_type = "image/png"
                    elif "image/webp" in header:
                        mime_type = "image/webp"
                image_bytes = base64.b64decode(b64_str)

            if not image_bytes:
                return self.json({"success": False, "error": "Kein Bild empfangen"}, status_code=400)

            result = await ocr_engine.scan_image(image_bytes, meter_type=meter_type, mime_type=mime_type)
            return self.json(result)

        except Exception as err:
            _LOGGER.exception("Error in MeterSnapScanView: %s", err)
            return self.json({"success": False, "error": str(err)}, status_code=500)


class MeterSnapReadingView(HomeAssistantView):
    """View to add, list and delete meter readings."""

    url = "/api/meter_snap/reading"
    name = "api:meter_snap:reading"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Get readings and KPIs for a specific meter type."""
        res = get_coordinator_and_ocr(request.app["hass"])
        if not res:
            return self.json({"success": False, "error": "MeterSnap nicht initialisiert"}, status_code=500)

        coordinator, _ = res
        meter_type = request.query.get("meter_type", METER_ELECTRICITY)
        if meter_type not in METER_TYPES:
            meter_type = METER_ELECTRICITY

        readings = coordinator.get_readings(meter_type)
        kpis = coordinator.get_kpis(meter_type)

        return self.json({"success": True, "readings": readings, "kpis": kpis})

    async def post(self, request: web.Request) -> web.Response:
        """Save a confirmed meter reading."""
        res = get_coordinator_and_ocr(request.app["hass"])
        if not res:
            return self.json({"success": False, "error": "MeterSnap nicht initialisiert"}, status_code=500)

        coordinator, _ = res

        try:
            body = await request.json()
            meter_type = body.get("meter_type", METER_ELECTRICITY)
            reading_val = float(body.get("reading"))
            timestamp = body.get("timestamp")
            image_base64 = body.get("image_base64")
            notes = body.get("notes", "")

            entry = await coordinator.async_add_reading(
                meter_type=meter_type,
                reading=reading_val,
                timestamp_str=timestamp,
                image_base64=image_base64,
                notes=notes,
            )

            kpis = coordinator.get_kpis(meter_type)
            return self.json({"success": True, "entry": entry, "kpis": kpis})

        except Exception as err:
            _LOGGER.exception("Error saving reading in MeterSnapReadingView: %s", err)
            return self.json({"success": False, "error": str(err)}, status_code=400)

    async def delete(self, request: web.Request) -> web.Response:
        """Delete a reading by ID."""
        res = get_coordinator_and_ocr(request.app["hass"])
        if not res:
            return self.json({"success": False, "error": "MeterSnap nicht initialisiert"}, status_code=500)

        coordinator, _ = res
        meter_type = request.query.get("meter_type", METER_ELECTRICITY)
        entry_id = request.query.get("id")

        if not entry_id:
            return self.json({"success": False, "error": "ID fehlt"}, status_code=400)

        success = await coordinator.async_delete_reading(meter_type, entry_id)
        kpis = coordinator.get_kpis(meter_type)
        readings = coordinator.get_readings(meter_type)

        return self.json({"success": success, "readings": readings, "kpis": kpis})


class MeterSnapImageView(HomeAssistantView):
    """View to securely serve saved meter reading photos."""

    url = "/api/meter_snap/image/{filename}"
    name = "api:meter_snap:image"
    requires_auth = True

    async def get(self, request: web.Request, filename: str) -> web.Response:
        """Serve the requested image file."""
        res = get_coordinator_and_ocr(request.app["hass"])
        if not res:
            return web.Response(status=500, text="MeterSnap nicht initialisiert")

        coordinator, _ = res
        # Basic sanitization
        safe_filename = os.path.basename(filename)
        img_path = coordinator.get_image_path(safe_filename)

        if not os.path.isfile(img_path):
            return web.Response(status=404, text="Bild nicht gefunden")

        return web.FileResponse(img_path)


class MeterSnapConfigView(HomeAssistantView):
    """View to get config info and status."""

    url = "/api/meter_snap/config"
    name = "api:meter_snap:config"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        """Return configured tariffs and status."""
        res = get_coordinator_and_ocr(request.app["hass"])
        if not res:
            return self.json({"success": False, "error": "MeterSnap nicht initialisiert"}, status_code=500)

        coordinator, _ = res
        cfg = dict(coordinator.config)
        # Redact API key
        if "api_key" in cfg and cfg["api_key"]:
            cfg["api_key"] = "***" + cfg["api_key"][-4:]

        return self.json({"success": True, "config": cfg})
