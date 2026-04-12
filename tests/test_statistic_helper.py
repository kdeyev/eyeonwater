"""Tests for statistic_helper utilities."""

import datetime

import pyonwater
import pytest
from homeassistant.const import UnitOfVolume

from custom_components.eyeonwater.statistic_helper import (
    _STATISTIC_MEAN_TYPE_NONE,
    UnrecognizedUnitError,
    convert_cost_statistic_data,
    convert_statistic_data,
    filter_newer_data,
    get_cost_statistic_metadata,
    get_cost_statistics_id,
    get_ha_native_unit_of_measurement,
    get_statistic_metadata,
    get_statistic_name,
    get_statistics_id,
    normalize_id,
    volume_conversion_factor,
)

from .conftest import FakeDataPoint, _make_meter

# ---------- normalize_id ----------


def test_normalize_id_basic() -> None:
    """Uppercase and hyphens are lowercased and replaced with underscores."""
    assert normalize_id("ABC-123") == "abc_123"


def test_normalize_id_already_clean() -> None:
    """Already-normalized IDs pass through unchanged."""
    assert normalize_id("hello_world") == "hello_world"


def test_normalize_id_special_chars() -> None:
    """Special characters are replaced with underscores."""
    assert normalize_id("a.b/c@d") == "a_b_c_d"


# ---------- unit mapping ----------


def test_unit_mapping_gallons() -> None:
    """GAL maps to GALLONS."""
    assert (
        get_ha_native_unit_of_measurement(pyonwater.NativeUnits.GAL)
        == UnitOfVolume.GALLONS
    )


def test_unit_mapping_cubic_feet() -> None:
    """CF maps to CUBIC_FEET."""
    assert (
        get_ha_native_unit_of_measurement(pyonwater.NativeUnits.CF)
        == UnitOfVolume.CUBIC_FEET
    )


def test_unit_mapping_cubic_meters() -> None:
    """CM maps to CUBIC_METERS."""
    assert (
        get_ha_native_unit_of_measurement(pyonwater.NativeUnits.CM)
        == UnitOfVolume.CUBIC_METERS
    )


def test_unit_mapping_unknown_raises() -> None:
    """Unrecognized unit raises UnrecognizedUnitError."""
    with pytest.raises(UnrecognizedUnitError):
        get_ha_native_unit_of_measurement("UNKNOWN_UNIT")


# ---------- naming helpers ----------


def test_get_statistic_name() -> None:
    """Statistic name includes normalized meter ID."""
    name = get_statistic_name("meter-001")
    assert name == "Water Meter meter_001"


def test_get_statistics_id() -> None:
    """Statistics ID follows eyeonwater:<normalised> format."""
    sid = get_statistics_id("meter-001")
    assert sid == "eyeonwater:water_meter_meter_001"


# ---------- statistic metadata ----------


def test_get_statistic_metadata() -> None:
    """StatisticMetaData is built with correct source, sum flag, and optional mean_type."""
    meter = _make_meter(meter_id="meter-001")
    meta = get_statistic_metadata(meter)

    assert meta.get("has_mean") is False
    assert meta.get("has_sum") is True
    assert meta.get("source") == "eyeonwater"
    assert "meter_001" in (meta.get("statistic_id") or "")
    if _STATISTIC_MEAN_TYPE_NONE is not None:
        assert meta.get("mean_type") == _STATISTIC_MEAN_TYPE_NONE


# ---------- convert_statistic_data ----------


def test_convert_statistic_data_empty() -> None:
    """Empty input returns empty list."""
    assert convert_statistic_data([]) == []


def test_convert_statistic_data_single() -> None:
    """Single data point is converted to StatisticData with correct sum and state."""
    dp = FakeDataPoint(
        dt=datetime.datetime(2025, 6, 1, tzinfo=datetime.UTC),
        reading=100.0,
    )
    result = convert_statistic_data([dp])
    assert len(result) == 1
    assert result[0].get("sum") == 100.0
    assert result[0].get("state") == 100.0


def test_convert_statistic_data_multiple() -> None:
    """Multiple data points are all converted in order."""
    points = [
        FakeDataPoint(
            dt=datetime.datetime(2025, 6, i, tzinfo=datetime.UTC),
            reading=float(i * 10),
        )
        for i in range(1, 4)
    ]
    result = convert_statistic_data(points)
    assert len(result) == 3
    assert [r.get("sum") for r in result] == [10.0, 20.0, 30.0]


# ---------- filter_newer_data ----------


def test_filter_newer_data_no_cutoff() -> None:
    """Without a cutoff all data points are returned."""
    points = [FakeDataPoint(), FakeDataPoint()]
    assert filter_newer_data(points, None) == points


def test_filter_newer_data_filters_old() -> None:
    """Data points older than the cutoff are excluded."""
    old = FakeDataPoint(
        dt=datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC),
        reading=10.0,
    )
    new = FakeDataPoint(
        dt=datetime.datetime(2025, 6, 1, tzinfo=datetime.UTC),
        reading=20.0,
    )
    cutoff = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC)
    result = filter_newer_data([old, new], cutoff)
    assert len(result) == 1
    assert result[0].reading == 20.0


def test_filter_newer_data_excludes_equal() -> None:
    """A point exactly at the cutoff timestamp is excluded (strictly newer required)."""
    exact = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC)
    dp = FakeDataPoint(dt=exact, reading=10.0)
    result = filter_newer_data([dp], exact)
    assert not result


def test_filter_newer_data_empty_input() -> None:
    """Empty input with no cutoff returns empty list."""
    result = filter_newer_data([], None)
    assert not result


def test_filter_newer_data_empty_input_with_cutoff() -> None:
    """Empty input with a cutoff returns empty list."""
    cutoff = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC)
    result = filter_newer_data([], cutoff)
    assert not result


# ---------- cost statistics helpers ----------


def test_get_cost_statistics_id() -> None:
    """Cost statistics ID follows eyeonwater:water_cost_<normalised> format."""
    sid = get_cost_statistics_id("meter-001")
    assert sid == "eyeonwater:water_cost_meter_001"


def test_get_cost_statistic_metadata() -> None:
    """Cost StatisticMetaData has unit_class=monetary and optional mean_type."""
    meter = _make_meter(meter_id="meter-001")
    meta = get_cost_statistic_metadata(meter, "USD")

    assert meta.get("has_mean") is False
    assert meta.get("has_sum") is True
    assert meta.get("source") == "eyeonwater"
    assert meta.get("statistic_id") == "eyeonwater:water_cost_meter_001"
    assert meta.get("unit_of_measurement") == "USD"
    assert meta.get("name") == "Water Meter meter_001 Cost"
    assert meta.get("unit_class") == "monetary"
    if _STATISTIC_MEAN_TYPE_NONE is not None:
        assert meta.get("mean_type") == _STATISTIC_MEAN_TYPE_NONE


def test_get_cost_statistic_metadata_different_currency() -> None:
    """Cost metadata uses the provided currency as unit_of_measurement."""
    meter = _make_meter(meter_id="meter-001")
    meta = get_cost_statistic_metadata(meter, "EUR")
    assert meta["unit_of_measurement"] == "EUR"


def test_convert_cost_statistic_data_empty() -> None:
    """Empty input returns empty list."""
    assert convert_cost_statistic_data([], 1.5) == []


def test_convert_cost_statistic_data_single() -> None:
    """Single data point is converted with correct cost."""
    dp = FakeDataPoint(
        dt=datetime.datetime(2025, 6, 1, tzinfo=datetime.UTC),
        reading=100.0,
    )
    result = convert_cost_statistic_data([dp], 0.005)
    assert len(result) == 1
    assert result[0].get("sum") == pytest.approx(0.5)
    assert result[0].get("state") == pytest.approx(0.5)


def test_convert_cost_statistic_data_multiple() -> None:
    """Multiple data points all converted in order."""
    points = [
        FakeDataPoint(
            dt=datetime.datetime(2025, 6, i, tzinfo=datetime.UTC),
            reading=float(i * 1000),
        )
        for i in range(1, 4)
    ]
    result = convert_cost_statistic_data(points, 0.01)
    assert len(result) == 3
    assert [r.get("sum") for r in result] == [
        pytest.approx(10.0),
        pytest.approx(20.0),
        pytest.approx(30.0),
    ]


def test_convert_cost_statistic_data_zero_price() -> None:
    """Zero unit price produces zero cost."""
    dp = FakeDataPoint(reading=500.0)
    result = convert_cost_statistic_data([dp], 0.0)
    assert result[0].get("sum") == pytest.approx(0.0)


# ---------- volume conversion ----------


def test_volume_conversion_same_unit() -> None:
    assert volume_conversion_factor(UnitOfVolume.GALLONS, UnitOfVolume.GALLONS) == 1.0


def test_volume_conversion_gallons_to_liters() -> None:
    factor = volume_conversion_factor(UnitOfVolume.GALLONS, UnitOfVolume.LITERS)
    assert factor == pytest.approx(3.78541, rel=1e-4)


def test_volume_conversion_cubic_feet_to_gallons() -> None:
    factor = volume_conversion_factor(UnitOfVolume.CUBIC_FEET, UnitOfVolume.GALLONS)
    assert factor == pytest.approx(7.48052, rel=1e-3)


def test_volume_conversion_cubic_meters_to_liters() -> None:
    factor = volume_conversion_factor(UnitOfVolume.CUBIC_METERS, UnitOfVolume.LITERS)
    assert factor == pytest.approx(1000.0, rel=1e-4)


# ---------- display unit in metadata ----------


def test_get_statistic_metadata_with_display_unit() -> None:
    meter = _make_meter(meter_id="meter-001")
    meta = get_statistic_metadata(meter, display_unit=UnitOfVolume.LITERS)
    assert meta["unit_of_measurement"] == UnitOfVolume.LITERS
    assert meta["unit_class"] == "volume"


def test_get_statistic_metadata_no_display_unit_uses_native() -> None:
    meter = _make_meter(meter_id="meter-001", native_unit=pyonwater.NativeUnits.GAL)
    meta = get_statistic_metadata(meter)
    assert meta["unit_of_measurement"] == UnitOfVolume.GALLONS


# ---------- convert_statistic_data with factor ----------


def test_convert_statistic_data_with_factor() -> None:
    dp = FakeDataPoint(
        dt=datetime.datetime(2025, 6, 1, tzinfo=datetime.UTC),
        reading=100.0,
    )
    factor = volume_conversion_factor(UnitOfVolume.GALLONS, UnitOfVolume.LITERS)
    result = convert_statistic_data([dp], factor)
    assert result[0]["sum"] == pytest.approx(378.541, rel=1e-3)
    assert result[0]["state"] == pytest.approx(378.541, rel=1e-3)
