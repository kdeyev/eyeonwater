# PR B: feat/statistics-integrity-engine → chore/toolchain-modernization

## Summary

Complete rewrite of `statistic_helper.py` and introduction of the new
`statistics_tools.py` module.  Addresses the root cause of the "negative water usage"
Energy Dashboard bug: the HA statistics compiler can write `sum=0` rows into the
long-term statistics (LTS) table when an entity is offline at an hourly rollup boundary.
This PR introduces carry-forward repair, monotonicity enforcement, and compiler
contamination detection.

> **Requires:** `pyonwater >= 0.4.0` (`enforce_monotonic_total`, `filter_points_after`,
> `DataPoint.unit`).  An inline fallback is provided for CI compatibility while
> [kdeyev/pyonwater#46](https://github.com/kdeyev/pyonwater/pull/46) lands on PyPI.

---

## Target branch

`chore/toolchain-modernization` — base: `58b8917`

## CI Status

| Workflow | Result |
| ---------- | -------- |
| `pre-commit` | ✅ Passing |
| `Tests` | ✅ Passing (inline fallback active; 52/52) |
| `hassfest` (validate) | ✅ Passing |

---

## Commits

| SHA | Message |
| ----- | --------- |
| `5f8c4d2` | feat: statistics integrity engine — carry-forward repair, monotonicity, and compiler contamination fixes |

---

## Files changed (7 files, +1 130 −106)

| File | Change |
| ------ | -------- |
| `custom_components/eyeonwater/statistic_helper.py` | Complete rewrite — see key exports below (+945 lines) |
| `custom_components/eyeonwater/statistics_tools.py` | **New** — monotonic validation and bulk-delete helpers (+226 lines) |
| `custom_components/eyeonwater/const.py` | Adds `STATISTICS_VALIDATION_BATCH_SIZE`, `MAX_VIOLATION_LOG_DISPLAY`, `COST_STAT_SUFFIX` |
| `custom_components/eyeonwater/coordinator.py` | Updates import: `get_last_imported_time` → `get_last_imported_stat`; fixes tuple unpacking |
| `tests/conftest.py` | Adds `sample_datapoints` fixture; `unit=NativeUnits.GAL` on `FakeDataPoint` |
| `tests/test_statistic_helper.py` | Updates tests to new API: `get_entity_statistic_id`, `source="recorder"`, 3-tuple returns |
| `tests/test_coordinator.py` | Removes stale patches for moved functions |

---

## Key new exports — `statistic_helper.py`

### Entry points

| Function | Description |
| ---------- | ------------- |
| `centralized_import_statistics` | Single entry point for LTS import (consumption + cost rows) |
| `async_write_carry_forward_stats` | Detects compiler-contaminated `sum=0` rows and overwrites them with carried-forward values |
| `get_last_imported_stat` | Returns `(datetime \| None, state \| None, sum \| None)` — the full last-row context needed for continuity |

### Computation helpers

| Function | Description |
| ---------- | ------------- |
| `convert_statistic_data` | Converts `list[DataPoint]` → `list[StatisticData]`; integrates `enforce_monotonic_total(clamp_min=None)` |
| `convert_cost_statistic_data` | Parallel cost rows from energy-price schedule |
| `filter_newer_data` | Drops data points at or before the last imported timestamp |
| `get_statistic_metadata` | Builds `StatisticMetaData` TypedDict with `source="recorder"` |
| `get_entity_statistic_id` | Returns `sensor.water_meter_{normalized_id}` |
| `get_cost_statistic_id` | Returns `sensor.water_meter_{normalized_id}_cost` |

### Anchor/overlap helpers

| Function | Description |
| ---------- | ------------- |
| `async_get_highest_sum_stat` | Finds the uncorrupted maximum-sum row (baseline anchor) |
| `async_get_stat_just_before` | Finds the last clean row before a given timestamp (backfill overlap base) |

### Bulk-delete helpers

| Function | Description |
| ---------- | ------------- |
| `async_delete_statistics_after` | Deletes LTS rows after a given timestamp |
| `async_delete_all_short_term_statistics` | Purges all short-term statistics for a statistic ID |
| `async_delete_entity_states` | Purges entity state history |

---

## Key new exports — `statistics_tools.py`

```python
@dataclass
class MonotonicViolation:
    """Represents a sum regression in the LTS table."""
    statistic_id: str
    start: datetime
    expected_min: float
    actual_sum: float

@dataclass
class MonotonicValidationResult:
    violations: list[MonotonicViolation]
    rows_checked: int
    statistic_id: str

async def validate_monotonic_sums(
    hass, statistic_id, *, start=None, end=None, batch_size=500
) -> MonotonicValidationResult: ...

async def delete_statistics(hass, statistic_id, *, after=None) -> int: ...
async def resolve_statistic_id(hass, entity_id) -> str | None: ...
```

---

## Architecture: why `source="recorder"` not `"eyeonwater"`?

Prior versions used `async_add_external_statistics` with `source="eyeonwater"`.  This
produced correct LTS rows but prevented the Energy Dashboard cost column from populating,
because HA only links cost to `sensor.*`-namespace statistics with `TOTAL_INCREASING`
state class.

The rewrite uses `async_import_statistics` with `source="recorder"`, which writes
directly into the recorder namespace so the entity's `state_class = TOTAL_INCREASING`
drives Energy Dashboard cost calculation natively.

---

## Notes

- The inline fallback for `enforce_monotonic_total` / `filter_points_after` in
  `statistic_helper.py` is intentionally temporary.  It will be removed once
  `pyonwater==0.4.0` is published and `D`/`E` branches land.
- `get_statistics_id` (old external-statistics name) has been removed; use
  `get_entity_statistic_id` going forward.
- `_HAS_MEAN_TYPE` guard is gone — `StatisticMeanType` is unconditionally available
  in the HA versions we target.
