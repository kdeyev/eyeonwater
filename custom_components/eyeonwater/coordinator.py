"""EyeOnWater coordinator."""
import logging
import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import UpdateFailed

# from homeassistant.components.recorder import get_instance
# from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
# from homeassistant.components.recorder.statistics import (
#     async_add_external_statistics,
#     get_last_statistics,
#     statistics_during_period,
# )
# from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    async_import_statistics
)

from .const import (
    DATA_COORDINATOR,
    DATA_SMART_METER,
    DEBOUNCE_COOLDOWN,
    DOMAIN,
    SCAN_INTERVAL,
)

WATER_METER = "Water Meter"

from .config_flow import create_account_from_config
from .eow import Account, Client, EyeOnWaterAPIError, EyeOnWaterAuthError

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


    async def update_statistics(self):
        # Example: https://github.com/janmolemans/huawei_fusionsolar/blob/ea2b58ee8a537b02ab1a367107f77c5960ac9f7a/sensor.py#L101
        for meter in self.meters:
            
            # statistic_id = f"{DOMAIN}:{meter.meter_uuid}"
            name = f"{WATER_METER} {meter.meter_uuid}"
            # statistic_id = f"{WATER_METER} {meter.meter_uuid}"
            # statistic_id = f"{WATER_METER} {meter.meter_uuid}"
            statistic_id = name = f"sensor.water_meter_{meter.meter_uuid}"

            _LOGGER.info(f"adding historical statistics for {statistic_id}")

            # last_stats = await get_instance(self.hass).async_add_executor_job(
            #     get_last_statistics, self.hass, 1, statistic_id, True, set()
            # )

            now = datetime.datetime.now()

            # if not last_stats:
            #     # First time we insert 5 years of data (if available)
            #     hourly_data = await home.get_historic_data(
            #         5 * 365 * 24, production=is_production
                        
            yesterday = now - datetime.timedelta(days=7)

            data = await meter.get_consumption(date=yesterday.strftime('%m/%d/%Y'), client=self.client)

            statistics = []
            for row in data:
                statistics.append(StatisticData(
                        start=row["start"],
                        sum=row["sum"],
                        min=row["sum"], #convert to Watt
                        max=row["sum"], #convert to Watt
                    ))

            metadata = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                name=name,
                source='recorder',
                statistic_id=statistic_id,
                unit_of_measurement="GAL",
            )
            async_import_statistics(self.hass, metadata, statistics)


