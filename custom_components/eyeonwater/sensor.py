"""Support for EyeOnWater sensors."""
import datetime
import logging
from typing import Any

from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from pyonwater import DataPoint, Meter

from .const import DATA_COORDINATOR, DATA_SMART_METER, DOMAIN, WATER_METER_NAME
from .statistic_helper import (
    convert_statistic_data,
    filter_newer_data,
    get_last_imported_time,
    get_statistic_metadata,
)

_LOGGER = logging.getLogger(__name__)
_LOGGER.addHandler(logging.StreamHandler())


async def build_water_meter_sensor(
    hass: HomeAssistant,
    meter: Meter,
    coordinator: Any,
    historical_sensor: bool,
) -> "EyeOnWaterSensor":
    """Build water meter sensor."""
    last_imported_time = await get_last_imported_time(
        hass=hass,
        meter=meter,
        historical_sensor=historical_sensor,
    )
    return EyeOnWaterStatistic(
        meter,
        last_imported_time,
        coordinator,
        historical_sensor=historical_sensor,
    )


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Set up the EyeOnWater sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    meters = hass.data[DOMAIN][config_entry.entry_id][DATA_SMART_METER].meters

    sensors = []
    for meter in meters:
        # Add "statistic" water meter sensor
        sensors.append(
            await build_water_meter_sensor(
                hass,
                meter,
                coordinator,
                historical_sensor=True,
            ),
        )
        sensors.append(EyeOnWaterSensor(meter, coordinator))
        sensors.append(EyeOnWaterTempSensor(meter, coordinator))

    async_add_entities(sensors, update_before_add=False)


class EyeOnWaterStatistic(CoordinatorEntity, SensorEntity):
    """Representation of an EyeOnWater sensor."""

    def __init__(
        self,
        meter: Meter,
        last_imported_time: datetime.datetime | None,
        coordinator: DataUpdateCoordinator,
        historical_sensor: bool,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.meter = meter
        self._state = None
        self._available = False
        self._historical_sensor = historical_sensor

        self._attr_name = f"{WATER_METER_NAME} {self.meter.meter_id} Statistic"
        self._attr_device_class = SensorDeviceClass.WATER
        #self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_unique_id = f"{self.meter.meter_uuid}_statistic"
        self._attr_native_unit_of_measurement = meter.native_unit_of_measurement
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.meter.meter_uuid)},
            name=f"{WATER_METER_NAME} {self.meter.meter_id}",
            model=self.meter.meter_info.reading.model,
            manufacturer=self.meter.meter_info.reading.customer_name,
            hw_version=self.meter.meter_info.reading.hardware_version,
            sw_version=self.meter.meter_info.reading.firmware_version,
        )
        self._last_historical_data: list[DataPoint] = []
        self._last_imported_time = last_imported_time

    @property
    def available(self):
        """Return True if entity is available."""
        return self._available

    @property
    def native_value(self):
        """Get the latest reading."""
        return self._state

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
        self.async_on_remove(self.coordinator.async_add_listener(self._state_update))

        if self.coordinator.last_update_success:
            return

        if last_state := await self.async_get_last_state():
            self._state = last_state.state
            self._available = True

    def import_historical_data(self):
        """Import historical data for today and past N days."""
        if not self._last_historical_data:
            _LOGGER.info("There is no new historical data")
            # Nothing to import
            return

        _LOGGER.info("%i data points will be imported", len(self._last_historical_data))
        statistics = convert_statistic_data(self._last_historical_data)
        metadata = get_statistic_metadata(
            self.meter,
            historical_sensor=self._historical_sensor,
        )

        async_import_statistics(self.hass, metadata, statistics)

    async def import_historical_data_handler(self, days: int):
        """Import historical data."""
        data = await self.meter.reader.read_historical_data(days)
        _LOGGER.info("%i data points will be imported", len(data))
        statistics = convert_statistic_data(data)
        metadata = get_statistic_metadata(
            self.meter,
            historical_sensor=self._historical_sensor,
        )
        async_import_statistics(self.hass, metadata, statistics)


class EyeOnWaterTempSensor(CoordinatorEntity, SensorEntity):
    """Representation of an EyeOnWater temperature sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        meter: Meter,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.meter = meter
        self._attr_unique_id = f"{self.meter.meter_uuid}_temperature"
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
        return self.meter.meter_info.sensors.endpoint_temperature.seven_day_min


class EyeOnWaterSensor(CoordinatorEntity, SensorEntity):
    """Representation of an EyeOnWater sensor."""

    def __init__(
        self,
        meter: Meter,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.meter = meter
        self._state = None
        self._available = False

        self._attr_has_entity_name = True
        self._attr_name = None
        self._attr_device_class = SensorDeviceClass.WATER
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_unique_id = meter.meter_uuid
        self._attr_native_unit_of_measurement = meter.native_unit_of_measurement
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.meter.meter_uuid)},
            name=f"{WATER_METER_NAME} {self.meter.meter_id}",
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
        return self._state

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
