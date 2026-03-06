"""Tests for EyeOnWater sensor entities."""
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pyonwater
import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfVolume
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.eyeonwater.const import CONF_UNIT_PRICE, DOMAIN, WATER_METER_NAME
from custom_components.eyeonwater.sensor import (
    EyeOnWaterCostSensor,
    EyeOnWaterSensor,
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

    def test_no_state_class(self, coordinator) -> None:
        meter = _make_meter()
        sensor = EyeOnWaterSensor(meter, coordinator)
        assert not hasattr(sensor, "_attr_state_class")

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


# ---------- EyeOnWaterCostSensor ----------


def _make_config_entry(unit_price: float | None = None) -> MagicMock:
    """Create a mock ConfigEntry with optional unit_price in options."""
    entry = MagicMock(spec=ConfigEntry)
    entry.options = {}
    if unit_price is not None:
        entry.options[CONF_UNIT_PRICE] = unit_price
    return entry


class TestEyeOnWaterCostSensor:
    """Tests for the cost sensor."""

    def test_unique_id(self, coordinator) -> None:
        meter = _make_meter()
        entry = _make_config_entry()
        sensor = EyeOnWaterCostSensor(meter, coordinator, entry)
        assert sensor._attr_unique_id == f"{normalize_id(MOCK_METER_UUID)}_cost"

    def test_device_class(self, coordinator) -> None:
        meter = _make_meter()
        entry = _make_config_entry()
        sensor = EyeOnWaterCostSensor(meter, coordinator, entry)
        assert sensor._attr_device_class == SensorDeviceClass.MONETARY

    def test_state_class(self, coordinator) -> None:
        meter = _make_meter()
        entry = _make_config_entry()
        sensor = EyeOnWaterCostSensor(meter, coordinator, entry)
        assert sensor._attr_state_class == SensorStateClass.TOTAL_INCREASING

    def test_translation_key(self, coordinator) -> None:
        meter = _make_meter()
        entry = _make_config_entry()
        sensor = EyeOnWaterCostSensor(meter, coordinator, entry)
        assert sensor._attr_translation_key == "water_cost"

    def test_native_value_none_when_no_price(self, coordinator) -> None:
        meter = _make_meter()
        entry = _make_config_entry()  # no price
        sensor = EyeOnWaterCostSensor(meter, coordinator, entry)
        assert sensor.native_value is None

    def test_native_value_none_when_price_is_zero(self, coordinator) -> None:
        meter = _make_meter()
        entry = _make_config_entry(unit_price=0)
        sensor = EyeOnWaterCostSensor(meter, coordinator, entry)
        assert sensor.native_value is None

    def test_available_false_without_price(self, coordinator) -> None:
        meter = _make_meter()
        entry = _make_config_entry()
        sensor = EyeOnWaterCostSensor(meter, coordinator, entry)
        sensor._available = True
        assert sensor.available is False  # no price configured

    def test_available_true_with_price(self, coordinator) -> None:
        meter = _make_meter()
        entry = _make_config_entry(unit_price=0.005)
        sensor = EyeOnWaterCostSensor(meter, coordinator, entry)
        sensor._available = True
        assert sensor.available is True

    def test_cost_accumulates_on_update(self, coordinator) -> None:
        meter = _make_meter()
        entry = _make_config_entry(unit_price=0.005)
        sensor = EyeOnWaterCostSensor(meter, coordinator, entry)
        sensor.hass = MagicMock()
        sensor.hass.config.currency = "USD"
        sensor.async_write_ha_state = MagicMock()

        # First update — sets last_reading, no cost delta
        meter.reading = FakeDataPoint(reading=1000.0)
        sensor._state_update()
        assert sensor._last_reading == 1000.0
        assert sensor._cost == 0.0

        # Second update — 10 gallons used
        meter.reading = FakeDataPoint(reading=1010.0)
        sensor._state_update()
        assert sensor._last_reading == 1010.0
        assert sensor._cost == pytest.approx(0.05)  # 10 * 0.005

        # Third update — 5 more gallons
        meter.reading = FakeDataPoint(reading=1015.0)
        sensor._state_update()
        assert sensor._cost == pytest.approx(0.075)  # 15 * 0.005

    def test_cost_ignores_decreasing_reading(self, coordinator) -> None:
        meter = _make_meter()
        entry = _make_config_entry(unit_price=0.005)
        sensor = EyeOnWaterCostSensor(meter, coordinator, entry)
        sensor.hass = MagicMock()
        sensor.hass.config.currency = "USD"
        sensor.async_write_ha_state = MagicMock()

        # First update
        meter.reading = FakeDataPoint(reading=1000.0)
        sensor._state_update()

        # Decreasing reading (shouldn't happen, but handle gracefully)
        meter.reading = FakeDataPoint(reading=990.0)
        sensor._state_update()
        assert sensor._cost == 0.0  # no negative cost

    def test_cost_no_accumulation_without_price(self, coordinator) -> None:
        meter = _make_meter()
        entry = _make_config_entry()  # no price
        sensor = EyeOnWaterCostSensor(meter, coordinator, entry)
        sensor.hass = MagicMock()
        sensor.async_write_ha_state = MagicMock()

        meter.reading = FakeDataPoint(reading=1000.0)
        sensor._state_update()

        meter.reading = FakeDataPoint(reading=1010.0)
        sensor._state_update()

        assert sensor._cost == 0.0
        assert sensor._last_reading is None

    def test_native_unit_from_hass_currency(self, coordinator) -> None:
        meter = _make_meter()
        entry = _make_config_entry(unit_price=0.005)
        sensor = EyeOnWaterCostSensor(meter, coordinator, entry)
        sensor.hass = MagicMock()
        sensor.hass.config.currency = "EUR"
        assert sensor.native_unit_of_measurement == "EUR"

    def test_extra_state_attributes(self, coordinator) -> None:
        meter = _make_meter()
        entry = _make_config_entry(unit_price=0.005)
        sensor = EyeOnWaterCostSensor(meter, coordinator, entry)
        attrs = sensor.extra_state_attributes
        assert attrs["unit_price"] == 0.005
        assert attrs["last_reading"] is None

    def test_device_info(self, coordinator) -> None:
        meter = _make_meter()
        entry = _make_config_entry()
        sensor = EyeOnWaterCostSensor(meter, coordinator, entry)
        info = sensor._attr_device_info
        assert (DOMAIN, normalize_id(MOCK_METER_UUID)) in info["identifiers"]
