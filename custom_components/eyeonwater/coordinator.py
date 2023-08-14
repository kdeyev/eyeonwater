"""EyeOnWater coordinator."""
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import aiohttp_client, debounce
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .config_flow import create_account_from_config
from .const import (
    DATA_COORDINATOR,
    DATA_SMART_METER,
    DEBOUNCE_COOLDOWN,
    DOMAIN,
    SCAN_INTERVAL,
)
from .eow import Account, Client, EyeOnWaterAPIError, EyeOnWaterAuthError

_LOGGER = logging.getLogger(__name__)
_LOGGER.addHandler(logging.StreamHandler())



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

