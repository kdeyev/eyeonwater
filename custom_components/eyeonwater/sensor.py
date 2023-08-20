"""Support for EyeOnWater sensors."""
import datetime
import logging

import pytz

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    get_last_statistics,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DATA_COORDINATOR, DATA_SMART_METER, DOMAIN, WATER_METER_NAME
from .eow import Meter

_LOGGER = logging.getLogger(__name__)
_LOGGER.addHandler(logging.StreamHandler())


def get_statistics_id(meter) -> str:
    return f"sensor.water_meter_{meter.meter_id}"


async def get_last_imported_time(hass, meter):
    # https://github.com/home-assistant/core/blob/74e2d5c5c312cf3ba154b5206ceb19ba884c6fb4/homeassistant/components/tibber/sensor.py#L11

    statistic_id = get_statistics_id(meter)

    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, set(["start", "sum"])
    )
    _LOGGER.warning(f"last_stats {last_stats}")

    if last_stats:
        date = last_stats[statistic_id][0]["start"]
        _LOGGER.warning(f"date {date}")
        date = datetime.datetime.fromtimestamp(date)
        _LOGGER.warning(f"date {date}")
        date = pytz.UTC.localize(date)
        _LOGGER.warning(f"date {date}")

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

    async_add_entities(sensors, False)


class EyeOnWaterSensor(CoordinatorEntity, SensorEntity):
    """Representation of an EyeOnWater sensor."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self, meter: Meter, last_imported_time, coordinator: DataUpdateCoordinator
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.meter = meter
        self._state = None
        self._available = False
        self._attr_unique_id = meter.meter_uuid
        self._attr_native_unit_of_measurement = meter.native_unit_of_measurement
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.meter.meter_uuid)},
            name=f"{WATER_METER_NAME} {self.meter.meter_id}",
        )
        self._last_historical_data = []
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
    def extra_state_attributes(self):
        """Return the device specific state attributes."""
        return self.meter.attributes["register_0"]

    @callback
    def _state_update(self):
        """Call when the coordinator has an update."""
        self._available = self.coordinator.last_update_success
        if self._available:
            self._state = self.meter.reading

            self._last_historical_data = self.meter.last_historical_data.copy()
            if self._last_imported_time:
                _LOGGER.warning(
                    f"_last_imported_time {self._last_imported_time} - self._last_historical_data {self._last_historical_data[-1]['start']}"
                )
                self._last_historical_data = list(
                    filter(
                        lambda r: r["start"] > self._last_imported_time,
                        self._last_historical_data,
                    )
                )
                _LOGGER.warning(
                    f"{len(self._last_historical_data)} data points will be imported"
                )

            if self._last_historical_data:
                self.import_historical_data()

                self._last_imported_time = self._last_historical_data[-1]["start"]

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
            _LOGGER.warning("There is no new historical data")
            # Nothing to import
            return

        _LOGGER.warning(
            f"{len(self._last_historical_data)} data points will be imported"
        )

        statistics = [
            StatisticData(
                start=row["start"],
                sum=row["sum"],
                state=row["sum"],
            )
            for row in self._last_historical_data
        ]

        name = f"{WATER_METER_NAME} {self.meter.meter_id}"
        statistic_id = get_statistics_id(self.meter)

        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=name,
            source="recorder",
            statistic_id=statistic_id,
            unit_of_measurement=self.meter.native_unit_of_measurement,
        )
        async_import_statistics(self.hass, metadata, statistics)
