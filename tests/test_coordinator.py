"""Tests for the EyeOnWater coordinator."""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pyonwater import EyeOnWaterAPIError, EyeOnWaterAuthError

from custom_components.eyeonwater.coordinator import EyeOnWaterData

from .conftest import _make_hass


@pytest.fixture
def eow_data(mock_account, mock_client) -> EyeOnWaterData:
    """Build an EyeOnWaterData instance with mocked deps."""
    hass = _make_hass()
    config_entry = MagicMock()
    config_entry.options = {}
    with (
        patch(
            "custom_components.eyeonwater.coordinator.aiohttp_client.async_get_clientsession",
        ),
        patch(
            "custom_components.eyeonwater.coordinator.Client",
            return_value=mock_client,
        ),
        patch(
            "custom_components.eyeonwater.coordinator.get_last_imported_time",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        return EyeOnWaterData(hass, mock_account, config_entry)


# ---------- setup ----------


@pytest.mark.asyncio
async def test_setup_fetches_meters(eow_data, mock_account) -> None:
    """setup() should populate the meters list."""
    with patch(
        "custom_components.eyeonwater.coordinator.get_last_imported_time",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await eow_data.setup()
    mock_account.fetch_meters.assert_awaited_once_with(
        eow_data.client,
        prefer_new_search=False,
    )
    assert len(eow_data.meters) == 1


@pytest.mark.asyncio
async def test_setup_passes_prefer_new_search(mock_account, mock_client) -> None:
    """setup() should pass prefer_new_search=True when option is set."""
    hass = _make_hass()
    config_entry = MagicMock()
    config_entry.options = {"prefer_new_search": True}
    with (
        patch(
            "custom_components.eyeonwater.coordinator.aiohttp_client.async_get_clientsession",
        ),
        patch(
            "custom_components.eyeonwater.coordinator.Client",
            return_value=mock_client,
        ),
        patch(
            "custom_components.eyeonwater.coordinator.get_last_imported_time",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        data = EyeOnWaterData(hass, mock_account, config_entry)
        await data.setup()
    mock_account.fetch_meters.assert_awaited_once_with(
        data.client,
        prefer_new_search=True,
    )


# ---------- read_meters ----------


@pytest.mark.asyncio
async def test_read_meters_success(eow_data) -> None:
    """read_meters should call read_meter_info + read_historical_data."""
    with patch(
        "custom_components.eyeonwater.coordinator.get_last_imported_time",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await eow_data.setup()
    with patch(
        "custom_components.eyeonwater.coordinator.async_add_external_statistics",
    ):
        meters = await eow_data.read_meters(days_to_load=3)
    assert len(meters) == 1
    meter = meters[0]
    meter.read_meter_info.assert_awaited_once()
    meter.read_historical_data.assert_awaited()


@pytest.mark.asyncio
async def test_read_meters_api_error_raises_update_failed(eow_data) -> None:
    """API errors should be wrapped in UpdateFailed."""
    with patch(
        "custom_components.eyeonwater.coordinator.get_last_imported_time",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await eow_data.setup()
    eow_data.meters[0].read_meter_info.side_effect = EyeOnWaterAPIError("fail")

    with pytest.raises(UpdateFailed):
        await eow_data.read_meters()


@pytest.mark.asyncio
async def test_read_meters_auth_error_raises_update_failed(eow_data) -> None:
    """Auth errors should be wrapped in UpdateFailed."""
    with patch(
        "custom_components.eyeonwater.coordinator.get_last_imported_time",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await eow_data.setup()
    eow_data.meters[0].read_meter_info.side_effect = EyeOnWaterAuthError("denied")

    with pytest.raises(UpdateFailed):
        await eow_data.read_meters()


# ---------- import_historical_data ----------


@pytest.mark.asyncio
async def test_import_historical_data(eow_data) -> None:
    """import_historical_data should read data and call async_import_statistics."""
    with patch(
        "custom_components.eyeonwater.coordinator.get_last_imported_time",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await eow_data.setup()

    with patch(
        "custom_components.eyeonwater.coordinator.async_add_external_statistics",
    ) as mock_import:
        await eow_data.import_historical_data(days=30)

    eow_data.meters[0].read_historical_data.assert_awaited()
    call_args = mock_import.call_args[0]
    assert len(call_args) == 3  # (hass, metadata, statistics)
    assert len(call_args[2]) > 0  # at least one StatisticData row passed


@pytest.mark.asyncio
async def test_read_meters_imports_statistics(eow_data) -> None:
    """read_meters should import new statistics automatically."""
    with patch(
        "custom_components.eyeonwater.coordinator.get_last_imported_time",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await eow_data.setup()

    with patch(
        "custom_components.eyeonwater.coordinator.async_add_external_statistics",
    ) as mock_import:
        await eow_data.read_meters(days_to_load=3)

    call_args = mock_import.call_args[0]
    assert len(call_args) == 3  # (hass, metadata, statistics)
    assert len(call_args[2]) > 0  # at least one StatisticData row passed


@pytest.mark.asyncio
async def test_read_meters_skips_import_when_no_new_data(eow_data) -> None:
    """read_meters should skip import if no data is newer than last import."""
    last_time = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    with patch(
        "custom_components.eyeonwater.coordinator.get_last_imported_time",
        new_callable=AsyncMock,
        return_value=last_time,
    ):
        await eow_data.setup()

    # The fake data point is from 2025-01-01 which is before last_time
    with patch(
        "custom_components.eyeonwater.coordinator.async_add_external_statistics",
    ) as mock_import:
        await eow_data.read_meters(days_to_load=3)

    mock_import.assert_not_called()


# ---------- cost statistics import ----------


@pytest.mark.asyncio
async def test_read_meters_imports_cost_stats_when_price_set(eow_data) -> None:
    """read_meters should import cost statistics when unit_price is configured."""
    eow_data._config_entry.options = {"unit_price": 0.005}
    eow_data.hass.config.currency = "USD"

    with patch(
        "custom_components.eyeonwater.coordinator.get_last_imported_time",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await eow_data.setup()

    with patch(
        "custom_components.eyeonwater.coordinator.async_add_external_statistics",
    ) as mock_import:
        await eow_data.read_meters(days_to_load=3)

    # Should be called twice: once for water stats, once for cost stats
    assert mock_import.call_count == 2


@pytest.mark.asyncio
async def test_read_meters_skips_cost_stats_when_no_price(eow_data) -> None:
    """read_meters should NOT import cost statistics when no unit_price."""
    eow_data._config_entry.options = {}
    eow_data.hass.config.currency = "USD"

    with patch(
        "custom_components.eyeonwater.coordinator.get_last_imported_time",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await eow_data.setup()

    with patch(
        "custom_components.eyeonwater.coordinator.async_add_external_statistics",
    ) as mock_import:
        await eow_data.read_meters(days_to_load=3)

    # Only water stats, no cost stats
    mock_import.assert_called_once()


@pytest.mark.asyncio
async def test_read_meters_skips_cost_stats_when_no_currency(eow_data) -> None:
    """read_meters should skip cost statistics when no currency configured."""
    eow_data._config_entry.options = {"unit_price": 0.005}
    eow_data.hass.config.currency = ""

    with patch(
        "custom_components.eyeonwater.coordinator.get_last_imported_time",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await eow_data.setup()

    with patch(
        "custom_components.eyeonwater.coordinator.async_add_external_statistics",
    ) as mock_import:
        await eow_data.read_meters(days_to_load=3)

    # Only water stats, no cost stats
    mock_import.assert_called_once()


@pytest.mark.asyncio
async def test_import_historical_data_includes_cost_stats(eow_data) -> None:
    """import_historical_data should also import cost stats if price is set."""
    eow_data._config_entry.options = {"unit_price": 0.01}
    eow_data.hass.config.currency = "EUR"

    with patch(
        "custom_components.eyeonwater.coordinator.get_last_imported_time",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await eow_data.setup()

    with patch(
        "custom_components.eyeonwater.coordinator.async_add_external_statistics",
    ) as mock_import:
        await eow_data.import_historical_data(days=30)

    # Water + cost
    assert mock_import.call_count == 2


@pytest.mark.asyncio
async def test_import_historical_data_continues_on_api_error(eow_data) -> None:
    """import_historical_data should log and skip meters that fail."""
    with patch(
        "custom_components.eyeonwater.coordinator.get_last_imported_time",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await eow_data.setup()

    eow_data.meters[0].read_historical_data.side_effect = EyeOnWaterAPIError(
        "empty response",
    )

    with patch(
        "custom_components.eyeonwater.coordinator.async_add_external_statistics",
    ) as mock_import:
        # Should NOT raise
        await eow_data.import_historical_data(days=30)

    mock_import.assert_not_called()


# ---------- display unit ----------


@pytest.mark.asyncio
async def test_read_meters_uses_display_unit(eow_data) -> None:
    """read_meters should pass display_unit to metadata and convert data."""
    eow_data._config_entry.options = {"display_unit": "L"}

    with patch(
        "custom_components.eyeonwater.coordinator.get_last_imported_time",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await eow_data.setup()

    with patch(
        "custom_components.eyeonwater.coordinator.async_add_external_statistics",
    ) as mock_import:
        await eow_data.read_meters(days_to_load=3)

    mock_import.assert_called_once()
    metadata = mock_import.call_args[0][1]
    assert metadata["unit_of_measurement"] == "L"


@pytest.mark.asyncio
async def test_import_historical_data_uses_display_unit(eow_data) -> None:
    """import_historical_data should respect display_unit."""
    eow_data._config_entry.options = {"display_unit": "m\u00b3"}

    with patch(
        "custom_components.eyeonwater.coordinator.get_last_imported_time",
        new_callable=AsyncMock,
        return_value=None,
    ):
        await eow_data.setup()

    with patch(
        "custom_components.eyeonwater.coordinator.async_add_external_statistics",
    ) as mock_import:
        await eow_data.import_historical_data(days=30)

    mock_import.assert_called_once()
    metadata = mock_import.call_args[0][1]
    assert metadata["unit_of_measurement"] == "m\u00b3"
