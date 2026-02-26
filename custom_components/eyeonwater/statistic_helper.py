"""Helper functions used for import statistics."""

import asyncio
import datetime
import logging
from collections.abc import Sequence

import pyonwater
import sqlalchemy as sa
from homeassistant import exceptions
from homeassistant.components.recorder.db_schema import (
    States,
    StatesMeta,
    Statistics,
    StatisticsMeta,
    StatisticsShortTerm,
)
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dtutil
from pyonwater import DataPoint, Meter, enforce_monotonic_total, filter_points_after

from .const import COST_STAT_SUFFIX, WATER_METER_NAME

_LOGGER = logging.getLogger(__name__)


PYONWATER_UNIT_MAP: dict[pyonwater.NativeUnits, UnitOfVolume] = {
    pyonwater.NativeUnits.GAL: UnitOfVolume.GALLONS,
    pyonwater.NativeUnits.CF: UnitOfVolume.CUBIC_FEET,
    pyonwater.NativeUnits.CM: UnitOfVolume.CUBIC_METERS,
}


class UnrecognizedUnitError(exceptions.HomeAssistantError):
    """Error to indicate unrecognized pyonwater native unit."""


def get_ha_native_unit_of_measurement(
    unit: pyonwater.NativeUnits,
) -> UnitOfVolume:
    """Convert pyonwater native units to HA native units."""
    ha_unit = PYONWATER_UNIT_MAP.get(unit)
    if ha_unit is None:
        msg = f"Unrecognized pyonwater unit {unit}"
        raise UnrecognizedUnitError(msg)
    return ha_unit


def get_statistic_name(meter_id: str) -> str:
    """Generate statistic name for a meter."""
    meter_id = normalize_id(meter_id)
    return f"{WATER_METER_NAME} {meter_id}"


def normalize_id(uuid: str) -> str:
    """Normalize an identifier for entity/statistic usage."""
    chars = [c if c.isalnum() or c == "_" else "_" for c in uuid]
    uuid = "".join(chars)
    return uuid.lower()


def get_entity_statistic_id(meter_id: str) -> str:
    """Generate statistic ID that matches the sensor entity ID."""
    meter_id = normalize_id(meter_id)
    return f"sensor.water_meter_{meter_id}"


def get_cost_statistic_id(meter_id: str) -> str:
    """Generate cost statistic ID for a meter (parallel to consumption stat)."""
    return f"{get_entity_statistic_id(meter_id)}{COST_STAT_SUFFIX}"


def get_cost_statistic_name(meter_id: str) -> str:
    """Generate human-readable cost statistic name for a meter."""
    meter_id = normalize_id(meter_id)
    return f"{WATER_METER_NAME} {meter_id} Cost"


def get_cost_statistic_metadata(
    meter: Meter,
    *,
    statistic_id: str | None = None,
    name: str | None = None,
    currency: str = "USD",
) -> StatisticMetaData:
    """Build statistic metadata for the cost LTS companion stat.

    The cost stat has no backing entity — it is written exclusively via
    ``async_import_statistics`` and read by the Energy Dashboard frontend
    via ``statistics_during_period`` when configured as ``stat_cost``.
    """
    name = name or get_cost_statistic_name(meter_id=meter.meter_id)
    statistic_id = statistic_id or get_cost_statistic_id(meter.meter_id)
    return StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=name,
        source="recorder",
        statistic_id=statistic_id,
        unit_of_measurement=currency,
        mean_type=StatisticMeanType.NONE,
        unit_class=None,
    )


def convert_cost_statistic_data(
    data: Sequence[DataPoint],
    price_per_unit: float,
    *,
    last_cost_sum: float | None = None,
    last_reading: float | None = None,
) -> list[StatisticData]:
    """Convert meter readings into cost LTS rows.

    Mirrors ``convert_statistic_data`` but accumulates cost instead of volume.
    Each interval's cost = consumption_delta x price_per_unit.

    Args:
        data: Sequence of DataPoint readings (already monotonic).
        price_per_unit: Rate in currency-per-unit-of-volume.
        last_cost_sum: Previous cumulative cost sum for continuity.
        last_reading: Previous meter reading (volume) for delta calculation.

    Returns:
        List of StatisticData ready for ``async_import_statistics``.

    """
    if not data:
        return []

    normalized_data = enforce_monotonic_total(list(data), clamp_min=None)

    result: list[StatisticData] = []
    cumulative_cost = last_cost_sum or 0.0
    previous_reading = (
        last_reading if last_reading is not None else normalized_data[0].reading
    )

    for row in normalized_data:
        consumption = row.reading - previous_reading
        cost_delta = consumption * price_per_unit
        cumulative_cost += cost_delta

        result.append(
            {
                "start": row.dt,
                "state": float(cumulative_cost),
                "sum": float(cumulative_cost),
            },
        )
        previous_reading = row.reading

    _LOGGER.debug(
        "convert_cost_statistic_data: %d rows, rate=%.6f, final_sum=%.4f",
        len(result),
        price_per_unit,
        result[-1].get("sum", 0.0) if result else 0.0,
    )
    return result


def get_statistic_metadata(
    meter: Meter,
    *,
    statistic_id: str | None = None,
    name: str | None = None,
) -> StatisticMetaData:
    """Build statistic metadata for a given meter."""
    name = name or get_statistic_name(meter_id=meter.meter_id)
    statistic_id = statistic_id or get_entity_statistic_id(meter.meter_id)
    unit_str = meter.native_unit_of_measurement
    unit_enum = pyonwater.NativeUnits(unit_str)

    return StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=name,
        source="recorder",
        statistic_id=statistic_id,
        unit_of_measurement=get_ha_native_unit_of_measurement(unit_enum).value,
        mean_type=StatisticMeanType.NONE,
        unit_class="volume",
    )


def convert_statistic_data(
    data: Sequence[DataPoint],
    *,
    last_sum: float | None = None,
    last_reading: float | None = None,
) -> list[StatisticData]:
    """Convert meter readings into Home Assistant statistic rows.

    Home Assistant expects a monotonic cumulative `sum`. Consumption per interval
    is derived from changes in this cumulative value.

    Args:
        data: Sequence of DataPoint readings (list, tuple, or other sequence).
        last_sum: Previous cumulative sum for continuity.
        last_reading: Previous meter reading for delta calculation.

    Returns:
        List of StatisticData ready for import.

    """
    _LOGGER.debug("convert_statistic_data: input %d points", len(data))
    if data:
        _LOGGER.debug(
            "convert_statistic_data: first point dt=%s, reading=%s",
            data[0].dt,
            data[0].reading,
        )

    normalized_data = enforce_monotonic_total(list(data), clamp_min=None)

    _LOGGER.debug(
        "convert_statistic_data: after enforce_monotonic_total %d points",
        len(normalized_data),
    )
    if normalized_data:
        _LOGGER.debug(
            "convert_statistic_data: first normalized dt=%s, reading=%s",
            normalized_data[0].dt,
            normalized_data[0].reading,
        )

    result: list[StatisticData] = []
    # Continue cumulative sum from the last database value (or start at 0).
    cumulative_sum = last_sum or 0.0
    # For delta calculation, use last_reading if provided.
    previous_reading = (
        last_reading
        if last_reading is not None
        else (normalized_data[0].reading if normalized_data else 0.0)
    )

    _LOGGER.debug(
        "Starting loop: len=%d, prev_reading=%.2f, cumsum=%.2f (continuation=%s)",
        len(normalized_data),
        previous_reading,
        cumulative_sum,
        last_reading is not None,
    )

    for i, row in enumerate(normalized_data):
        # Calculate consumption as delta from previous reading and accumulate.
        consumption = row.reading - previous_reading
        cumulative_sum += consumption

        _LOGGER.debug(
            "Loop iteration %d: Converting reading: previous=%.2f, current=%.2f, "
            "delta=%.2f, cumulative=%.2f, dt=%s",
            i,
            previous_reading,
            row.reading,
            consumption,
            cumulative_sum,
            row.dt,
        )

        stat_dict: StatisticData = {
            "start": row.dt,
            "state": float(row.reading),
            "sum": float(cumulative_sum),
        }
        _LOGGER.debug(
            "Created stat_dict %d: start=%s, state=%.2f, sum=%.2f",
            i,
            stat_dict["start"],
            stat_dict["state"],
            stat_dict["sum"],
        )
        result.append(stat_dict)
        previous_reading = row.reading

    _LOGGER.debug(
        "convert_statistic_data: returning %d dicts",
        len(result),
    )
    return result


async def get_last_imported_stat(
    hass: HomeAssistant,
    meter: Meter,
    *,
    statistic_id: str | None = None,
) -> tuple[datetime.datetime | None, float | None, float | None]:
    """Return last imported statistic datetime, state, and sum."""
    statistic_id = statistic_id or get_entity_statistic_id(meter.meter_id)
    recorder = get_instance(hass)
    _LOGGER.debug("Recorder db_url=%s", recorder.db_url)
    _LOGGER.debug("Querying last statistics for %s", statistic_id)
    include_start = True
    last_stats = await recorder.async_add_executor_job(
        get_last_statistics,
        hass,
        1,
        statistic_id,
        include_start,
        {"start", "state", "sum"},
    )
    _LOGGER.debug(
        "last_stats keys=%s",
        list(last_stats.keys()) if last_stats else None,
    )

    if last_stats and statistic_id in last_stats:
        first_stat = last_stats[statistic_id][0]
        start_time = first_stat.get("start")
        last_state = first_stat.get("state")
        last_sum = first_stat.get("sum")

        if start_time is not None:
            # Always use Home Assistant's timezone utilities for consistency
            date = dtutil.as_local(
                datetime.datetime.fromtimestamp(
                    start_time,
                    tz=datetime.datetime.now(datetime.UTC).tzinfo,
                ),
            )
            _LOGGER.debug(
                "Last stat date %s, state %s, sum %s",
                date,
                last_state,
                last_sum,
            )
            return date, last_state, last_sum

    _LOGGER.debug("No previous statistics found for %s", statistic_id)
    return None, None, None


def filter_newer_data(
    data: list[DataPoint],
    last_imported_time: datetime.datetime | None,
) -> list[DataPoint]:
    """Filter data points newer than given datetime.

    Uses pyonwater's filter_points_after for optimized filtering.
    """
    if not data:
        return data

    _LOGGER.debug(
        "last_imported_time %s - data %s",
        last_imported_time,
        data[-1].dt if data else None,
    )

    if last_imported_time is not None:
        data = filter_points_after(data, last_imported_time)

    _LOGGER.debug("%i data points found", len(data))
    return data


async def async_get_stat_just_before(
    hass: HomeAssistant,
    statistic_id: str,
    before_dt: datetime.datetime,
) -> tuple[float | None, float | None]:
    """Return (state, sum) of the last statistic strictly before before_dt.

    Used to find the correct continuation base when a backfill import overlaps
    with data already in the statistics table.
    """
    # Search up to 1 year back to find a previous stat.
    window_start = before_dt - datetime.timedelta(days=365)
    recorder = get_instance(hass)
    stats = await recorder.async_add_executor_job(
        statistics_during_period,
        hass,
        window_start,
        before_dt,
        {statistic_id},
        "hour",
        None,
        {"state", "sum"},
    )
    if stats and statistic_id in stats:
        entries = stats[statistic_id]
        if entries:
            last = entries[-1]
            state = last.get("state")
            cumsum = last.get("sum")
            _LOGGER.debug(
                "async_get_stat_just_before %s: found state=%.2f, sum=%.2f",
                before_dt,
                state if state is not None else 0.0,
                cumsum if cumsum is not None else 0.0,
            )
            return state, cumsum
    _LOGGER.debug("async_get_stat_just_before %s: no stat found", before_dt)
    return None, None


async def async_get_highest_sum_stat(
    hass: HomeAssistant,
    statistic_id: str,
) -> tuple[datetime.datetime | None, float | None, float | None]:
    """Return (start_dt, state, sum) for the row with the highest cumulative sum.

    For a ``TOTAL_INCREASING`` statistic the cumulative sum only ever grows
    when data is imported via ``async_import_statistics``.  When HA's hourly
    statistics compiler writes rows after a restart it derives its sum from the
    entity's short-term stat sum (which resets to ≈0) rather than from the
    correct LTS baseline, producing rows with a *lower* sum than the last
    correctly-imported row.  The row with the **maximum** sum is therefore
    always the last row written by a real import — never a compiler row —
    making it a reliable uncorrupted anchor even when the contamination spans
    multiple days.

    Returns ``(None, None, None)`` when the statistics table has no rows for
    the given statistic_id.
    """
    recorder_instance = get_instance(hass)

    def _do_query() -> tuple[datetime.datetime | None, float | None, float | None]:
        with recorder_instance.get_session() as session:
            row = session.execute(
                sa.select(
                    Statistics.start_ts,
                    Statistics.state,
                    Statistics.sum,
                )
                .join(
                    StatisticsMeta,
                    Statistics.metadata_id == StatisticsMeta.id,
                )
                .where(StatisticsMeta.statistic_id == statistic_id)
                .order_by(Statistics.sum.desc())
                .limit(1),
            ).fetchone()
        if row is None:
            return None, None, None
        start_dt = dtutil.as_local(
            datetime.datetime.fromtimestamp(
                row.start_ts,
                tz=datetime.UTC,
            ),
        )
        return start_dt, row.state, row.sum

    result = await recorder_instance.async_add_executor_job(_do_query)
    if result[0] is not None:
        _LOGGER.debug(
            "async_get_highest_sum_stat for %s: start=%s state=%.4f sum=%.4f",
            statistic_id,
            result[0],
            result[1],
            result[2],
        )
    else:
        _LOGGER.debug("async_get_highest_sum_stat for %s: no rows found", statistic_id)
    return result


async def async_delete_statistics_after(
    hass: HomeAssistant,
    statistic_id: str,
    after_dt: datetime.datetime,
) -> tuple[int, int]:
    """Delete LTS and short-term statistics rows strictly after after_dt.

    Used to remove contaminated recorder-compiled rows (e.g. sum=0 rows
    written by HA's stats compiler after a TOTAL_INCREASING restore) that fall
    beyond the last manually imported data point.  After deletion, HA's
    recorder re-derives those hours correctly from the clean LTS anchor.

    Args:
        hass: Home Assistant instance.
        statistic_id: Statistic ID whose rows should be cleaned.
        after_dt: Timezone-aware datetime.  Rows with start_ts > this are deleted.

    Returns:
        Tuple of (lts_deleted, short_term_deleted) row counts.

    """
    recorder_instance = get_instance(hass)
    after_ts = after_dt.timestamp()

    def _do_delete() -> tuple[int, int]:
        with recorder_instance.get_session() as session:
            # Fetch ALL metadata rows for this statistic_id.  HA uses a single
            # source="recorder" for all statistics, but defensive iteration over
            # every matching metadata_id guard against any future schema change
            # or duplicate rows.  Using .first() would silently skip extras,
            # potentially leaving contaminated rows behind.
            meta_rows = session.execute(
                sa.select(StatisticsMeta.id, StatisticsMeta.source).where(
                    StatisticsMeta.statistic_id == statistic_id,
                ),
            ).fetchall()
            if not meta_rows:
                _LOGGER.warning(
                    "No metadata_id found for %s in statistics_meta; cannot purge",
                    statistic_id,
                )
                return 0, 0

            n_lts = 0
            n_short = 0
            for meta_row in meta_rows:
                metadata_id = meta_row[0]
                source = meta_row[1]
                lts_deleted = session.execute(
                    sa.delete(Statistics).where(
                        Statistics.metadata_id == metadata_id,
                        Statistics.start_ts > after_ts,
                    ),
                ).rowcount
                short_deleted = session.execute(
                    sa.delete(StatisticsShortTerm).where(
                        StatisticsShortTerm.metadata_id == metadata_id,
                        StatisticsShortTerm.start_ts > after_ts,
                    ),
                ).rowcount
                _LOGGER.debug(
                    "Deleted %d LTS + %d short-term rows for metadata_id=%d "
                    "(source=%s, statistic_id=%s)",
                    lts_deleted,
                    short_deleted,
                    metadata_id,
                    source,
                    statistic_id,
                )
                n_lts += lts_deleted
                n_short += short_deleted
            session.commit()
        return n_lts, n_short

    n_lts, n_short = await recorder_instance.async_add_executor_job(_do_delete)
    _LOGGER.info(
        "Purged %d LTS and %d short-term statistics after %s for %s",
        n_lts,
        n_short,
        after_dt,
        statistic_id,
    )
    return n_lts, n_short


async def async_delete_all_short_term_statistics(
    hass: HomeAssistant,
    statistic_id: str,
) -> int:
    """Delete ALL statistics_short_term rows for a statistic_id.

    Used for synthetic statistics (e.g. the cost companion stat) that have no
    valid backing entity.  HA's 5-min recorder compiler derives short-term rows
    from the EnergyCostSensor entity state, which oscillates between $0 and the
    correct value during startup.  Because there is no sensor state to restore
    from after a historical import cleans the states table, all short-term rows
    for the cost stat are stale and should be wiped so the History view cannot
    render a spurious TOTAL_INCREASING decrease (negative bar).

    Unlike ``async_delete_statistics_after`` this function removes every
    short-term row regardless of timestamp — LTS rows are left untouched.

    Args:
        hass: Home Assistant instance.
        statistic_id: Statistic ID whose short-term rows should be cleared.

    Returns:
        Number of short-term rows deleted.

    """
    recorder_instance = get_instance(hass)

    def _do_delete() -> int:
        with recorder_instance.get_session() as session:
            meta_rows = session.execute(
                sa.select(StatisticsMeta.id).where(
                    StatisticsMeta.statistic_id == statistic_id,
                ),
            ).fetchall()
            if not meta_rows:
                _LOGGER.debug(
                    "No metadata found for %s; nothing to purge from short-term",
                    statistic_id,
                )
                return 0
            total_deleted = 0
            for (metadata_id,) in meta_rows:
                n = session.execute(
                    sa.delete(StatisticsShortTerm).where(
                        StatisticsShortTerm.metadata_id == metadata_id,
                    ),
                ).rowcount
                _LOGGER.debug(
                    "Deleted %d short-term rows for metadata_id=%d (statistic_id=%s)",
                    n,
                    metadata_id,
                    statistic_id,
                )
                total_deleted += n
            session.commit()
        return total_deleted

    n = await recorder_instance.async_add_executor_job(_do_delete)
    _LOGGER.info(
        "Purged all %d short-term statistics rows for %s",
        n,
        statistic_id,
    )
    return n


async def async_delete_entity_states(
    hass: HomeAssistant,
    entity_id: str,
) -> int:
    """Delete all rows from the states table for entity_id via raw SQL.

    This bypasses HA's entity machinery entirely — no entity restore or
    EnergyCostSensor re-write is triggered.  Used to clean up $0 state
    entries left by HA's auto-generated EnergyCostSensor between imports.

    Args:
        hass: Home Assistant instance.
        entity_id: Entity ID whose state history should be cleared.

    Returns:
        Number of state rows deleted.

    """
    recorder_instance = get_instance(hass)

    def _delete() -> int:
        with recorder_instance.get_session() as session:
            meta_row = session.execute(
                sa.select(StatesMeta.metadata_id).where(
                    StatesMeta.entity_id == entity_id,
                ),
            ).first()
            if meta_row is None:
                _LOGGER.debug(
                    "No states metadata found for %s; nothing to delete",
                    entity_id,
                )
                return 0
            n = session.execute(
                sa.delete(States).where(
                    States.metadata_id == meta_row[0],
                ),
            ).rowcount
            session.commit()
        return n

    n = await recorder_instance.async_add_executor_job(_delete)
    _LOGGER.info(
        "Deleted %d state history entries for %s",
        n,
        entity_id,
    )
    return n


async def async_write_carry_forward_stats(
    hass: HomeAssistant,
    meter: Meter,
    statistic_id: str,
    statistic_name: str | None,
    from_dt: datetime.datetime,
    through_dt: datetime.datetime,
    carry_state: float,
    carry_sum: float,
    *,
    metadata: StatisticMetaData | None = None,
) -> int:
    """Overwrite compiler-contaminated LTS rows with correct carry-forward values.

    Called reactively when HA's hourly statistics compiler writes ``sum=0.0``
    for hours after our last real import — a known failure mode when
    ``statistics_runs`` has no entry for today (e.g. after an HA restart).

    Upserts zero-delta rows (same *state*, same *sum*) for every hourly slot
    in the half-open range ``(from_dt, through_dt]``.  Uses
    ``async_import_statistics`` which is always an upsert, so there is no
    ``UniqueViolation`` risk even though the target rows already exist.

    When *metadata* is supplied (e.g. for a cost companion stat), it is used
    directly instead of building consumption metadata from *meter*.  This
    allows the same helper to repair any LTS series — consumption or cost.

    Returns the number of rows submitted.
    """
    metadata = metadata or get_statistic_metadata(
        meter,
        statistic_id=statistic_id,
        name=statistic_name,
    )
    rows: list[StatisticData] = []
    current = from_dt + datetime.timedelta(hours=1)
    end = through_dt + datetime.timedelta(seconds=1)
    while current <= end:
        rows.append({"start": current, "state": carry_state, "sum": carry_sum})
        current += datetime.timedelta(hours=1)
    if not rows:
        return 0
    async_import_statistics(hass, metadata, rows)
    _LOGGER.info(
        "Wrote %d carry-forward row(s) for %s (%s → %s, "
        "state=%.4f, sum=%.4f) to repair compiler-contaminated LTS rows",
        len(rows),
        statistic_id,
        from_dt,
        through_dt,
        carry_state,
        carry_sum,
    )
    return len(rows)


async def centralized_import_statistics(
    hass: HomeAssistant,
    meter: Meter,
    data_points: Sequence[DataPoint],
    statistic_id: str,
    statistic_name: str,
    wait_for_commit: bool = False,
    price_per_unit: float | None = None,
    currency: str = "USD",
) -> tuple[datetime.datetime, float, float] | None:
    """Import statistics with consistent cumulative sum handling.

    Always queries the recorder for the latest state and sum before conversion.
    When *price_per_unit* is provided, also imports a parallel cost LTS stat
    (statistic_id + "_cost") so the Energy Dashboard can use it as ``stat_cost``
    for per-hour cost attribution on backfilled data.

    Args:
        hass: Home Assistant instance.
        meter: Meter object with meter info.
        data_points: Sequence of DataPoint readings (list, tuple, or other sequence).
        statistic_id: Statistic ID for Home Assistant database.
        statistic_name: Human-readable name for statistic.
        wait_for_commit: If True, wait for database commit before returning.
        price_per_unit: Rate in *currency* per unit-of-volume. When set, cost
            statistics are imported alongside consumption.
        currency: ISO 4217 currency code for cost stat metadata (default "USD").

    Returns:
        ``(last_dt, last_state, last_sum)`` of the last imported row, or ``None``
        if nothing was imported.  The caller is responsible for writing the
        current-hour LTS anchor using these values.

    """
    if not data_points:
        _LOGGER.info("No data points to import for %s", statistic_id)
        return None

    # Query last_db_sum and last_db_state to keep continuity and valid deltas.
    (
        last_db_stat_time,
        fresh_last_db_state,
        fresh_last_db_sum,
    ) = await get_last_imported_stat(
        hass,
        meter,
        statistic_id=statistic_id,
    )

    # Detect backfill / overlap: the import data starts at or before the last
    # existing DB stat.  Using the final DB entry as the delta base would produce
    # a large negative delta (the meter reading at the start of the overlap window
    # is lower than the most-recent reading already stored).  Instead, find the
    # stat immediately preceding the first data point and use that as the base.
    first_point_dt = data_points[0].dt
    if last_db_stat_time is not None and first_point_dt <= last_db_stat_time:
        _LOGGER.info(
            "Backfill overlap detected for %s: first import point %s <= "
            "last DB stat %s — querying base stat just before first import point",
            statistic_id,
            first_point_dt,
            last_db_stat_time,
        )
        prev_state, prev_sum = await async_get_stat_just_before(
            hass,
            statistic_id,
            first_point_dt,
        )
        if prev_state is not None:
            _LOGGER.debug(
                "Backfill base for %s: using state=%.2f, sum=%.2f "
                "(from stat before %s)",
                statistic_id,
                prev_state,
                prev_sum if prev_sum is not None else 0.0,
                first_point_dt,
            )
        else:
            _LOGGER.debug(
                "No stat found before %s for %s — starting sum from 0",
                first_point_dt,
                statistic_id,
            )
        fresh_last_db_state = prev_state
        fresh_last_db_sum = prev_sum

    _LOGGER.debug(
        "Importing statistics for %s: using last_reading=%.2f, last_sum=%.2f",
        statistic_id,
        fresh_last_db_state if fresh_last_db_state is not None else 0.0,
        fresh_last_db_sum if fresh_last_db_sum is not None else 0.0,
    )

    # Convert raw readings to cumulative sum dicts.
    statistics_dicts = convert_statistic_data(
        data_points,
        last_sum=fresh_last_db_sum,
        last_reading=fresh_last_db_state,
    )

    if not statistics_dicts:
        _LOGGER.info("No statistics to import for %s after conversion", statistic_id)
        return None

    # Import statistics into the recorder.
    metadata = get_statistic_metadata(
        meter,
        statistic_id=statistic_id,
        name=statistic_name,
    )

    async_import_statistics(hass, metadata, statistics_dicts)

    # --- Optional cost statistics import ---
    # When a rate is provided, compute and import a parallel cumulative cost LTS
    # so the Energy Dashboard can attribute per-hour cost to backfilled data via
    # the ``stat_cost`` config field.
    if price_per_unit is not None:
        cost_stat_id = f"{statistic_id}{COST_STAT_SUFFIX}"
        cost_stat_name = get_cost_statistic_name(meter.meter_id)

        # Determine cost-sum base for this import window (same overlap detection as
        # consumption).
        prev_cost_state, prev_cost_sum = await async_get_stat_just_before(
            hass,
            cost_stat_id,
            first_point_dt,
        )
        if prev_cost_state is not None:
            _LOGGER.debug(
                "Cost backfill base for %s: prev_cost_sum=%.4f (before %s)",
                cost_stat_id,
                prev_cost_sum if prev_cost_sum is not None else 0.0,
                first_point_dt,
            )
        else:
            _LOGGER.debug(
                "No prior cost stat found before %s for %s — starting from 0",
                first_point_dt,
                cost_stat_id,
            )

        cost_dicts = convert_cost_statistic_data(
            data_points,
            price_per_unit,
            last_cost_sum=prev_cost_sum,
            last_reading=fresh_last_db_state,
        )
        if cost_dicts:
            cost_metadata = get_cost_statistic_metadata(
                meter,
                statistic_id=cost_stat_id,
                name=cost_stat_name,
                currency=currency,
            )
            async_import_statistics(hass, cost_metadata, cost_dicts)
            _LOGGER.info(
                "Imported %d cost statistics for %s "
                "(rate=%.6f %s/unit, range: %s to %s)",
                len(cost_dicts),
                cost_stat_id,
                price_per_unit,
                currency,
                cost_dicts[0]["start"],
                cost_dicts[-1]["start"],
            )

    # Optionally wait for database commit to avoid reading stale rows.
    if wait_for_commit:
        await asyncio.sleep(2.0)

    _LOGGER.info(
        "Imported %d statistics for %s (range: %s to %s)",
        len(statistics_dicts),
        statistic_id,
        statistics_dicts[0]["start"] if statistics_dicts else None,
        statistics_dicts[-1]["start"] if statistics_dicts else None,
    )

    last_imported = statistics_dicts[-1]
    return (
        last_imported["start"],
        float(last_imported.get("state") or 0.0),
        float(last_imported.get("sum") or 0.0),
    )
