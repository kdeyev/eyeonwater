"""EyeOnWater coordinator."""
import datetime
import logging

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import WATER_METER_NAME
from .eow import (
    Account,
    Client,
    EyeOnWaterAPIError,
    EyeOnWaterAuthError,
    EyeOnWaterResponseIsEmpty,
    Meter,
)

_LOGGER = logging.getLogger(__name__)


class EyeOnWaterData:
    """Manages coordinatation of API data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        account: Account,
    ) -> None:
        """Initialize the data coordintator."""
        self._entry = entry
        self.account = account
        websession = aiohttp_client.async_get_clientsession(hass)
        self.client = Client(websession, account)
        self.meters: list = []
        self.hass = hass

    async def setup(self):
        """Fetch all of the user's meters."""
        self.meters = await self.account.fetch_meters(self.client)
        _LOGGER.debug("Discovered %s meter(s)", len(self.meters))

    async def read_meters(self):
        """Read each meter."""
        for meter in self.meters:
            try:
                await meter.read_meter(self.client)
            except (EyeOnWaterAPIError, EyeOnWaterAuthError) as error:
                raise UpdateFailed(error) from error
        return self.meters

    async def import_historical_data(self, days_to_load: int = 2):
        """Import historical data for today and past N days."""
        for meter in self.meters:
            statistics = await self.get_historical_data(meter, days_to_load)

            if statistics:
                name = f"{WATER_METER_NAME} {meter.meter_id}"
                statistic_id = name = f"sensor.water_meter_{meter.meter_id.lower()}"

                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=name,
                    source="recorder",
                    statistic_id=statistic_id,
                    unit_of_measurement=meter.native_unit_of_measurement,
                )
                async_import_statistics(self.hass, metadata, statistics)

    async def get_historical_data(
        self,
        meter: Meter,
        days_to_load: int = 2,
    ) -> list[StatisticData]:
        """Retrieve historical data for today and past N days."""
        today = datetime.datetime.now().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        date_list = [today - datetime.timedelta(days=x) for x in range(0, days_to_load)]

        if meter.metric_measurement_system:
            units = "CM"
        else:
            units = meter.native_unit_of_measurement.upper()

        message = (
            f"adding historical statistics for {meter.meter_id} on {date_list} with units {units}",
        )
        _LOGGER.info(message)

        statistics = []

        for date in date_list:
            _LOGGER.debug(
                f"requesting historical statistics for {meter.meter_id} on {date} with units {units}",
            )
            try:
                data = await meter.get_historical_data(
                    date=date,
                    units=units,
                    client=self.client,
                )
            except EyeOnWaterResponseIsEmpty:
                # Suppress this exception. It's valid situation when data was not reported by EOW for the requested day
                continue
            except (EyeOnWaterAPIError, EyeOnWaterAuthError) as error:
                raise UpdateFailed(error) from error

            for row in data:
                _LOGGER.debug(row)
                if row["reading"] > 0:
                    statistics.append(
                        StatisticData(
                            start=row["dt"],
                            sum=row["reading"],
                        ),
                    )

        return statistics
