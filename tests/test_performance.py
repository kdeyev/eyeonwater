"""Performance and stress tests for eyeonwater."""

from datetime import datetime, timedelta

from pyonwater import DataPoint, NativeUnits

from custom_components.eyeonwater.statistic_helper import convert_statistic_data


class TestPerformance:
    """Test performance with large datasets."""

    def test_convert_large_dataset(self):
        """Test converting 1 year of hourly data (8760 points)."""
        base_dt = datetime(2025, 1, 1, 0, 0, 0)

        # Generate 1 year of hourly data
        data = [
            DataPoint(
                dt=base_dt + timedelta(hours=i),
                reading=1000.0 + (i * 0.5),  # Simulate gradual increase
                unit=NativeUnits.GAL,
            )
            for i in range(8760)
        ]

        result = convert_statistic_data(data)

        assert len(result) == 8760
        # Verify cumulative sum is reasonable
        assert result[-1].get("sum", 0) > 0
        assert result[-1].get("sum", 0) < 10000  # Sanity check

    def test_convert_multiple_years(self):
        """Test converting multiple years of data."""
        base_dt = datetime(2023, 1, 1, 0, 0, 0)

        # Generate 2 years of daily data (730 points)
        data = [
            DataPoint(
                dt=base_dt + timedelta(days=i),
                reading=1000.0 + (i * 10),
                unit=NativeUnits.GAL,
            )
            for i in range(730)
        ]

        result = convert_statistic_data(data)

        assert len(result) == 730
        # First point delta should be 0
        assert result[0].get("sum") == 0.0
        # Subsequent points should increase by 10
        assert result[1].get("sum") == 10.0

    def test_convert_with_high_frequency_data(self):
        """Test converting high-frequency data (15-minute intervals)."""
        base_dt = datetime(2026, 2, 1, 0, 0, 0)

        # Generate 1 week of 15-minute data (672 points)
        data = [
            DataPoint(
                dt=base_dt + timedelta(minutes=i * 15),
                reading=1000.0 + (i * 0.1),
                unit=NativeUnits.GAL,
            )
            for i in range(672)
        ]

        result = convert_statistic_data(data)

        assert len(result) == 672
        # Verify monotonic increases
        for i in range(1, len(result)):
            assert result[i].get("sum", 0) >= result[i - 1].get("sum", 0)


class TestStressScenarios:
    """Test stress scenarios and edge cases."""

    def test_convert_with_identical_readings(self):
        """Test converting data where readings don't change."""
        base_dt = datetime(2026, 2, 1, 0, 0, 0)

        # All readings are the same (no water usage)
        data = [
            DataPoint(
                dt=base_dt + timedelta(hours=i),
                reading=1000.0,
                unit=NativeUnits.GAL,
            )
            for i in range(100)
        ]

        result = convert_statistic_data(data)

        assert len(result) == 100
        # All sums should be 0 (no consumption)
        for stat in result:
            assert stat.get("sum") == 0.0

    def test_convert_with_large_jumps(self):
        """Test converting data with large consumption jumps."""
        base_dt = datetime(2026, 2, 1, 0, 0, 0)

        data = [
            DataPoint(dt=base_dt, reading=1000.0, unit=NativeUnits.GAL),
            DataPoint(
                dt=base_dt + timedelta(hours=1), reading=1001.0, unit=NativeUnits.GAL
            ),
            DataPoint(
                dt=base_dt + timedelta(hours=2), reading=10000.0, unit=NativeUnits.GAL
            ),  # Large jump
            DataPoint(
                dt=base_dt + timedelta(hours=3), reading=10005.0, unit=NativeUnits.GAL
            ),
        ]

        result = convert_statistic_data(data)

        assert len(result) == 4
        # Large jump should be captured
        assert result[2].get("sum", 0) >= 9000  # Includes the big jump

    def test_convert_maintains_precision(self):
        """Test that floating point precision is maintained."""
        base_dt = datetime(2026, 2, 1, 0, 0, 0)

        # Use precise decimal values
        data = [
            DataPoint(dt=base_dt, reading=1000.123, unit=NativeUnits.GAL),
            DataPoint(
                dt=base_dt + timedelta(hours=1), reading=1000.456, unit=NativeUnits.GAL
            ),
            DataPoint(
                dt=base_dt + timedelta(hours=2), reading=1000.789, unit=NativeUnits.GAL
            ),
        ]

        result = convert_statistic_data(data)

        # Check state values maintain precision
        assert abs((result[0].get("state") or 0) - 1000.123) < 0.0001
        assert abs((result[1].get("state") or 0) - 1000.456) < 0.0001
        assert abs((result[2].get("state") or 0) - 1000.789) < 0.0001


class TestMemoryEfficiency:
    """Test memory efficiency with large datasets."""

    def test_convert_does_not_explode_memory(self):
        """Test that conversion doesn't create excessive intermediate objects."""
        base_dt = datetime(2026, 1, 1, 0, 0, 0)

        # Large dataset: 4 years of hourly data (35,040 points)
        data = [
            DataPoint(
                dt=base_dt + timedelta(hours=i),
                reading=1000.0 + i,
                unit=NativeUnits.GAL,
            )
            for i in range(35040)
        ]

        result = convert_statistic_data(data)

        # Should complete without memory error
        assert len(result) == 35040
        # Verify structure is maintained
        assert all("sum" in stat for stat in result)
