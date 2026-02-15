"""Support for EyeOnWater sensors."""
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pyonwater
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DATA_COORDINATOR, DATA_SMART_METER, DOMAIN, WATER_METER_NAME
from .statistic_helper import (
    get_ha_native_unit_of_measurement,
    normalize_id,
)

if TYPE_CHECKING:
    from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)
_LOGGER.addHandler(logging.StreamHandler())


@dataclass(frozen=True, kw_only=True)
class EyeOnWaterSensorDescription(SensorEntityDescription):
    """Describe an EyeOnWater diagnostic sensor."""

    value_fn: Callable[[pyonwater.Meter], float | None]
    available_fn: Callable[[pyonwater.Meter], bool]


def _temp_available(meter: pyonwater.Meter) -> bool:
    """Check if temperature data is available."""
    return bool(
        meter.meter_info.sensors and meter.meter_info.sensors.endpoint_temperature,
    )


def _battery_available(meter: pyonwater.Meter) -> bool:
    """Check if battery data is available."""
    return meter.meter_info.reading.battery is not None


def _signal_available(meter: pyonwater.Meter) -> bool:
    """Check if signal/pwr data is available."""
    return meter.meter_info.reading.pwr is not None


TEMPERATURE_SENSORS: tuple[EyeOnWaterSensorDescription, ...] = (
    EyeOnWaterSensorDescription(
        key="temperature_7day_min",
        translation_key="temperature_7day_min",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda m: (
            m.meter_info.sensors.endpoint_temperature.seven_day_min
            if _temp_available(m)
            else None
        ),
        available_fn=_temp_available,
    ),
    EyeOnWaterSensorDescription(
        key="temperature_7day_avg",
        translation_key="temperature_7day_avg",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda m: (
            m.meter_info.sensors.endpoint_temperature.seven_day_average
            if _temp_available(m)
            else None
        ),
        available_fn=_temp_available,
    ),
    EyeOnWaterSensorDescription(
        key="temperature_7day_max",
        translation_key="temperature_7day_max",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda m: (
            m.meter_info.sensors.endpoint_temperature.seven_day_max
            if _temp_available(m)
            else None
        ),
        available_fn=_temp_available,
    ),
    EyeOnWaterSensorDescription(
        key="temperature_latest_avg",
        translation_key="temperature_latest_avg",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda m: (
            m.meter_info.sensors.endpoint_temperature.latest_average
            if _temp_available(m)
            else None
        ),
        available_fn=_temp_available,
    ),
)


BATTERY_SENSORS: tuple[EyeOnWaterSensorDescription, ...] = (
    EyeOnWaterSensorDescription(
        key="battery_level",
        translation_key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda m: m.meter_info.reading.battery.level
        if _battery_available(m)
        else None,
        available_fn=_battery_available,
    ),
)


SIGNAL_SENSORS: tuple[EyeOnWaterSensorDescription, ...] = (
    EyeOnWaterSensorDescription(
        key="signal_strength",
        translation_key="signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda m: m.meter_info.reading.pwr.signal_strength
        if _signal_available(m)
        else None,
        available_fn=_signal_available,
    ),
)


ALL_DIAGNOSTIC_SENSORS = TEMPERATURE_SENSORS + BATTERY_SENSORS + SIGNAL_SENSORS


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
        sensors.extend(
            EyeOnWaterDiagnosticSensor(meter, coordinator, description)
            for description in ALL_DIAGNOSTIC_SENSORS
            if description.available_fn(meter)
        )

    async_add_entities(sensors, update_before_add=False)


class EyeOnWaterDiagnosticSensor(CoordinatorEntity, SensorEntity):
    """Representation of an EyeOnWater diagnostic sensor."""

    _attr_has_entity_name = True
    entity_description: EyeOnWaterSensorDescription

    def __init__(
        self,
        meter: pyonwater.Meter,
        coordinator: DataUpdateCoordinator,
        description: EyeOnWaterSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self.meter = meter
        self._uuid = normalize_id(meter.meter_uuid)
        self._id = normalize_id(meter.meter_id)

        self._attr_unique_id = f"{self._uuid}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._uuid)},
            name=f"{WATER_METER_NAME} {self._id}",
            model=self.meter.meter_info.reading.model,
            manufacturer=self.meter.meter_info.reading.customer_name,
            hw_version=self.meter.meter_info.reading.hardware_version,
            sw_version=self.meter.meter_info.reading.firmware_version,
        )

        # Set unit dynamically for flow sensors (uses meter's native unit).
        if (
            description.device_class == SensorDeviceClass.WATER
            and not description.native_unit_of_measurement
        ):
            self._attr_native_unit_of_measurement = get_ha_native_unit_of_measurement(
                meter.native_unit_of_measurement,
            )

    @property
    def native_value(self) -> float | None:
        """Get native value."""
        return self.entity_description.value_fn(self.meter)


class EyeOnWaterSensor(CoordinatorEntity, SensorEntity):
    """Representation of an EyeOnWater sensor."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = SensorDeviceClass.WATER

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
