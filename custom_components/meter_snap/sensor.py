"""Sensor platform for MeterSnap."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ELEC_ENABLED,
    CONF_GAS_ENABLED,
    DOMAIN,
    METER_ELECTRICITY,
    METER_GAS,
    VERSION,
)
from .coordinator import MeterSnapCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MeterSnap sensor entities based on config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: MeterSnapCoordinator = data["coordinator"]
    cfg = coordinator.config

    entities: list[SensorEntity] = []

    # Electricity sensors
    if cfg.get(CONF_ELEC_ENABLED, True):
        entities.extend(
            [
                MeterSnapReadingSensor(
                    coordinator,
                    METER_ELECTRICITY,
                    "strom_stand",
                    "Stromzähler Stand",
                    UnitOfEnergy.KILO_WATT_HOUR,
                    SensorDeviceClass.ENERGY,
                    SensorStateClass.TOTAL_INCREASING,
                ),
                MeterSnapLastConsumptionSensor(
                    coordinator,
                    METER_ELECTRICITY,
                    "strom_verbrauch_letzter",
                    "Stromverbrauch Letzter Zeitraum",
                    UnitOfEnergy.KILO_WATT_HOUR,
                    SensorDeviceClass.ENERGY,
                ),
                MeterSnapLastCostSensor(
                    coordinator,
                    METER_ELECTRICITY,
                    "strom_kosten_letzter",
                    "Stromkosten Letzter Zeitraum",
                ),
                MeterSnapProjectedCostSensor(
                    coordinator,
                    METER_ELECTRICITY,
                    "strom_monatsprognose",
                    "Strom Monatsprognose Kosten",
                ),
            ]
        )

    # Gas sensors
    if cfg.get(CONF_GAS_ENABLED, True):
        entities.extend(
            [
                MeterSnapReadingSensor(
                    coordinator,
                    METER_GAS,
                    "gas_stand",
                    "Gaszähler Stand",
                    UnitOfVolume.CUBIC_METERS,
                    SensorDeviceClass.GAS,
                    SensorStateClass.TOTAL_INCREASING,
                ),
                MeterSnapGasEnergySensor(
                    coordinator,
                    "gas_energie_stand",
                    "Gaszähler Stand (Energie)",
                ),
                MeterSnapLastConsumptionSensor(
                    coordinator,
                    METER_GAS,
                    "gas_verbrauch_letzter",
                    "Gasverbrauch Letzter Zeitraum",
                    UnitOfVolume.CUBIC_METERS,
                    SensorDeviceClass.GAS,
                ),
                MeterSnapLastCostSensor(
                    coordinator,
                    METER_GAS,
                    "gas_kosten_letzter",
                    "Gaskosten Letzter Zeitraum",
                ),
                MeterSnapProjectedCostSensor(
                    coordinator,
                    METER_GAS,
                    "gas_monatsprognose",
                    "Gas Monatsprognose Kosten",
                ),
            ]
        )

    async_add_entities(entities, update_before_add=True)


class MeterSnapBaseSensor(SensorEntity):
    """Base sensor entity for MeterSnap."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MeterSnapCoordinator,
        meter_type: str,
        unique_key: str,
        name: str,
    ) -> None:
        self.coordinator = coordinator
        self.meter_type = meter_type
        self._attr_unique_id = f"{DOMAIN}_{coordinator.config_entry.entry_id}_{unique_key}"
        self._attr_name = name
        self._remove_listener = None

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        meter_title = "Stromzähler" if self.meter_type == METER_ELECTRICITY else "Gaszähler"
        return {
            "identifiers": {(DOMAIN, f"{self.coordinator.config_entry.entry_id}_{self.meter_type}")},
            "name": f"MeterSnap {meter_title}",
            "manufacturer": "MeterSnap",
            "model": "Visual Meter Reader",
            "sw_version": VERSION,
        }

    async def async_added_to_hass(self) -> None:
        """Register callbacks when added to hass."""
        self._remove_listener = self.coordinator.register_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callbacks when removed."""
        if self._remove_listener:
            self._remove_listener()

    @callback
    def _handle_update(self) -> None:
        """Handle updated data from coordinator."""
        self.async_write_ha_state()


class MeterSnapReadingSensor(MeterSnapBaseSensor):
    """Persisted forward-only total; physical reading remains an attribute."""

    def __init__(
        self,
        coordinator: MeterSnapCoordinator,
        meter_type: str,
        unique_key: str,
        name: str,
        unit: str,
        device_class: SensorDeviceClass,
        state_class: SensorStateClass,
    ) -> None:
        super().__init__(coordinator, meter_type, unique_key, name)
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class

    @property
    def native_value(self) -> float | None:
        """Return the recorder-safe persisted total."""
        return self.coordinator.get_statistics(self.meter_type).get("total")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        latest = self.coordinator.get_latest_reading(self.meter_type)
        if not latest:
            return {}
        return {
            "physical_reading": latest.get("reading"),
            "statistics_corrections": self.coordinator.get_statistics(self.meter_type).get("corrections", False),
            "statistics_policy": "forward_only",
            "timestamp": latest.get("timestamp"),
            "daily_average": latest.get("daily_average"),
            "image_file": latest.get("image_file"),
            "notes": latest.get("notes"),
        }


class MeterSnapGasEnergySensor(MeterSnapBaseSensor):
    """Persisted gas energy total, advanced only for newly reported intervals."""

    def __init__(
        self,
        coordinator: MeterSnapCoordinator,
        unique_key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator, METER_GAS, unique_key, name)
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> float | None:
        """Return the total gas in kWh."""
        return self.coordinator.get_statistics(METER_GAS).get("energy")


class MeterSnapLastConsumptionSensor(MeterSnapBaseSensor):
    """Sensor for consumption in the last recorded interval."""

    def __init__(
        self,
        coordinator: MeterSnapCoordinator,
        meter_type: str,
        unique_key: str,
        name: str,
        unit: str,
        device_class: SensorDeviceClass,
    ) -> None:
        super().__init__(coordinator, meter_type, unique_key, name)
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class

    @property
    def native_value(self) -> float | None:
        """Return last consumption value."""
        latest = self.coordinator.get_latest_reading(self.meter_type)
        if latest:
            return latest.get("consumption")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return interval attributes."""
        latest = self.coordinator.get_latest_reading(self.meter_type)
        if not latest:
            return {}
        return {
            "period_days": latest.get("days"),
            "daily_average": latest.get("daily_average"),
            "consumption_kwh": latest.get("consumption_kwh"),
        }


class MeterSnapLastCostSensor(MeterSnapBaseSensor):
    """Sensor for cost of the last recorded interval."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"

    def __init__(
        self,
        coordinator: MeterSnapCoordinator,
        meter_type: str,
        unique_key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator, meter_type, unique_key, name)

    @property
    def native_value(self) -> float | None:
        """Return cost in EUR."""
        latest = self.coordinator.get_latest_reading(self.meter_type)
        if latest:
            return latest.get("cost")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return cost breakdown attributes."""
        latest = self.coordinator.get_latest_reading(self.meter_type)
        if not latest:
            return {}
        return {
            "work_cost": latest.get("work_cost"),
            "base_cost": latest.get("base_cost"),
            "period_days": latest.get("days"),
        }


class MeterSnapProjectedCostSensor(MeterSnapBaseSensor):
    """Sensor for monthly projected cost based on recent daily average."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "EUR"

    def __init__(
        self,
        coordinator: MeterSnapCoordinator,
        meter_type: str,
        unique_key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator, meter_type, unique_key, name)

    @property
    def native_value(self) -> float | None:
        """Return projected monthly cost in EUR."""
        kpis = self.coordinator.get_kpis(self.meter_type)
        return kpis.get("projected_monthly_cost")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return projection attributes."""
        kpis = self.coordinator.get_kpis(self.meter_type)
        return {
            "monthly_payment": kpis.get("monthly_payment"),
            "monthly_payment_diff": kpis.get("monthly_payment_diff"),
            "daily_average": kpis.get("daily_average"),
        }
