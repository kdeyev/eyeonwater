"""Fixtures for EyeOnWater tests."""

import asyncio
import datetime
from collections.abc import Generator
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pyonwater
import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

# ---------- test data ----------

MOCK_USERNAME = "test@example.com"

MOCK_CONFIG = {
    CONF_USERNAME: MOCK_USERNAME,
    CONF_PASSWORD: "testpassword",
}


MOCK_METER_UUID = "abc-123-def-456"
MOCK_METER_ID = "meter_001"


# ---------- lightweight fakes ----------


@dataclass
class FakeFlags:
    """Fake meter flag data for testing."""

    leak: bool = False
    empty_pipe: bool = False
    tamper: bool = False
    cover_removed: bool = False
    reverse_flow: bool = False
    low_battery: bool = False
    battery_charging: bool = False


@dataclass
class FakeReading:
    """Fake meter reading data for testing."""

    model: str = "TestModel"
    customer_name: str = "TestCustomer"
    hardware_version: str = "1.0"
    firmware_version: str = "2.0"
    flags: FakeFlags = field(default_factory=FakeFlags)

    def dict(self) -> dict[str, str]:
        """Return reading fields as a plain dict."""
        return {
            "model": self.model,
            "customer_name": self.customer_name,
            "hardware_version": self.hardware_version,
            "firmware_version": self.firmware_version,
        }


@dataclass
class FakeSensors:
    """Fake meter sensors data for testing."""

    endpoint_temperature: None = None


@dataclass
class FakeMeterInfo:
    """Fake meter info container for testing."""

    reading: FakeReading = field(default_factory=FakeReading)
    sensors: FakeSensors = field(default_factory=FakeSensors)


@dataclass
class FakeDataPoint(pyonwater.DataPoint):
    """DataPoint subclass with test defaults (dt, reading, unit)."""

    dt: datetime.datetime = field(
        default_factory=lambda: datetime.datetime(
            2025,
            1,
            1,
            tzinfo=datetime.UTC,
        ),
    )
    reading: float = 123.45
    unit: str = pyonwater.NativeUnits.GAL


def _make_meter(
    *,
    meter_uuid: str = MOCK_METER_UUID,
    meter_id: str = MOCK_METER_ID,
    native_unit: str | None = None,
) -> MagicMock:
    """Return a lightweight fake Meter."""
    meter = MagicMock(spec=pyonwater.Meter)
    meter.meter_uuid = meter_uuid
    meter.meter_id = meter_id
    meter.meter_info = FakeMeterInfo()
    meter.native_unit_of_measurement = native_unit or pyonwater.NativeUnits.GAL
    meter.reading = FakeDataPoint()
    meter.last_historical_data = [FakeDataPoint()]
    meter.read_meter_info = AsyncMock()
    meter.read_historical_data = AsyncMock(return_value=[FakeDataPoint()])
    return meter


def _make_hass() -> MagicMock:
    """Create a minimal mock HomeAssistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.config.country = "US"
    hass.services = MagicMock()
    hass.services.async_register = MagicMock()

    def _create_task(coro: object, *_args: object, **_kwargs: object) -> MagicMock:
        """Close any coroutine immediately so GC never sees an unawaited coro."""
        if asyncio.iscoroutine(coro):
            coro.close()
        task = MagicMock()
        task.cancel = MagicMock(return_value=False)
        return task

    hass.async_create_task = _create_task

    # config_entries mock
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    return hass


@pytest.fixture
def hass() -> MagicMock:
    """Provide a mock HomeAssistant instance."""
    return _make_hass()


@pytest.fixture
def mock_meter() -> MagicMock:
    """Provide a single fake meter."""
    return _make_meter()


@pytest.fixture
def mock_account() -> MagicMock:
    """Provide a fake Account."""
    account = MagicMock(spec=pyonwater.Account)
    account.username = MOCK_USERNAME
    account.fetch_meters = AsyncMock(return_value=[_make_meter()])
    return account


@pytest.fixture
def mock_client() -> MagicMock:
    """Provide a fake Client."""
    client = MagicMock(spec=pyonwater.Client)
    client.authenticate = AsyncMock()
    return client


@pytest.fixture
def patch_pyonwater(mock_account, mock_client) -> Generator:
    """Patch pyonwater Account and Client constructors."""
    with (
        patch(
            "custom_components.eyeonwater.config_flow.Account",
            return_value=mock_account,
        ),
        patch(
            "custom_components.eyeonwater.config_flow.Client",
            return_value=mock_client,
        ),
    ):
        yield
