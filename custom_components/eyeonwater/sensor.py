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
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
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

    async def _update_statistics(self):
        statistic_id = self.unique_id


        now = datetime.datetime.now()
        yesterday = now - datetime.timedelta(days=1)

        statistics = await self.meter.get_consumption(date=yesterday.strftime('%m/%d/%Y'), client=client)


        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=self.name,
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_of_measurement="GAL",
        )
        async_add_external_statistics(self.hass, metadata, statistics)

                #         statistic_id = (
                #     f"{TIBBER_DOMAIN}:energy_"
                #     f"{sensor_type.lower()}_"
                #     f"{home.home_id.replace('-', '')}"
                # )

                # last_stats = await get_instance(self.hass).async_add_executor_job(
                #     get_last_statistics, self.hass, 1, statistic_id, True, set()
                # )

                # if not last_stats:
                #     # First time we insert 5 years of data (if available)
                #     hourly_data = await home.get_historic_data(
                #         5 * 365 * 24, production=is_production
                #     )

                #     _sum = 0.0
                #     last_stats_time = None
                # else:
                #     # hourly_consumption/production_data contains the last 30 days
                #     # of consumption/production data.
                #     # We update the statistics with the last 30 days
                #     # of data to handle corrections in the data.
                #     hourly_data = (
                #         home.hourly_production_data
                #         if is_production
                #         else home.hourly_consumption_data
                #     )

                #     from_time = dt_util.parse_datetime(hourly_data[0]["from"])
                #     if from_time is None:
                #         continue
                #     start = from_time - timedelta(hours=1)
                #     stat = await get_instance(self.hass).async_add_executor_job(
                #         statistics_during_period,
                #         self.hass,
                #         start,
                #         None,
                #         {statistic_id},
                #         "hour",
                #         None,
                #         {"sum"},
                #     )
                #     first_stat = stat[statistic_id][0]
                #     _sum = cast(float, first_stat["sum"])
                #     last_stats_time = first_stat["start"]

                # statistics = []

                # last_stats_time_dt = (
                #     dt_util.utc_from_timestamp(last_stats_time)
                #     if last_stats_time
                #     else None
                # )

                # for data in hourly_data:
                #     if data.get(sensor_type) is None:
                #         continue

                #     from_time = dt_util.parse_datetime(data["from"])
                #     if from_time is None or (
                #         last_stats_time_dt is not None
                #         and from_time <= last_stats_time_dt
                #     ):
                #         continue

                #     _sum += data[sensor_type]

                #     statistics.append(
                #         StatisticData(
                #             start=from_time,
                #             state=data[sensor_type],
                #             sum=_sum,
                #         )
                #     )

                # metadata = StatisticMetaData(
                #     has_mean=False,
                #     has_sum=True,
                #     name=f"{home.name} {sensor_type}",
                #     source=TIBBER_DOMAIN,
                #     statistic_id=statistic_id,
                #     unit_of_measurement=unit,
                # )
                # async_add_external_statistics(self.hass, metadata, statistics)

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
