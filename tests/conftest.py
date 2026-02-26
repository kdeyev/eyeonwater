"""Pytest configuration for eyeonwater tests."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from pyonwater import Client, DataPoint, Meter, NativeUnits

# ---------------------------------------------------------------------------
# Module-level constants shared by test modules that import directly from here
# ---------------------------------------------------------------------------

MOCK_METER_ID = "60439875"
MOCK_METER_UUID = "5215777958325016766"
MOCK_CONFIG = {
    "username": "test@example.com",
    "password": "test_password",
}


def _make_hass() -> MagicMock:
    """Return a minimal mock HomeAssistant instance with a real data dict."""
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.services.async_register = MagicMock()
    # Close coroutines immediately so unawaited-coroutine warnings are suppressed.
    # HA's async_create_task schedules work on the event loop; in unit tests we
    # just need to discard the coroutine cleanly.
    hass.async_create_task = lambda coro, *_a, **_kw: coro.close()
    return hass


def _make_meter() -> MagicMock:
    """Return a minimal mock Meter object."""
    meter = MagicMock(spec=Meter)
    meter.meter_id = MOCK_METER_ID
    meter.meter_uuid = MOCK_METER_UUID
    meter.native_unit_of_measurement = "gal"
    meter.reading = DataPoint(
        dt=datetime(2026, 2, 17, 12, 0, 0),
        reading=204797.7,
        unit=NativeUnits.GAL,
    )
    meter.last_historical_data = []
    return meter


@pytest.fixture
def mock_hass():
    """Mock Home Assistant instance."""
    hass = MagicMock()
    hass.config.time_zone = "America/New_York"
    return hass


@pytest.fixture
def mock_client():
    """Mock pyonwater Client."""
    client = MagicMock(spec=Client)
    return client


@pytest.fixture
def mock_meter():
    """Mock pyonwater Meter with sample data."""
    meter = MagicMock(spec=Meter)
    meter.meter_id = "12345678"
    meter.native_unit_of_measurement = "gal"
    meter.reading = DataPoint(
        dt=datetime(2026, 2, 17, 12, 0, 0),
        reading=1000.0,
        unit=NativeUnits.GAL,
    )
    return meter


@pytest.fixture
def sample_datapoints():
    """Sample DataPoint sequence for testing."""
    base_dt = datetime(2026, 2, 1, 0, 0, 0)
    return [
        DataPoint(dt=base_dt, reading=1000.0, unit=NativeUnits.GAL),
        DataPoint(
            dt=base_dt + timedelta(hours=1), reading=1005.0, unit=NativeUnits.GAL
        ),
        DataPoint(
            dt=base_dt + timedelta(hours=2), reading=1012.0, unit=NativeUnits.GAL
        ),
        DataPoint(
            dt=base_dt + timedelta(hours=3), reading=1015.0, unit=NativeUnits.GAL
        ),
    ]


@pytest.fixture
def mock_recorder():
    """Mock Home Assistant recorder instance."""
    recorder = MagicMock()
    session = MagicMock()
    recorder.get_session.return_value.__enter__ = MagicMock(return_value=session)
    recorder.get_session.return_value.__exit__ = MagicMock(return_value=None)
    return recorder


@pytest.fixture
def mock_config_entry():
    """Mock Home Assistant config entry."""
    entry = MagicMock()
    entry.data = {
        "username": "test@example.com",
        "password": "test_password",
    }
    entry.entry_id = "test_entry_id"
    entry.unique_id = "test_unique_id"
    return entry
