"""Helper functions used for import statistics."""

import datetime
import logging

import pyonwater
from homeassistant import exceptions
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import get_last_statistics
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dtutil
from pyonwater import DataPoint, Meter, enforce_monotonic_total, filter_points_after

from .const import WATER_METER_NAME

_LOGGER = logging.getLogger(__name__)
_LOGGER.addHandler(logging.StreamHandler())


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
    return f"{WATER_METER_NAME} {meter_id} Statistic"


def normalize_id(uuid: str) -> str:
    """Normalize ID."""
    chars = [c if c.isalnum() or c == "_" else "_" for c in uuid]
    uuid = "".join(chars)
    return uuid.lower()


def get_statistics_id(meter_id: str) -> str:
    """Generate statistic ID for a meter."""
    meter_id = normalize_id(meter_id)
    return f"sensor.water_meter_{meter_id}_statistic"


def get_statistic_metadata(meter: Meter) -> StatisticMetaData:
    """Build statistic metadata for a given meter."""
    name = get_statistic_name(meter_id=meter.meter_id)
    statistic_id = get_statistics_id(meter.meter_id)
    unit_str = meter.native_unit_of_measurement
    unit_enum = pyonwater.NativeUnits(unit_str)

    return StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=name,
        source="recorder",
        statistic_id=statistic_id,
        unit_of_measurement=get_ha_native_unit_of_measurement(unit_enum),
    )  # type: ignore[call-arg]


def convert_statistic_data(data: list[DataPoint]) -> list[StatisticData]:
    """Convert statistics data to HA StatisticData format.

    Applies monotonic enforcement to ensure readings only increase,
    preventing negative deltas in the recorder statistics.
    """
    # Enforce monotonic increasing readings to handle data anomalies
    normalized_data = enforce_monotonic_total(data)

    return [
        StatisticData(
            start=row.dt,
            sum=row.reading,
            state=row.reading,
        )
        for row in normalized_data
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
        {"start", "sum"},
    )
    _LOGGER.debug("last_stats %s", last_stats)

    if last_stats and statistic_id in last_stats:
        first_stat = last_stats[statistic_id][0]
        start_time = first_stat.get("start")
        if start_time is not None:
            date = datetime.datetime.fromtimestamp(
                start_time,
                tz=dtutil.DEFAULT_TIME_ZONE,
            )
            date = dtutil.as_local(date)
            _LOGGER.debug("date %s", date)
            return date
    return None


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

    _LOGGER.info("%i data points found", len(data))
    return data
