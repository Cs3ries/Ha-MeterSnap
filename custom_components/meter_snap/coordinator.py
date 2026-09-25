"""Data Coordinator and Storage for MeterSnap."""
from __future__ import annotations

from datetime import datetime, timezone
import asyncio
from copy import deepcopy
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

from .readings import ReadingError, parse_timestamp, number, interval, sort_key, validate_change, confirmation_token

_LOGGER = logging.getLogger(__name__)


def parse_iso_datetime(dt_str: str) -> datetime:
    """Parse timestamps strictly, retaining legacy UTC interpretation."""
    return parse_timestamp(dt_str)


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
        self._lock = asyncio.Lock()
        self._statistics = {}
        self._extra_storage = {}
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
            self._extra_storage = {k: v for k, v in data.items() if k not in METER_TYPES}
            self._statistics = deepcopy(data.get("_statistics", {}))
            for meter_type in METER_TYPES:
                items = data.get(meter_type, [])
                for item in items:
                    if item.get("image_file") is not None:
                        item["image_file"] = None
                        needs_save = True
                self._readings[meter_type] = items
                self._recalculate_metrics(meter_type)

        for meter_type in METER_TYPES:
            if meter_type not in self._statistics:
                self._statistics[meter_type] = self._initial_statistics(meter_type)
                needs_save = True

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

    def _factor(self, meter_type):
        if meter_type == METER_ELECTRICITY:
            return 1.0
        return float(self.config.get(CONF_GAS_CALORIFIC_VALUE, DEFAULT_GAS_CALORIFIC_VALUE)) * float(self.config.get(CONF_GAS_CONVERSION_FACTOR, DEFAULT_GAS_CONVERSION_FACTOR))

    def _initial_statistics(self, meter_type):
        latest = self.get_latest_reading(meter_type)
        try:
            value = number(latest.get("reading"), optional=True) if latest else None
        except ReadingError:
            value = None
        try:
            watermark = parse_timestamp(latest["timestamp"]).isoformat() if latest else None
        except ReadingError:
            watermark = None
            latest = None
        return {"total": value, "energy": round(value * self._factor(meter_type), 2) if value is not None else None,
                "anchor": deepcopy(latest), "watermark": watermark,
                "segment": next((r["id"] for r in reversed(self._readings[meter_type]) if r.get("kind") == "replacement"), None),
                "corrections": False}

    def get_statistics(self, meter_type):
        return self._statistics.get(meter_type, {})

    def _advance_statistics(self, meter_type, entry, candidate, editing=False):
        state = self._statistics.setdefault(meter_type, self._initial_statistics(meter_type))
        anchor = state.get("anchor")
        watermark = state.get("watermark")
        segment = next((r["id"] for r in reversed(candidate) if r.get("kind") == "replacement"), None)
        if not editing and (not watermark or sort_key(entry) > parse_timestamp(watermark)):
            delta = None
            if anchor:
                try:
                    delta, _ = interval(anchor, entry)
                except ReadingError:
                    pass
            if state["total"] is None:
                state["total"] = entry.get("reading")
                state["energy"] = round(state["total"] * self._factor(meter_type), 2) if state["total"] is not None else None
            elif delta is not None:
                state["total"] = round(state["total"] + delta, 3)
                state["energy"] = round(state["energy"] + delta * self._factor(meter_type), 2)
            else:
                state["corrections"] = True
            state["anchor"] = deepcopy(entry)
            state["watermark"] = entry["timestamp"]
        else:
            state["corrections"] = True
            # Rebase after corrections, without changing previously published totals.
            latest = candidate[-1]
            if segment != state.get("segment") or (editing and (not anchor or anchor["id"] == entry["id"] or sort_key(latest) > sort_key(anchor))):
                state["anchor"] = deepcopy(latest)
                state["watermark"] = max(parse_timestamp(watermark), sort_key(latest)).isoformat() if watermark else latest["timestamp"]

        state["segment"] = segment

    async def async_add_reading(self, meter_type, reading, timestamp_str=None,
                                image_base64=None, notes="", **kwargs):
        return await self.async_write_reading(meter_type, reading, timestamp_str, notes, **kwargs)

    async def async_write_reading(self, meter_type, reading, timestamp_str=None, notes="",
                                  entry_id=None, kind="reading", old_reading=None, confirmation=None):
        async with self._lock:
            if meter_type not in METER_TYPES:
                raise ReadingError("Ungültiger Zählertyp / Invalid meter type")
            if kind not in ("reading", "replacement"):
                raise ReadingError("Ungültiger Eintragstyp / Invalid record type")
            if not isinstance(notes, str):
                raise ReadingError("Ungültige Notiz / Invalid note")
            before = self._readings[meter_type]
            original = next((r for r in before if r['id'] == entry_id), None)
            if entry_id and original is None:
                raise ReadingError("Ablesung nicht gefunden / Reading not found")
            if original and original.get('kind', 'reading') != kind:
                raise ReadingError("Eintragstyp darf nicht geändert werden / Record type cannot be changed")
            timestamp = parse_timestamp(timestamp_str if timestamp_str is not None else datetime.now(timezone.utc).isoformat()).isoformat()
            entry = {**(original or {}), "id": entry_id or "pending", "timestamp": timestamp,
                     "reading": number(reading, optional=kind == "replacement"), "kind": kind,
                     "notes": notes, "image_file": None}
            if kind == "replacement":
                entry['old_reading'] = number(old_reading, optional=True)
            candidate = sorted([deepcopy(r) for r in before if r['id'] != entry_id] + [entry], key=sort_key)
            warnings = validate_change(before, candidate, entry['id'], meter_type)
            token = confirmation_token(candidate, warnings)
            if warnings and confirmation != token:
                return {"warning": True, "warnings": warnings, "confirmation": token}
            if not entry_id:
                entry['id'] = str(uuid.uuid4())
            old_state = deepcopy(self._statistics)
            self._statistics.setdefault(meter_type, self._initial_statistics(meter_type))
            self._advance_statistics(meter_type, entry, candidate, editing=bool(entry_id))
            self._readings[meter_type] = candidate
            self._recalculate_metrics(meter_type)
            try:
                await self._async_save()
            except Exception:
                self._readings[meter_type] = before
                self._statistics = old_state
                raise
            self._notify_listeners()
            return entry

    async def async_delete_reading(self, meter_type, entry_id):
        async with self._lock:
            before = self._readings.get(meter_type, [])
            original = next((r for r in before if r['id'] == entry_id), None)
            if original is None:
                return False
            if original.get('kind') == 'replacement':
                raise ReadingError("Zählerwechsel bitte bearbeiten, nicht löschen / Edit a meter replacement instead of deleting it")
            candidate = [deepcopy(r) for r in before if r['id'] != entry_id]
            validate_change(before, candidate, entry_id, meter_type)
            old_state = deepcopy(self._statistics)
            self._statistics.setdefault(meter_type, self._initial_statistics(meter_type))["corrections"] = True
            # Keep the published anchor when deleting latest, to avoid counting it twice.
            self._readings[meter_type] = candidate
            self._recalculate_metrics(meter_type)
            try:
                await self._async_save()
            except Exception:
                self._readings[meter_type] = before
                self._statistics = old_state
                raise
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
                "current_reading": None,
                "last_consumption": None,
                "last_consumption_kwh": None,
                "last_cost": None,
                "daily_average": None,
                "projected_monthly_cost": None,
                "monthly_payment_diff": None,
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

        daily_avg = latest.get("daily_average")
        incomplete = daily_avg is None
        daily_avg = float(daily_avg or 0.0)
        # 30.4375 days per average month
        proj_monthly_work_cost = daily_avg * 30.4375 * unit_price
        proj_monthly_cost = proj_monthly_work_cost + base_price
        diff_to_payment = monthly_payment - proj_monthly_cost

        return {
            "current_reading": latest.get("reading", 0.0),
            "last_consumption": latest.get("consumption", 0.0),
            "last_consumption_kwh": latest.get("consumption_kwh", 0.0),
            "last_cost": latest.get("cost", 0.0),
            "daily_average": None if incomplete else daily_avg,
            "projected_monthly_cost": None if incomplete else round(proj_monthly_cost, 2),
            "monthly_payment": monthly_payment,
            "monthly_payment_diff": None if incomplete else round(diff_to_payment, 2),
            "unit": "kWh" if meter_type == METER_ELECTRICITY else "m³",
        }

    def _recalculate_metrics(self, meter_type: str) -> None:
        """Sort chronologically and calculate consumption, costs and averages."""
        items = self._readings.get(meter_type, [])
        if not items:
            return

        # Sort by timestamp ascending
        items.sort(key=sort_key)

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
            item["incomplete"] = False
            item.pop("data_issue", None)
            if i == 0:
                item["consumption"] = 0.0
                item["consumption_kwh"] = 0.0
                item["days"] = 0.0
                item["daily_average"] = 0.0
                item["cost"] = 0.0
                item["work_cost"] = 0.0
                item["base_cost"] = 0.0
                try:
                    parse_timestamp(item.get("timestamp"))
                    number(item.get("reading"))
                    if item.get("kind") == "replacement":
                        number(item.get("old_reading"))
                except ReadingError as err:
                    item["incomplete"] = True
                    item["data_issue"] = str(err)
                    for field in ("consumption", "consumption_kwh", "days", "daily_average", "cost", "work_cost", "base_cost"):
                        item[field] = None
                continue

            prev = items[i - 1]
            try:
                delta_raw, days = interval(prev, item)
                if delta_raw is None:
                    raise ReadingError("Wechselstand fehlt / Missing replacement reading")
            except ReadingError as err:
                item['incomplete'] = True
                item['data_issue'] = str(err)
                for field in ('consumption', 'consumption_kwh', 'days', 'daily_average', 'cost', 'work_cost', 'base_cost'):
                    item[field] = None
                continue

            if meter_type == METER_ELECTRICITY:
                delta_kwh = delta_raw
            else:
                # Gas: m³ converted to kWh via Brennwert and Zustandszahl
                delta_kwh = delta_raw * calorific * z_factor

            work_cost = delta_kwh * unit_price
            period_base_cost = days * daily_base_price
            total_cost = work_cost + period_base_cost
            daily_avg = delta_kwh / days

            if item.get("kind") == "replacement" and item.get("reading") is None:
                item["incomplete"] = True
                item["data_issue"] = "Neuer Anfangsstand fehlt / New starting reading missing"
            item["consumption"] = round(delta_raw, 3)
            item["consumption_kwh"] = round(delta_kwh, 2)
            item["days"] = days
            item["daily_average"] = round(daily_avg, 2)
            item["work_cost"] = round(work_cost, 2)
            item["base_cost"] = round(period_base_cost, 2)
            item["cost"] = round(total_cost, 2)

    async def _async_save(self) -> None:
        """Save readings to persistent storage."""
        await self._store.async_save({**self._extra_storage, **self._readings, "_schema": 2, "_statistics": self._statistics})
