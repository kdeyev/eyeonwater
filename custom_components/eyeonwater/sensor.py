"""Support for EyeOnWater sensors."""
import contextlib
import logging
from typing import TYPE_CHECKING, Any

import pyonwater
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    CONF_UNIT_PRICE,
    DATA_COORDINATOR,
    DATA_SMART_METER,
    DOMAIN,
    WATER_METER_NAME,
)
from .statistic_helper import (
    get_ha_native_unit_of_measurement,
    normalize_id,
)

if TYPE_CHECKING:
    from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)
_LOGGER.addHandler(logging.StreamHandler())


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the EyeOnWater sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    meters = hass.data[DOMAIN][config_entry.entry_id][DATA_SMART_METER].meters

    sensors: list[Entity] = []
    for meter in meters:
        sensors.append(EyeOnWaterSensor(meter, coordinator))
        sensors.append(EyeOnWaterCostSensor(meter, coordinator, config_entry))
        if meter.meter_info.sensors and meter.meter_info.sensors.endpoint_temperature:
            sensors.append(EyeOnWaterTempSensor(meter, coordinator))

    async_add_entities(sensors, update_before_add=False)


class EyeOnWaterTempSensor(CoordinatorEntity, SensorEntity):
    """Representation of an EyeOnWater temperature sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        meter: pyonwater.Meter,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.meter = meter
        self._uuid = normalize_id(meter.meter_uuid)
        self._id = normalize_id(meter.meter_id)

        self._attr_unique_id = f"{self._uuid}_temperature"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._uuid)},
            name=f"{WATER_METER_NAME} {self._id}",
            model=self.meter.meter_info.reading.model,
            manufacturer=self.meter.meter_info.reading.customer_name,
            hw_version=self.meter.meter_info.reading.hardware_version,
            sw_version=self.meter.meter_info.reading.firmware_version,
        )

    @property
    def native_value(self) -> float | None:
        """Get native value."""
        if (
            self.meter.meter_info.sensors
            and self.meter.meter_info.sensors.endpoint_temperature
        ):
            return self.meter.meter_info.sensors.endpoint_temperature.seven_day_min

        return None


class EyeOnWaterSensor(CoordinatorEntity, SensorEntity):
    """Representation of an EyeOnWater sensor."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        meter: pyonwater.Meter,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.meter = meter
        self._uuid = normalize_id(meter.meter_uuid)
        self._id = normalize_id(meter.meter_id)

        self._state: pyonwater.DataPoint | None = None
        self._available = False

        self._attr_unique_id = self._uuid
        self._attr_native_unit_of_measurement = get_ha_native_unit_of_measurement(
            meter.native_unit_of_measurement,
        )
        self._attr_suggested_display_precision = 0
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._uuid)},
            name=f"{WATER_METER_NAME} {self._id}",
            model=self.meter.meter_info.reading.model,
            manufacturer=self.meter.meter_info.reading.customer_name,
            hw_version=self.meter.meter_info.reading.hardware_version,
            sw_version=self.meter.meter_info.reading.firmware_version,
        )

    @property
    def available(self):
        """Return True if entity is available."""
        return self._available

    @property
    def native_value(self):
        """Get the latest reading."""
        return self._state.reading

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the device specific state attributes."""
        return self.meter.meter_info.reading.dict()

    @callback
    def _state_update(self):
        """Call when the coordinator has an update."""
        self._available = self.coordinator.last_update_success
        if self._available:
            self._state = self.meter.reading
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Subscribe to updates."""
        self.async_on_remove(self.coordinator.async_add_listener(self._state_update))

        if self.coordinator.last_update_success:
            return

        if last_state := await self.async_get_last_state():
            self._state = last_state.state
            self._available = True


class EyeOnWaterCostSensor(CoordinatorEntity, RestoreEntity, SensorEntity):
    """Representation of an EyeOnWater cost sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "water_cost"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        meter: pyonwater.Meter,
        coordinator: DataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the cost sensor."""
        super().__init__(coordinator)
        self.meter = meter
        self._config_entry = config_entry
        self._uuid = normalize_id(meter.meter_uuid)
        self._id = normalize_id(meter.meter_id)
        self._cost: float = 0.0
        self._last_reading: float | None = None
        self._available = False

        self._attr_unique_id = f"{self._uuid}_cost"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._uuid)},
            name=f"{WATER_METER_NAME} {self._id}",
            model=self.meter.meter_info.reading.model,
            manufacturer=self.meter.meter_info.reading.customer_name,
            hw_version=self.meter.meter_info.reading.hardware_version,
            sw_version=self.meter.meter_info.reading.firmware_version,
        )

    @property
    def _unit_price(self) -> float | None:
        """Return the configured unit price."""
        price = self._config_entry.options.get(CONF_UNIT_PRICE)
        if price is not None and price > 0:
            return price
        return None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the currency from HA config."""
        if self.hass and self.hass.config.currency:
            return self.hass.config.currency
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available and self._unit_price is not None

    @property
    def native_value(self) -> float | None:
        """Get the current cumulative cost."""
        if self._unit_price is None:
            return None
        return self._cost

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for debugging and restore."""
        return {
            "unit_price": self._unit_price,
            "last_reading": self._last_reading,
        }

    @callback
    def _state_update(self) -> None:
        """Call when the coordinator has an update."""
        self._available = self.coordinator.last_update_success
        if self._available and self.meter.reading and self._unit_price is not None:
            current_reading = self.meter.reading.reading
            if self._last_reading is not None and current_reading > self._last_reading:
                delta = current_reading - self._last_reading
                self._cost += delta * self._unit_price
            self._last_reading = current_reading
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates and restore previous state."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self._state_update),
        )

        if self.coordinator.last_update_success:
            return

        if last_state := await self.async_get_last_state():
            try:
                if last_state.state not in (None, "unknown", "unavailable"):
                    self._cost = float(last_state.state)
            except (ValueError, TypeError):
                self._cost = 0.0

            if last_state.attributes.get("last_reading") is not None:
                with contextlib.suppress(ValueError, TypeError):
                    self._last_reading = float(
                        last_state.attributes["last_reading"],
                    )

            self._available = True
