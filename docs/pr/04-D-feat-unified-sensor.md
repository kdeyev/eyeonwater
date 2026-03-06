# PR D: feat/unified-sensor → feat/coordinator-hardening

## Summary

Replaces the legacy `EyeOnWaterSensor(CoordinatorEntity)` with a new
`EyeOnWaterUnifiedSensor(RestoreEntity, SensorEntity)` architecture.  One sensor per
meter, `TOTAL_INCREASING` state class, LTS carry-forward on startup, and five HA service
actions for operator control.  Also adds an `EyeOnWaterOptionsFlow` and removes the
custom cost option UI (cost is now resolved from the HA Energy Dashboard automatically).

> **Requires:** `pyonwater >= 0.4.0` — this PR sets `pyonwater==0.4.0` in
> `.github/workflows/tests.yml`.  The `Tests` CI workflow will fail until
> [kdeyev/pyonwater#46](https://github.com/kdeyev/pyonwater/pull/46) is merged and
> published to PyPI.  `pre-commit` and `hassfest` pass today.

---

## Target branch

`feat/coordinator-hardening` — base: `38ee9b2`

## CI Status

| Workflow | Result |
| ---------- | -------- |
| `pre-commit` | ✅ Passing |
| `Tests` | ❌ Expected failure — `pyonwater==0.4.0` not yet on PyPI |
| `hassfest` (validate) | ✅ Passing |

---

## Commits

| SHA | Message |
| ----- | --------- |
| `72bc6d0` | feat: unified sensor architecture — EyeOnWaterUnifiedSensor, service actions, config flow, pyonwater 0.4.0 |

---

## Files changed (10 files, +1 624 −138)

| File | Change |
| ------ | -------- |
| `custom_components/eyeonwater/sensor.py` | `EyeOnWaterUnifiedSensor` (+749 lines) |
| `custom_components/eyeonwater/__init__.py` | 5 service handlers (+591 lines) |
| `custom_components/eyeonwater/services.yaml` | Full service schema (+208 lines) |
| `custom_components/eyeonwater/strings.json` | Service strings + options flow strings (+95 lines) |
| `custom_components/eyeonwater/config_flow.py` | `EyeOnWaterOptionsFlow`, `is_matching`, typed params (+53 lines) |
| `custom_components/eyeonwater/binary_sensor.py` | MRO fix, startup state population, type annotations (+36 lines) |
| `custom_components/eyeonwater/const.py` | Service-name constants, `DEBOUNCE_COOLDOWN` (+7 lines) |
| `custom_components/eyeonwater/system_health.py` | Minor type annotation (+4 lines) |
| `custom_components/eyeonwater/translations/en.json` | Removes custom cost UI strings (−13 lines) |
| `.github/workflows/tests.yml` | Sets `pip install "pyonwater==0.4.0"` |

---

## Key changes — `sensor.py`

### New class: `EyeOnWaterUnifiedSensor`

```python
class EyeOnWaterUnifiedSensor(RestoreEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_should_poll = False
```

**Why `RestoreEntity` instead of `CoordinatorEntity`?**

`CoordinatorEntity` pushes state on every coordinator poll (every ~15 minutes), which
creates spurious short-term statistics rows and causes the HA recorder to overwrite
correctly-imported LTS rows at the next hourly rollup.  `RestoreEntity` gives full
control: state is written only when the API delivers genuinely new data points.

**Startup reconciliation** (`async_added_to_hass`):

1. Restores last known `_attr_native_value` from HA state machine.
2. Queries recorder for last LTS row via `get_last_imported_stat`.
3. If restored value diverges from DB sum, applies carry-forward correction before
   writing state.

**Statistic ID format change:**

| Old (PR A base) | New (PR D) |
| --------------- | ------------ |
| `eyeonwater:water_meter_{id}` | `sensor.water_meter_{id}` |

This shifts from the external-statistics namespace to the recorder namespace, enabling
native `TOTAL_INCREASING` cost calculation in the Energy Dashboard.

---

## Key changes — `__init__.py` — Service actions

Five operator services registered in `async_setup_entry`:

| Service | Description |
| --------- | ------------- |
| `import_historical_data` | Fetches full API history and imports to LTS; optional `meter_id`, `days_to_load`, `force_overwrite`, `purge_states` |
| `replay_scenario` | Replays a JSON fixture file into LTS (testing/recovery) |
| `validate_statistics_monotonic` | Scans LTS for sum regressions and logs violations |
| `read_meter` | Forces an immediate single-meter API read + state update |
| `reset_statistics` | Deletes all LTS rows and entity states for a meter |

---

## Key changes — `config_flow.py`

```python
class EyeOnWaterOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        """Options: days_to_load, scan_interval."""

@staticmethod
def async_get_options_flow(config_entry):
    return EyeOnWaterOptionsFlow(config_entry)
```

`is_matching` added for config-entry deduplication:

```python
@staticmethod
def is_matching(self, other_flow) -> bool:
    return other_flow.context.get("unique_id") == self.context.get("unique_id")
```

---

## Notes

- `EyeOnWaterSensor` (the old sensor class) is fully replaced; there is no migration
  path for existing entity IDs.  Users upgrading from v2.6.x will see a new
  `sensor.water_meter_*` entity; the old entity can be removed manually.
- The cost option (`CONF_COST_PER_UNIT`, `CONF_METER_UNIT`) is removed from the UI.
  Cost is resolved automatically from the HA Energy Dashboard water-source price.
- `binary_sensor.py` MRO fix: `CoordinatorEntity` was previously listed after
  `BinarySensorEntity`, causing `async_added_to_hass` to not subscribe to coordinator
  updates on some HA versions.  Fixed to `CoordinatorEntity, BinarySensorEntity, RestoreEntity`.
