"""Helper functions used for import statistics."""

import datetime
import logging

import pyonwater
from homeassistant import exceptions
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import get_last_statistics
from homeassistant.const import UnitOfVolume
from homeassistant.util import dt as dtutil
from pyonwater import DataPoint, Meter

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


def get_ha_native_unit_of_measurement(unit: pyonwater.NativeUnits):
    """Convert pyonwater native units to HA native units."""
    ha_unit = PYONWATER_UNIT_MAP.get(unit, None)
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
    return f"sensor.water_meter_{meter_id}"


def get_statistic_metadata(meter: Meter) -> StatisticMetaData:
    """Build statistic metadata for a given meter."""
    name = get_statistic_name(meter_id=meter.meter_id)
    statistic_id = get_statistics_id(meter.meter_id)

    return StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=name,
        source="recorder",
        statistic_id=statistic_id,
        unit_of_measurement=get_ha_native_unit_of_measurement(
            meter.native_unit_of_measurement,
        ),
    )


def convert_statistic_data(data: list[DataPoint]) -> list[StatisticData]:
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
    hass,
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

    if last_stats:
        date = last_stats[statistic_id][0]["start"]
        date = datetime.datetime.fromtimestamp(date, tz=dtutil.DEFAULT_TIME_ZONE)
        date = dtutil.as_local(date)
        _LOGGER.debug("date %s", date)

        return date
    return None


def filter_newer_data(
    data: list[DataPoint],
    last_imported_time: datetime.datetime | None,
) -> list[DataPoint]:
    """Filter data points that newer than given datetime."""
    _LOGGER.debug(
        "last_imported_time %s - data %s",
        last_imported_time,
        data[-1].dt,
    )
    if last_imported_time is not None:
        data = list(
            filter(
                lambda r: r.dt > last_imported_time,
                data,
            ),
        )
    _LOGGER.info("%i data points found", len(data))

    return data
