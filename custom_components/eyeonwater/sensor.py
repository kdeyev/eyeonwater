"""Support for EyeOnWater sensors."""
import datetime
import logging
from typing import Any

from pyonwater import DataPoint, Meter

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    get_last_statistics,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTemperature, UnitOfVolume
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import dt as dtutil

from .const import DATA_COORDINATOR, DATA_SMART_METER, DOMAIN, WATER_METER_NAME

_LOGGER = logging.getLogger(__name__)
_LOGGER.addHandler(logging.StreamHandler())


def get_statistics_id(meter_id: str) -> str:
    """Generate statistics ID for meter."""
    return f"sensor.water_meter_{meter_id.lower()}"


def get_statistic_metadata(meter: Meter) -> StatisticMetaData:
    """Build statistic metadata for a given meter."""
    name = f"{WATER_METER_NAME} {meter.meter_id}"
    statistic_id = get_statistics_id(meter.meter_id)

    return StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=name,
        source="recorder",
        statistic_id=statistic_id,
        unit_of_measurement=meter.native_unit_of_measurement,
    )


def convert_statistic_data(data: list[DataPoint]) -> list[StatisticData]:
    """Convert statistics data to HA StatisticData format."""
    return [
        StatisticData(
            start=row.dt,
            sum=row.reading,
            state=row.reading,
        )
        for row in data
    ]


async def get_last_imported_time(hass, meter):
    """Return last imported data datetime."""
    # https://github.com/home-assistant/core/blob/74e2d5c5c312cf3ba154b5206ceb19ba884c6fb4/homeassistant/components/tibber/sensor.py#L11

    statistic_id = get_statistics_id(meter.meter_id)

    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics,
        hass,
        1,
        statistic_id,
        True,
        {"start", "sum"},
    )
    _LOGGER.debug("last_stats %s", last_stats)

    if last_stats:
        date = last_stats[statistic_id][0]["start"]
        _LOGGER.debug("date %d", date)
        date = datetime.datetime.fromtimestamp(date, tz=dtutil.DEFAULT_TIME_ZONE)
        _LOGGER.debug("date %d", date)
        date = dtutil.as_local(date)
        _LOGGER.debug("date %d", date)

        return date
    return None


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the EyeOnWater sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    meters = hass.data[DOMAIN][config_entry.entry_id][DATA_SMART_METER].meters

    sensors = []
    for meter in meters:
        last_imported_time = await get_last_imported_time(hass=hass, meter=meter)
        sensors.append(EyeOnWaterSensor(meter, last_imported_time, coordinator))
        sensors.append(EyeOnWaterTempSensor(meter, coordinator))

    async_add_entities(sensors, update_before_add=False)


class EyeOnWaterSensor(CoordinatorEntity, SensorEntity):
    """Representation of an EyeOnWater sensor."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = SensorDeviceClass.WATER

    # We should not specify the state_class for workarounding the #30 issue

    def __init__(
        self,
        meter: Meter,
        last_imported_time: datetime.datetime,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.meter = meter
        self._state = None
        self._available = False
        self._attr_unique_id = meter.meter_uuid
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
    def native_unit_of_measurement(self) -> str:
        """Get the unit of measurement from reading."""
        if self.meter.meter_info.reading.latest_read.units == "GAL":
            return UnitOfVolume.GALLONS
        else:
            return UnitOfVolume.MILLILITERS

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

            self._last_historical_data = self.meter.last_historical_data.copy()
            if self._last_imported_time and self._last_historical_data:
                _LOGGER.info(
                    "_last_imported_time %d - self._last_historical_data %d",
                    self._last_imported_time,
                    self._last_historical_data[-1].dt,
                )
                self._last_historical_data = list(
                    filter(
                        lambda r: r.dt > self._last_imported_time,
                        self._last_historical_data,
                    ),
                )
                _LOGGER.info(
                    "%i data points will be imported",
                    len(self._last_historical_data),
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
        metadata = get_statistic_metadata(self.meter)

        async_import_statistics(self.hass, metadata, statistics)

    async def import_historical_data_handler(self, days: int):
        """Import historical data."""
        data = await self.meter.reader.read_historical_data(days)
        _LOGGER.info("%i data points will be imported", len(data))
        statistics = convert_statistic_data(data)
        metadata = get_statistic_metadata(self.meter)
        async_import_statistics(self.hass, metadata, statistics)


class EyeOnWaterTempSensor(CoordinatorEntity, SensorEntity):
    """Representation of an EyeOnWater temperature sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement=UnitOfTemperature.CELSIUS

    def __init__(
        self,
        meter: Meter,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.meter = meter
        self._attr_unique_id = f"temperature_{self.meter.meter_uuid}"
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
