---
name: debug-ha-coordinator
description: 'Debug data flow and update failures in the eyeonwater EyeOnWaterCoordinator. Use this when entities show unavailable, coordinator updates fail, sensors show stale data, statistics stop updating, or a KeyError on meter_uuid occurs. Maps the full update chain from Account to MeterReader to coordinator.data to entity.'
---

# Debug HA Coordinator Issues

The `EyeOnWaterCoordinator` in `coordinator.py` is the single data source for all entities. All debugging starts here.

## Data Flow

```
EyeOnWaterCoordinator.async_update_data()
    → Account.authenticate()
    → MeterReader.read_meter_info(client)        # populates meter metadata
    → Meter.read_historical_data(client, ...)    # populates usage data
    → stores result in coordinator.data
        → CoordinatorEntity.coordinator.data     # entities read from here
```

## Symptom: All Sensors Show Unavailable

**Cause**: `coordinator.last_update_success` is `False` — an exception was raised during `async_update_data()`.

**Check**:
1. Enable debug logging in `configuration.yaml`:
   ```yaml
   logger:
     default: warning
     logs:
       custom_components.eyeonwater: debug
       pyonwater: debug
   ```
2. Look for `EyeOnWaterAuthError`, `EyeOnWaterRateLimitError`, or `EyeOnWaterAPIError` in HA logs.

**Common causes**:
- `EyeOnWaterAuthError` → credentials changed or account locked
- `EyeOnWaterRateLimitError` → too many requests; coordinator backs off automatically via tenacity
- `EyeOnWaterAPIError` with "Unexpected EOW response" → API shape changed; check `pyonwater` models against live API

## Symptom: Some Sensors Unavailable, Others Fine

An entity's `available` property delegates to `coordinator.last_update_success`. If only some entities are unavailable, check that they all inherit from `CoordinatorEntity` and don't override `available` incorrectly.

## Symptom: Stale Data / No Updates

**Check update interval**: `const.py` defines `SCAN_INTERVAL`. The coordinator calls `async_config_entry_first_refresh()` on setup (raises `ConfigEntryNotReady` if it fails) and then polls on `SCAN_INTERVAL`.

**Check `coordinator.data` shape**: The coordinator stores `dict[str, Meter]` keyed by `meter_uuid`. Each entity reads `coordinator.data[meter_uuid]`. If the key changes (meter UUID changed), entities will raise `KeyError`.

## Symptom: Statistics Not Updating

Statistics are injected by `statistic_helper.py`, not the coordinator. Debug separately:
- Check `statistics_tools.py` for `validate_statistics()` and `delete_statistics()` helpers.
- Statistics use `recorder` — ensure the recorder integration is running.

## Writing a Coordinator Test

```python
from unittest.mock import AsyncMock, patch

async def test_coordinator_update(hass, config_entry):
    with patch("custom_components.eyeonwater.coordinator.Account") as mock_account:
        mock_account.return_value.fetch_meters = AsyncMock(return_value=[...])
        coordinator = EyeOnWaterCoordinator(hass, config_entry)
        await coordinator.async_config_entry_first_refresh()
        assert coordinator.last_update_success is True
```

Always mock at `coordinator.py`'s import boundary, not inside pyonwater.
