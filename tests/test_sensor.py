"""Tests for EyeOnWater sensor entities."""
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pyonwater
import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature, UnitOfVolume
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.eyeonwater.const import DOMAIN, WATER_METER_NAME
from custom_components.eyeonwater.sensor import (
    EyeOnWaterSensor,
    EyeOnWaterStatistic,
    EyeOnWaterTempSensor,
)
from custom_components.eyeonwater.statistic_helper import normalize_id

from .conftest import (
    FakeDataPoint,
    FakeMeterInfo,
    FakeReading,
    FakeSensors,
    MOCK_METER_ID,
    MOCK_METER_UUID,
    _make_meter,
)


@pytest.fixture
def coordinator() -> MagicMock:
    """Provide a mock coordinator."""
    coord = MagicMock(spec=DataUpdateCoordinator)
    coord.last_update_success = True
    coord.async_add_listener = MagicMock(return_value=lambda: None)
    return coord


# ---------- EyeOnWaterSensor ----------


class TestEyeOnWaterSensor:
    """Tests for the main water usage sensor."""

    def test_unique_id(self, coordinator) -> None:
        meter = _make_meter()
        sensor = EyeOnWaterSensor(meter, coordinator)
        assert sensor._attr_unique_id == normalize_id(MOCK_METER_UUID)

    def test_device_class(self, coordinator) -> None:
        meter = _make_meter()
        sensor = EyeOnWaterSensor(meter, coordinator)
        assert sensor._attr_device_class == SensorDeviceClass.WATER

    def test_state_class(self, coordinator) -> None:
        meter = _make_meter()
        sensor = EyeOnWaterSensor(meter, coordinator)
        assert sensor._attr_state_class == SensorStateClass.TOTAL_INCREASING

    def test_unit_gallons(self, coordinator) -> None:
        meter = _make_meter(native_unit=pyonwater.NativeUnits.GAL)
        sensor = EyeOnWaterSensor(meter, coordinator)
        assert sensor._attr_native_unit_of_measurement == UnitOfVolume.GALLONS

    def test_unit_cubic_feet(self, coordinator) -> None:
        meter = _make_meter(native_unit=pyonwater.NativeUnits.CF)
        sensor = EyeOnWaterSensor(meter, coordinator)
        assert sensor._attr_native_unit_of_measurement == UnitOfVolume.CUBIC_FEET

    def test_available_initially_false(self, coordinator) -> None:
        meter = _make_meter()
        sensor = EyeOnWaterSensor(meter, coordinator)
        assert sensor.available is False

    def test_state_update_sets_available(self, coordinator) -> None:
        meter = _make_meter()
        sensor = EyeOnWaterSensor(meter, coordinator)
        sensor.hass = MagicMock()
        sensor.async_write_ha_state = MagicMock()

        sensor._state_update()

        assert sensor._available is True
        assert sensor._state == meter.reading

    def test_state_update_unavailable(self, coordinator) -> None:
        meter = _make_meter()
        sensor = EyeOnWaterSensor(meter, coordinator)
        sensor.hass = MagicMock()
        sensor.async_write_ha_state = MagicMock()
        coordinator.last_update_success = False

        sensor._state_update()

        assert sensor._available is False

    def test_extra_state_attributes(self, coordinator) -> None:
        meter = _make_meter()
        sensor = EyeOnWaterSensor(meter, coordinator)
        attrs = sensor.extra_state_attributes
        assert "model" in attrs
        assert attrs["model"] == "TestModel"

    def test_device_info(self, coordinator) -> None:
        meter = _make_meter()
        sensor = EyeOnWaterSensor(meter, coordinator)
        info = sensor._attr_device_info
        assert (DOMAIN, normalize_id(MOCK_METER_UUID)) in info["identifiers"]


# ---------- EyeOnWaterStatistic ----------


class TestEyeOnWaterStatistic:
    """Tests for the statistic sensor."""

    def test_unique_id(self, coordinator) -> None:
        meter = _make_meter()
        sensor = EyeOnWaterStatistic(meter, coordinator, last_imported_time=None)
        assert sensor._attr_unique_id == f"{normalize_id(MOCK_METER_UUID)}_statistic"

    def test_name(self, coordinator) -> None:
        meter = _make_meter()
        sensor = EyeOnWaterStatistic(meter, coordinator, last_imported_time=None)
        expected_id = normalize_id(MOCK_METER_ID)
        assert sensor._attr_name == f"{WATER_METER_NAME} {expected_id} Statistic"

    def test_device_class(self, coordinator) -> None:
        meter = _make_meter()
        sensor = EyeOnWaterStatistic(meter, coordinator, last_imported_time=None)
        assert sensor._attr_device_class == SensorDeviceClass.WATER

    def test_import_historical_data_empty(self, coordinator) -> None:
        """No data to import should be a no-op."""
        meter = _make_meter()
        sensor = EyeOnWaterStatistic(meter, coordinator, last_imported_time=None)
        sensor.hass = MagicMock()
        sensor._last_historical_data = []

        # Should not raise
        sensor.import_historical_data()


# ---------- EyeOnWaterTempSensor ----------


class TestEyeOnWaterTempSensor:
    """Tests for the temperature sensor."""

    def test_unique_id(self, coordinator) -> None:
        meter = _make_meter()
        sensor = EyeOnWaterTempSensor(meter, coordinator)
        assert sensor._attr_unique_id == f"{normalize_id(MOCK_METER_UUID)}_temperature"

    def test_device_class(self, coordinator) -> None:
        meter = _make_meter()
        sensor = EyeOnWaterTempSensor(meter, coordinator)
        assert sensor._attr_device_class == SensorDeviceClass.TEMPERATURE

    def test_unit(self, coordinator) -> None:
        meter = _make_meter()
        sensor = EyeOnWaterTempSensor(meter, coordinator)
        assert sensor._attr_native_unit_of_measurement == UnitOfTemperature.CELSIUS

    def test_native_value_none_when_no_temp(self, coordinator) -> None:
        meter = _make_meter()
        # Default FakeSensors has endpoint_temperature = None
        sensor = EyeOnWaterTempSensor(meter, coordinator)
        assert sensor.native_value is None

    def test_native_value_with_temp(self, coordinator) -> None:
        meter = _make_meter()
        temp_mock = MagicMock()
        temp_mock.seven_day_min = 15.5
        meter.meter_info.sensors.endpoint_temperature = temp_mock

        sensor = EyeOnWaterTempSensor(meter, coordinator)
        assert sensor.native_value == 15.5
