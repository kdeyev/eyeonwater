"""Tests for eyeonwater statistic_helper module."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from homeassistant.const import UnitOfVolume
from pyonwater import DataPoint, NativeUnits

from custom_components.eyeonwater.statistic_helper import (
    UnrecognizedUnitError,
    convert_cost_statistic_data,
    convert_statistic_data,
    filter_newer_data,
    get_cost_statistic_id,
    get_cost_statistic_name,
    get_cost_statistic_metadata,
    get_entity_statistic_id,
    get_ha_native_unit_of_measurement,
    get_statistic_metadata,
    get_statistic_name,
    normalize_id,
)


class TestUnitConversion:
    """Test unit conversion functions."""

    def test_convert_gallons(self):
        """Test converting GAL to Home Assistant units."""
        result = get_ha_native_unit_of_measurement(NativeUnits.GAL)
        assert result == UnitOfVolume.GALLONS

    def test_convert_cubic_feet(self):
        """Test converting CF to Home Assistant units."""
        result = get_ha_native_unit_of_measurement(NativeUnits.CF)
        assert result == UnitOfVolume.CUBIC_FEET

    def test_convert_cubic_meters(self):
        """Test converting CM to Home Assistant units."""
        result = get_ha_native_unit_of_measurement(NativeUnits.CM)
        assert result == UnitOfVolume.CUBIC_METERS

    def test_unrecognized_unit_raises_error(self):
        """Test that unrecognized units raise an error."""
        with pytest.raises(UnrecognizedUnitError):
            # Create a mock unit that's not in the map
            get_ha_native_unit_of_measurement("INVALID_UNIT")  # type: ignore[arg-type]


class TestIdNormalization:
    """Test ID normalization functions."""

    def test_normalize_simple_id(self):
        """Test normalizing a simple alphanumeric ID."""
        result = normalize_id("12345678")
        assert result == "12345678"

    def test_normalize_id_with_special_chars(self):
        """Test normalizing ID with special characters."""
        result = normalize_id("12-34-56@78")
        assert result == "12_34_56_78"

    def test_normalize_id_with_uppercase(self):
        """Test normalizing ID converts to lowercase."""
        result = normalize_id("ABC123")
        assert result == "abc123"

    def test_normalize_id_with_spaces(self):
        """Test normalizing ID replaces spaces with underscores."""
        result = normalize_id("ABC 123 XYZ")
        assert result == "abc_123_xyz"

    def test_get_statistic_name(self):
        """Test generating statistic name."""
        result = get_statistic_name("12345678")
        assert result == "Water Meter 12345678"

    def test_get_statistic_name_normalizes(self):
        """Test statistic name normalizes ID."""
        result = get_statistic_name("ABC-123")
        assert result == "Water Meter abc_123"

    def test_get_entity_statistic_id(self):
        """Test generating entity statistic ID."""
        result = get_entity_statistic_id("12345678")
        assert result == "sensor.water_meter_12345678"

    def test_get_entity_statistic_id_normalizes(self):
        """Test entity statistic ID normalizes meter ID."""
        result = get_entity_statistic_id("ABC-123@Test")
        assert result == "sensor.water_meter_abc_123_test"


class TestStatisticMetadata:
    """Test statistic metadata generation."""

    def test_get_statistic_metadata_default(self, mock_meter: MagicMock):
        """Test generating metadata with defaults."""
        result = get_statistic_metadata(mock_meter)

        assert result["name"] == "Water Meter 12345678"
        assert result["statistic_id"] == "sensor.water_meter_12345678"
        assert result["unit_of_measurement"] == "gal"
        assert result["has_sum"] is True
        assert result.get("has_mean") is False
        assert result["source"] == "recorder"

    def test_get_statistic_metadata_custom_name(self, mock_meter: MagicMock):
        """Test generating metadata with custom name."""
        result = get_statistic_metadata(mock_meter, name="Custom Water Meter")

        assert result["name"] == "Custom Water Meter"
        assert result["statistic_id"] == "sensor.water_meter_12345678"

    def test_get_statistic_metadata_custom_id(self, mock_meter: MagicMock):
        """Test generating metadata with custom statistic_id."""
        result = get_statistic_metadata(
            mock_meter,
            statistic_id="sensor.custom_meter_id",
        )

        assert result["statistic_id"] == "sensor.custom_meter_id"
        assert result["name"] == "Water Meter 12345678"


class TestConvertStatisticData:
    """Test statistic data conversion."""

    def test_convert_empty_data(self):
        """Test converting empty data returns empty list."""
        result = convert_statistic_data([])
        assert not result

    def test_convert_single_point_from_zero(self, sample_datapoints: list[DataPoint]):
        """Test converting single point starting from zero."""
        data = [sample_datapoints[0]]
        result = convert_statistic_data(data)

        assert len(result) == 1
        assert result[0]["start"] == sample_datapoints[0].dt
        assert result[0].get("state") == 1000.0
        # First point: consumption = 1000 - 1000 = 0, cumsum = 0 + 0 = 0
        assert result[0].get("sum") == 0.0

    def test_convert_multiple_points(self, sample_datapoints: list[DataPoint]):
        """Test converting multiple points."""
        result = convert_statistic_data(sample_datapoints)

        assert len(result) == 4

        # First point: delta = 0 (same as initial), cumsum = 0
        assert result[0].get("state") == 1000.0
        assert result[0].get("sum") == 0.0

        # Second point: delta = 5, cumsum = 5
        assert result[1].get("state") == 1005.0
        assert result[1].get("sum") == 5.0

        # Third point: delta = 7, cumsum = 12
        assert result[2].get("state") == 1012.0
        assert result[2].get("sum") == 12.0

        # Fourth point: delta = 3, cumsum = 15
        assert result[3].get("state") == 1015.0
        assert result[3].get("sum") == 15.0

    def test_convert_with_last_sum(self, sample_datapoints: list[DataPoint]):
        """Test converting with existing cumulative sum."""
        result = convert_statistic_data(sample_datapoints, last_sum=100.0)

        assert len(result) == 4

        # First point: delta = 0, cumsum = 100 + 0 = 100
        assert result[0].get("sum") == 100.0

        # Second point: delta = 5, cumsum = 100 + 5 = 105
        assert result[1].get("sum") == 105.0

        # Last point should be 100 + 15 = 115
        assert result[3].get("sum") == 115.0

    def test_convert_with_last_reading(self, sample_datapoints: list[DataPoint]):
        """Test converting with previous reading for delta calculation."""
        # Previous reading was 950, so first delta should be 1000 - 950 = 50
        result = convert_statistic_data(
            sample_datapoints,
            last_reading=950.0,
        )

        assert len(result) == 4

        # First point: delta = 1000 - 950 = 50, cumsum = 50
        assert result[0].get("state") == 1000.0
        assert result[0].get("sum") == 50.0

        # Second point: delta = 5, cumsum = 55
        assert result[1].get("sum") == 55.0

        # Last point: cumsum = 50 + 5 + 7 + 3 = 65
        assert result[3].get("sum") == 65.0

    def test_convert_with_both_continuity_params(
        self, sample_datapoints: list[DataPoint]
    ):
        """Test converting with both last_sum and last_reading."""
        result = convert_statistic_data(
            sample_datapoints,
            last_sum=200.0,
            last_reading=980.0,
        )

        # First point: delta = 1000 - 980 = 20, cumsum = 200 + 20 = 220
        assert result[0].get("sum") == 220.0

        # Second point: delta = 5, cumsum = 225
        assert result[1].get("sum") == 225.0

        # Last point: cumsum = 200 + 20 + 5 + 7 + 3 = 235
        assert result[3].get("sum") == 235.0

    def test_convert_handles_monotonic_enforcement(self):
        """Test that conversion handles non-monotonic data."""
        # Create data with a backward jump (enforced by pyonwater)
        data = [
            DataPoint(
                dt=datetime(2026, 2, 1, 0, 0), reading=1000.0, unit=NativeUnits.GAL
            ),
            DataPoint(
                dt=datetime(2026, 2, 1, 1, 0), reading=1010.0, unit=NativeUnits.GAL
            ),
            DataPoint(
                dt=datetime(2026, 2, 1, 2, 0), reading=995.0, unit=NativeUnits.GAL
            ),  # Backward jump
            DataPoint(
                dt=datetime(2026, 2, 1, 3, 0), reading=1020.0, unit=NativeUnits.GAL
            ),
        ]

        result = convert_statistic_data(data)

        # Should have 4 points (enforce_monotonic_total should handle the backward jump)
        assert len(result) == 4

        # All sums should be valid (non-negative deltas after enforcement)
        for i in range(1, len(result)):
            curr = result[i].get("sum")
            prev = result[i - 1].get("sum")
            assert curr is not None and prev is not None
            assert curr >= prev, f"Non-monotonic sum at index {i}: {curr} < {prev}"


class TestFilterNewerData:
    """Test filter_newer_data function."""

    def test_no_cutoff_returns_all(self, sample_datapoints: list[DataPoint]):
        """When last_imported_time is None all points are returned unchanged."""
        result = filter_newer_data(sample_datapoints, None)
        assert result == sample_datapoints

    def test_empty_data_no_cutoff_returns_empty(self):
        """Empty list with no cutoff returns empty list."""
        result = filter_newer_data([], None)
        assert not result

    def test_empty_data_with_cutoff_returns_empty(self):
        """Empty list with a cutoff returns empty list."""
        result = filter_newer_data([], datetime(2025, 1, 1))
        assert not result

    def test_cutoff_at_midpoint_removes_older_points(
        self, sample_datapoints: list[DataPoint]
    ):
        """Points at-or-before the cutoff are removed; newer ones are kept."""
        # sample_datapoints has 4 points at hours 0, 1, 2, 3
        # Cutting at hour 1 should keep only hours 2 and 3
        cutoff = sample_datapoints[1].dt  # hour 1
        result = filter_newer_data(sample_datapoints, cutoff)
        assert len(result) == 2
        assert result[0].dt == sample_datapoints[2].dt
        assert result[1].dt == sample_datapoints[3].dt

    def test_cutoff_before_all_returns_all(self, sample_datapoints: list[DataPoint]):
        """A cutoff older than all data returns all points."""
        cutoff = datetime(2020, 1, 1, 0, 0)  # well before 2026
        result = filter_newer_data(sample_datapoints, cutoff)
        assert len(result) == 4

    def test_cutoff_after_all_returns_empty(self, sample_datapoints: list[DataPoint]):
        """A cutoff at-or-after the last point returns no points."""
        cutoff = sample_datapoints[-1].dt  # hour 3 — last point
        result = filter_newer_data(sample_datapoints, cutoff)
        assert not result


class TestCostStatisticHelpers:
    """Test cost statistic ID/name/metadata helpers."""

    def test_get_cost_statistic_id(self):
        """get_cost_statistic_id appends _cost to the consumption stat ID."""
        result = get_cost_statistic_id("12345678")
        assert result == "sensor.water_meter_12345678_cost"

    def test_get_cost_statistic_id_normalizes(self):
        """get_cost_statistic_id normalises the meter ID."""
        result = get_cost_statistic_id("ABC-123")
        assert result == "sensor.water_meter_abc_123_cost"

    def test_get_cost_statistic_name(self):
        """get_cost_statistic_name returns a human-readable cost name."""
        result = get_cost_statistic_name("12345678")
        assert result == "Water Meter 12345678 Cost"

    def test_get_cost_statistic_metadata_defaults(self, mock_meter: MagicMock):
        """Metadata has USD currency and has_sum=True."""
        result = get_cost_statistic_metadata(mock_meter)

        assert result["statistic_id"] == "sensor.water_meter_12345678_cost"
        assert result["name"] == "Water Meter 12345678 Cost"
        assert result["unit_of_measurement"] == "USD"
        assert result["has_sum"] is True
        assert result.get("has_mean") is False
        assert result["source"] == "recorder"

    def test_get_cost_statistic_metadata_custom_currency(self, mock_meter: MagicMock):
        """Metadata reflects a non-USD currency."""
        result = get_cost_statistic_metadata(mock_meter, currency="EUR")
        assert result["unit_of_measurement"] == "EUR"

    def test_get_cost_statistic_metadata_custom_id_and_name(
        self, mock_meter: MagicMock
    ):
        """Custom statistic_id and name are respected."""
        result = get_cost_statistic_metadata(
            mock_meter,
            statistic_id="sensor.my_custom_cost",
            name="My Custom Cost",
        )
        assert result["statistic_id"] == "sensor.my_custom_cost"
        assert result["name"] == "My Custom Cost"


class TestConvertCostStatisticData:
    """Test convert_cost_statistic_data."""

    def test_empty_input_returns_empty(self):
        """Empty data returns empty list."""
        result = convert_cost_statistic_data([], price_per_unit=0.01)
        assert not result

    def test_single_point_from_scratch(self, sample_datapoints: list[DataPoint]):
        """First point with no prior reading consumes 0 gallons → 0 cost."""
        result = convert_cost_statistic_data(
            [sample_datapoints[0]],
            price_per_unit=0.01,
        )
        assert len(result) == 1
        assert result[0].get("state") == pytest.approx(0.0)
        assert result[0].get("sum") == pytest.approx(0.0)

    def test_multiple_points_correct_cost(self, sample_datapoints: list[DataPoint]):
        """Cost equals cumulative consumption × rate.

        sample_datapoints deltas: 0, 5, 7, 3 gallons  (total 15 gal)
        rate = 0.01 USD/gal → cumulative costs: 0, 0.05, 0.12, 0.15
        """
        rate = 0.01
        result = convert_cost_statistic_data(sample_datapoints, price_per_unit=rate)

        assert len(result) == 4
        assert result[0].get("sum") == pytest.approx(0.0)  # 0 gal × 0.01
        assert result[1].get("sum") == pytest.approx(0.05)  # 5 gal × 0.01
        assert result[2].get("sum") == pytest.approx(0.12)  # +7 gal × 0.01
        assert result[3].get("sum") == pytest.approx(0.15)  # +3 gal × 0.01

    def test_with_prior_cost_sum(self, sample_datapoints: list[DataPoint]):
        """Existing cost sum is continued correctly."""
        result = convert_cost_statistic_data(
            sample_datapoints,
            price_per_unit=0.01,
            last_cost_sum=1.00,
        )
        # base=1.00, then 0, 0.05, 0.12, 0.15 added on top
        assert result[0].get("sum") == pytest.approx(1.00)
        assert result[1].get("sum") == pytest.approx(1.05)
        assert result[3].get("sum") == pytest.approx(1.15)

    def test_with_prior_reading(self, sample_datapoints: list[DataPoint]):
        """previous meter reading is used as delta base for the first row."""
        # Previous reading was 990 → first delta = 1000 - 990 = 10 gal
        result = convert_cost_statistic_data(
            sample_datapoints,
            price_per_unit=0.01,
            last_reading=990.0,
        )
        assert result[0].get("sum") == pytest.approx(0.10)  # 10 gal × 0.01
        assert result[1].get("sum") == pytest.approx(0.15)  # +5 gal
        assert result[3].get("sum") == pytest.approx(0.25)  # +7+3 gal

    def test_state_equals_sum(self, sample_datapoints: list[DataPoint]):
        """For cost rows state is always equal to sum (running total)."""
        result = convert_cost_statistic_data(sample_datapoints, price_per_unit=0.02)
        for row in result:
            assert row.get("state") == pytest.approx(row.get("sum"))

    def test_timestamps_preserved(self, sample_datapoints: list[DataPoint]):
        """start timestamps from DataPoints are preserved in cost rows."""
        result = convert_cost_statistic_data(sample_datapoints, price_per_unit=0.01)
        for i, row in enumerate(result):
            assert row["start"] == sample_datapoints[i].dt

    def test_cost_is_monotonic(self, sample_datapoints: list[DataPoint]):
        """Cost sum series is always non-decreasing (monotonic)."""
        result = convert_cost_statistic_data(sample_datapoints, price_per_unit=0.01)
        for i in range(1, len(result)):
            assert result[i].get("sum", 0.0) >= result[i - 1].get("sum", 0.0)
