"""EyeOnWater integration."""

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import debounce
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pyonwater import EyeOnWaterAuthError

from .config_flow import create_account_from_config
from .const import (
    DATA_COORDINATOR,
    DATA_SMART_METER,
    DEBOUNCE_COOLDOWN,
    DOMAIN,
    IMPORT_HISTORICAL_DATA_DAYS_DEFAULT,
    IMPORT_HISTORICAL_DATA_DAYS_NAME,
    IMPORT_HISTORICAL_DATA_SERVICE_NAME,
    SCAN_INTERVAL,
)
from .coordinator import EyeOnWaterData

_LOGGER = logging.getLogger(__name__)
_LOGGER.addHandler(logging.StreamHandler())

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eye On Water from a config entry."""
    account = create_account_from_config(hass, entry.data)
    eye_on_water_data = EyeOnWaterData(hass, account)
    try:
        await eye_on_water_data.client.authenticate()
    except EyeOnWaterAuthError:
        _LOGGER.exception("Username or password was not accepted")
        return False
    except asyncio.TimeoutError as error:
        raise ConfigEntryNotReady from error

    try:
        await eye_on_water_data.setup()
    except Exception:
        _LOGGER.exception("Fetching meters failed")
        raise

    async def async_update_data():
        _LOGGER.debug("Fetching latest data")
        await eye_on_water_data.read_meters(days_to_load=3)
        return eye_on_water_data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="EyeOnWater",
        update_method=async_update_data,
        update_interval=SCAN_INTERVAL,
        request_refresh_debouncer=debounce.Debouncer(
            hass,
            _LOGGER,
            cooldown=DEBOUNCE_COOLDOWN,
            immediate=True,
        ),
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        DATA_SMART_METER: eye_on_water_data,
    }

    hass.async_create_task(coordinator.async_refresh())

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Add listener for options changes to reload entry when sensor mode is toggled
    entry.async_on_modify(lambda: hass.async_create_task(
        hass.config_entries.async_reload(entry.entry_id)
    ))

    async def async_service_handler(call: ServiceCall) -> None:
        days = call.data.get(
            IMPORT_HISTORICAL_DATA_DAYS_NAME,
            IMPORT_HISTORICAL_DATA_DAYS_DEFAULT,
        )
        await eye_on_water_data.import_historical_data(days)

    hass.services.async_register(
        DOMAIN,
        IMPORT_HISTORICAL_DATA_SERVICE_NAME,
        async_service_handler,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
