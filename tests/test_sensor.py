"""Tests for EyeOnWater sensor entities."""
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pyonwater
import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.eyeonwater.const import DOMAIN, WATER_METER_NAME
from custom_components.eyeonwater.sensor import (
    ALL_DIAGNOSTIC_SENSORS,
    BATTERY_SENSORS,
    EyeOnWaterDiagnosticSensor,
    EyeOnWaterSensor,
    SIGNAL_SENSORS,
    TEMPERATURE_SENSORS,
)
from custom_components.eyeonwater.statistic_helper import normalize_id

from .conftest import (
    FakeBattery,
    FakeDataPoint,
    FakeEndpointTemperature,
    FakeMeterInfo,
    FakePwr,
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


# ---------- EyeOnWaterDiagnosticSensor ----------


class TestTemperatureSensors:
    """Tests for the temperature diagnostic sensors."""

    def test_descriptions_count(self) -> None:
        assert len(TEMPERATURE_SENSORS) == 4

    def test_unique_ids(self, coordinator) -> None:
        meter = _make_meter()
        meter.meter_info.sensors.endpoint_temperature = FakeEndpointTemperature()
        for desc in TEMPERATURE_SENSORS:
            sensor = EyeOnWaterDiagnosticSensor(meter, coordinator, desc)
            assert (
                sensor._attr_unique_id == f"{normalize_id(MOCK_METER_UUID)}_{desc.key}"
            )

    def test_device_class(self, coordinator) -> None:
        meter = _make_meter()
        meter.meter_info.sensors.endpoint_temperature = FakeEndpointTemperature()
        for desc in TEMPERATURE_SENSORS:
            sensor = EyeOnWaterDiagnosticSensor(meter, coordinator, desc)
            assert (
                sensor.entity_description.device_class == SensorDeviceClass.TEMPERATURE
            )

    def test_unit(self, coordinator) -> None:
        meter = _make_meter()
        meter.meter_info.sensors.endpoint_temperature = FakeEndpointTemperature()
        for desc in TEMPERATURE_SENSORS:
            sensor = EyeOnWaterDiagnosticSensor(meter, coordinator, desc)
            assert (
                sensor.entity_description.native_unit_of_measurement
                == UnitOfTemperature.CELSIUS
            )

    def test_values_with_temperature_data(self, coordinator) -> None:
        meter = _make_meter()
        meter.meter_info.sensors.endpoint_temperature = FakeEndpointTemperature()
        expected = {
            "temperature_7day_min": 12.0,
            "temperature_7day_avg": 15.5,
            "temperature_7day_max": 19.0,
            "temperature_latest_avg": 16.2,
        }
        for desc in TEMPERATURE_SENSORS:
            sensor = EyeOnWaterDiagnosticSensor(meter, coordinator, desc)
            assert sensor.native_value == expected[desc.key]

    def test_values_none_without_temperature_data(self, coordinator) -> None:
        meter = _make_meter()
        # Default: endpoint_temperature is None
        for desc in TEMPERATURE_SENSORS:
            sensor = EyeOnWaterDiagnosticSensor(meter, coordinator, desc)
            assert sensor.native_value is None

    def test_available_fn(self) -> None:
        meter = _make_meter()
        assert TEMPERATURE_SENSORS[0].available_fn(meter) is False

        meter.meter_info.sensors.endpoint_temperature = FakeEndpointTemperature()
        assert TEMPERATURE_SENSORS[0].available_fn(meter) is True


class TestBatterySensors:
    """Tests for the battery diagnostic sensor."""

    def test_descriptions_count(self) -> None:
        assert len(BATTERY_SENSORS) == 1

    def test_device_class(self, coordinator) -> None:
        meter = _make_meter()
        meter.meter_info.reading.battery = FakeBattery()
        desc = BATTERY_SENSORS[0]
        sensor = EyeOnWaterDiagnosticSensor(meter, coordinator, desc)
        assert sensor.entity_description.device_class == SensorDeviceClass.BATTERY

    def test_unit(self, coordinator) -> None:
        meter = _make_meter()
        meter.meter_info.reading.battery = FakeBattery()
        desc = BATTERY_SENSORS[0]
        sensor = EyeOnWaterDiagnosticSensor(meter, coordinator, desc)
        assert sensor.entity_description.native_unit_of_measurement == PERCENTAGE

    def test_value_with_battery_data(self, coordinator) -> None:
        meter = _make_meter()
        meter.meter_info.reading.battery = FakeBattery()
        desc = BATTERY_SENSORS[0]
        sensor = EyeOnWaterDiagnosticSensor(meter, coordinator, desc)
        assert sensor.native_value == 85.0

    def test_value_none_without_battery_data(self, coordinator) -> None:
        meter = _make_meter()
        desc = BATTERY_SENSORS[0]
        sensor = EyeOnWaterDiagnosticSensor(meter, coordinator, desc)
        assert sensor.native_value is None

    def test_available_fn(self) -> None:
        meter = _make_meter()
        assert BATTERY_SENSORS[0].available_fn(meter) is False

        meter.meter_info.reading.battery = FakeBattery()
        assert BATTERY_SENSORS[0].available_fn(meter) is True


class TestSignalSensors:
    """Tests for the signal strength diagnostic sensor."""

    def test_descriptions_count(self) -> None:
        assert len(SIGNAL_SENSORS) == 1

    def test_device_class(self, coordinator) -> None:
        meter = _make_meter()
        meter.meter_info.reading.pwr = FakePwr()
        desc = SIGNAL_SENSORS[0]
        sensor = EyeOnWaterDiagnosticSensor(meter, coordinator, desc)
        assert (
            sensor.entity_description.device_class == SensorDeviceClass.SIGNAL_STRENGTH
        )

    def test_unit(self, coordinator) -> None:
        meter = _make_meter()
        meter.meter_info.reading.pwr = FakePwr()
        desc = SIGNAL_SENSORS[0]
        sensor = EyeOnWaterDiagnosticSensor(meter, coordinator, desc)
        assert (
            sensor.entity_description.native_unit_of_measurement
            == SIGNAL_STRENGTH_DECIBELS
        )

    def test_value_with_signal_data(self, coordinator) -> None:
        meter = _make_meter()
        meter.meter_info.reading.pwr = FakePwr()
        desc = SIGNAL_SENSORS[0]
        sensor = EyeOnWaterDiagnosticSensor(meter, coordinator, desc)
        assert sensor.native_value == -65.0

    def test_value_none_without_signal_data(self, coordinator) -> None:
        meter = _make_meter()
        desc = SIGNAL_SENSORS[0]
        sensor = EyeOnWaterDiagnosticSensor(meter, coordinator, desc)
        assert sensor.native_value is None

    def test_available_fn(self) -> None:
        meter = _make_meter()
        assert SIGNAL_SENSORS[0].available_fn(meter) is False

        meter.meter_info.reading.pwr = FakePwr()
        assert SIGNAL_SENSORS[0].available_fn(meter) is True


class TestAllDiagnosticSensors:
    """Cross-cutting tests for all diagnostic sensor descriptions."""

    def test_total_count(self) -> None:
        assert len(ALL_DIAGNOSTIC_SENSORS) == 6

    def test_unique_keys(self) -> None:
        keys = [d.key for d in ALL_DIAGNOSTIC_SENSORS]
        assert len(keys) == len(set(keys))

    def test_device_info_shared_with_main_sensor(self, coordinator) -> None:
        meter = _make_meter()
        meter.meter_info.reading.battery = FakeBattery()
        main = EyeOnWaterSensor(meter, coordinator)
        diag = EyeOnWaterDiagnosticSensor(meter, coordinator, BATTERY_SENSORS[0])
        assert (
            main._attr_device_info["identifiers"]
            == diag._attr_device_info["identifiers"]
        )
