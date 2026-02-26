"""Integration tests for eyeonwater components."""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytz
import pytest
from pyonwater import DataPoint, NativeUnits

from custom_components.eyeonwater.statistic_helper import (
    centralized_import_statistics,
    convert_statistic_data,
    filter_newer_data,
    get_entity_statistic_id,
)


class TestEndToEndDataFlow:
    """Test end-to-end data flow from API to statistics."""

    @pytest.mark.asyncio
    async def test_full_import_pipeline(self):
        """Test complete data import pipeline."""
        # Create sample historical data
        base_dt = datetime(2026, 2, 1, 0, 0, 0)
        historical_data = [
            DataPoint(dt=base_dt, reading=1000.0, unit=NativeUnits.GAL),
            DataPoint(
                dt=base_dt + timedelta(hours=1), reading=1005.0, unit=NativeUnits.GAL
            ),
            DataPoint(
                dt=base_dt + timedelta(hours=2), reading=1012.0, unit=NativeUnits.GAL
            ),
        ]

        # Convert to statistics
        statistic_data = convert_statistic_data(historical_data)

        # Verify conversion
        assert len(statistic_data) == 3
        assert statistic_data[0].get("sum") == 0.0  # First delta
        assert statistic_data[1].get("sum") == 5.0  # Second delta
        assert statistic_data[2].get("sum") == 12.0  # Third delta

        # Verify all required fields present
        for stat in statistic_data:
            assert "start" in stat
            assert "state" in stat
            assert "sum" in stat

    def test_statistic_id_consistency(self, mock_meter: MagicMock):
        """Test statistic ID generation is consistent."""
        statistic_id_1 = get_entity_statistic_id(mock_meter.meter_id)
        statistic_id_2 = get_entity_statistic_id(mock_meter.meter_id)

        assert statistic_id_1 == statistic_id_2
        assert statistic_id_1 == "sensor.water_meter_12345678"


class TestDataFiltering:
    """Test data filtering logic."""

    def test_filter_newer_data_removes_old_points(self):
        """Test filtering removes points before cutoff."""
        cutoff = datetime(2026, 2, 1, 12, 0, 0)

        data = [
            DataPoint(
                dt=datetime(2026, 2, 1, 10, 0, 0), reading=1000.0, unit=NativeUnits.GAL
            ),
            DataPoint(
                dt=datetime(2026, 2, 1, 13, 0, 0), reading=1005.0, unit=NativeUnits.GAL
            ),
            DataPoint(
                dt=datetime(2026, 2, 1, 14, 0, 0), reading=1010.0, unit=NativeUnits.GAL
            ),
        ]

        filtered = filter_newer_data(data, last_imported_time=cutoff)

        # Should only include points after cutoff
        assert len(filtered) == 2
        assert all(point.dt > cutoff for point in filtered)

    def test_filter_newer_data_handles_none_cutoff(self):
        """Test filtering with None cutoff returns all data."""
        data = [
            DataPoint(
                dt=datetime(2026, 2, 1, 10, 0, 0), reading=1000.0, unit=NativeUnits.GAL
            ),
            DataPoint(
                dt=datetime(2026, 2, 1, 11, 0, 0), reading=1005.0, unit=NativeUnits.GAL
            ),
        ]

        filtered = filter_newer_data(data, last_imported_time=None)

        # Should return all data when cutoff is None
        assert len(filtered) == len(data)


class TestMultipleMeterScenarios:
    """Test scenarios with multiple meters."""

    def test_different_meter_ids_generate_unique_statistic_ids(self):
        """Test each meter gets unique statistic ID."""
        meter_id_1 = "12345678"
        meter_id_2 = "87654321"

        stat_id_1 = get_entity_statistic_id(meter_id_1)
        stat_id_2 = get_entity_statistic_id(meter_id_2)

        assert stat_id_1 != stat_id_2
        assert "12345678" in stat_id_1
        assert "87654321" in stat_id_2

    def test_convert_data_independent_per_meter(self):
        """Test data conversion is independent for each meter."""
        # Meter 1 data
        meter1_data = [
            DataPoint(
                dt=datetime(2026, 2, 1, 0, 0, 0), reading=1000.0, unit=NativeUnits.GAL
            ),
            DataPoint(
                dt=datetime(2026, 2, 1, 1, 0, 0), reading=1010.0, unit=NativeUnits.GAL
            ),
        ]

        # Meter 2 data
        meter2_data = [
            DataPoint(
                dt=datetime(2026, 2, 1, 0, 0, 0), reading=5000.0, unit=NativeUnits.GAL
            ),
            DataPoint(
                dt=datetime(2026, 2, 1, 1, 0, 0), reading=5020.0, unit=NativeUnits.GAL
            ),
        ]

        stats1 = convert_statistic_data(meter1_data)
        stats2 = convert_statistic_data(meter2_data)

        # Both should have 2 points
        assert len(stats1) == 2
        assert len(stats2) == 2

        # Verify independent cumulative sums
        assert stats1[1].get("sum") == 10.0  # 1010 - 1000
        assert stats2[1].get("sum") == 20.0  # 5020 - 5000


class TestErrorRecovery:
    """Test error recovery scenarios."""

    def test_convert_handles_empty_data_gracefully(self):
        """Test conversion handles empty data without error."""
        result = convert_statistic_data([])

        assert not result
        assert isinstance(result, list)

    def test_convert_handles_single_point(self):
        """Test conversion handles single data point."""
        data = [
            DataPoint(
                dt=datetime(2026, 2, 1, 0, 0, 0), reading=1000.0, unit=NativeUnits.GAL
            ),
        ]

        result = convert_statistic_data(data)

        assert len(result) == 1
        assert result[0].get("state") == 1000.0
        assert result[0].get("sum") == 0.0  # No previous reading, delta is 0


class TestTimezoneHandling:
    """Test timezone-aware datetime handling."""

    def test_convert_preserves_timezone_info(self):
        """Test that timezone information is preserved through conversion."""
        tz = pytz.timezone("America/New_York")
        base_dt = tz.localize(datetime(2026, 2, 1, 0, 0, 0))

        data = [
            DataPoint(dt=base_dt, reading=1000.0, unit=NativeUnits.GAL),
            DataPoint(
                dt=base_dt + timedelta(hours=1), reading=1005.0, unit=NativeUnits.GAL
            ),
        ]

        result = convert_statistic_data(data)

        # Verify timezone is preserved in output
        assert result[0]["start"].tzinfo is not None
        assert result[1]["start"].tzinfo is not None


class TestStatisticDataValidation:
    """Test statistic data structure validation."""

    def test_converted_data_has_required_fields(
        self, sample_datapoints: list[DataPoint]
    ):
        """Test all converted statistics have required fields."""
        result = convert_statistic_data(sample_datapoints)

        required_fields = ["start", "state", "sum"]

        for stat in result:
            for field in required_fields:
                assert field in stat, f"Missing required field: {field}"

    def test_converted_data_types_correct(self, sample_datapoints: list[DataPoint]):
        """Test converted data has correct types."""
        result = convert_statistic_data(sample_datapoints)

        for stat in result:
            assert isinstance(stat["start"], datetime)
            assert isinstance(stat.get("state"), float)
            assert isinstance(stat.get("sum"), float)

    def test_cumulative_sum_always_increasing(self, sample_datapoints: list[DataPoint]):
        """Test cumulative sum is monotonically increasing."""
        result = convert_statistic_data(sample_datapoints)

        for i in range(1, len(result)):
            sum_i = result[i].get("sum")
            sum_prev = result[i - 1].get("sum")
            assert sum_i is not None and sum_prev is not None
            assert sum_i >= sum_prev, f"Sum decreased at index {i}"


class TestBackfillOverlapDetection:
    """Test that centralized_import_statistics handles backfill/overlap correctly.

    When importing data whose first point is <= the last stat already in the DB,
    the code must use the stat just BEFORE the first import point as the delta
    base — not the last DB stat (which would produce a large negative delta and
    corrupt the stored sums).
    """

    @pytest.mark.asyncio
    async def test_normal_continuation_uses_last_db_stat(
        self, mock_hass: MagicMock, mock_meter: MagicMock
    ):
        """Normal case: new data starts after last DB stat → uses last DB stat."""
        tz = timezone.utc
        last_db_dt = datetime(2026, 2, 18, 12, 0, 0, tzinfo=tz)
        # New data starts AFTER last_db_dt → normal continuation
        new_data = [
            DataPoint(
                dt=datetime(2026, 2, 18, 13, 0, 0, tzinfo=tz),
                reading=204215.0,
                unit=NativeUnits.GAL,
            ),
            DataPoint(
                dt=datetime(2026, 2, 18, 14, 0, 0, tzinfo=tz),
                reading=204220.0,
                unit=NativeUnits.GAL,
            ),
        ]

        captured_stats: list[Any] = []

        def _capture_normal(_hass: Any, _meta: Any, stats: Any) -> None:
            captured_stats.extend(stats)

        with (
            patch(
                "custom_components.eyeonwater.statistic_helper.get_last_imported_stat",
                new=AsyncMock(return_value=(last_db_dt, 204211.8, 11460.0)),
            ),
            patch(
                "custom_components.eyeonwater.statistic_helper.async_import_statistics",
                side_effect=_capture_normal,
            ),
            patch(
                "custom_components.eyeonwater.statistic_helper.get_statistic_metadata",
                return_value={},
            ),
        ):
            await centralized_import_statistics(
                mock_hass,
                mock_meter,
                new_data,
                statistic_id="sensor.water_meter_12345678",
                statistic_name="Water Meter 12345678",
            )

        assert len(captured_stats) == 2
        # delta(0): 204215 - 204211.8 = 3.2, cumsum = 11460 + 3.2 = 11463.2
        assert abs(captured_stats[0]["sum"] - 11463.2) < 0.01
        # delta(1): 204220 - 204215 = 5.0, cumsum = 11463.2 + 5.0 = 11468.2
        assert abs(captured_stats[1]["sum"] - 11468.2) < 0.01

    @pytest.mark.asyncio
    async def test_backfill_overlap_uses_stat_before_first_point(
        self, mock_hass: MagicMock, mock_meter: MagicMock
    ):
        """Backfill case: data starts before last DB stat → uses stat-before as base.

        Scenario: DB has stats through Feb 18 (sum=11460, state=204211.8).
        Service import re-sends Feb 12-18 data (starting at 203428.6).
        Without the fix, delta = 203428.6 - 204211.8 = -783.2 (negative!).
        With the fix, the stat before Feb 12 is queried (state=203000, sum=10000)
        and used as the base so delta = 203428.6 - 203000 = 428.6 (correct).
        """
        tz = timezone.utc
        last_db_dt = datetime(2026, 2, 18, 12, 0, 0, tzinfo=tz)
        first_point_dt = datetime(2026, 2, 12, 0, 0, 0, tzinfo=tz)

        # Simulate DB having stats through Feb 18 (most-recent)
        # The stat just BEFORE Feb 12 had state=203000, sum=10000
        stat_before_first_point = (203000.0, 10000.0)

        backfill_data = [
            DataPoint(dt=first_point_dt, reading=203428.6, unit=NativeUnits.GAL),
            DataPoint(
                dt=datetime(2026, 2, 12, 1, 0, 0, tzinfo=tz),
                reading=203430.0,
                unit=NativeUnits.GAL,
            ),
        ]

        captured_stats: list[Any] = []

        def _capture_backfill(_hass: Any, _meta: Any, stats: Any) -> None:
            captured_stats.extend(stats)

        with (
            patch(
                "custom_components.eyeonwater.statistic_helper.get_last_imported_stat",
                new=AsyncMock(return_value=(last_db_dt, 204211.8, 11460.0)),
            ),
            patch(
                "custom_components.eyeonwater.statistic_helper"
                ".async_get_stat_just_before",
                new=AsyncMock(return_value=stat_before_first_point),
            ),
            patch(
                "custom_components.eyeonwater.statistic_helper.async_import_statistics",
                side_effect=_capture_backfill,
            ),
            patch(
                "custom_components.eyeonwater.statistic_helper.get_statistic_metadata",
                return_value={},
            ),
        ):
            await centralized_import_statistics(
                mock_hass,
                mock_meter,
                backfill_data,
                statistic_id="sensor.water_meter_12345678",
                statistic_name="Water Meter 12345678",
            )

        assert len(captured_stats) == 2
        # delta(0): 203428.6 - 203000.0 = 428.6, cumsum = 10000 + 428.6 = 10428.6
        assert captured_stats[0]["sum"] > 0, "First sum must not be negative"
        assert abs(captured_stats[0]["sum"] - 10428.6) < 0.01
        # delta(1): 203430.0 - 203428.6 = 1.4, cumsum ≈ 10430.0
        assert abs(captured_stats[1]["sum"] - 10430.0) < 0.01

    @pytest.mark.asyncio
    async def test_backfill_with_no_prior_stat_starts_from_zero(
        self, mock_hass: MagicMock, mock_meter: MagicMock
    ):
        """Backfill when no stat exists before the first point → sum starts from 0."""
        tz = timezone.utc
        last_db_dt = datetime(2026, 2, 18, 12, 0, 0, tzinfo=tz)
        first_point_dt = datetime(2026, 2, 12, 0, 0, 0, tzinfo=tz)

        # No stat found before Feb 12
        stat_before_first_point = (None, None)

        backfill_data = [
            DataPoint(dt=first_point_dt, reading=203428.6, unit=NativeUnits.GAL),
            DataPoint(
                dt=datetime(2026, 2, 12, 1, 0, 0, tzinfo=tz),
                reading=203434.0,
                unit=NativeUnits.GAL,
            ),
        ]

        captured_stats: list[Any] = []

        def _capture_no_prior(_hass: Any, _meta: Any, stats: Any) -> None:
            captured_stats.extend(stats)

        with (
            patch(
                "custom_components.eyeonwater.statistic_helper.get_last_imported_stat",
                new=AsyncMock(return_value=(last_db_dt, 204211.8, 11460.0)),
            ),
            patch(
                "custom_components.eyeonwater.statistic_helper"
                ".async_get_stat_just_before",
                new=AsyncMock(return_value=stat_before_first_point),
            ),
            patch(
                "custom_components.eyeonwater.statistic_helper.async_import_statistics",
                side_effect=_capture_no_prior,
            ),
            patch(
                "custom_components.eyeonwater.statistic_helper.get_statistic_metadata",
                return_value={},
            ),
        ):
            await centralized_import_statistics(
                mock_hass,
                mock_meter,
                backfill_data,
                statistic_id="sensor.water_meter_12345678",
                statistic_name="Water Meter 12345678",
            )

        assert len(captured_stats) == 2
        # No prior stat → treat first reading as baseline → first sum = 0
        assert captured_stats[0]["sum"] == 0.0
        # delta(1): 203434 - 203428.6 = 5.4
        assert abs(captured_stats[1]["sum"] - 5.4) < 0.01
