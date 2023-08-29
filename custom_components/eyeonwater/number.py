"""Support for EyeOnWater number sensors."""
from dataclasses import dataclass

from pyonwater import Meter

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DATA_COORDINATOR, DATA_SMART_METER, DOMAIN, WATER_METER_NAME


@dataclass
class Description:
    key: str
    device_class: NumberDeviceClass
    native_unit_of_measurement: str | None = None
    translation_key: str | None = None


NUM_SENSORS = [
    Description(
        key="temperature",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    )
]


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the EyeOnWater number sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    meters = hass.data[DOMAIN][config_entry.entry_id][DATA_SMART_METER].meters

    sensors = []
    for meter in meters:
        for description in NUM_SENSORS:
            sensors.append(EyeOnWaterNumberSensor(meter, coordinator, description))

    async_add_entities(sensors, False)


class EyeOnWaterNumberSensor(CoordinatorEntity, NumberEntity):
    """Representation of an EyeOnWater number sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        meter: Meter,
        coordinator: DataUpdateCoordinator,
        description: Description,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = NumberEntityDescription(
            key=description.key,
            device_class=description.device_class,
            translation_key=description.translation_key,
            native_unit_of_measurement=description.native_unit_of_measurement,
        )
        self.meter = meter
        self._attr_unique_id = f"{description.key}_{self.meter.meter_uuid}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.meter.meter_uuid)},
            name=f"{WATER_METER_NAME} {self.meter.meter_id}",
            model=self.meter.meter_info.reading.model,
            manufacturer=self.meter.meter_info.reading.customer_name,
            hw_version=self.meter.meter_info.reading.hardware_version,
            sw_version=self.meter.meter_info.reading.firmware_version,
        )

    @property
    def native_value(self) -> float | None:
        """Get native value."""
        return 10

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        return self.meter.meter_info.sensors.endpoint_temperature.seven_day_min
