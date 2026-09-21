"""Data Coordinator and Storage for MeterSnap."""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import uuid
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CONF_ELEC_BASE_PRICE,
    CONF_ELEC_MONTHLY_PAYMENT,
    CONF_ELEC_UNIT_PRICE,
    CONF_GAS_BASE_PRICE,
    CONF_GAS_CALORIFIC_VALUE,
    CONF_GAS_CONVERSION_FACTOR,
    CONF_GAS_MONTHLY_PAYMENT,
    CONF_GAS_UNIT_PRICE,
    DEFAULT_ELEC_BASE_PRICE,
    DEFAULT_ELEC_MONTHLY_PAYMENT,
    DEFAULT_ELEC_UNIT_PRICE,
    DEFAULT_GAS_BASE_PRICE,
    DEFAULT_GAS_CALORIFIC_VALUE,
    DEFAULT_GAS_CONVERSION_FACTOR,
    DEFAULT_GAS_MONTHLY_PAYMENT,
    DEFAULT_GAS_UNIT_PRICE,
    IMAGE_DIR,
    METER_ELECTRICITY,
    METER_GAS,
    METER_TYPES,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


def parse_iso_datetime(dt_str: str) -> datetime:
    """Safely parse ISO datetime string."""
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


class MeterSnapCoordinator:
    """Coordinator managing meter readings, persistence, and tariff calculations."""

    def __init__(self, hass: HomeAssistant, config_entry: Any) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.config_entry = config_entry
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._readings: dict[str, list[dict[str, Any]]] = {
            METER_ELECTRICITY: [],
            METER_GAS: [],
        }
        self._listeners: list[Callable[[], None]] = []
        self._image_dir = hass.config.path(IMAGE_DIR)

    @property
    def config(self) -> dict[str, Any]:
        """Return combined config entry data and options."""
        cfg = dict(self.config_entry.data)
        if self.config_entry.options:
            cfg.update(self.config_entry.options)
        return cfg

    async def async_setup(self) -> None:
        """Load stored readings, migrate legacy records, and clean up stored images."""
        data = await self._store.async_load()
        needs_save = False
        if data and isinstance(data, dict):
            for meter_type in METER_TYPES:
                items = data.get(meter_type, [])
                for item in items:
                    if item.get("image_file") is not None:
                        item["image_file"] = None
                        needs_save = True
                self._readings[meter_type] = items
                self._recalculate_metrics(meter_type)

        if needs_save:
            await self._async_save()
            _LOGGER.info("MeterSnap: Migrated legacy readings, cleared image_file references")

        # Clean up legacy images directory if present
        await self._async_cleanup_legacy_images()

        _LOGGER.info(
            "MeterSnap coordinator loaded: %d electricity readings, %d gas readings",
            len(self._readings[METER_ELECTRICITY]),
            len(self._readings[METER_GAS]),
        )

    async def _async_cleanup_legacy_images(self) -> None:
        """Remove any previously saved meter photos to reclaim disk space."""
        if not os.path.exists(self._image_dir):
            return

        def _cleanup():
            try:
                for fname in os.listdir(self._image_dir):
                    fpath = os.path.join(self._image_dir, fname)
                    if os.path.isfile(fpath):
                        try:
                            os.remove(fpath)
                            _LOGGER.debug("Removed legacy meter photo: %s", fpath)
                        except Exception as err:
                            _LOGGER.warning("Could not remove legacy photo %s: %s", fpath, err)
                try:
                    os.rmdir(self._image_dir)
                    _LOGGER.info("Removed empty legacy image directory: %s", self._image_dir)
                except Exception:
                    pass
            except Exception as err:
                _LOGGER.warning("Error during legacy image cleanup in %s: %s", self._image_dir, err)

        await self.hass.async_add_executor_job(_cleanup)

    def register_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register entity update listener."""
        self._listeners.append(listener)

        def remove():
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    def _notify_listeners(self) -> None:
        """Notify all registered sensor entities of new data."""
        for listener in self._listeners:
            try:
                listener()
            except Exception as err:
                _LOGGER.error("Error notifying MeterSnap listener: %s", err)

    async def async_add_reading(
        self,
        meter_type: str,
        reading: float,
        timestamp_str: str | None = None,
        image_base64: str | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        """Add a new reading and recompute metrics."""
        if meter_type not in METER_TYPES:
            raise ValueError(f"Ungültiger Zählertyp: {meter_type}")

        if not timestamp_str:
            timestamp_str = datetime.now(timezone.utc).isoformat()

        entry_id = str(uuid.uuid4())
        entry = {
            "id": entry_id,
            "timestamp": timestamp_str,
            "reading": round(float(reading), 3),
            "image_file": None,
            "notes": notes,
        }

        self._readings[meter_type].append(entry)
        self._recalculate_metrics(meter_type)
        await self._async_save()
        self._notify_listeners()

        # Find updated entry with calculated fields
        for r in self._readings[meter_type]:
            if r.get("id") == entry_id:
                return r
        return entry

    async def async_delete_reading(self, meter_type: str, entry_id: str) -> bool:
        """Delete a reading by ID and recalculate."""
        if meter_type not in METER_TYPES:
            return False

        original_count = len(self._readings[meter_type])
        remaining = [item for item in self._readings[meter_type] if item.get("id") != entry_id]

        if len(remaining) == original_count:
            return False

        self._readings[meter_type] = remaining
        self._recalculate_metrics(meter_type)
        await self._async_save()
        self._notify_listeners()
        return True

    def get_readings(self, meter_type: str) -> list[dict[str, Any]]:
        """Get all readings for a meter sorted newest first."""
        return list(reversed(self._readings.get(meter_type, [])))

    def get_latest_reading(self, meter_type: str) -> dict[str, Any] | None:
        """Get the latest reading for a meter."""
        items = self._readings.get(meter_type, [])
        return items[-1] if items else None

    def get_kpis(self, meter_type: str) -> dict[str, Any]:
        """Compute key summary figures (current reading, last consumption, cost projection)."""
        latest = self.get_latest_reading(meter_type)
        if not latest:
            return {
                "current_reading": 0.0,
                "last_consumption": 0.0,
                "last_consumption_kwh": 0.0,
                "last_cost": 0.0,
                "daily_average": 0.0,
                "projected_monthly_cost": 0.0,
                "monthly_payment_diff": 0.0,
                "unit": "kWh" if meter_type == METER_ELECTRICITY else "m³",
            }

        cfg = self.config
        if meter_type == METER_ELECTRICITY:
            unit_price = float(cfg.get(CONF_ELEC_UNIT_PRICE, DEFAULT_ELEC_UNIT_PRICE))
            base_price = float(cfg.get(CONF_ELEC_BASE_PRICE, DEFAULT_ELEC_BASE_PRICE))
            monthly_payment = float(
                cfg.get(CONF_ELEC_MONTHLY_PAYMENT, DEFAULT_ELEC_MONTHLY_PAYMENT)
            )
        else:
            unit_price = float(cfg.get(CONF_GAS_UNIT_PRICE, DEFAULT_GAS_UNIT_PRICE))
            base_price = float(cfg.get(CONF_GAS_BASE_PRICE, DEFAULT_GAS_BASE_PRICE))
            monthly_payment = float(
                cfg.get(CONF_GAS_MONTHLY_PAYMENT, DEFAULT_GAS_MONTHLY_PAYMENT)
            )

        daily_avg = float(latest.get("daily_average", 0.0))
        # 30.4375 days per average month
        proj_monthly_work_cost = daily_avg * 30.4375 * unit_price
        proj_monthly_cost = proj_monthly_work_cost + base_price
        diff_to_payment = monthly_payment - proj_monthly_cost

        return {
            "current_reading": latest.get("reading", 0.0),
            "last_consumption": latest.get("consumption", 0.0),
            "last_consumption_kwh": latest.get("consumption_kwh", 0.0),
            "last_cost": latest.get("cost", 0.0),
            "daily_average": daily_avg,
            "projected_monthly_cost": round(proj_monthly_cost, 2),
            "monthly_payment": monthly_payment,
            "monthly_payment_diff": round(diff_to_payment, 2),
            "unit": "kWh" if meter_type == METER_ELECTRICITY else "m³",
        }

    def _recalculate_metrics(self, meter_type: str) -> None:
        """Sort chronologically and calculate consumption, costs and averages."""
        items = self._readings.get(meter_type, [])
        if not items:
            return

        # Sort by timestamp ascending
        items.sort(key=lambda x: parse_iso_datetime(x.get("timestamp", "")))

        cfg = self.config
        if meter_type == METER_ELECTRICITY:
            unit_price = float(cfg.get(CONF_ELEC_UNIT_PRICE, DEFAULT_ELEC_UNIT_PRICE))
            base_price = float(cfg.get(CONF_ELEC_BASE_PRICE, DEFAULT_ELEC_BASE_PRICE))
            calorific = 1.0
            z_factor = 1.0
        else:
            unit_price = float(cfg.get(CONF_GAS_UNIT_PRICE, DEFAULT_GAS_UNIT_PRICE))
            base_price = float(cfg.get(CONF_GAS_BASE_PRICE, DEFAULT_GAS_BASE_PRICE))
            calorific = float(
                cfg.get(CONF_GAS_CALORIFIC_VALUE, DEFAULT_GAS_CALORIFIC_VALUE)
            )
            z_factor = float(
                cfg.get(CONF_GAS_CONVERSION_FACTOR, DEFAULT_GAS_CONVERSION_FACTOR)
            )

        daily_base_price = (base_price * 12.0) / 365.25

        for i, item in enumerate(items):
            reading = float(item.get("reading", 0.0))
            if i == 0:
                item["consumption"] = 0.0
                item["consumption_kwh"] = 0.0
                item["days"] = 0.0
                item["daily_average"] = 0.0
                item["cost"] = 0.0
                item["work_cost"] = 0.0
                item["base_cost"] = 0.0
                continue

            prev = items[i - 1]
            prev_reading = float(prev.get("reading", 0.0))
            dt_curr = parse_iso_datetime(item.get("timestamp", ""))
            dt_prev = parse_iso_datetime(prev.get("timestamp", ""))

            delta_seconds = max(60, (dt_curr - dt_prev).total_seconds())
            days = round(delta_seconds / 86400.0, 2)
            if days < 0.01:
                days = 0.01

            delta_raw = max(0.0, reading - prev_reading)

            if meter_type == METER_ELECTRICITY:
                delta_kwh = delta_raw
            else:
                # Gas: m³ converted to kWh via Brennwert and Zustandszahl
                delta_kwh = delta_raw * calorific * z_factor

            work_cost = delta_kwh * unit_price
            period_base_cost = days * daily_base_price
            total_cost = work_cost + period_base_cost
            daily_avg = delta_kwh / days

            item["consumption"] = round(delta_raw, 3)
            item["consumption_kwh"] = round(delta_kwh, 2)
            item["days"] = days
            item["daily_average"] = round(daily_avg, 2)
            item["work_cost"] = round(work_cost, 2)
            item["base_cost"] = round(period_base_cost, 2)
            item["cost"] = round(total_cost, 2)

    async def _async_save(self) -> None:
        """Save readings to persistent storage."""
        await self._store.async_save(self._readings)
