"""Fixtures for EyeOnWater tests."""
import datetime
from collections.abc import Generator
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.eyeonwater.const import DOMAIN

# ---------- test data ----------

MOCK_USERNAME = "test@example.com"
MOCK_PASSWORD = "testpassword"

MOCK_CONFIG = {
    CONF_USERNAME: MOCK_USERNAME,
    CONF_PASSWORD: MOCK_PASSWORD,
}


MOCK_METER_UUID = "abc-123-def-456"
MOCK_METER_ID = "meter_001"


# ---------- lightweight fakes ----------


@dataclass
class FakeFlags:
    leak: bool = False
    empty_pipe: bool = False
    tamper: bool = False
    cover_removed: bool = False
    reverse_flow: bool = False
    low_battery: bool = False
    battery_charging: bool = False


@dataclass
class FakeFlow:
    this_week: float = 10.5
    last_week: float = 20.3
    this_month: float = 45.2
    last_month: float = 90.1


@dataclass
class FakeBattery:
    level: float = 85.0


@dataclass
class FakePwr:
    signal_strength: float = -65.0


@dataclass
class FakeEndpointTemperature:
    seven_day_min: float = 12.0
    seven_day_average: float = 15.5
    seven_day_max: float = 19.0
    latest_average: float = 16.2


@dataclass
class FakeReading:
    model: str = "TestModel"
    customer_name: str = "TestCustomer"
    hardware_version: str = "1.0"
    firmware_version: str = "2.0"
    flags: FakeFlags = field(default_factory=FakeFlags)
    flow: FakeFlow | None = None
    battery: FakeBattery | None = None
    pwr: FakePwr | None = None

    def dict(self):
        return {
            "model": self.model,
            "customer_name": self.customer_name,
            "hardware_version": self.hardware_version,
            "firmware_version": self.firmware_version,
        }


@dataclass
class FakeSensors:
    endpoint_temperature: FakeEndpointTemperature | None = None


@dataclass
class FakeMeterInfo:
    reading: FakeReading = field(default_factory=FakeReading)
    sensors: FakeSensors = field(default_factory=FakeSensors)


@dataclass
class FakeDataPoint:
    dt: datetime.datetime = field(
        default_factory=lambda: datetime.datetime(
            2025, 1, 1, tzinfo=datetime.timezone.utc
        ),
    )
    reading: float = 123.45


def _make_meter(
    *,
    meter_uuid: str = MOCK_METER_UUID,
    meter_id: str = MOCK_METER_ID,
    native_unit: str | None = None,
) -> MagicMock:
    """Return a lightweight fake Meter."""
    import pyonwater

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
    import pyonwater

    account = MagicMock(spec=pyonwater.Account)
    account.username = MOCK_USERNAME
    account.fetch_meters = AsyncMock(return_value=[_make_meter()])
    return account


@pytest.fixture
def mock_client() -> MagicMock:
    """Provide a fake Client."""
    import pyonwater

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
