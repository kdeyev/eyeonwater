"""Tests for the EyeOnWater __init__ (setup / unload)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from pyonwater import EyeOnWaterAuthError

from custom_components.eyeonwater import async_setup_entry, async_unload_entry
from custom_components.eyeonwater.const import (
    DATA_COORDINATOR,
    DATA_SMART_METER,
    DOMAIN,
)

from .conftest import (
    MOCK_CONFIG,
    _make_hass,
    _make_meter,
)


def _mock_config_entry() -> ConfigEntry:
    """Create a minimal fake ConfigEntry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = MOCK_CONFIG
    entry.title = "test@example.com"
    return entry


@pytest.fixture
def config_entry() -> ConfigEntry:
    """Create a mock config entry for testing."""
    return _mock_config_entry()


# ---------- async_setup_entry ----------


@pytest.mark.asyncio
async def test_setup_entry_success(config_entry) -> None:
    """Successful setup should register data and forward platforms."""
    hass = _make_hass()
    meter = _make_meter()

    with (
        patch(
            "custom_components.eyeonwater.create_account_from_config",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.eyeonwater.EyeOnWaterData",
        ) as mock_data_cls,
        patch(
            "custom_components.eyeonwater.DataUpdateCoordinator",
        ) as mock_coordinator_cls,
        patch(
            "custom_components.eyeonwater.debounce.Debouncer",
            return_value=MagicMock(),
        ),
    ):
        data_instance = MagicMock()
        data_instance.client = MagicMock()
        data_instance.client.authenticate = AsyncMock()
        data_instance.setup = AsyncMock()
        data_instance.read_meters = AsyncMock(return_value=[meter])
        data_instance.meters = [meter]
        mock_data_cls.return_value = data_instance

        coordinator_instance = MagicMock()
        coordinator_instance.async_refresh = AsyncMock()
        mock_coordinator_cls.return_value = coordinator_instance

        result = await async_setup_entry(hass, config_entry)

    assert result is True
    assert DOMAIN in hass.data
    assert config_entry.entry_id in hass.data[DOMAIN]
    assert DATA_COORDINATOR in hass.data[DOMAIN][config_entry.entry_id]
    assert DATA_SMART_METER in hass.data[DOMAIN][config_entry.entry_id]


@pytest.mark.asyncio
async def test_setup_entry_auth_error(config_entry) -> None:
    """Auth errors during setup should return False."""
    hass = _make_hass()

    with (
        patch(
            "custom_components.eyeonwater.create_account_from_config",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.eyeonwater.EyeOnWaterData",
        ) as mock_data_cls,
    ):
        data_instance = MagicMock()
        data_instance.client = MagicMock()
        data_instance.client.authenticate = AsyncMock(
            side_effect=EyeOnWaterAuthError("bad"),
        )
        mock_data_cls.return_value = data_instance

        result = await async_setup_entry(hass, config_entry)

    assert result is False


@pytest.mark.asyncio
async def test_setup_entry_timeout(config_entry) -> None:
    """Timeout during auth should raise ConfigEntryNotReady."""
    hass = _make_hass()

    with (
        patch(
            "custom_components.eyeonwater.create_account_from_config",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.eyeonwater.EyeOnWaterData",
        ) as mock_data_cls,
    ):
        data_instance = MagicMock()
        data_instance.client = MagicMock()
        data_instance.client.authenticate = AsyncMock(
            side_effect=asyncio.TimeoutError,
        )
        mock_data_cls.return_value = data_instance

        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, config_entry)


# ---------- async_unload_entry ----------


@pytest.mark.asyncio
async def test_unload_entry(config_entry) -> None:
    """Successful unload should remove data from hass."""
    hass = _make_hass()
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config_entry.entry_id] = {
        DATA_COORDINATOR: MagicMock(),
        DATA_SMART_METER: MagicMock(),
    }

    result = await async_unload_entry(hass, config_entry)

    assert result is True
    assert config_entry.entry_id not in hass.data[DOMAIN]
