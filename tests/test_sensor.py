"""Tests for eyeonwater sensor module."""

import inspect
import re
from datetime import datetime
from typing import cast
from unittest.mock import MagicMock, patch

import pyonwater
from pyonwater import DataPoint, NativeUnits

from custom_components.eyeonwater import sensor
from custom_components.eyeonwater.sensor import (
    EyeOnWaterTempSensor,
    EyeOnWaterUnifiedSensor,
)


def _make_coordinator_mock(last_update_success=True):
    """Return a minimal mock DataUpdateCoordinator."""
    coord = MagicMock()
    coord.last_update_success = last_update_success
    coord.async_add_listener = MagicMock(return_value=MagicMock())
    return coord


def _make_unified_sensor(last_update_success=True, historical_data=None):
    """Return an EyeOnWaterUnifiedSensor with minimal mocks, ready for unit tests."""
    meter = MagicMock(spec=pyonwater.Meter)
    meter.meter_id = "60439875"
    meter.meter_uuid = "abc123"
    # str/Enum — "gal" is a valid NativeUnits value so no patching needed
    meter.native_unit_of_measurement = "gal"
    meter.last_historical_data = historical_data if historical_data is not None else []

    reading = MagicMock()
    reading.model = "DS-RCDL"
    reading.customer_name = "Test Co"
    reading.hardware_version = "1.0"
    reading.firmware_version = "2.0"
    reading.flags = MagicMock()
    reading.model_dump = MagicMock(return_value={"model": "DS-RCDL"})
    meter.meter_info = MagicMock()
    meter.meter_info.reading = reading
    meter.meter_info.sensors = None

    coord = _make_coordinator_mock(last_update_success)

    with patch(
        "custom_components.eyeonwater.sensor.get_ha_native_unit_of_measurement",
        return_value="gal",
    ):
        s = EyeOnWaterUnifiedSensor(
            meter,
            coord,
            last_imported_time=None,
            statistic_id="sensor.water_meter_60439875",
            statistic_name="Water Meter 60439875",
        )

    mock_hass = MagicMock()
    mock_hass.create_task.side_effect = lambda coro, *_a, **_kw: coro.close()
    s.hass = mock_hass
    s.async_write_ha_state = MagicMock()
    return s, meter, coord


def test_can_import_sensor_module():
    """Test that sensor module can be imported."""
    assert hasattr(sensor, "async_setup_entry")
    assert hasattr(sensor, "EyeOnWaterUnifiedSensor")


def test_can_import_unified_sensor():
    """Test EyeOnWaterUnifiedSensor exists."""
    assert EyeOnWaterUnifiedSensor is not None


def test_can_import_temp_sensor():
    """Test EyeOnWaterTempSensor exists."""
    assert EyeOnWaterTempSensor is not None


def test_unified_sensor_has_total_increasing_state_class():
    """TOTAL_INCREASING is required for Energy Dashboard cost calculation.

    Without state_class=TOTAL_INCREASING the Energy Dashboard entity picker
    will not list this sensor as a water source and cost-per-unit calculation
    will never run — even if the statistics table has correct data.

    HA's SensorEntity base may wrap _attr_* assignments via cached_property
    descriptors in the test environment, so we inspect the class source
    directly to verify the correct declaration is present.
    """
    source = inspect.getsource(EyeOnWaterUnifiedSensor)
    assert re.search(
        r"_attr_state_class\s*=\s*SensorStateClass\.TOTAL_INCREASING",
        source,
    ), (
        "_attr_state_class must be set to SensorStateClass.TOTAL_INCREASING"
        " for Energy Dashboard cost calculation"
    )


def test_unified_sensor_has_water_device_class():
    """WATER device_class is required for the Energy Dashboard water section."""
    source = inspect.getsource(EyeOnWaterUnifiedSensor)
    assert re.search(
        r"_attr_device_class\s*=\s*SensorDeviceClass\.WATER",
        source,
    ), "_attr_device_class must be set to SensorDeviceClass.WATER"


def test_unified_sensor_not_polled():
    """Sensor drives state from coordinator callbacks, never from HA polling."""
    source = inspect.getsource(EyeOnWaterUnifiedSensor)
    assert re.search(
        r"_attr_should_poll\s*=\s*False", source
    ), "_attr_should_poll must be False — sensor uses coordinator push updates"


def test_unified_sensor_has_entity_name_disabled():
    """has_entity_name=False keeps the entity name standalone (not device-prefixed)."""
    source = inspect.getsource(EyeOnWaterUnifiedSensor)
    assert re.search(
        r"_attr_has_entity_name\s*=\s*False", source
    ), "_attr_has_entity_name must be False to preserve standalone entity name"


def test_temp_sensor_has_temp_device_class():
    """Temperature sensor must declare TEMPERATURE device class."""
    source = inspect.getsource(EyeOnWaterTempSensor)
    assert re.search(
        r"_attr_device_class\s*=\s*SensorDeviceClass\.TEMPERATURE",
        source,
    ), "EyeOnWaterTempSensor must use SensorDeviceClass.TEMPERATURE"


def test_temp_sensor_reports_celsius():
    """Temperature sensor must report in Celsius."""
    source = inspect.getsource(EyeOnWaterTempSensor)
    assert re.search(
        r"_attr_native_unit_of_measurement\s*=\s*UnitOfTemperature\.CELSIUS",
        source,
    ), "EyeOnWaterTempSensor must use UnitOfTemperature.CELSIUS"


def test_temp_sensor_not_polled():
    """Temperature sensor drives state from coordinator callbacks, not HA polling."""
    source = inspect.getsource(EyeOnWaterTempSensor)
    assert re.search(
        r"_attr_should_poll\s*=\s*False", source
    ), "EyeOnWaterTempSensor._attr_should_poll must be False"


class TestUnifiedSensorStateUpdate:
    """Verify _state_update writes HA state in all code paths so activity is recorded."""

    def test_coordinator_failure_sets_unavailable_and_writes_state(self):
        """When coordinator fails, sensor must write unavailable state to recorder."""
        s, _, _ = _make_unified_sensor(last_update_success=False)
        s._state_update()

        assert s._attr_available is False
        cast(MagicMock, s.async_write_ha_state).assert_called_once()

    def test_coordinator_failure_does_not_schedule_task(self):
        """When coordinator fails, no async import task should be created."""
        s, _, _ = _make_unified_sensor(last_update_success=False)
        s._state_update()

        cast(MagicMock, s.hass).create_task.assert_not_called()

    def test_empty_historical_data_writes_state(self):
        """Empty historical data on a successful poll still writes state to recorder."""
        s, _, _ = _make_unified_sensor(last_update_success=True, historical_data=[])
        s._state_update()

        # State must be committed so the entity appears in History/Activity
        cast(MagicMock, s.async_write_ha_state).assert_called_once()

    def test_empty_historical_data_does_not_schedule_task(self):
        """No import task when there's no historical data to process."""
        s, _, _ = _make_unified_sensor(last_update_success=True, historical_data=[])
        s._state_update()

        cast(MagicMock, s.hass).create_task.assert_not_called()

    def test_with_historical_data_schedules_async_task(self):
        """When data is available, import task is scheduled (async_write_ha_state
        is called from within that task, not directly from _state_update)."""
        dp = DataPoint(
            dt=datetime(2026, 2, 17, 12, 0, 0), reading=1000.0, unit=NativeUnits.GAL
        )
        s, _, _ = _make_unified_sensor(last_update_success=True, historical_data=[dp])
        # Reset write mock in case the helper triggered it during construction
        cast(MagicMock, s.async_write_ha_state).reset_mock()

        s._state_update()

        cast(MagicMock, s.hass).create_task.assert_called_once()
        # _state_update itself must not call async_write_ha_state —
        # that happens inside _handle_update_locked once the import is done
        cast(MagicMock, s.async_write_ha_state).assert_not_called()


class TestUnifiedSensorExtraStateAttributes:
    """Verify extra_state_attributes is a live property, not a cached value."""

    def test_returns_empty_when_no_state(self):
        """Before first data arrives, attributes dict should be empty."""
        s, _, _ = _make_unified_sensor()
        assert s._state is None
        assert s.extra_state_attributes == {}

    def test_returns_model_dump_when_state_is_set(self):
        """After state is set, attributes should reflect live meter reading."""
        s, meter, _ = _make_unified_sensor()
        s._state = DataPoint(
            dt=datetime(2026, 2, 17, 12, 0, 0), reading=1000.0, unit=NativeUnits.GAL
        )
        # Invalidate the cached_property so it re-evaluates with the new _state
        vars(s).pop("extra_state_attributes", None)
        attrs = s.extra_state_attributes
        meter.meter_info.reading.model_dump.assert_called_once()
        assert attrs == {"model": "DS-RCDL"}

    def test_reflects_updated_meter_data_after_cache_invalidation(self):
        """cached_property must re-evaluate after invalidation, as _state_update does."""
        s, meter, _ = _make_unified_sensor()
        dp = DataPoint(
            dt=datetime(2026, 2, 17, 12, 0, 0), reading=1000.0, unit=NativeUnits.GAL
        )
        s._state = dp

        vars(s).pop("extra_state_attributes", None)
        meter.meter_info.reading.model_dump.return_value = {"model": "V1"}
        first = s.extra_state_attributes
        assert first == {"model": "V1"}

        # Simulate cache invalidation as performed by _state_update / _handle_update_locked
        vars(s).pop("extra_state_attributes", None)
        meter.meter_info.reading.model_dump.return_value = {"model": "V2"}
        second = s.extra_state_attributes
        assert second == {
            "model": "V2"
        }, "cached_property must recompute after invalidation"
