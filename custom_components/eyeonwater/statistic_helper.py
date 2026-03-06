"""Helper functions used for import statistics."""

import datetime
import logging
from collections.abc import Sequence
from typing import Any

import pyonwater
from homeassistant import exceptions
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
)
from homeassistant.helpers.recorder import get_instance

try:
    from homeassistant.components.recorder.models import (
        StatisticMeanType as _StatisticMeanType,
    )

    _STATISTIC_MEAN_TYPE_NONE: int | None = _StatisticMeanType.NONE
except ImportError:
    _STATISTIC_MEAN_TYPE_NONE = None
from homeassistant.components.recorder.statistics import get_last_statistics
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dtutil
from pyonwater import DataPoint, Meter

from .const import WATER_METER_NAME

_LOGGER = logging.getLogger(__name__)


PYONWATER_UNIT_MAP: dict[str, UnitOfVolume] = {
    pyonwater.NativeUnits.GAL: UnitOfVolume.GALLONS,
    pyonwater.NativeUnits.CF: UnitOfVolume.CUBIC_FEET,
    pyonwater.NativeUnits.CM: UnitOfVolume.CUBIC_METERS,
}


class UnrecognizedUnitError(exceptions.HomeAssistantError):
    """Error to indicate unrecognized pyonwater native unit."""


def get_ha_native_unit_of_measurement(
    unit: pyonwater.NativeUnits | str,
) -> UnitOfVolume:
    """Convert pyonwater native units to HA native units."""
    ha_unit = PYONWATER_UNIT_MAP.get(unit)
    if ha_unit is None:
        msg = "Unrecognized pyonwater unit {unit}"
        raise UnrecognizedUnitError(msg)
    return ha_unit


def get_statistic_name(meter_id: str) -> str:
    """Generate statistic name for a meter."""
    meter_id = normalize_id(meter_id)
    return f"{WATER_METER_NAME} {meter_id}"


def normalize_id(uuid: str) -> str:
    """Normalize ID."""
    chars = [c if c.isalnum() or c == "_" else "_" for c in uuid]
    uuid = "".join(chars)
    return uuid.lower()


def get_statistics_id(meter_id: str) -> str:
    """Generate statistic ID for a meter."""
    meter_id = normalize_id(meter_id)
    return f"eyeonwater:water_meter_{meter_id}"


def get_cost_statistics_id(meter_id: str) -> str:
    """Generate cost statistic ID for a meter."""
    meter_id = normalize_id(meter_id)
    return f"eyeonwater:water_cost_{meter_id}"


def get_statistic_metadata(meter: Meter) -> StatisticMetaData:
    """Build statistic metadata for a given meter."""
    name = get_statistic_name(meter_id=meter.meter_id)
    statistic_id = get_statistics_id(meter.meter_id)

    unit = get_ha_native_unit_of_measurement(meter.native_unit_of_measurement)

    kwargs: dict[str, Any] = {
        "has_mean": False,
        "has_sum": True,
        "name": name,
        "source": "eyeonwater",
        "statistic_id": statistic_id,
        "unit_of_measurement": unit,
        "unit_class": "volume",
    }
    if _STATISTIC_MEAN_TYPE_NONE is not None:
        kwargs["mean_type"] = _STATISTIC_MEAN_TYPE_NONE
        kwargs["unit_class"] = "volume"

    return StatisticMetaData(**kwargs)  # type: ignore[typeddict-item, no-any-return]


def get_cost_statistic_metadata(
    meter: Meter,
    currency: str,
) -> StatisticMetaData:
    """Build cost statistic metadata for a given meter."""
    name = f"{get_statistic_name(meter_id=meter.meter_id)} Cost"
    statistic_id = get_cost_statistics_id(meter.meter_id)

    kwargs: dict = {
        "has_mean": False,
        "has_sum": True,
        "name": name,
        "source": "eyeonwater",
        "statistic_id": statistic_id,
        "unit_of_measurement": currency,
        "unit_class": "monetary",
    }
    if _STATISTIC_MEAN_TYPE_NONE is not None:
        kwargs["mean_type"] = _STATISTIC_MEAN_TYPE_NONE

    return StatisticMetaData(**kwargs)  # type: ignore[typeddict-item, no-any-return]


def convert_cost_statistic_data(
    data: Sequence[DataPoint],
    unit_price: float,
) -> list[StatisticData]:
    """Convert water usage data to cost statistics.

    Each DataPoint has a cumulative meter reading as `reading`.
    Cost = reading * unit_price (same cumulative approach).
    """
    return [
        StatisticData(
            start=row.dt,
            sum=row.reading * unit_price,
            state=row.reading * unit_price,
        )
        for row in data
    ]


def convert_statistic_data(data: Sequence[DataPoint]) -> list[StatisticData]:
    """Convert statistics data to HA StatisticData format."""
    return [
        StatisticData(
            start=row.dt,
            sum=row.reading,
            state=row.reading,
        )
        for row in data
    ]


async def get_last_imported_time(
    hass: HomeAssistant,
    meter: Meter,
) -> datetime.datetime | None:
    """Return last imported data datetime."""
    # https://github.com/home-assistant/core/blob/74e2d5c5c312cf3ba154b5206ceb19ba884c6fb4/homeassistant/components/tibber/sensor.py#L11

    statistic_id = get_statistics_id(meter.meter_id)
    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics,
        hass,
        1,
        statistic_id,
        True,  # noqa: FBT003
        # HA get_last_statistics requires a boolean positional arg;
        # no keyword alternative exists in the public API
        {"start", "sum"},
    )
    _LOGGER.debug("last_stats %s", last_stats)

    if last_stats:
        timestamp = last_stats[statistic_id][0].get("start")
        if timestamp is None:
            return None
        date = datetime.datetime.fromtimestamp(timestamp, tz=dtutil.DEFAULT_TIME_ZONE)
        date = dtutil.as_local(date)
        _LOGGER.debug("date %s", date)

        return date
    return None


def filter_newer_data(
    data: Sequence[DataPoint],
    last_imported_time: datetime.datetime | None,
) -> list[DataPoint]:
    """Filter data points that are newer than given datetime."""
    if not data:
        _LOGGER.info("0 data points found (empty input)")
        return []

    _LOGGER.debug(
        "last_imported_time %s - data %s",
        last_imported_time,
        data[-1].dt,
    )
    result: list[DataPoint] = list(data)
    if last_imported_time is not None:
        result = [r for r in data if r.dt > last_imported_time]
    _LOGGER.info("%i data points found", len(result))

    return result
