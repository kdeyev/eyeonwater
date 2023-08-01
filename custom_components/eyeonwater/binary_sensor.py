"""Support for Eye On Water binary sensors."""
from .eow import Meter

from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

from .const import (
    DATA_COORDINATOR,
    DATA_SMART_METER,
    DOMAIN,
    WATER_LEAK_SENSOR,
)

FLAG_SENSORS = [
    BinarySensorEntityDescription(
        key="Leak",
        name="Leak Sensor",
        device_class=BinarySensorDeviceClass.MOISTURE,
    ),
]


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Eye On Water sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    meters = hass.data[DOMAIN][config_entry.entry_id][DATA_SMART_METER].meters

    sensors = []
    for meter in meters:  
        sensors.append(
            EyeOnWaterBinarySensor(meter, coordinator, description)
            for description in FLAG_SENSORS
        )

    async_add_entities(sensors, False)


class EyeOnWaterBinarySensor(CoordinatorEntity, RestoreEntity, BinarySensorEntity):
    """Representation of an EyeOnWater binary flag sensor."""

    def __init__(self, meter: Meter, coordinator: DataUpdateCoordinator, description: BinarySensorEntityDescription) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.meter = meter
        self._state = None
        self._flag = description.key
        self._available = False
        self._attr_unique_id = f"{decription.key}_{self.meter.meter_uuid}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, meter.meter_uuid)},
            name=f"Water Meter {meter.meter_info['meter_id']}",
        )

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
        return self._state == True

    @callback
    def _state_update(self):
        """Call when the coordinator has an update."""
        self._available = self.coordinator.last_update_success
        if self._available:
            self._state = self.meter.get_flags(self._flag)
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
