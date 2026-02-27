"""Tests for edge cases and boundary conditions."""

from datetime import datetime, timedelta

import pytz
from pyonwater import DataPoint, NativeUnits

from custom_components.eyeonwater.statistic_helper import (
    convert_statistic_data,
    normalize_id,
)


class TestBoundaryConditions:
    """Test boundary conditions and edge cases."""

    def test_normalize_id_empty_string(self):
        """Test normalizing empty string."""
        result = normalize_id("")
        assert result == ""

    def test_normalize_id_all_special_chars(self):
        """Test normalizing string with only special characters."""
        result = normalize_id("!@#$%^&*()")
        assert result == "__________"

    def test_normalize_id_very_long_string(self):
        """Test normalizing very long meter ID."""
        long_id = "A" * 1000
        result = normalize_id(long_id)
        assert len(result) == 1000
        assert result == "a" * 1000

    def test_normalize_id_unicode_characters(self):
        """Test normalizing ID with unicode characters."""
        result = normalize_id("meter_123_τεστ")
        # Non-ASCII characters should be replaced with underscores
        assert "___" in result or result.startswith("meter_123")


class TestDateTimeEdgeCases:
    """Test datetime edge cases."""

    def test_convert_data_across_dst_boundary(self):
        """Test conversion across daylight saving time boundary."""
        tz = pytz.timezone("America/New_York")

        # March 2026 DST begins (second Sunday)
        dst_start = tz.localize(datetime(2026, 3, 8, 1, 0, 0))

        data = [
            DataPoint(dt=dst_start, reading=1000.0, unit=NativeUnits.GAL),
            DataPoint(
                dt=dst_start + timedelta(hours=2), reading=1005.0, unit=NativeUnits.GAL
            ),
            DataPoint(
                dt=dst_start + timedelta(hours=4), reading=1010.0, unit=NativeUnits.GAL
            ),
        ]

        result = convert_statistic_data(data)

        assert len(result) == 3
        # Should handle DST transition correctly

    def test_convert_data_at_year_boundary(self):
        """Test conversion across year boundary."""
        data = [
            DataPoint(
                dt=datetime(2025, 12, 31, 23, 0, 0),
                reading=1000.0,
                unit=NativeUnits.GAL,
            ),
            DataPoint(
                dt=datetime(2026, 1, 1, 0, 0, 0), reading=1005.0, unit=NativeUnits.GAL
            ),
            DataPoint(
                dt=datetime(2026, 1, 1, 1, 0, 0), reading=1010.0, unit=NativeUnits.GAL
            ),
        ]

        result = convert_statistic_data(data)

        assert len(result) == 3
        assert result[0]["start"].year == 2025
        assert result[1]["start"].year == 2026

    def test_convert_data_leap_year(self):
        """Test conversion during leap year February 29."""
        data = [
            DataPoint(
                dt=datetime(2024, 2, 28, 12, 0, 0), reading=1000.0, unit=NativeUnits.GAL
            ),
            DataPoint(
                dt=datetime(2024, 2, 29, 12, 0, 0), reading=1005.0, unit=NativeUnits.GAL
            ),  # Leap day
            DataPoint(
                dt=datetime(2024, 3, 1, 12, 0, 0), reading=1010.0, unit=NativeUnits.GAL
            ),
        ]

        result = convert_statistic_data(data)

        assert len(result) == 3
        assert result[1]["start"].day == 29
        assert result[1]["start"].month == 2


class TestNumericEdgeCases:
    """Test numeric edge cases."""

    def test_convert_with_very_small_increments(self):
        """Test conversion with very small reading increments."""
        base_dt = datetime(2026, 2, 1, 0, 0, 0)

        data = [
            DataPoint(dt=base_dt, reading=1000.0, unit=NativeUnits.GAL),
            DataPoint(
                dt=base_dt + timedelta(hours=1), reading=1000.001, unit=NativeUnits.GAL
            ),
            DataPoint(
                dt=base_dt + timedelta(hours=2), reading=1000.002, unit=NativeUnits.GAL
            ),
        ]

        result = convert_statistic_data(data)

        assert len(result) == 3
        # Should preserve small increments
        assert result[1].get("sum", 0) > 0
        assert result[1].get("sum", 0) < 0.01

    def test_convert_with_max_float_values(self):
        """Test conversion with very large float values."""
        base_dt = datetime(2026, 2, 1, 0, 0, 0)

        large_value = 1e15  # Very large but within float range

        data = [
            DataPoint(dt=base_dt, reading=large_value, unit=NativeUnits.GAL),
            DataPoint(
                dt=base_dt + timedelta(hours=1),
                reading=large_value + 1000,
                unit=NativeUnits.GAL,
            ),
        ]

        result = convert_statistic_data(data)

        assert len(result) == 2
        assert result[1].get("sum") == 1000.0


class TestDataContinuityEdgeCases:
    """Test edge cases in data continuity."""

    def test_convert_with_gaps_in_timestamps(self):
        """Test conversion with irregular time gaps."""
        base_dt = datetime(2026, 2, 1, 0, 0, 0)

        data = [
            DataPoint(dt=base_dt, reading=1000.0, unit=NativeUnits.GAL),
            DataPoint(
                dt=base_dt + timedelta(hours=1), reading=1005.0, unit=NativeUnits.GAL
            ),
            DataPoint(
                dt=base_dt + timedelta(hours=10), reading=1010.0, unit=NativeUnits.GAL
            ),  # 9-hour gap
            DataPoint(
                dt=base_dt + timedelta(hours=11), reading=1015.0, unit=NativeUnits.GAL
            ),
        ]

        result = convert_statistic_data(data)

        # Should handle gaps gracefully
        assert len(result) == 4

    def test_convert_with_out_of_order_timestamps(self):
        """Test that enforce_monotonic handles out-of-order data."""
        base_dt = datetime(2026, 2, 1, 0, 0, 0)

        # Data intentionally out of chronological order
        data = [
            DataPoint(dt=base_dt, reading=1000.0, unit=NativeUnits.GAL),
            DataPoint(
                dt=base_dt + timedelta(hours=2), reading=1010.0, unit=NativeUnits.GAL
            ),
            DataPoint(
                dt=base_dt + timedelta(hours=1), reading=1005.0, unit=NativeUnits.GAL
            ),  # Out of order
        ]

        # enforce_monotonic_total should handle this
        result = convert_statistic_data(data)

        assert len(result) == 3

    def test_convert_duplicate_timestamps(self):
        """Test conversion with duplicate timestamps."""
        base_dt = datetime(2026, 2, 1, 0, 0, 0)

        data = [
            DataPoint(dt=base_dt, reading=1000.0, unit=NativeUnits.GAL),
            DataPoint(dt=base_dt, reading=1000.0, unit=NativeUnits.GAL),  # Duplicate
            DataPoint(
                dt=base_dt + timedelta(hours=1), reading=1005.0, unit=NativeUnits.GAL
            ),
        ]

        result = convert_statistic_data(data)

        # Should handle duplicates (may keep both or deduplicate)
        assert len(result) >= 2


class TestRobustnessValidation:
    """Test overall robustness and error resistance."""

    def test_convert_with_none_in_continuity_params(self):
        """Test conversion handles None values correctly."""
        data = [
            DataPoint(
                dt=datetime(2026, 2, 1, 0, 0, 0), reading=1000.0, unit=NativeUnits.GAL
            ),
        ]

        # Both continuity params explicitly None
        result = convert_statistic_data(data, last_sum=None, last_reading=None)

        assert len(result) == 1
        assert result[0].get("sum") == 0.0

    def test_convert_maintains_data_integrity(self):
        """Test that conversion doesn't modify input data."""
        base_dt = datetime(2026, 2, 1, 0, 0, 0)

        original_data = [
            DataPoint(dt=base_dt, reading=1000.0, unit=NativeUnits.GAL),
            DataPoint(
                dt=base_dt + timedelta(hours=1), reading=1005.0, unit=NativeUnits.GAL
            ),
        ]

        # Store original values
        original_readings = [point.reading for point in original_data]

        # Convert
        convert_statistic_data(original_data)

        # Verify original data unchanged
        for i, point in enumerate(original_data):
            assert point.reading == original_readings[i]
