"""Tests for statistic_helper utilities."""
import datetime

import pyonwater
import pytest
from homeassistant.const import UnitOfVolume

from custom_components.eyeonwater.statistic_helper import (
    UnrecognizedUnitError,
    _HAS_MEAN_TYPE,
    convert_statistic_data,
    filter_newer_data,
    get_ha_native_unit_of_measurement,
    get_statistic_metadata,
    get_statistic_name,
    get_statistics_id,
    normalize_id,
)

from .conftest import FakeDataPoint, _make_meter


# ---------- normalize_id ----------


def test_normalize_id_basic() -> None:
    assert normalize_id("ABC-123") == "abc_123"


def test_normalize_id_already_clean() -> None:
    assert normalize_id("hello_world") == "hello_world"


def test_normalize_id_special_chars() -> None:
    assert normalize_id("a.b/c@d") == "a_b_c_d"


# ---------- unit mapping ----------


def test_unit_mapping_gallons() -> None:
    from homeassistant.const import UnitOfVolume

    assert (
        get_ha_native_unit_of_measurement(pyonwater.NativeUnits.GAL)
        == UnitOfVolume.GALLONS
    )


def test_unit_mapping_cubic_feet() -> None:
    from homeassistant.const import UnitOfVolume

    assert (
        get_ha_native_unit_of_measurement(pyonwater.NativeUnits.CF)
        == UnitOfVolume.CUBIC_FEET
    )


def test_unit_mapping_cubic_meters() -> None:
    from homeassistant.const import UnitOfVolume

    assert (
        get_ha_native_unit_of_measurement(pyonwater.NativeUnits.CM)
        == UnitOfVolume.CUBIC_METERS
    )


def test_unit_mapping_unknown_raises() -> None:
    with pytest.raises(UnrecognizedUnitError):
        get_ha_native_unit_of_measurement("UNKNOWN_UNIT")


# ---------- naming helpers ----------


def test_get_statistic_name() -> None:
    name = get_statistic_name("meter-001")
    assert name == "Water Meter meter_001 Statistic"


def test_get_statistics_id() -> None:
    sid = get_statistics_id("meter-001")
    assert sid == "eyeonwater:water_meter_meter_001"


# ---------- statistic metadata ----------


def test_get_statistic_metadata() -> None:
    meter = _make_meter(meter_id="meter-001")
    meta = get_statistic_metadata(meter)

    assert meta["has_mean"] is False
    assert meta["has_sum"] is True
    assert meta["source"] == "eyeonwater"
    assert "meter_001" in meta["statistic_id"]
    if _HAS_MEAN_TYPE:
        assert meta["mean_type"] == 0  # StatisticMeanType.NONE
        assert meta["unit_class"] == "volume"


# ---------- convert_statistic_data ----------


def test_convert_statistic_data_empty() -> None:
    assert convert_statistic_data([]) == []


def test_convert_statistic_data_single() -> None:
    dp = FakeDataPoint(
        dt=datetime.datetime(2025, 6, 1, tzinfo=datetime.timezone.utc),
        reading=100.0,
    )
    result = convert_statistic_data([dp])
    assert len(result) == 1
    assert result[0]["sum"] == 100.0
    assert result[0]["state"] == 100.0


def test_convert_statistic_data_multiple() -> None:
    points = [
        FakeDataPoint(
            dt=datetime.datetime(2025, 6, i, tzinfo=datetime.timezone.utc),
            reading=float(i * 10),
        )
        for i in range(1, 4)
    ]
    result = convert_statistic_data(points)
    assert len(result) == 3
    assert [r["sum"] for r in result] == [10.0, 20.0, 30.0]


# ---------- filter_newer_data ----------


def test_filter_newer_data_no_cutoff() -> None:
    points = [FakeDataPoint(), FakeDataPoint()]
    assert filter_newer_data(points, None) == points


def test_filter_newer_data_filters_old() -> None:
    old = FakeDataPoint(
        dt=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
        reading=10.0,
    )
    new = FakeDataPoint(
        dt=datetime.datetime(2025, 6, 1, tzinfo=datetime.timezone.utc),
        reading=20.0,
    )
    cutoff = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    result = filter_newer_data([old, new], cutoff)
    assert len(result) == 1
    assert result[0].reading == 20.0


def test_filter_newer_data_excludes_equal() -> None:
    exact = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    dp = FakeDataPoint(dt=exact, reading=10.0)
    result = filter_newer_data([dp], exact)
    assert result == []


def test_filter_newer_data_empty_input() -> None:
    result = filter_newer_data([], None)
    assert result == []


def test_filter_newer_data_empty_input_with_cutoff() -> None:
    cutoff = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    result = filter_newer_data([], cutoff)
    assert result == []
