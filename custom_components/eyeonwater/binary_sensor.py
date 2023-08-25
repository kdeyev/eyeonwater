"""Support for EyeOnWater binary sensors."""
from dataclasses import dataclass

from pyonwater import Meter

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DATA_COORDINATOR, DATA_SMART_METER, DOMAIN


@dataclass
class Description:
    name: str
    key: str
    translation_key: str
    device_class: BinarySensorDeviceClass


FLAG_SENSORS = [
    Description(
        name="Leak",
        key="leak`",
        translation_key="leak",
        device_class=BinarySensorDeviceClass.MOISTURE,
    ),
    Description(
        name="EmptyPipe",
        key="empty_pipe",
        translation_key="emptypipe",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    Description(
        name="Tamper",
        key="tamper",
        translation_key="tamper",
        device_class=BinarySensorDeviceClass.TAMPER,
    ),
    Description(
        name="CoverRemoved",
        key="cover_removed",
        translation_key="coverremoved",
        device_class=BinarySensorDeviceClass.TAMPER,
    ),
    Description(
        name="ReverseFlow",
        key="reverse_flow",
        translation_key="reverseflow",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    Description(
        name="LowBattery",
        key="low_battery",
        translation_key="lowbattery",
        device_class=BinarySensorDeviceClass.BATTERY,
    ),
    Description(
        name="BatteryCharging",
        key="battery_charging",
        translation_key="batterycharging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
    ),
]


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the EyeOnWater sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    meters = hass.data[DOMAIN][config_entry.entry_id][DATA_SMART_METER].meters

    sensors = []
    for meter in meters:
        for description in FLAG_SENSORS:
            sensors.append(EyeOnWaterBinarySensor(meter, coordinator, description))

    async_add_entities(sensors, False)


class EyeOnWaterBinarySensor(CoordinatorEntity, RestoreEntity, BinarySensorEntity):
    """Representation of an EyeOnWater binary flag sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        meter: Meter,
        coordinator: DataUpdateCoordinator,
        description: Description,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = BinarySensorEntityDescription(
            key=description.key,
            device_class=description.device_class,
            translation_key=description.translation_key,
        )
        self.meter = meter
        self._state = False
        self._available = False
        self._attr_unique_id = f"{description.name}_{self.meter.meter_uuid}"
        self._attr_is_on = self._state
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.meter.meter_uuid)},
            name=f"Water Meter {self.meter.meter_id}",
        )

    def get_flag(self, key: str) -> bool:
        return self.meter.meter_info.reading.flags.__dict__[self.entity_description.key]

    @callback
    def _state_update(self):
        """Call when the coordinator has an update."""
        self._available = self.coordinator.last_update_success
        if self._available:
            self._state = self.get_flags(self.entity_description.key)
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Subscribe to updates."""
        self.async_on_remove(self.coordinator.async_add_listener(self._state_update))

        if self.coordinator.last_update_success:
            return

        if last_state := await self.async_get_last_state():
            self._state = last_state.state
            self._available = True
