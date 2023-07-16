"""Support for Eye On Water sensors."""
from .eow import Meter
import datetime

from homeassistant.components.sensor import STATE_CLASS_TOTAL_INCREASING, SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)


from .const import (
    DATA_COORDINATOR,
    DATA_SMART_METER,
    DOMAIN,
    WATER_LEAK_SENSOR,
    WATER_METER,
    DEVICE_CLASS_WATER
)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Eye On Water sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    meters = hass.data[DOMAIN][config_entry.entry_id][DATA_SMART_METER].meters

    sensors = []
    for meter in meters:
        sensors.append(EyeOnWaterSensor(meter, coordinator))
        sensors.append(EyeOnWaterLeakSensor(meter, coordinator))

    async_add_entities(sensors, False)


class EyeOnWaterSensor(CoordinatorEntity, RestoreEntity, SensorEntity):
    """Representation of an Eye On Water sensor."""

    _attr_device_class = DEVICE_CLASS_WATER
    _attr_state_class = STATE_CLASS_TOTAL_INCREASING

    def __init__(self, meter: Meter, coordinator: DataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.meter = meter
        self._state = None
        self._available = False
        self._attr_native_unit_of_measurement = meter.native_unit_of_measurement

    @property
    def name(self):
        """Device Name."""
        return f"{WATER_METER} {self.meter.meter_uuid}"

    @property
    def unique_id(self):
        """Device Uniqueid."""
        return f"{self.meter.meter_uuid}"

    @property
    def available(self):
        """Return True if entity is available."""
        return self._available

    @property
    def native_value(self):
        """Get the latest reading."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the device specific state attributes."""
        attributes = self.meter.attributes
        return attributes

    @callback
    def _state_update(self):
        """Call when the coordinator has an update."""
        self._available = self.coordinator.last_update_success
        if self._available:
            self._state = self.meter.reading
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Subscribe to updates."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self._state_update))

        # If the background update finished before
        # we added the entity, there is no need to restore
        # state.
        if self.coordinator.last_update_success:
            return

        if last_state := await self.async_get_last_state():
            self._state = last_state.state
            self._available = True


class EyeOnWaterLeakSensor(CoordinatorEntity, RestoreEntity, BinarySensorEntity):
    """Representation of an Eye On Water leak sensor."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, meter: Meter, coordinator: DataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.meter = meter
        self._state = None
        self._available = False

    @property
    def name(self):
        """Device Name."""
        return f"{WATER_LEAK_SENSOR} {self.meter.meter_uuid}"

    @property
    def unique_id(self):
        """Device Uniqueid."""
        return f"leak_{self.meter.meter_uuid}"

    @property
    def available(self):
        """Return True if entity is available."""
        return self._available

    @property
    def native_value(self):
        """Get the latest reading."""
        return self._state

    @property
    def is_on(self):
        """Return the status of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the device specific state attributes."""
        attributes = self.meter.attributes
        return attributes

    @callback
    def _state_update(self):
        """Call when the coordinator has an update."""
        self._available = self.coordinator.last_update_success
        if self._available:
            self._state = self.meter.has_leak
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Subscribe to updates."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self._state_update))

        # If the background update finished before
        # we added the entity, there is no need to restore
        # state.
        if self.coordinator.last_update_success:
            return

        if last_state := await self.async_get_last_state():
            self._state = last_state.state
            self._available = True
