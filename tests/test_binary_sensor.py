"""Tests for eyeonwater binary_sensor module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.eyeonwater.binary_sensor import (
    Description,
    EyeOnWaterBinarySensor,
    FLAG_SENSORS,
    async_setup_entry,
)
from custom_components.eyeonwater.const import (
    DATA_COORDINATOR,
    DATA_SMART_METER,
    DOMAIN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_meter_mock(meter_id="60439875", meter_uuid="5215777958325016766"):
    """Return a minimal mock meter with meter_info.reading attributes set."""
    meter = MagicMock()
    meter.meter_id = meter_id
    meter.meter_uuid = meter_uuid
    # meter_info.reading fields consumed by __init__
    meter.meter_info.reading.model = "ITRON"
    meter.meter_info.reading.customer_name = "Acme Water"
    meter.meter_info.reading.hardware_version = "1.0"
    meter.meter_info.reading.firmware_version = "2.3"
    # flags used by get_flag
    meter.meter_info.reading.flags.leak = False
    meter.meter_info.reading.flags.empty_pipe = False
    meter.meter_info.reading.flags.tamper = False
    meter.meter_info.reading.flags.cover_removed = False
    meter.meter_info.reading.flags.reverse_flow = False
    meter.meter_info.reading.flags.low_battery = True
    meter.meter_info.reading.flags.battery_charging = False
    # flags.__dict__ is used by get_flag – set up a real dict via spec trick
    meter.meter_info.reading.flags.__dict__ = {
        "leak": False,
        "empty_pipe": False,
        "tamper": False,
        "cover_removed": False,
        "reverse_flow": False,
        "low_battery": True,
        "battery_charging": False,
    }
    return meter


def _make_coordinator_mock(last_update_success=True):
    """Return a minimal mock DataUpdateCoordinator."""
    coord = MagicMock()
    coord.last_update_success = last_update_success
    coord.async_add_listener = MagicMock(return_value=MagicMock())  # returns remover
    return coord


def _make_sensor(key="leak", device_class=BinarySensorDeviceClass.MOISTURE):
    """Instantiate an EyeOnWaterBinarySensor with minimal mocks."""
    meter = _make_meter_mock()
    coordinator = _make_coordinator_mock()
    description = Description(key=key, device_class=device_class)
    sensor = EyeOnWaterBinarySensor(meter, coordinator, description)
    return sensor, meter, coordinator


# ---------------------------------------------------------------------------
# FLAG_SENSORS constant tests
# ---------------------------------------------------------------------------


class TestFlagSensors:
    """Verify FLAG_SENSORS list is complete and well-formed."""

    def test_flag_sensors_count(self):
        """There must be exactly 7 flag sensors."""
        assert len(FLAG_SENSORS) == 7

    def test_all_descriptions_have_key(self):
        """Every entry must have a non-empty key."""
        for desc in FLAG_SENSORS:
            assert isinstance(desc.key, str) and desc.key

    def test_all_descriptions_have_device_class(self):
        """Every entry must have a BinarySensorDeviceClass."""
        for desc in FLAG_SENSORS:
            assert isinstance(desc.device_class, BinarySensorDeviceClass)

    def test_keys_are_unique(self):
        """Keys must be unique across FLAG_SENSORS."""
        keys = [d.key for d in FLAG_SENSORS]
        assert len(keys) == len(set(keys))

    def test_leak_sensor_device_class(self):
        """leak → MOISTURE."""
        leak = next(d for d in FLAG_SENSORS if d.key == "leak")
        assert leak.device_class == BinarySensorDeviceClass.MOISTURE

    def test_tamper_sensor_device_class(self):
        """tamper → TAMPER."""
        tamper = next(d for d in FLAG_SENSORS if d.key == "tamper")
        assert tamper.device_class == BinarySensorDeviceClass.TAMPER

    def test_empty_pipe_sensor_device_class(self):
        """empty_pipe → PROBLEM."""
        ep = next(d for d in FLAG_SENSORS if d.key == "empty_pipe")
        assert ep.device_class == BinarySensorDeviceClass.PROBLEM

    def test_cover_removed_device_class(self):
        """cover_removed → TAMPER."""
        cr = next(d for d in FLAG_SENSORS if d.key == "cover_removed")
        assert cr.device_class == BinarySensorDeviceClass.TAMPER

    def test_reverse_flow_device_class(self):
        """reverse_flow → PROBLEM."""
        rf = next(d for d in FLAG_SENSORS if d.key == "reverse_flow")
        assert rf.device_class == BinarySensorDeviceClass.PROBLEM

    def test_low_battery_device_class(self):
        """low_battery → BATTERY."""
        lb = next(d for d in FLAG_SENSORS if d.key == "low_battery")
        assert lb.device_class == BinarySensorDeviceClass.BATTERY

    def test_battery_charging_device_class(self):
        """battery_charging → BATTERY_CHARGING."""
        bc = next(d for d in FLAG_SENSORS if d.key == "battery_charging")
        assert bc.device_class == BinarySensorDeviceClass.BATTERY_CHARGING

    def test_translation_keys_present_for_named_sensors(self):
        """Most sensors have a translation key; low_battery/battery_charging may not."""
        keyed = {d.key: d.translation_key for d in FLAG_SENSORS}
        assert keyed["leak"] == "leak"
        assert keyed["tamper"] == "tamper"
        assert keyed["empty_pipe"] == "emptypipe"


# ---------------------------------------------------------------------------
# async_setup_entry tests
# ---------------------------------------------------------------------------


class TestAsyncSetupEntry:
    """Test that async_setup_entry registers sensors correctly."""

    @pytest.mark.asyncio
    async def test_adds_one_sensor_per_flag_per_meter(self):
        """Should add len(FLAG_SENSORS) sensors for a single meter."""
        hass = MagicMock()
        coordinator = _make_coordinator_mock()
        meter = _make_meter_mock()
        smart_meter_data = MagicMock()
        smart_meter_data.meters = [meter]

        hass.data = {
            DOMAIN: {
                "entry_id": {
                    DATA_COORDINATOR: coordinator,
                    DATA_SMART_METER: smart_meter_data,
                }
            }
        }

        config_entry = MagicMock()
        config_entry.entry_id = "entry_id"

        added_entities: list = []
        capture_entities = MagicMock(
            side_effect=lambda entities, **_: added_entities.extend(entities)
        )

        await async_setup_entry(hass, config_entry, capture_entities)

        assert len(added_entities) == len(FLAG_SENSORS)
        assert all(isinstance(e, EyeOnWaterBinarySensor) for e in added_entities)

    @pytest.mark.asyncio
    async def test_adds_sensors_for_two_meters(self):
        """Each meter gets its own full set of flag sensors."""
        hass = MagicMock()
        coordinator = _make_coordinator_mock()
        meters = [_make_meter_mock("m1", "uuid1"), _make_meter_mock("m2", "uuid2")]
        smart_meter_data = MagicMock()
        smart_meter_data.meters = meters

        hass.data = {
            DOMAIN: {
                "entry_id": {
                    DATA_COORDINATOR: coordinator,
                    DATA_SMART_METER: smart_meter_data,
                }
            }
        }

        config_entry = MagicMock()
        config_entry.entry_id = "entry_id"

        added_entities: list = []
        capture_entities = MagicMock(
            side_effect=lambda entities, **_: added_entities.extend(entities)
        )

        await async_setup_entry(hass, config_entry, capture_entities)

        assert len(added_entities) == 2 * len(FLAG_SENSORS)


# ---------------------------------------------------------------------------
# EyeOnWaterBinarySensor.__init__ tests
# ---------------------------------------------------------------------------


class TestEyeOnWaterBinarySensorInit:
    """Test constructor sets instance attributes correctly."""

    def test_unique_id_format(self):
        """unique_id should be <key>_<normalised_uuid>."""
        sensor, _, _ = _make_sensor(key="leak")
        unique_id = sensor._attr_unique_id
        assert unique_id is not None
        assert unique_id.startswith("leak_")

    def test_device_info_has_domain_identifier(self):
        """DeviceInfo identifiers must contain the DOMAIN."""
        sensor, _, _ = _make_sensor()
        device_info = sensor._attr_device_info
        assert device_info is not None
        identifiers = device_info.get("identifiers") or set()
        assert any(DOMAIN in ident for ident in identifiers)

    def test_entity_description_key(self):
        """entity_description.key must match the Description key."""
        sensor, _, _ = _make_sensor(key="tamper")
        assert sensor.entity_description.key == "tamper"

    def test_entity_description_device_class(self):
        """entity_description.device_class must match the Description device_class."""
        sensor, _, _ = _make_sensor(
            key="tamper", device_class=BinarySensorDeviceClass.TAMPER
        )
        assert sensor.entity_description.device_class == BinarySensorDeviceClass.TAMPER

    def test_device_info_model_forwarded(self):
        """Device model comes from meter.meter_info.reading.model."""
        sensor, meter, _ = _make_sensor()
        device_info = sensor._attr_device_info
        assert device_info is not None
        assert device_info.get("model") == meter.meter_info.reading.model

    def test_device_info_manufacturer_forwarded(self):
        """Device manufacturer comes from meter.meter_info.reading.customer_name."""
        sensor, meter, _ = _make_sensor()
        device_info = sensor._attr_device_info
        assert device_info is not None
        assert device_info.get("manufacturer") == meter.meter_info.reading.customer_name


# ---------------------------------------------------------------------------
# get_flag tests
# ---------------------------------------------------------------------------


class TestGetFlag:
    """Test flag value retrieval."""

    def test_get_flag_returns_false(self):
        """get_flag returns False when the flag is False."""
        sensor, _, _ = _make_sensor(key="leak")
        # leak is False in our mock
        assert sensor.get_flag() is False

    def test_get_flag_returns_true(self):
        """get_flag returns True when the flag is True."""
        sensor, _, _ = _make_sensor(key="low_battery")
        # low_battery is True in our mock
        assert sensor.get_flag() is True

    def test_get_flag_battery_charging(self):
        """get_flag returns False for battery_charging flag."""
        sensor, _, _ = _make_sensor(key="battery_charging")
        assert sensor.get_flag() is False


# ---------------------------------------------------------------------------
# _state_update tests
# ---------------------------------------------------------------------------


class TestStateUpdate:
    """Test callback-driven state updates."""

    def test_state_update_sets_is_on_when_available(self):
        """When coordinator is successful, _attr_is_on is updated from flag."""
        sensor, _, coordinator = _make_sensor(key="low_battery")
        sensor._attr_is_on = None
        # Make sensor.available == True (coordinator.last_update_success=True & added)
        sensor.coordinator = coordinator
        coordinator.last_update_success = True
        # Patch available property to return True
        with patch.object(
            type(sensor), "available", new_callable=lambda: property(lambda s: True)
        ):
            sensor.async_write_ha_state = MagicMock()
            sensor._state_update()
        assert sensor._attr_is_on is True  # low_battery flag is True in mock
        sensor.async_write_ha_state.assert_called_once()

    def test_state_update_skips_set_when_unavailable(self):
        """When coordinator update failed, _attr_is_on is not updated."""
        sensor, _, _ = _make_sensor(key="low_battery")
        sensor._attr_is_on = None
        with patch.object(
            type(sensor), "available", new_callable=lambda: property(lambda s: False)
        ):
            sensor.async_write_ha_state = MagicMock()
            sensor._state_update()
        assert sensor._attr_is_on is None  # unchanged
        sensor.async_write_ha_state.assert_called_once()

    def test_state_update_always_calls_write_ha_state(self):
        """async_write_ha_state is always called regardless of availability."""
        for avail in (True, False):
            sensor, _, _ = _make_sensor(key="leak")
            sensor.async_write_ha_state = MagicMock()
            # Capture avail by value via default arg to avoid cell-var-from-loop
            avail_prop = property(lambda s, v=avail: v)
            with patch.object(type(sensor), "available", new=avail_prop):
                sensor._state_update()
            sensor.async_write_ha_state.assert_called_once()


# ---------------------------------------------------------------------------
# async_added_to_hass tests
# ---------------------------------------------------------------------------


class TestAsyncAddedToHass:
    """Test lifecycle subscription and optional state restore."""

    @pytest.mark.asyncio
    async def test_registers_listener_on_coordinator(self):
        """async_added_to_hass must register a coordinator listener."""
        sensor, _, coordinator = _make_sensor(key="leak")
        coordinator.last_update_success = True
        sensor.async_on_remove = MagicMock()
        sensor.async_get_last_state = AsyncMock(return_value=None)

        await sensor.async_added_to_hass()

        coordinator.async_add_listener.assert_called_once_with(sensor._state_update)
        sensor.async_on_remove.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_early_when_coordinator_success(self):
        """When coordinator.last_update_success=True, state is set from live data.

        No restore from last_state is attempted; _attr_is_on is populated
        directly so sensors are not Unknown at startup. HA writes state itself
        after async_added_to_hass returns — no explicit write needed here.
        """
        sensor, _, coordinator = _make_sensor(key="leak")
        coordinator.last_update_success = True
        sensor.async_on_remove = MagicMock()
        sensor.async_get_last_state = AsyncMock(return_value=MagicMock(state="on"))

        await sensor.async_added_to_hass()

        # Restore from last_state should NOT have been called
        sensor.async_get_last_state.assert_not_called()
        # State IS populated from live data (leak flag is False in mock)
        assert sensor._attr_is_on is False

    @pytest.mark.asyncio
    async def test_restores_on_state_when_no_coordinator_update(self):
        """When coordinator failed, last state 'on' is restored."""
        sensor, _, coordinator = _make_sensor(key="leak")
        coordinator.last_update_success = False
        sensor.async_on_remove = MagicMock()
        last_state = MagicMock()
        last_state.state = "on"
        sensor.async_get_last_state = AsyncMock(return_value=last_state)

        await sensor.async_added_to_hass()

        assert sensor._attr_is_on is True

    @pytest.mark.asyncio
    async def test_restores_off_state_when_no_coordinator_update(self):
        """When coordinator failed, last state 'off' is restored."""
        sensor, _, coordinator = _make_sensor(key="leak")
        coordinator.last_update_success = False
        sensor.async_on_remove = MagicMock()
        last_state = MagicMock()
        last_state.state = "off"
        sensor.async_get_last_state = AsyncMock(return_value=last_state)

        await sensor.async_added_to_hass()

        assert sensor._attr_is_on is False

    @pytest.mark.asyncio
    async def test_no_restore_when_last_state_missing(self):
        """When coordinator failed but no last state exists, _attr_is_on stays None."""
        sensor, _, coordinator = _make_sensor(key="leak")
        coordinator.last_update_success = False
        sensor.async_on_remove = MagicMock()
        sensor.async_get_last_state = AsyncMock(return_value=None)

        await sensor.async_added_to_hass()

        assert sensor._attr_is_on is None
