"""Tests for eyeonwater coordinator module."""

import inspect
from collections.abc import Generator
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pyonwater import (
    Client,
    DataPoint,
    EyeOnWaterAPIError,
    EyeOnWaterAuthError,
    NativeUnits,
)

from custom_components.eyeonwater import coordinator
from custom_components.eyeonwater.coordinator import EyeOnWaterData


def test_can_import_coordinator():
    """Test that coordinator module can be imported."""
    assert hasattr(coordinator, "EyeOnWaterData")


def test_can_import_eyeonwater_data():
    """Test EyeOnWaterData class exists."""
    assert EyeOnWaterData is not None


def test_eyeonwater_data_has_required_methods():
    """EyeOnWaterData must expose setup() and read_meters() for the coordinator."""
    assert callable(
        getattr(EyeOnWaterData, "setup", None)
    ), "EyeOnWaterData must have a setup() coroutine"
    assert callable(
        getattr(EyeOnWaterData, "read_meters", None)
    ), "EyeOnWaterData must have a read_meters() coroutine"


def test_eyeonwater_data_read_meters_is_async():
    """read_meters must be a coroutine function (async def)."""
    assert inspect.iscoroutinefunction(
        EyeOnWaterData.read_meters
    ), "EyeOnWaterData.read_meters must be an async method"


def test_eyeonwater_data_setup_is_async():
    """setup must be a coroutine function (async def)."""
    assert inspect.iscoroutinefunction(
        EyeOnWaterData.setup
    ), "EyeOnWaterData.setup must be an async method"


# ---------------------------------------------------------------------------
# Constructor and internal-method coverage
# ---------------------------------------------------------------------------


@pytest.fixture
def eow_data(mock_hass: MagicMock) -> Generator[EyeOnWaterData, None, None]:
    """EyeOnWaterData instance with mocked HA dependencies."""
    with patch(
        "custom_components.eyeonwater.coordinator"
        ".aiohttp_client.async_get_clientsession",
        return_value=MagicMock(),
    ):
        yield EyeOnWaterData(mock_hass, MagicMock())


def test_eyeonwater_data_init_stores_hass(
    mock_hass: MagicMock, eow_data: EyeOnWaterData
):
    """EyeOnWaterData.__init__ stores hass and starts with an empty meters list."""
    assert eow_data.hass is mock_hass
    assert eow_data.meters == []


def test_eyeonwater_data_init_creates_client(eow_data: EyeOnWaterData):
    """EyeOnWaterData.__init__ creates a pyonwater Client."""
    assert isinstance(eow_data.client, Client)


# ---------------------------------------------------------------------------
# setup() and read_meters() runtime tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_fetches_meters(eow_data: EyeOnWaterData):
    """setup() must populate eow_data.meters via account.fetch_meters."""
    fake_meter = MagicMock()
    eow_data.account.fetch_meters = AsyncMock(return_value=[fake_meter])

    await eow_data.setup()

    eow_data.account.fetch_meters.assert_called_once_with(eow_data.client)
    assert eow_data.meters == [fake_meter]


@pytest.mark.asyncio
async def test_read_meters_returns_meters(eow_data: EyeOnWaterData):
    """read_meters() returns the meters list after reading each one."""
    meter = MagicMock()
    meter.read_meter_info = AsyncMock()
    meter.read_historical_data = AsyncMock(return_value=[])
    eow_data.meters = [meter]

    result = await eow_data.read_meters(days_to_load=1)

    assert result == [meter]
    meter.read_meter_info.assert_awaited_once()
    meter.read_historical_data.assert_awaited_once()


# ---------------------------------------------------------------------------
# _read_single_meter error path tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_single_meter_auth_error_raises_update_failed(
    eow_data: EyeOnWaterData,
):
    """EyeOnWaterAuthError must be re-raised as UpdateFailed."""
    meter = MagicMock()
    meter.read_meter_info = AsyncMock(side_effect=EyeOnWaterAuthError("bad creds"))

    with pytest.raises(UpdateFailed):
        await eow_data._read_single_meter(meter, 3)


@pytest.mark.asyncio
async def test_read_single_meter_api_error_json_invalid_fallback(
    eow_data: EyeOnWaterData,
):
    """EyeOnWaterAPIError with 'json_invalid' triggers a 1-day fallback, not failure."""
    meter = MagicMock()
    meter.meter_id = "12345"
    meter.read_meter_info = AsyncMock()
    # First call raises; second (1-day fallback) succeeds.
    meter.read_historical_data = AsyncMock(
        side_effect=[EyeOnWaterAPIError("json_invalid parse error"), []]
    )

    await eow_data._read_single_meter(meter, 3)  # must NOT raise

    assert meter.read_historical_data.call_count == 2
    # Second call used days_to_load=1
    _, kwargs = meter.read_historical_data.call_args
    assert kwargs.get("days_to_load") == 1


@pytest.mark.asyncio
async def test_read_single_meter_api_error_eof_fallback(eow_data: EyeOnWaterData):
    """EyeOnWaterAPIError with 'EOF while parsing' also triggers a 1-day fallback."""
    meter = MagicMock()
    meter.meter_id = "12345"
    meter.read_meter_info = AsyncMock()
    meter.read_historical_data = AsyncMock(
        side_effect=[EyeOnWaterAPIError("EOF while parsing"), []]
    )

    await eow_data._read_single_meter(meter, 3)

    assert meter.read_historical_data.call_count == 2


@pytest.mark.asyncio
async def test_read_single_meter_api_error_other_raises_update_failed(
    eow_data: EyeOnWaterData,
):
    """Unrecognised EyeOnWaterAPIError must raise UpdateFailed."""
    meter = MagicMock()
    meter.meter_id = "12345"
    meter.read_meter_info = AsyncMock()
    meter.read_historical_data = AsyncMock(
        side_effect=EyeOnWaterAPIError("connection refused")
    )

    with pytest.raises(UpdateFailed):
        await eow_data._read_single_meter(meter, 3)


@pytest.mark.asyncio
async def test_read_single_meter_fallback_also_fails_no_raise(eow_data: EyeOnWaterData):
    """If 1-day fallback also raises EyeOnWaterAPIError just log, do not raise."""
    meter = MagicMock()
    meter.meter_id = "noop"
    meter.read_meter_info = AsyncMock()
    meter.read_historical_data = AsyncMock(
        side_effect=EyeOnWaterAPIError("json_invalid x")
    )

    # Both the original and the fallback raise — no UpdateFailed should bubble up.
    await eow_data._read_single_meter(meter, 3)


# ---------------------------------------------------------------------------
# import_historical_data tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_historical_data_calls_centralized_import(
    eow_data: EyeOnWaterData,
):
    """import_historical_data calls centralized_import_statistics for each meter."""
    dp = DataPoint(dt=datetime(2026, 1, 1, 0, 0), reading=1000.0, unit=NativeUnits.GAL)
    meter = MagicMock()
    meter.meter_id = "12345"
    meter.read_meter_info = AsyncMock()
    meter.read_historical_data = AsyncMock(return_value=[dp])
    meter.reading = dp
    eow_data.meters = [meter]

    with patch(
        "custom_components.eyeonwater.coordinator.centralized_import_statistics",
        new=AsyncMock(),
    ) as mock_import:
        await eow_data.import_historical_data(days=1)

    mock_import.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_historical_data_purge_states_calls_helpers(
    mock_hass: MagicMock, eow_data: EyeOnWaterData
):
    """With purge_states=True, delete helpers and purge_entities service are called."""
    dp = DataPoint(dt=datetime(2026, 1, 1, 0, 0), reading=1000.0, unit=NativeUnits.GAL)
    meter = MagicMock()
    meter.meter_id = "12345"
    meter.read_meter_info = AsyncMock()
    meter.read_historical_data = AsyncMock(return_value=[dp])
    meter.reading = dp
    eow_data.meters = [meter]
    eow_data.hass = mock_hass
    mock_hass.services.async_call = AsyncMock()

    with (
        patch(
            "custom_components.eyeonwater.coordinator.centralized_import_statistics",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.eyeonwater.coordinator.async_delete_statistics_after",
            new=AsyncMock(),
        ) as mock_del_after,
        patch(
            "custom_components.eyeonwater.coordinator.async_delete_all_short_term_statistics",
            new=AsyncMock(),
        ) as mock_del_short,
        patch(
            "custom_components.eyeonwater.coordinator.async_delete_entity_states",
            new=AsyncMock(),
        ) as mock_del_states,
    ):
        await eow_data.import_historical_data(days=1, purge_states=True)

    assert mock_del_after.call_count >= 1
    assert mock_del_short.call_count >= 1
    assert mock_del_states.call_count >= 1
    mock_hass.services.async_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_historical_data_empty_data_skips_meter(eow_data: EyeOnWaterData):
    """When read_historical_data returns [] the loop continues without import."""
    meter = MagicMock()
    meter.meter_id = "99999"
    meter.read_meter_info = AsyncMock()
    meter.read_historical_data = AsyncMock(return_value=[])
    eow_data.meters = [meter]

    with patch(
        "custom_components.eyeonwater.coordinator.centralized_import_statistics",
        new=AsyncMock(),
    ) as mock_import:
        await eow_data.import_historical_data(days=1)

    mock_import.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_historical_data_force_overwrite_logs_warning(
    eow_data: EyeOnWaterData,
):
    """force_overwrite=True must log a warning (covers the force_overwrite branch)."""
    dp = DataPoint(dt=datetime(2026, 1, 1, 0, 0), reading=1000.0, unit=NativeUnits.GAL)
    meter = MagicMock()
    meter.meter_id = "12345"
    meter.read_meter_info = AsyncMock()
    meter.read_historical_data = AsyncMock(return_value=[dp])
    meter.reading = dp
    eow_data.meters = [meter]

    with patch(
        "custom_components.eyeonwater.coordinator.centralized_import_statistics",
        new=AsyncMock(),
    ) as mock_import:
        await eow_data.import_historical_data(days=1, force_overwrite=True)

    mock_import.assert_awaited_once()


@pytest.mark.asyncio
async def test_import_historical_data_swallows_api_errors(eow_data: EyeOnWaterData):
    """EyeOnWaterAPIError/AuthError during import are caught and logged, not raised."""
    meter = MagicMock()
    meter.meter_id = "badmeter"
    meter.read_meter_info = AsyncMock(side_effect=EyeOnWaterAPIError("fail"))
    eow_data.meters = [meter]

    # Should complete without raising
    await eow_data.import_historical_data(days=1)
