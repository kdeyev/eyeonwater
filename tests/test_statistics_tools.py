"""Tests for eyeonwater statistics_tools module."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.recorder.db_schema import StatisticsMeta

from custom_components.eyeonwater.statistics_tools import (
    MonotonicValidationResult,
    MonotonicViolation,
    _get_statistics_rows,
    delete_statistics,
    resolve_statistic_id,
    validate_monotonic_sums,
)


class TestResolveStatisticId:
    """Test statistic ID resolution."""

    def test_resolve_with_statistic_id(self):
        """Test resolving when statistic_id is provided."""
        result = resolve_statistic_id(
            statistic_id="sensor.custom_meter",
            entity_id=None,
            meter_id=None,
        )
        assert result == "sensor.custom_meter"

    def test_resolve_with_entity_id_valid(self):
        """Test resolving with valid entity_id."""
        result = resolve_statistic_id(
            statistic_id=None,
            entity_id="sensor.water_meter_12345678",
            meter_id=None,
        )
        assert result == "sensor.water_meter_12345678"

    def test_resolve_with_entity_id_invalid(self):
        """Test resolving with invalid entity_id returns None."""
        result = resolve_statistic_id(
            statistic_id=None,
            entity_id="sensor.other_sensor",
            meter_id=None,
        )
        assert result is None

    def test_resolve_with_meter_id(self):
        """Test resolving from meter_id."""
        result = resolve_statistic_id(
            statistic_id=None,
            entity_id=None,
            meter_id="12345678",
        )
        assert result == "sensor.water_meter_12345678"

    def test_resolve_priority_statistic_id_over_entity_id(self):
        """Test statistic_id takes priority over entity_id."""
        result = resolve_statistic_id(
            statistic_id="sensor.custom_meter",
            entity_id="sensor.water_meter_99999999",
            meter_id=None,
        )
        assert result == "sensor.custom_meter"

    def test_resolve_priority_entity_id_over_meter_id(self):
        """Test entity_id takes priority over meter_id."""
        result = resolve_statistic_id(
            statistic_id=None,
            entity_id="sensor.water_meter_12345678",
            meter_id="99999999",
        )
        assert result == "sensor.water_meter_12345678"

    def test_resolve_all_none_returns_none(self):
        """Test all None parameters returns None."""
        result = resolve_statistic_id(
            statistic_id=None,
            entity_id=None,
            meter_id=None,
        )
        assert result is None


class TestMonotonicViolation:
    """Test MonotonicViolation dataclass."""

    def test_violation_delta_positive(self):
        """Test violation delta calculation for backward jump."""
        violation = MonotonicViolation(
            index=5,
            start=datetime(2026, 2, 1, 5, 0),
            previous_sum=1000.0,
            current_sum=995.0,
        )

        assert violation.delta == -5.0
        assert violation.index == 5
        assert violation.previous_sum == 1000.0
        assert violation.current_sum == 995.0

    def test_violation_delta_negative(self):
        """Test violation delta for forward jump."""
        violation = MonotonicViolation(
            index=10,
            start=datetime(2026, 2, 1, 10, 0),
            previous_sum=1000.0,
            current_sum=1050.0,
        )

        assert violation.delta == 50.0

    def test_violation_immutable(self):
        """Test MonotonicViolation is immutable (frozen dataclass)."""
        violation = MonotonicViolation(
            index=1,
            start=datetime(2026, 2, 1),
            previous_sum=100.0,
            current_sum=95.0,
        )

        with pytest.raises(AttributeError):
            violation.index = 2  # type: ignore[misc]

        with pytest.raises(AttributeError):
            violation.delta = 10.0  # type: ignore[misc]


class TestMonotonicValidationResult:
    """Test MonotonicValidationResult dataclass."""

    def test_result_has_expected_fields(self):
        """Test MonotonicValidationResult stores all provided fields."""
        result = MonotonicValidationResult(
            statistic_id="sensor.water_meter_12345678",
            checked=100,
            violations=[],
            start_time=None,
        )

        assert result.statistic_id == "sensor.water_meter_12345678"
        assert result.checked == 100
        assert not result.violations
        assert result.start_time is None

    def test_result_with_violations(self):
        """Test MonotonicValidationResult stores violation list correctly."""
        violation = MonotonicViolation(
            index=5,
            start=datetime(2026, 2, 1, 5, 0),
            previous_sum=1000.0,
            current_sum=980.0,
        )
        result = MonotonicValidationResult(
            statistic_id="sensor.water_meter_test",
            checked=10,
            violations=[violation],
            start_time=None,
        )

        assert len(result.violations) == 1
        assert result.violations[0] is violation
        assert result.checked == 10

    def test_result_immutable(self):
        """Test MonotonicValidationResult is immutable (frozen dataclass)."""
        result = MonotonicValidationResult(
            statistic_id="sensor.test",
            checked=10,
            violations=[],
            start_time=None,
        )

        with pytest.raises(AttributeError):
            result.checked = 20  # type: ignore[misc]

    def test_result_with_start_time(self):
        """Test MonotonicValidationResult stores optional start_time correctly."""
        start = datetime(2026, 2, 1, 0, 0)
        result = MonotonicValidationResult(
            statistic_id="sensor.test",
            checked=50,
            violations=[],
            start_time=start,
        )

        assert result.start_time == start
        assert result.checked == 50

    def test_result_multiple_violations(self):
        """Test MonotonicValidationResult with multiple violations."""
        violations = [
            MonotonicViolation(
                index=i,
                start=datetime(2026, 2, 1, i, 0),
                previous_sum=float(100 + i * 10),
                current_sum=float(100 + i * 10 - 5),
            )
            for i in range(3)
        ]
        result = MonotonicValidationResult(
            statistic_id="sensor.multi",
            checked=50,
            violations=violations,
            start_time=None,
        )

        assert len(result.violations) == 3
        assert result.violations[0].index == 0
        assert result.violations[2].index == 2


# ---------------------------------------------------------------------------
# _get_statistics_rows / validate_monotonic_sums / delete_statistics
# ---------------------------------------------------------------------------


class TestGetStatisticsRows:
    """Tests for the synchronous _get_statistics_rows helper."""

    def _make_session_context(self, meta_id=1, rows=None):
        """Return a mock recorder whose session context yields a usable session."""
        session = MagicMock()

        # meta_id query chain
        meta_q = MagicMock()
        meta_q.filter.return_value.scalar.return_value = meta_id

        # rows query chain
        rows_q = MagicMock()
        rows_q.filter.return_value = rows_q
        rows_q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = (
            rows or []
        )

        def query_side_effect(model):
            if model is StatisticsMeta.id or model is StatisticsMeta:
                return meta_q
            return rows_q

        session.query.side_effect = query_side_effect

        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=session)
        cm.__exit__ = MagicMock(return_value=None)

        recorder = MagicMock()
        recorder.get_session.return_value = cm
        return recorder

    def test_returns_empty_list_when_no_meta_id(self):
        """Should return [] when the statistic_id has no metadata row."""
        session = MagicMock()
        session.query.return_value.filter.return_value.scalar.return_value = None

        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=session)
        cm.__exit__ = MagicMock(return_value=None)

        recorder = MagicMock()
        recorder.get_session.return_value = cm
        hass = MagicMock()

        with patch(
            "custom_components.eyeonwater.statistics_tools.get_instance",
            return_value=recorder,
        ):
            result = _get_statistics_rows(
                hass, "sensor.unknown", start_time=None, offset=0, limit=100
            )

        assert not result

    def test_returns_rows_when_meta_exists(self):
        """Should return the query result rows when meta_id is found."""
        fake_rows = [MagicMock(), MagicMock()]

        session = MagicMock()
        # meta query
        meta_query = MagicMock()
        meta_query.filter.return_value.scalar.return_value = 42

        # rows query chain
        rows_query = MagicMock()
        filtered_query = MagicMock()
        ordered_query = MagicMock()
        offset_query = MagicMock()

        rows_query.filter.return_value = filtered_query
        filtered_query.order_by.return_value = ordered_query
        ordered_query.offset.return_value = offset_query
        offset_query.limit.return_value.all.return_value = fake_rows

        def query_side_effect(model):
            if model is StatisticsMeta.id or model is StatisticsMeta:
                return meta_query
            return rows_query

        session.query.side_effect = query_side_effect

        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=session)
        cm.__exit__ = MagicMock(return_value=None)

        recorder = MagicMock()
        recorder.get_session.return_value = cm
        hass = MagicMock()

        with patch(
            "custom_components.eyeonwater.statistics_tools.get_instance",
            return_value=recorder,
        ):
            result = _get_statistics_rows(
                hass, "sensor.water", start_time=None, offset=0, limit=100
            )

        assert isinstance(result, list)
        assert result == fake_rows


class TestValidateMonotonicSums:
    """Tests for validate_monotonic_sums async function."""

    @pytest.mark.asyncio
    async def test_returns_result_with_no_rows(self):
        """Empty history → checked=0, no violations."""
        recorder = MagicMock()
        recorder.async_add_executor_job = AsyncMock(return_value=[])
        hass = MagicMock()

        with patch(
            "custom_components.eyeonwater.statistics_tools.get_instance",
            return_value=recorder,
        ):
            result = await validate_monotonic_sums(hass, "sensor.water")

        assert result.checked == 0
        assert result.violations == []
        assert result.statistic_id == "sensor.water"

    @pytest.mark.asyncio
    async def test_detects_violation(self):
        """A decreasing sum pair should produce one MonotonicViolation."""
        row1 = MagicMock()
        row1.sum = 100.0
        row1.start = datetime(2026, 1, 1, 0, 0)
        row2 = MagicMock()
        row2.sum = 90.0  # drops — violation
        row2.start = datetime(2026, 1, 1, 1, 0)

        # First batch has 2 rows, second batch is empty (terminates loop)
        recorder = MagicMock()
        recorder.async_add_executor_job = AsyncMock(side_effect=[[row1, row2], []])
        hass = MagicMock()

        with patch(
            "custom_components.eyeonwater.statistics_tools.get_instance",
            return_value=recorder,
        ):
            result = await validate_monotonic_sums(hass, "sensor.water")

        assert result.checked == 2
        assert len(result.violations) == 1
        assert result.violations[0].previous_sum == 100.0
        assert result.violations[0].current_sum == 90.0

    @pytest.mark.asyncio
    async def test_no_violation_for_increasing_sums(self):
        """Monotonically increasing sums produce zero violations."""
        rows = []
        for i in range(5):
            r = MagicMock()
            r.sum = float(i * 10)
            r.start = datetime(2026, 1, 1, i, 0)
            rows.append(r)

        recorder = MagicMock()
        recorder.async_add_executor_job = AsyncMock(side_effect=[rows, []])
        hass = MagicMock()

        with patch(
            "custom_components.eyeonwater.statistics_tools.get_instance",
            return_value=recorder,
        ):
            result = await validate_monotonic_sums(hass, "sensor.water")

        assert result.checked == 5
        assert result.violations == []

    @pytest.mark.asyncio
    async def test_hours_parameter_sets_start_time(self):
        """When hours= is provided, start_time is set (not None)."""
        recorder = MagicMock()
        recorder.async_add_executor_job = AsyncMock(return_value=[])
        hass = MagicMock()

        with patch(
            "custom_components.eyeonwater.statistics_tools.get_instance",
            return_value=recorder,
        ):
            result = await validate_monotonic_sums(hass, "sensor.water", hours=24)

        assert result.start_time is not None

    @pytest.mark.asyncio
    async def test_full_scan_ignores_hours(self):
        """With full_scan=True, start_time stays None regardless of hours."""
        recorder = MagicMock()
        recorder.async_add_executor_job = AsyncMock(return_value=[])
        hass = MagicMock()

        with patch(
            "custom_components.eyeonwater.statistics_tools.get_instance",
            return_value=recorder,
        ):
            result = await validate_monotonic_sums(
                hass, "sensor.water", hours=24, full_scan=True
            )

        assert result.start_time is None

    @pytest.mark.asyncio
    async def test_row_with_none_sum_skipped(self):
        """Rows with sum=None are skipped without raising or recording a violation."""
        row_none = MagicMock()
        row_none.sum = None
        row_none.start = datetime(2026, 1, 1, 0, 0)
        row_good = MagicMock()
        row_good.sum = 50.0
        row_good.start = datetime(2026, 1, 1, 1, 0)

        recorder = MagicMock()
        recorder.async_add_executor_job = AsyncMock(
            side_effect=[[row_none, row_good], []]
        )
        hass = MagicMock()

        with patch(
            "custom_components.eyeonwater.statistics_tools.get_instance",
            return_value=recorder,
        ):
            result = await validate_monotonic_sums(hass, "sensor.water")

        assert result.violations == []


class TestDeleteStatistics:
    """Tests for the delete_statistics async function."""

    @pytest.mark.asyncio
    async def test_calls_executor_with_inner_fn(self):
        """delete_statistics must invoke async_add_executor_job on the recorder."""
        recorder = MagicMock()
        recorder.async_add_executor_job = AsyncMock(return_value=5)
        hass = MagicMock()

        with patch(
            "custom_components.eyeonwater.statistics_tools.get_instance",
            return_value=recorder,
        ):
            result = await delete_statistics(hass, "sensor.water")

        recorder.async_add_executor_job.assert_awaited_once()
        assert result == 5

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_rows_deleted(self):
        """Return value of 0 when executor reports no deletions."""
        recorder = MagicMock()
        recorder.async_add_executor_job = AsyncMock(return_value=0)
        hass = MagicMock()

        with patch(
            "custom_components.eyeonwater.statistics_tools.get_instance",
            return_value=recorder,
        ):
            result = await delete_statistics(hass, "sensor.nonexistent")

        assert result == 0
