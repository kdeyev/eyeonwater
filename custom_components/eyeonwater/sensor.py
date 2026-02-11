"""Support for EyeOnWater sensors."""

import datetime
import logging
from typing import TYPE_CHECKING, Any

import pyonwater
from homeassistant import exceptions
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from propcache.api import cached_property

from .const import (
    DATA_COORDINATOR,
    DATA_SMART_METER,
    DOMAIN,
    USE_SINGLE_SENSOR_MODE,
    USE_SINGLE_SENSOR_MODE_DEFAULT,
    WATER_METER_NAME,
)
from .statistic_helper import (
    convert_statistic_data,
    filter_newer_data,
    get_ha_native_unit_of_measurement,
    get_last_imported_time,
    get_statistic_metadata,
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
    """Set up the EyeOnWater sensors.

    Supports two modes:
    - Single-sensor mode (new): One sensor per meter with state
    - Two-sensor mode (legacy, deprecated): Separate statistics and display
    """
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    meters = hass.data[DOMAIN][config_entry.entry_id][DATA_SMART_METER].meters

    # Check if single-sensor mode is enabled via config option
    use_single_sensor = config_entry.options.get(
        USE_SINGLE_SENSOR_MODE,
        USE_SINGLE_SENSOR_MODE_DEFAULT,
    )

    sensors: list[Entity] = []
    for meter in meters:
        last_imported_time = await get_last_imported_time(hass, meter)

        if use_single_sensor:
            # Single-sensor mode (new architecture)
            sensors.append(
                EyeOnWaterUnifiedSensor(
                    meter,
                    coordinator,
                    last_imported_time=last_imported_time,
                ),
            )
        else:
            # Legacy: Two-sensor mode (old architecture) - DEPRECATED
            _LOGGER.warning(
                "Using legacy two-sensor mode for meter %s. "
                "This is deprecated and will be removed in a future release. "
                "Enable single-sensor mode in integration options.",
                meter.meter_id,
            )
            sensors.append(
                EyeOnWaterStatistic(
                    meter,
                    coordinator,
                    last_imported_time=last_imported_time,
                ),
            )
            sensors.append(EyeOnWaterSensor(meter, coordinator))

        if meter.meter_info.sensors and meter.meter_info.sensors.endpoint_temperature:
            sensors.append(EyeOnWaterTempSensor(meter, coordinator))

    async_add_entities(sensors, update_before_add=False)


class NoDataFound(exceptions.HomeAssistantError):
    """Error to indicate there is no data."""


class EyeOnWaterUnifiedSensor(RestoreEntity, SensorEntity):
    """Unified EyeOnWater sensor (Single Sensor Mode).

    Combines historical data import and live readings into a single sensor.
    Replaces legacy two-sensor with cleaner single-sensor design.
    """

    _attr_has_entity_name = False
    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_should_poll = False

    def __init__(
        self,
        meter: pyonwater.Meter,
        coordinator: DataUpdateCoordinator,
        last_imported_time: datetime.datetime | None,
    ) -> None:
        """Initialize the unified sensor."""
        super().__init__()
        self.coordinator = coordinator
        self.meter = meter
        self._uuid = normalize_id(meter.meter_uuid)
        self._id = normalize_id(meter.meter_id)

        self._state: pyonwater.DataPoint | None = None
        self._available = False
        self._last_historical_data: list[pyonwater.DataPoint] = []
        self._last_imported_time = last_imported_time

        self._attr_name = f"{WATER_METER_NAME} {self._id}"
        self._attr_unique_id = self._uuid
        unit_str = meter.native_unit_of_measurement
        unit_enum = pyonwater.NativeUnits(unit_str)
        self._attr_native_unit_of_measurement = get_ha_native_unit_of_measurement(
            unit_enum,
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

    @cached_property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @cached_property
    def native_value(self):
        """Get the latest reading."""
        if self._state:
            return self._state.reading
        return None

    @cached_property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the device specific state attributes."""
        if self._state:
            return self.meter.meter_info.reading.model_dump()
        return {}

    @callback
    def _state_update(self):
        """Call when the coordinator has an update."""
        self._available = self.coordinator.last_update_success
        if self._available:
            self._state = self.meter.reading

            if not self.meter.last_historical_data:
                msg = "Meter doesn't have recent readings"
                raise NoDataFound(msg)

            self._last_historical_data = filter_newer_data(
                self.meter.last_historical_data,
                self._last_imported_time,
            )
            if self._last_historical_data:
                self.import_historical_data()
                self._last_imported_time = self._last_historical_data[-1].dt

        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Subscribe to updates."""
        listener = self.coordinator.async_add_listener(self._state_update)
        self.async_on_remove(listener)

        # Restore initial state availability flag if available
        if self.coordinator.last_update_success:
            return

        last_state = await self.async_get_last_state()
        if last_state:
            self._available = True

    def import_historical_data(self):
        """Import historical data for today and past N days."""
        if not self._last_historical_data:
            _LOGGER.info("There is no new historical data")
            return

        history_len = len(self._last_historical_data)
        _LOGGER.info("%i data points will be imported", history_len)
        statistics = convert_statistic_data(self._last_historical_data)
        metadata = get_statistic_metadata(self.meter)

        async_import_statistics(self.hass, metadata, statistics)


class EyeOnWaterStatistic(RestoreEntity, SensorEntity):
    """Representation of an EyeOnWater historical statistics sensor.

    DEPRECATED: This is part of the legacy two-sensor architecture.
    Use EyeOnWaterUnifiedSensor instead.
    """

    def __init__(
        self,
        meter: pyonwater.Meter,
        coordinator: DataUpdateCoordinator,
        last_imported_time: datetime.datetime | None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self.coordinator = coordinator
        self.meter = meter
        self._uuid = normalize_id(meter.meter_uuid)
        self._id = normalize_id(meter.meter_id)

        self._state: pyonwater.DataPoint | None = None
        self._available = False
        self._historical_sensor = True

        self._attr_name = f"{WATER_METER_NAME} {self._id} Statistic"
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_unique_id = f"{self._uuid}_statistic"
        unit_str = meter.native_unit_of_measurement
        unit_enum = pyonwater.NativeUnits(unit_str)
        self._attr_native_unit_of_measurement = get_ha_native_unit_of_measurement(
            unit_enum,
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
        self._last_historical_data: list[pyonwater.DataPoint] = []
        self._last_imported_time = last_imported_time

    @cached_property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @cached_property
    def native_value(self):
        """Get the latest reading."""
        if self._state:
            return self._state.reading
        return None

    @callback
    def _state_update(self):
        """Call when the coordinator has an update."""
        self._available = self.coordinator.last_update_success
        if self._available:
            self._state = self.meter.reading

            if not self.meter.last_historical_data:
                msg = "Meter doesn't have recent readings"
                raise NoDataFound(msg)

            self._last_historical_data = filter_newer_data(
                self.meter.last_historical_data,
                self._last_imported_time,
            )
            if self._last_historical_data:
                self.import_historical_data()
                self._last_imported_time = self._last_historical_data[-1].dt

        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Subscribe to updates."""
        listener = self.coordinator.async_add_listener(self._state_update)
        self.async_on_remove(listener)

        # Restore initial state availability flag if available
        if self.coordinator.last_update_success:
            return

        last_state = await self.async_get_last_state()
        if last_state:
            self._available = True

    def import_historical_data(self):
        """Import historical data for today and past N days."""
        if not self._last_historical_data:
            _LOGGER.info("There is no new historical data")
            # Nothing to import
            return

        history_len = len(self._last_historical_data)
        _LOGGER.info("%i data points will be imported", history_len)
        statistics = convert_statistic_data(self._last_historical_data)
        metadata = get_statistic_metadata(self.meter)

        async_import_statistics(self.hass, metadata, statistics)


class EyeOnWaterTempSensor(SensorEntity):
    """Representation of an EyeOnWater temperature sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_should_poll = False

    def __init__(
        self,
        meter: pyonwater.Meter,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self.coordinator = coordinator
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

    @cached_property
    def native_value(self) -> float | None:
        """Get native value."""
        if (
            self.meter.meter_info.sensors
            and self.meter.meter_info.sensors.endpoint_temperature
        ):
            temp = self.meter.meter_info.sensors.endpoint_temperature
            return temp.seven_day_min

        return None

    @cached_property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @callback
    def _state_update(self) -> None:
        """Call when the coordinator has an update."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        self.async_on_remove(self.coordinator.async_add_listener(self._state_update))


class EyeOnWaterSensor(RestoreEntity, SensorEntity):
    """Representation of an EyeOnWater live readings sensor.

    DEPRECATED: This is part of the legacy two-sensor architecture.
    Use EyeOnWaterUnifiedSensor instead.
    """

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_should_poll = False

    def __init__(
        self,
        meter: pyonwater.Meter,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self.coordinator = coordinator
        self.meter = meter
        self._uuid = normalize_id(meter.meter_uuid)
        self._id = normalize_id(meter.meter_id)

        self._state: pyonwater.DataPoint | None = None
        self._available = False

        self._attr_unique_id = self._uuid
        unit_str = meter.native_unit_of_measurement
        unit_enum = pyonwater.NativeUnits(unit_str)
        self._attr_native_unit_of_measurement = get_ha_native_unit_of_measurement(
            unit_enum,
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

    @cached_property
    def available(self):
        """Return True if entity is available."""
        return self._available

    @cached_property
    def native_value(self):
        """Get the latest reading."""
        if self._state:
            return self._state.reading
        return None

    @cached_property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the device specific state attributes."""
        return self.meter.meter_info.reading.model_dump()

    @callback
    def _state_update(self):
        """Call when the coordinator has an update."""
        self._available = self.coordinator.last_update_success
        if self._available:
            self._state = self.meter.reading
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Subscribe to updates."""
        listener = self.coordinator.async_add_listener(self._state_update)
        self.async_on_remove(listener)

        # Restore initial state availability flag if available
        if self.coordinator.last_update_success:
            return

        last_state = await self.async_get_last_state()
        if last_state:
            self._available = True
