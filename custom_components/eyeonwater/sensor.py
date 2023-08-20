"""Support for EyeOnWater sensors."""
import datetime
import logging

from homeassistant_historical_sensor import (
    HistoricalSensor,
    HistoricalState,
    PollUpdateMixin,
)
import pytz

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    StatisticsRow,
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


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the EyeOnWater sensors."""
    # coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    meters = hass.data[DOMAIN][config_entry.entry_id][DATA_SMART_METER].meters

    sensors = []
    for meter in meters:
        sensors.append(EyeOnWaterSensor(meter))

    async_add_entities(sensors, False)


class EyeOnWaterSensor(PollUpdateMixin, HistoricalSensor, SensorEntity):
    """Representation of an EyeOnWater sensor."""

    def __init__(self, meter: Meter) -> None:
        """Initialize the sensor."""
        super().__init__()
        self.meter = meter

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.meter.meter_uuid)},
            name=f"{WATER_METER_NAME} {self.meter.meter_id}",
        )

        self._attr_unique_id = meter.meter_uuid
        # self._attr_entity_id = self.meter.meter_id

        self._attr_has_entity_name = True
        self._attr_name = None

        self._attr_entity_registry_enabled_default = True
        self._attr_state = None

        # Define whatever you are
        self._attr_native_unit_of_measurement = meter.native_unit_of_measurement
        self._attr_device_class = SensorDeviceClass.WATER

        # We DON'T opt-in for statistics (don't set state_class). Why?
        #
        # Those statistics are generated from a real sensor, this sensor, but we don't
        # want that hass try to do anything with those statistics because we
        # (HistoricalSensor) handle generation and importing
        #
        # self._attr_state_class = SensorStateClass.MEASUREMENT

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

    # @property
    # def extra_state_attributes(self):
    #     """Return the device specific state attributes."""
    #     return self.meter.attributes["register_0"]

    async def async_update_historical(self):
        statistics = [
            HistoricalState(
                dt=row["dt"],
                state=row["reading"],
            )
            for row in self.meter.last_historical_data
        ]

        self._attr_historical_states = statistics

    @property
    def statistic_id(self) -> str:
        return self.entity_id

    def get_statistic_metadata(self) -> StatisticMetaData:
        #
        # Add sum and mean to base statistics metadata
        # Important: HistoricalSensor.get_statistic_metadata returns an
        # internal source by default.
        #
        meta = super().get_statistic_metadata()
        meta["has_sum"] = True
        meta["has_mean"] = False

        return meta

    async def async_calculate_statistic_data(
        self,
        hist_states: list[HistoricalState],
        *,
        latest: StatisticsRow | None = None,
    ) -> list[StatisticData]:
        statistics = [
            StatisticData(
                start=row.dt,
                state=row.state,
                sum=row.state,
            )
            for row in hist_states
        ]

        return statistics
