"""EyeOnWater coordinator."""
import logging

from pyonwater import Account, Client, EyeOnWaterAPIError, EyeOnWaterAuthError, Meter

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import UpdateFailed

from .sensor import (
    async_import_statistics,
    convert_statistic_data,
    get_statistic_metadata,
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
        self.meters: list[Meter] = []
        self.hass = hass

    async def setup(self):
        """Fetch all of the user's meters."""
        self.meters = await self.account.fetch_meters(self.client)
        _LOGGER.debug("Discovered %s meter(s)", len(self.meters))

    async def read_meters(self, days_to_load=3):
        """Read each meter."""
        for meter in self.meters:
            try:
                await meter.read_meter(client=self.client, days_to_load=days_to_load)
            except (EyeOnWaterAPIError, EyeOnWaterAuthError) as error:
                raise UpdateFailed(error) from error
        return self.meters

    async def import_historical_data(self, days: int):
        """Import historical data."""
        for meter in self.meters:
            data = await meter.reader.read_historical_data(
                client=self.client,
                days_to_load=days,
            )
            _LOGGER.info("%i data points will be imported", len(data))
            statistics = convert_statistic_data(data)
            metadata = get_statistic_metadata(meter)
            async_import_statistics(self.hass, metadata, statistics)
