# PR C: feat/coordinator-hardening → feat/statistics-integrity-engine

## Summary

Hardens `EyeOnWaterData` to be resilient against the three most common real-world
failure modes: concurrent slow API reads, malformed JSON responses, and empty meter
readings on newly-provisioned accounts.  Also adds `"after_dependencies": ["energy"]`
to `manifest.json` so the integration initialises after the HA Energy Manager is ready.

**No pyonwater API changes in this PR beyond what PR B already introduced.**  The
coordinator consumes the new `statistic_helper.py` functions from PR B but adds no new
pyonwater 0.4.0 surface area.

> **Requires:** PR B (`feat/statistics-integrity-engine`) to be merged first.

---

## Target branch

`feat/statistics-integrity-engine` — base: `5f8c4d2`

## CI Status

| Workflow | Result |
| ---------- | -------- |
| `pre-commit` | ✅ Passing |
| `Tests` | ✅ Passing (52/52) |
| `hassfest` (validate) | ✅ Passing |

---

## Commits

| SHA | Message |
| ----- | --------- |
| `38ee9b2` | feat: coordinator hardening — concurrent reads, API resilience, empty-response fallback, and startup reconciliation |

---

## Files changed (4 files, +366 −130)

| File | Change |
| ------ | -------- |
| `custom_components/eyeonwater/coordinator.py` | Core rewrite — see key changes below (+368 lines) |
| `custom_components/eyeonwater/const.py` | Adds `CLIENT_TIMEOUT`, `EMPTY_RESPONSE_FINGERPRINTS`, `MAX_CONCURRENT_METER_READS` |
| `custom_components/eyeonwater/manifest.json` | Adds `"after_dependencies": ["energy"]` |
| `tests/test_coordinator.py` | Removes stale `get_last_imported_stat` / `async_add_external_statistics` patches; tests re-matched to new API |

---

## Key changes — `coordinator.py`

### 1. Concurrent meter reads

```python
# Before — sequential, O(n) wall-clock time
for meter in self.meters:
    await meter.read_meter_info(self.client)
    await meter.read_historical_data(self.client, days_to_load=days_to_load)

# After — concurrent via asyncio.gather, O(1) wall-clock time
async def _read_single_meter(meter, client, days_to_load):
    await meter.read_meter_info(client)
    await meter.read_historical_data(client, days_to_load=days_to_load)

meters = await asyncio.gather(
    *[_read_single_meter(m, self.client, days_to_load) for m in self.meters],
    return_exceptions=True,
)
```

### 2. Empty-response fingerprint fallback

Some API responses return a `{"error": "json_invalid"}` body or truncated JSON on the
first daily poll.  The coordinator now retries with `days_to_load=1` when it detects
these fingerprints:

```python
EMPTY_RESPONSE_FINGERPRINTS = {"json_invalid", "EOF while parsing"}

async def _read_single_meter(meter, client, days_to_load):
    try:
        await meter.read_historical_data(client, days_to_load=days_to_load)
    except EyeOnWaterAPIError as err:
        if any(fp in str(err) for fp in EMPTY_RESPONSE_FINGERPRINTS):
            await meter.read_historical_data(client, days_to_load=1)
        else:
            raise
```

### 3. `import_historical_data` keyword args

```python
async def import_historical_data(
    self,
    hass: HomeAssistant,
    meter: Meter,
    *,
    force_overwrite: bool = False,
    purge_states: bool = False,
) -> None:
```

### 4. `resolve_price_from_energy_manager`

```python
async def resolve_price_from_energy_manager(
    hass: HomeAssistant,
    statistic_id: str,
) -> float | None:
    """Read the configured water-source price from the HA Energy Manager."""
```

### 5. `manifest.json` — energy after-dependency

```json
{
  "after_dependencies": ["energy"],
  "dependencies": ["recorder"]
}
```

This ensures `async_setup_entry` is not called until after the HA Energy Manager has
finished configuring water sources, preventing a race condition on first boot where
`resolve_price_from_energy_manager` would return `None`.

---

## Notes

- `test_coordinator.py` was updated to remove patches for `coordinator.get_last_imported_stat`
  and `coordinator.async_add_external_statistics` — neither is imported directly into
  `coordinator.py` in this branch (they live in `statistic_helper.py`).
- All 52 tests pass; no new test files in this PR (comprehensive tests land in PR E).
