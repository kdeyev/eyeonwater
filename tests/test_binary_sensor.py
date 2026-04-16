"""Tests for EyeOnWater binary sensor entities."""

from unittest.mock import MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.eyeonwater.binary_sensor import (
    FLAG_SENSORS,
    Description,
    EyeOnWaterBinarySensor,
)
from custom_components.eyeonwater.statistic_helper import normalize_id

from .conftest import MOCK_METER_UUID, _make_meter


@pytest.fixture
def coordinator() -> MagicMock:
    """Provide a mock coordinator."""
    coord = MagicMock(spec=DataUpdateCoordinator)
    coord.last_update_success = True
    coord.async_add_listener = MagicMock(return_value=lambda: None)
    return coord


def _make_sensor(key: str, coordinator: MagicMock) -> EyeOnWaterBinarySensor:
    """Return a sensor for the given flag key."""
    desc = next(d for d in FLAG_SENSORS if d.key == key)
    return EyeOnWaterBinarySensor(_make_meter(), coordinator, desc)


# ---------- FLAG_SENSORS catalog ----------


class TestFlagSensorsCatalog:
    """Verify the FLAG_SENSORS list contains expected entries."""

    def test_encoder_leak_present(self) -> None:
        """encoder_leak sensor must exist in FLAG_SENSORS."""
        keys = [d.key for d in FLAG_SENSORS]
        assert "encoder_leak" in keys

    def test_endpoint_reading_missed_present(self) -> None:
        """endpoint_reading_missed sensor must exist in FLAG_SENSORS."""
        keys = [d.key for d in FLAG_SENSORS]
        assert "endpoint_reading_missed" in keys

    def test_device_alert_present(self) -> None:
        """device_alert sensor must exist in FLAG_SENSORS."""
        keys = [d.key for d in FLAG_SENSORS]
        assert "device_alert" in keys

    def test_encoder_leak_disabled_by_default(self) -> None:
        """encoder_leak must be disabled by default."""
        desc = next(d for d in FLAG_SENSORS if d.key == "encoder_leak")
        assert desc.enabled_by_default is False

    def test_endpoint_reading_missed_disabled_by_default(self) -> None:
        """endpoint_reading_missed must be disabled by default."""
        desc = next(d for d in FLAG_SENSORS if d.key == "endpoint_reading_missed")
        assert desc.enabled_by_default is False

    def test_device_alert_disabled_by_default(self) -> None:
        """device_alert must be disabled by default."""
        desc = next(d for d in FLAG_SENSORS if d.key == "device_alert")
        assert desc.enabled_by_default is False

    def test_leak_enabled_by_default(self) -> None:
        """Primary leak sensor must remain enabled by default."""
        desc = next(d for d in FLAG_SENSORS if d.key == "leak")
        assert desc.enabled_by_default is True

    def test_encoder_leak_is_moisture(self) -> None:
        """encoder_leak must have MOISTURE device class."""
        desc = next(d for d in FLAG_SENSORS if d.key == "encoder_leak")
        assert desc.device_class == BinarySensorDeviceClass.MOISTURE

    def test_endpoint_reading_missed_is_problem(self) -> None:
        """endpoint_reading_missed must have PROBLEM device class."""
        desc = next(d for d in FLAG_SENSORS if d.key == "endpoint_reading_missed")
        assert desc.device_class == BinarySensorDeviceClass.PROBLEM

    def test_device_alert_is_problem(self) -> None:
        """device_alert must have PROBLEM device class."""
        desc = next(d for d in FLAG_SENSORS if d.key == "device_alert")
        assert desc.device_class == BinarySensorDeviceClass.PROBLEM


# ---------- EyeOnWaterBinarySensor ----------


class TestEyeOnWaterBinarySensor:
    """Tests for EyeOnWaterBinarySensor entity behaviour."""

    def test_unique_id_encoder_leak(self, coordinator: MagicMock) -> None:
        """Unique ID must include sensor key and normalized UUID."""
        sensor = _make_sensor("encoder_leak", coordinator)
        assert sensor._attr_unique_id == f"encoder_leak_{normalize_id(MOCK_METER_UUID)}"

    def test_entity_registry_disabled_encoder_leak(self, coordinator: MagicMock) -> None:
        """encoder_leak entity must be disabled in the entity registry by default."""
        sensor = _make_sensor("encoder_leak", coordinator)
        assert sensor.entity_description.entity_registry_enabled_default is False

    def test_entity_registry_disabled_endpoint_reading_missed(
        self, coordinator: MagicMock,
    ) -> None:
        """endpoint_reading_missed entity must be disabled in the entity registry by default."""
        sensor = _make_sensor("endpoint_reading_missed", coordinator)
        assert sensor.entity_description.entity_registry_enabled_default is False

    def test_entity_registry_disabled_device_alert(self, coordinator: MagicMock) -> None:
        """device_alert entity must be disabled in the entity registry by default."""
        sensor = _make_sensor("device_alert", coordinator)
        assert sensor.entity_description.entity_registry_enabled_default is False

    def test_entity_registry_enabled_leak(self, coordinator: MagicMock) -> None:
        """Primary leak sensor must be enabled in the entity registry by default."""
        sensor = _make_sensor("leak", coordinator)
        assert sensor.entity_description.entity_registry_enabled_default is True

    def test_get_flag_true(self, coordinator: MagicMock) -> None:
        """get_flag returns True when the flag field is set on the meter."""
        meter = _make_meter()
        meter.meter_info.reading.flags.encoder_leak = True
        desc = next(d for d in FLAG_SENSORS if d.key == "encoder_leak")
        sensor = EyeOnWaterBinarySensor(meter, coordinator, desc)
        assert sensor.get_flag() is True

    def test_get_flag_false(self, coordinator: MagicMock) -> None:
        """get_flag returns False when the flag field is unset."""
        sensor = _make_sensor("encoder_leak", coordinator)
        assert sensor.get_flag() is False

    def test_get_flag_missing_field_returns_false(self, coordinator: MagicMock) -> None:
        """get_flag returns False gracefully for flags not present on the meter."""
        meter = _make_meter()
        # Remove a field entirely to simulate an older meter model
        del meter.meter_info.reading.flags.__dataclass_fields__
        desc = Description(
            key="nonexistent_flag",
            device_class=BinarySensorDeviceClass.PROBLEM,
        )
        sensor = EyeOnWaterBinarySensor(meter, coordinator, desc)
        assert sensor.get_flag() is False
