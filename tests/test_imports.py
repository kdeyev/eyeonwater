"""Basic import tests for eyeonwater."""

import pyonwater

from homeassistant.components.recorder.models import StatisticData
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant

from custom_components.eyeonwater import (
    config_flow,
    const,
    coordinator,
    sensor,
    statistic_helper,
    statistics_tools,
)


def test_can_import_eyeonwater_const():
    """Test that eyeonwater const module can be imported."""
    assert hasattr(const, "DOMAIN")
    assert const.DOMAIN == "eyeonwater"


def test_can_import_coordinator():
    """Test that coordinator module can be imported."""
    assert hasattr(coordinator, "EyeOnWaterData")


def test_can_import_statistic_helper():
    """Test that statistic_helper module can be imported."""
    assert hasattr(statistic_helper, "convert_statistic_data")
    assert hasattr(statistic_helper, "get_entity_statistic_id")


def test_can_import_statistics_tools():
    """Test that statistics_tools module can be imported."""
    assert hasattr(statistics_tools, "resolve_statistic_id")
    assert hasattr(statistics_tools, "MonotonicViolation")


def test_can_import_sensor():
    """Test that sensor module can be imported."""
    assert hasattr(sensor, "async_setup_entry")


def test_can_import_config_flow():
    """Test that config_flow module can be imported."""
    assert hasattr(config_flow, "ConfigFlow")


def test_pyonwater_dependency_available():
    """Test that pyonwater dependency is available."""
    assert hasattr(pyonwater, "Client")
    assert hasattr(pyonwater, "Meter")
    assert hasattr(pyonwater, "DataPoint")
    assert hasattr(pyonwater, "NativeUnits")


def test_homeassistant_imports():
    """Test that Home Assistant imports work."""
    assert HomeAssistant is not None
    assert SensorEntity is not None
    assert StatisticData is not None
