"""The Eye On Water integration."""
import asyncio
import datetime
import logging

from .eow import Account, Client, EyeOnWaterAPIError, EyeOnWaterAuthError
from .config_flow import create_account_from_config

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    Debouncer,
    UpdateFailed,
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
    DEBOUNCE_COOLDOWN,
    DOMAIN,
    SCAN_INTERVAL,
    WATER_METER
)

_LOGGER = logging.getLogger(__name__)
_LOGGER.addHandler(logging.StreamHandler())
# _LOGGER.setLevel(logging.DEBUG)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eye On Water from a config entry."""
    account = create_account_from_config(data=entry.data)
    eye_on_water_data = EyeOnWaterData(hass, entry, account)
    try:
        await eye_on_water_data.client.authenticate()
    except EyeOnWaterAuthError:
        _LOGGER.error("Username or password was not accepted")
        return False
    except asyncio.TimeoutError as error:
        raise ConfigEntryNotReady from error

    await eye_on_water_data.setup()

    async def async_update_data():
        _LOGGER.debug("Fetching latest data")
        await eye_on_water_data.read_meters()
        await eye_on_water_data.update_statistics()
        return eye_on_water_data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Eye On Water",
        update_method=async_update_data,
        update_interval=SCAN_INTERVAL,
        request_refresh_debouncer=Debouncer(
            hass, _LOGGER, cooldown=DEBOUNCE_COOLDOWN, immediate=True
        ),
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        DATA_SMART_METER: eye_on_water_data,
    }

    asyncio.create_task(coordinator.async_refresh())

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


class EyeOnWaterData:
    """Manages coordinatation of API data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        account: Account,
    ) -> None:
        """Initialize the data coordintator."""
        self.hass = hass
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
    
    async def update_statistics(self):
        for meter in self.meters:
            
            statistic_id = meter.unique_id
            name = f"{WATER_METER} {meter.meter_uuid}"

            last_stats = await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 1, statistic_id, True, set()
            )

            now = datetime.datetime.now()

            # if not last_stats:
            #     # First time we insert 5 years of data (if available)
            #     hourly_data = await home.get_historic_data(
            #         5 * 365 * 24, production=is_production
                        
            yesterday = now - datetime.timedelta(days=1)

            statistics = await meter.get_consumption(date=yesterday.strftime('%m/%d/%Y'), client=self.client)

            metadata = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                name=self.name,
                source=DOMAIN,
                statistic_id=statistic_id,
                unit_of_measurement="GAL",
            )
            async_add_external_statistics(self.hass, metadata, statistics)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
