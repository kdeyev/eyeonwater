"""Statistics maintenance utilities for EyeOnWater."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.components.recorder.db_schema import (
    Statistics,
    StatisticsMeta,
    StatisticsShortTerm,
)
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dtutil

from .const import STATISTICS_VALIDATION_BATCH_SIZE
from .statistic_helper import get_entity_statistic_id

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MonotonicViolation:
    """Represents a monotonic sum violation."""

    index: int
    start: datetime
    previous_sum: float
    current_sum: float

    @property
    def delta(self) -> float:
        """Return current minus previous sum."""
        return self.current_sum - self.previous_sum


@dataclass(frozen=True)
class MonotonicValidationResult:
    """Typed result from monotonic validation."""

    statistic_id: str
    checked: int
    violations: list[MonotonicViolation]
    start_time: datetime | None


def resolve_statistic_id(
    *,
    statistic_id: str | None,
    entity_id: str | None,
    meter_id: str | None,
) -> str | None:
    """Resolve statistic_id from provided identifiers."""
    if statistic_id:
        return statistic_id

    if entity_id:
        if entity_id.startswith("sensor.water_meter_"):
            return entity_id
        return None

    if meter_id:
        return get_entity_statistic_id(meter_id)

    return None


def _get_statistics_rows(
    hass: HomeAssistant,
    statistic_id: str,
    *,
    start_time: datetime | None,
    offset: int = 0,
    limit: int = 1000,
) -> list[Statistics]:
    """Fetch statistics rows for a statistic_id (paginated).

    Args:
        hass: Home Assistant instance.
        statistic_id: Statistic ID to query.
        start_time: Optional start time filter.
        offset: Pagination offset.
        limit: Maximum rows to return (default 1000).

    """
    recorder = get_instance(hass)
    with recorder.get_session() as session:
        meta_id = (
            session.query(StatisticsMeta.id)
            .filter(StatisticsMeta.statistic_id == statistic_id)
            .scalar()
        )
        if not meta_id:
            return []

        query = session.query(Statistics).filter(Statistics.metadata_id == meta_id)
        if start_time is not None:
            query = query.filter(Statistics.start >= start_time)

        return list(
            query.order_by(Statistics.start).offset(offset).limit(limit).all(),
        )


async def validate_monotonic_sums(
    hass: HomeAssistant,
    statistic_id: str,
    *,
    hours: int | None = None,
    full_scan: bool = False,
) -> MonotonicValidationResult:
    """Validate that cumulative sums are monotonic for a statistic.

    Fetches rows in batches to avoid blocking executor on large histories.

    Args:
        hass: Home Assistant instance.
        statistic_id: Statistic ID to validate.
        hours: Check only last N hours (default: all if full_scan=False).
        full_scan: If True, scan all history regardless of hours.

    Returns:
        MonotonicValidationResult with checked count, violations, and metadata.

    """
    start_time: datetime | None = None
    if hours is not None and not full_scan:
        start_time = dtutil.utcnow() - timedelta(hours=hours)

    recorder = get_instance(hass)
    violations: list[MonotonicViolation] = []
    previous_sum: float | None = None
    total_checked = 0
    offset = 0

    # Fetch and validate in batches
    while True:
        rows = await recorder.async_add_executor_job(
            _get_statistics_rows,
            hass,
            statistic_id,
            start_time,
            offset,
            STATISTICS_VALIDATION_BATCH_SIZE,
        )

        if not rows:
            break

        for index, row in enumerate(rows, start=total_checked):
            current_sum = row.sum
            if current_sum is None:
                continue
            current_sum = float(current_sum)
            if (
                previous_sum is not None
                and current_sum < previous_sum
                and row.start is not None
            ):
                violations.append(
                    MonotonicViolation(
                        index=index,
                        start=row.start,
                        previous_sum=previous_sum,
                        current_sum=current_sum,
                    ),
                )
            previous_sum = current_sum

        total_checked += len(rows)
        offset += STATISTICS_VALIDATION_BATCH_SIZE

    return MonotonicValidationResult(
        statistic_id=statistic_id,
        checked=total_checked,
        violations=violations,
        start_time=start_time,
    )


def _delete_statistics_rows(hass: HomeAssistant, statistic_id: str) -> int:
    """Delete all statistics rows for a statistic_id."""
    recorder = get_instance(hass)
    with recorder.get_session() as session:
        try:
            meta_id = (
                session.query(StatisticsMeta.id)
                .filter(StatisticsMeta.statistic_id == statistic_id)
                .scalar()
            )
            if not meta_id:
                return 0

            deleted_long = (
                session.query(Statistics)
                .filter(Statistics.metadata_id == meta_id)
                .delete(synchronize_session=False)
            )
            deleted_short = (
                session.query(StatisticsShortTerm)
                .filter(StatisticsShortTerm.metadata_id == meta_id)
                .delete(synchronize_session=False)
            )
            session.commit()
            return int((deleted_long or 0) + (deleted_short or 0))
        except Exception:
            session.rollback()
            raise


async def delete_statistics(
    hass: HomeAssistant,
    statistic_id: str,
) -> int:
    """Delete all statistics rows for a statistic_id."""
    recorder = get_instance(hass)
    return await recorder.async_add_executor_job(
        _delete_statistics_rows,
        hass,
        statistic_id,
    )
