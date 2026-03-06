---
name: add-ha-entity
description: 'Add a new sensor or binary_sensor entity to the eyeonwater Home Assistant integration following CoordinatorEntity patterns. Use this when asked to expose a new data point, add a water usage sensor, add a leak alert binary sensor, or surface any new meter attribute as a HA entity. Covers entity class, translation strings, const.py keys, async_setup_entry registration, and test pattern.'
---

# Add a New HA Entity

eyeonwater entities always read from `coordinator.data` — never call pyonwater directly. All entities must inherit from `CoordinatorEntity` and follow HA's update/availability contract.

## Checklist

- [ ] Entity class added to `sensor.py` or `binary_sensor.py`
- [ ] Entity registered in `async_setup_entry` of the same file
- [ ] Translation key added to `strings.json` and `translations/en.json` (identical structure)
- [ ] Constants (platform keys, state keys) added to `const.py`
- [ ] `unique_id` follows the pattern `{meter_uuid}_{attribute_name}`
- [ ] Test added to `test_sensor.py` or `test_binary_sensor.py`

## Sensor Entity Pattern

```python
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import EyeOnWaterCoordinator


class WaterUsageSensor(CoordinatorEntity[EyeOnWaterCoordinator], SensorEntity):
    """Sensor for current water usage reading."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_translation_key = "water_usage"  # must match strings.json key

    def __init__(self, coordinator: EyeOnWaterCoordinator, meter_uuid: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._meter_uuid = meter_uuid
        self._attr_unique_id = f"{meter_uuid}_usage"

    @property
    def native_value(self) -> float | None:
        """Return the current usage value."""
        meter = self.coordinator.data.get(self._meter_uuid)
        return meter.reading if meter is not None else None

    @property
    def available(self) -> bool:
        """Unavailable when coordinator failed or meter disappeared."""
        return (
            self.coordinator.last_update_success
            and self._meter_uuid in self.coordinator.data
        )
```

## Binary Sensor Entity Pattern

```python
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity


class LeakAlertBinarySensor(CoordinatorEntity[EyeOnWaterCoordinator], BinarySensorEntity):
    """Binary sensor for leak alert."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.MOISTURE
    _attr_translation_key = "leak_detected"

    def __init__(self, coordinator: EyeOnWaterCoordinator, meter_uuid: str) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._meter_uuid = meter_uuid
        self._attr_unique_id = f"{meter_uuid}_leak"

    @property
    def is_on(self) -> bool | None:
        """Return True if a leak is detected."""
        meter = self.coordinator.data.get(self._meter_uuid)
        return meter.has_leak if meter is not None else None

    @property
    def available(self) -> bool:
        """Unavailable when coordinator failed or meter disappeared."""
        return (
            self.coordinator.last_update_success
            and self._meter_uuid in self.coordinator.data
        )
```

## Translation Strings

Add to `strings.json` **and** `translations/en.json` (both files must be kept in sync):

```json
{
  "entity": {
    "sensor": {
      "water_usage": {
        "name": "Water Usage"
      }
    },
    "binary_sensor": {
      "leak_detected": {
        "name": "Leak Detected"
      }
    }
  }
}
```

## Registration in `async_setup_entry`

```python
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up eyeonwater sensors from a config entry."""
    coordinator: EyeOnWaterCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        WaterUsageSensor(coordinator, meter_uuid)
        for meter_uuid in coordinator.data
    )
```

## Test Pattern

```python
from unittest.mock import MagicMock

async def test_water_usage_sensor_native_value(hass: HomeAssistant) -> None:
    """Sensor returns reading from coordinator data."""
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {"meter-123": MagicMock(reading=42.5)}

    entity = WaterUsageSensor(coordinator, "meter-123")
    assert entity.native_value == 42.5
    assert entity.available is True


async def test_water_usage_sensor_unavailable_on_coordinator_failure(hass: HomeAssistant) -> None:
    """Sensor becomes unavailable when coordinator fails."""
    coordinator = MagicMock()
    coordinator.last_update_success = False
    coordinator.data = {}

    entity = WaterUsageSensor(coordinator, "meter-123")
    assert entity.available is False
```

## Invariants

- Entities **must** become unavailable when `coordinator.last_update_success` is `False` — never leave stale state
- All user-visible strings go through `_attr_translation_key` — never hardcode text
- All new keys in `const.py` — no magic strings inline in entity files
- `_attr_unique_id` must be globally unique; use `{meter_uuid}_{attribute_name}` pattern
- Always test both the happy path and the unavailable/missing-meter path
