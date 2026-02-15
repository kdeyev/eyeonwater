"""EyeOnWater coordinator."""
import logging
from typing import TYPE_CHECKING

from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import UpdateFailed
from pyonwater import Account, Client, EyeOnWaterAPIError, EyeOnWaterAuthError, Meter

from .statistic_helper import (
    convert_statistic_data,
    filter_newer_data,
    get_last_imported_time,
    get_statistic_metadata,
)

if TYPE_CHECKING:
    import datetime

_LOGGER = logging.getLogger(__name__)


class EyeOnWaterData:
    """Manages coordinatation of API data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        account: Account,
    ) -> None:
        """Initialize the data coordintator."""
        self.account = account
        websession = aiohttp_client.async_get_clientsession(hass)
        self.client = Client(websession, account)
        self.meters: list[Meter] = []
        self.hass = hass
        self._last_imported_times: dict[str, datetime.datetime | None] = {}

    async def setup(self):
        """Fetch all of the user's meters."""
        self.meters = await self.account.fetch_meters(self.client)
        _LOGGER.debug("Discovered %i meter(s)", len(self.meters))

        for meter in self.meters:
            self._last_imported_times[meter.meter_id] = await get_last_imported_time(
                self.hass,
                meter,
            )

    async def read_meters(self, days_to_load=3):
        """Read each meter."""
        for meter in self.meters:
            try:
                await meter.read_meter_info(client=self.client)
                await meter.read_historical_data(
                    client=self.client,
                    days_to_load=days_to_load,
                )
            except (EyeOnWaterAPIError, EyeOnWaterAuthError) as error:
                raise UpdateFailed(error) from error

            self._import_meter_statistics(meter)

        return self.meters

    def _import_meter_statistics(self, meter: Meter) -> None:
        """Filter and import new historical data points for a meter."""
        if not meter.last_historical_data:
            return

        last_imported = self._last_imported_times.get(meter.meter_id)
        new_data = filter_newer_data(meter.last_historical_data, last_imported)

        if not new_data:
            return

        _LOGGER.info("%i data points will be imported", len(new_data))
        statistics = convert_statistic_data(new_data)
        metadata = get_statistic_metadata(meter)
        async_add_external_statistics(self.hass, metadata, statistics)
        self._last_imported_times[meter.meter_id] = new_data[-1].dt

    async def import_historical_data(self, days: int):
        """Import historical data (service call)."""
        for meter in self.meters:
            data = await meter.read_historical_data(
                client=self.client,
                days_to_load=days,
            )
            _LOGGER.info("%i data points will be imported", len(data))
            statistics = convert_statistic_data(data)
            metadata = get_statistic_metadata(meter)
            async_add_external_statistics(self.hass, metadata, statistics)
