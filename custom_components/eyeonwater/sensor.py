"""Support for EyeOnWater sensors."""

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING, Any, cast

import pyonwater
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from propcache.api import cached_property
from sqlalchemy.exc import SQLAlchemyError

from .const import (
    CONF_PRICE_ENTITY,
    DATA_COORDINATOR,
    DATA_SMART_METER,
    DOMAIN,
    WATER_METER_NAME,
)
from .statistic_helper import (
    async_get_highest_sum_stat,
    async_get_stat_just_before,
    async_write_carry_forward_stats,
    centralized_import_statistics,
    filter_newer_data,
    get_cost_statistic_id,
    get_cost_statistic_metadata,
    get_entity_statistic_id,
    get_ha_native_unit_of_measurement,
    get_last_imported_stat,
    normalize_id,
)

if TYPE_CHECKING:
    from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EyeOnWater sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    meters = hass.data[DOMAIN][config_entry.entry_id][DATA_SMART_METER].meters

    sensors: list[Entity] = []
    for meter in meters:
        normalized_id = normalize_id(meter.meter_id)
        statistic_id = get_entity_statistic_id(meter.meter_id)
        statistic_name = f"{WATER_METER_NAME} {normalized_id}"
        price_entity_id = config_entry.options.get(CONF_PRICE_ENTITY) or None

        if price_entity_id:
            cost_stat_id = get_cost_statistic_id(meter.meter_id)
            _LOGGER.info(
                "Cost statistics enabled for meter %s using price entity '%s'. "
                "Set stat_cost: %s in your Energy Dashboard water source config.",
                meter.meter_id,
                price_entity_id,
                cost_stat_id,
            )
        else:
            _LOGGER.debug(
                "No price entity configured for meter %s — cost statistics disabled. "
                "Configure one via:"
                "  Settings > Devices & Services > EyeOnWater > Configure.",
                meter.meter_id,
            )

        # Fetch last imported statistic (datetime, state, and sum)
        last_imported_time, _, _ = await get_last_imported_stat(
            hass,
            meter,
            statistic_id=statistic_id,
        )

        sensors.append(
            EyeOnWaterUnifiedSensor(
                meter,
                coordinator,
                last_imported_time=last_imported_time,
                statistic_id=statistic_id,
                statistic_name=statistic_name,
                price_entity_id=price_entity_id,
            ),
        )

        if meter.meter_info.sensors and meter.meter_info.sensors.endpoint_temperature:
            sensors.append(EyeOnWaterTempSensor(meter, coordinator))

    async_add_entities(sensors, update_before_add=False)


class EyeOnWaterUnifiedSensor(RestoreEntity, SensorEntity):
    """Unified EyeOnWater sensor.

    Provides a single sensor per meter and manages long-term statistics.

    Entity ID Format:
        sensor.water_meter_{meter_uuid}
        Used in Home Assistant UI and automations.

    Statistic ID Format:
        sensor.water_meter_{meter_id}
        Used in service calls (import_historical_data, reset_statistics, etc.).

    Note:
        The meter_uuid (based on hardware serial) and meter_id (from API)
        may differ. Always use the correct format depending on context.

    """

    _attr_has_entity_name = False
    _attr_device_class = SensorDeviceClass.WATER
    # TOTAL_INCREASING is REQUIRED for the Energy Dashboard to:
    #   1. Allow this entity to appear in the Energy/Water source picker.
    #   2. Enable cost-per-unit calculation against tariff rates.
    # Without it, statistics bars may still render (the statistics table has
    # data) but the cost column will always be blank.
    #
    # HA will auto-generate statistics_short_term entries from each
    # async_write_ha_state() call.  We guard against spurious entries by
    # only writing state when the API delivers genuinely new data points
    # (see _handle_update_locked).  Stale 15-minute coordinator polls that
    # return no new readings are silently skipped.
    #
    # KNOWN RISK: if recorder.purge_entities (or clear_statistics) is called
    # outside normal operation, HA loses its statistics_short_term sum
    # baseline.  The first state write afterward produces a
    # statistics_short_term entry with sum≈0 which can overwrite the
    # correctly-imported statistics row for that hour at the next hourly
    # rollup.  Resolution: after any purge call, immediately trigger
    # import_historical_data (or replay_scenario) to re-establish correct
    # statistics BEFORE the next hourly rollup boundary.
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_should_poll = False

    def __init__(
        self,
        meter: pyonwater.Meter,
        coordinator: DataUpdateCoordinator,
        last_imported_time: datetime.datetime | None,
        *,
        statistic_id: str,
        statistic_name: str,
        price_entity_id: str | None = None,
    ) -> None:
        """Initialize the unified sensor."""
        super().__init__()
        self.coordinator = coordinator
        self.meter = meter
        self._uuid = normalize_id(meter.meter_uuid)
        self._id = normalize_id(meter.meter_id)

        self._state: pyonwater.DataPoint | None = None
        self._last_historical_data: list[pyonwater.DataPoint] = []
        self._last_imported_time = last_imported_time
        self._statistic_id = statistic_id
        self._statistic_name = statistic_name
        self._price_entity_id = price_entity_id
        self._import_lock = asyncio.Lock()

        self._attr_name = f"{WATER_METER_NAME} {self._id}"
        self._attr_unique_id = self._uuid
        self._attr_available = False
        self._attr_native_value = None
        unit_str = meter.native_unit_of_measurement
        unit_enum = pyonwater.NativeUnits(unit_str)
        self._attr_native_unit_of_measurement = get_ha_native_unit_of_measurement(
            unit_enum,
        )
        self._attr_suggested_display_precision = 0
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._uuid)},
            name=f"{WATER_METER_NAME} {self._id}",
            model=self.meter.meter_info.reading.model,
            manufacturer=self.meter.meter_info.reading.customer_name,
            hw_version=self.meter.meter_info.reading.hardware_version,
            sw_version=self.meter.meter_info.reading.firmware_version,
        )

    @cached_property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the device specific state attributes."""
        if self._state:
            return cast("dict[str, Any]", self.meter.meter_info.reading.model_dump())
        return {}

    @callback
    def _state_update(self) -> None:
        """Call when the coordinator has an update."""
        _LOGGER.debug(
            "Unified sensor _state_update called for meter %s",
            self.meter.meter_id,
        )
        self._attr_available = self.coordinator.last_update_success
        if not self._attr_available:
            # Coordinator failed — commit the unavailable state so HA recorder
            # captures the transition and the entity shows as unavailable in UI.
            self.async_write_ha_state()
            return

        if len(self.meter.last_historical_data) == 0:
            _LOGGER.warning(
                "Meter %s has no historical data yet",
                self.meter.meter_id,
            )
            # No data yet but coordinator succeeded — keep current state visible.
            self.async_write_ha_state()
            return

        # Get latest historical data point
        latest_data = self.meter.last_historical_data[-1]

        # Defer async work to avoid blocking the coordinator callback.
        self.hass.create_task(self._handle_update_async(latest_data))

    def _resolve_price_per_unit(self) -> float | None:
        """Return current price per unit-of-volume from the configured entity.

        Reads the live state of ``_price_entity_id`` from the HA state machine.
        Returns ``None`` when no price entity is configured, the entity is
        unavailable, or its state cannot be parsed as a float.
        """
        if not self._price_entity_id:
            return None
        state_obj = self.hass.states.get(self._price_entity_id)
        if state_obj is None or state_obj.state in ("unavailable", "unknown", None):
            _LOGGER.warning(
                "Price entity %s unavailable — cost statistics skipped",
                self._price_entity_id,
            )
            return None
        try:
            price = float(state_obj.state)
        except (ValueError, TypeError):
            _LOGGER.warning(
                "Price entity %s state '%s' is not numeric — cost statistics skipped",
                self._price_entity_id,
                state_obj.state,
            )
            return None
        if price <= 0:
            _LOGGER.warning(
                "Price entity %s state '%s' is zero/negative — cost statistics skipped",
                self._price_entity_id,
                state_obj.state,
            )
            return None
        _LOGGER.debug(
            "Price for cost stats: %s = %.6f %s/unit",
            self._price_entity_id,
            price,
            self.hass.config.currency or "USD",
        )
        return price

    async def _repair_db_ahead_baseline(
        self,
        last_stat_time: datetime.datetime,
        effective_last_time: datetime.datetime,
        last_stat_sum: float | None,
    ) -> tuple[datetime.datetime, float | None, float | None, bool]:
        """Repair compiler-contaminated rows when DB has advanced past import baseline.

        When the HA hourly statistics compiler writes rows between
        ``effective_last_time`` and ``last_stat_time`` (using short-term stats
        that reset to sum≈0 after a restart), those rows carry wrong cumulative
        sums.  Look up the correct sum at ``effective_last_time`` and overwrite
        contaminated hours with carry-forward rows.

        Returns (effective_last_time, last_stat_reading, last_stat_sum, repaired).
        """
        compiler_sum = last_stat_sum
        import_state, import_sum = await async_get_stat_just_before(
            self.hass,
            self._statistic_id,
            effective_last_time + datetime.timedelta(hours=1),
        )
        if import_state is None or import_sum is None:
            return effective_last_time, None, last_stat_sum, False

        if compiler_sum is None or abs(compiler_sum - import_sum) > 0.01:
            _LOGGER.warning(
                "DB ahead (%s > %s) with incorrect sum (%.4f vs "
                "correct %.4f) for %s — overwriting contaminated "
                "hours with carry-forward rows",
                last_stat_time,
                effective_last_time,
                compiler_sum,
                import_sum,
                self._statistic_id,
            )
            await async_write_carry_forward_stats(
                self.hass,
                self.meter,
                self._statistic_id,
                self._statistic_name,
                from_dt=effective_last_time,
                through_dt=last_stat_time,
                carry_state=import_state,
                carry_sum=import_sum,
            )
            self._last_imported_time = last_stat_time
            return last_stat_time, import_state, import_sum, True

        _LOGGER.debug(
            "DB ahead of last import (%s > %s) — compiler sums "
            "are consistent (%.4f); no carry-forward needed",
            last_stat_time,
            effective_last_time,
            import_sum,
        )
        return effective_last_time, import_state, import_sum, False

    async def _repair_sum_monotonicity(
        self,
        last_stat_time: datetime.datetime,
        last_stat_sum: float,
    ) -> tuple[datetime.datetime | None, float | None, float | None, bool]:
        """Repair LTS chain when max(sum) > latest sum (compiler reset after restart).

        For TOTAL_INCREASING the cumulative sum can never decrease.  The row
        with the MAXIMUM sum across all LTS rows is always the last row written
        by a real async_import_statistics call.  Write carry-forward rows from
        the max-sum anchor through ``last_stat_time`` so the corrupted rows are
        overwritten with correct cumulative values.

        Returns (new_effective_last_time, last_stat_reading, new_sum, repaired).
        All values are ``None``/``False`` when no violation is detected.
        """
        anchor_dt, anchor_state, anchor_sum = await async_get_highest_sum_stat(
            self.hass,
            self._statistic_id,
        )
        if (
            anchor_sum is None
            or anchor_sum <= last_stat_sum + 0.01
            or anchor_dt is None
        ):
            return None, None, None, False

        entity_reading = self._attr_native_value
        if (
            entity_reading is not None
            and anchor_state is not None
            and isinstance(entity_reading, (int, float))
            and isinstance(anchor_state, (int, float))
        ):
            correct_sum = anchor_sum + (float(entity_reading) - float(anchor_state))
            carry_state = float(entity_reading)
        else:
            correct_sum = anchor_sum
            carry_state = float(anchor_state) if anchor_state is not None else 0.0

        _LOGGER.warning(
            "Sum monotonicity violation for %s: max_import_sum=%.4f "
            "(at %s) > latest_sum=%.4f (at %s) — compiler reset LTS "
            "chain after HA restart; repairing with correct_sum=%.4f",
            self._statistic_id,
            anchor_sum,
            anchor_dt,
            last_stat_sum,
            last_stat_time,
            correct_sum,
        )
        await async_write_carry_forward_stats(
            self.hass,
            self.meter,
            self._statistic_id,
            self._statistic_name,
            from_dt=anchor_dt,
            through_dt=last_stat_time,
            carry_state=carry_state,
            carry_sum=correct_sum,
        )
        self._last_imported_time = last_stat_time
        return last_stat_time, carry_state, correct_sum, True

    async def _repair_cost_stat(self, last_stat_time: datetime.datetime) -> None:
        """Repair cost LTS chain using the same max(sum) carry-forward strategy.

        When a consumption repair just ran, cost rows in the same window are
        contaminated by the same HA compiler mechanism.  Overwrite them so the
        Energy Dashboard cost column self-heals at startup.
        """
        cost_stat_id = get_cost_statistic_id(self.meter.meter_id)
        (
            cost_anchor_dt,
            _cost_anchor_state,
            cost_anchor_sum,
        ) = await async_get_highest_sum_stat(self.hass, cost_stat_id)
        if cost_anchor_sum is None or cost_anchor_sum <= 0.01 or cost_anchor_dt is None:
            return
        cost_metadata = get_cost_statistic_metadata(
            self.meter,
            statistic_id=cost_stat_id,
            currency=self.hass.config.currency or "USD",
        )
        _LOGGER.warning(
            "Cost stat carry-forward repair for %s: "
            "max_cost_sum=%.4f (at %s) — carrying forward through %s",
            cost_stat_id,
            cost_anchor_sum,
            cost_anchor_dt,
            last_stat_time,
        )
        await async_write_carry_forward_stats(
            self.hass,
            self.meter,
            cost_stat_id,
            None,
            from_dt=cost_anchor_dt,
            through_dt=last_stat_time,
            carry_state=cost_anchor_sum,
            carry_sum=cost_anchor_sum,
            metadata=cost_metadata,
        )

    async def _resolve_effective_last_imported_time(
        self,
    ) -> tuple[datetime.datetime | None, float | None, float | None]:
        """Pick a safe baseline, favoring recorder statistics if a gap exists.

        Returns (effective_last_time, last_stat_reading, last_stat_sum) so
        callers can restore entity state from the DB when no new API data is
        available (e.g., immediately after a manual historical import service
        call) and can also write the current-hour anchor unconditionally.
        """
        (
            last_stat_time,
            last_stat_reading_raw,
            last_stat_sum,
        ) = await get_last_imported_stat(
            self.hass,
            self.meter,
            statistic_id=self._statistic_id,
        )
        last_stat_reading: float | None = (
            float(last_stat_reading_raw) if last_stat_reading_raw is not None else None
        )
        effective_last_time = self._last_imported_time
        consumption_repaired = False

        if last_stat_time is None and effective_last_time is not None:
            # DB is empty (e.g. after delete_statistics) but we still have a
            # stale in-memory timestamp.  Reset so the next import re-processes
            # all available API data from scratch.
            _LOGGER.warning(
                "Statistics table is empty but in-memory last_imported_time=%s "
                "— resetting to None so full re-import can proceed",
                effective_last_time,
            )
            self._last_imported_time = None
            effective_last_time = None
        elif last_stat_time is not None and (
            effective_last_time is None or last_stat_time < effective_last_time
        ):
            # DB lags behind in-memory timestamp — use the DB value so we
            # don't skip data that was never actually committed.
            _LOGGER.warning(
                "Detected statistics gap: resetting last_imported_time from %s to %s",
                effective_last_time,
                last_stat_time,
            )
            self._last_imported_time = last_stat_time
            effective_last_time = last_stat_time
        elif (
            last_stat_time is not None
            and effective_last_time is not None
            and last_stat_time > effective_last_time
        ):
            (
                effective_last_time,
                last_stat_reading,
                last_stat_sum,
                consumption_repaired,
            ) = await self._repair_db_ahead_baseline(
                last_stat_time,
                effective_last_time,
                last_stat_sum,
            )

        # Sum monotonicity check — catches post-restart corruption where the
        # compiler resets the LTS chain to sum≈0 even though last_stat_time ==
        # effective_last_time (so the "DB ahead" branch never fires).
        if last_stat_time is not None and last_stat_sum is not None:
            (
                new_elt,
                new_reading,
                new_sum,
                repaired,
            ) = await self._repair_sum_monotonicity(last_stat_time, last_stat_sum)
            if repaired:
                effective_last_time = new_elt
                last_stat_reading = new_reading
                last_stat_sum = new_sum
                consumption_repaired = True

        if (
            consumption_repaired
            and self._price_entity_id
            and last_stat_time is not None
        ):
            await self._repair_cost_stat(last_stat_time)

        return effective_last_time, last_stat_reading, last_stat_sum

    async def _handle_update_async(self, latest_data: pyonwater.DataPoint) -> None:
        """Handle imports and state updates with gap-aware baselines."""
        if self._import_lock.locked():
            _LOGGER.debug(
                "Skipping import; previous import still running for %s",
                self.meter.meter_id,
            )
            return

        async with self._import_lock:
            await self._handle_update_locked(latest_data)

    async def _handle_update_locked(self, latest_data: pyonwater.DataPoint) -> None:
        """Handle import and state update while holding the import lock."""
        (
            effective_last_time,
            last_stat_reading,
            _,
        ) = await self._resolve_effective_last_imported_time()

        # Import new historical data points with proper timestamps
        self._last_historical_data = filter_newer_data(
            self.meter.last_historical_data,
            effective_last_time,
        )

        # Baseline overshoot recovery: if the import baseline (set by a
        # previous carry-forward repair) is AHEAD of the latest available API
        # data, filter_newer_data drops every point — the coordinator poll can
        # never make progress until the API catches up to that future timestamp.
        # Detect this and reset the baseline so real data can be written now.
        # centralized_import_statistics anchors on existing DB rows, so it will
        # correctly compute cumulative sums even when starting from the
        # beginning of the available window.
        all_api_data = self.meter.last_historical_data
        if (
            len(self._last_historical_data) == 0
            and all_api_data
            and effective_last_time is not None
            and all_api_data[-1].dt < effective_last_time
        ):
            _LOGGER.warning(
                "Import baseline overshoot for %s: baseline=%s is ahead of "
                "latest API data=%s (carry-forward rows extend past available "
                "data). Resetting baseline to re-import available data so "
                "carry-forward rows are overwritten with real consumption.",
                self.meter.meter_id,
                effective_last_time,
                all_api_data[-1].dt,
            )
            effective_last_time = None
            self._last_imported_time = None
            self._last_historical_data = filter_newer_data(all_api_data, None)

        if len(self._last_historical_data) == 0:
            # No new API data on this poll.  Sync entity state from the DB
            # whenever it diverges from the last recorded statistic.  This
            # handles two cases:
            #   1. First-time initialisation: entity native_value is None
            #      (unavailable) immediately after the import service call.
            #   2. Post-purge resync: purge_entities wiped the states table
            #      but left the in-memory restored value (e.g. 204356.9)
            #      behind while the DB correctly shows a higher reading
            #      (e.g. 204397.7). Without this check the stale value is
            #      re-written to the states table, causing the History hybrid
            #      view to show a spurious TOTAL_INCREASING drop.
            if (
                last_stat_reading is not None
                and self._attr_native_value != last_stat_reading
            ):
                _LOGGER.info(
                    "Entity state (%s) diverges from last DB stat (%s); syncing",
                    self._attr_native_value,
                    last_stat_reading,
                )
                self._attr_native_value = last_stat_reading
                self._attr_available = True
                self.async_write_ha_state()
            else:
                _LOGGER.debug(
                    "No new points since last import at %s; latest API data is from %s"
                    " — skipping state update",
                    effective_last_time,
                    latest_data.dt,
                )
        else:
            _LOGGER.info(
                "%d new points to import (from %s to %s)",
                len(self._last_historical_data),
                self._last_historical_data[0].dt,
                self._last_historical_data[-1].dt,
            )
            import_result = await centralized_import_statistics(
                self.hass,
                self.meter,
                self._last_historical_data,
                self._statistic_id,
                self._statistic_name,
                wait_for_commit=True,
                price_per_unit=self._resolve_price_per_unit(),
                currency=self.hass.config.currency or "USD",
            )
            imported_time: datetime.datetime = self._last_historical_data[-1].dt
            self._last_imported_time = imported_time

            # Seal any carry-forward rows that exist beyond our freshly
            # imported endpoint.  Without this, a later import that overlaps
            # those rows can trigger HA's sum-adjustment mechanism, shifting
            # the carry-forward sums downward and producing a spurious
            # negative delta in the Energy Dashboard on the next hourly
            # statistics compiler run.
            if import_result is not None:
                _, last_import_state, last_import_sum = import_result
                db_tip_time, _, _ = await get_last_imported_stat(
                    self.hass,
                    self.meter,
                    statistic_id=self._statistic_id,
                )
                if db_tip_time is not None and db_tip_time > imported_time:
                    _LOGGER.debug(
                        "Sealing carry-forward rows for %s: %s → %s "
                        "(state=%.4f, sum=%.4f)",
                        self.meter.meter_id,
                        imported_time,
                        db_tip_time,
                        last_import_state,
                        last_import_sum,
                    )
                    await async_write_carry_forward_stats(
                        self.hass,
                        self.meter,
                        self._statistic_id,
                        self._statistic_name,
                        from_dt=imported_time,
                        through_dt=db_tip_time,
                        carry_state=last_import_state,
                        carry_sum=last_import_sum,
                    )

            # Invalidate the cached_property so async_write_ha_state picks up
            # the new reading returned by meter_info.reading.model_dump()
            vars(self).pop("extra_state_attributes", None)
            self._state = self._last_historical_data[-1]
            self._attr_native_value = self._state.reading
            _LOGGER.info(
                "New data received — updated state to %s (value: %s)",
                self._state.dt,
                self._attr_native_value,
            )
            self.async_write_ha_state()

        # Note: the previous "current-hour LTS anchor" write was removed.
        # It caused HA's hourly statistics compiler to fail with UniqueViolation
        # on every hourly run because async_import_statistics writes directly to
        # the statistics table but does NOT update statistics_runs (HA's internal
        # bookkeeping).  The compiler therefore always sees the period as
        # uncompiled, tries to INSERT, finds our row, and rolls back the entire
        # ~780-entity batch.  Correct LTS values are instead guaranteed by the
        # post-import upsert in centralized_import_statistics and by the
        # diverge-from-DB entity-state sync above.

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        listener = self.coordinator.async_add_listener(self._state_update)
        self.async_on_remove(listener)

        # Always attempt to restore last known state so the entity is not
        # unavailable after an HA restart while waiting for the next fresh
        # API data chunk (which may be hours away).
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unavailable", "unknown", None):
            try:
                self._attr_native_value = float(last_state.state)
                self._attr_available = True
                _LOGGER.debug(
                    "Restored last known state for %s: %s",
                    self.meter.meter_id,
                    self._attr_native_value,
                )
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "Could not restore last state '%s' for %s — waiting for live data",
                    last_state.state,
                    self.meter.meter_id,
                )

        # Immediately reconcile with the last recorded LTS value before HA's
        # entity platform writes state to the database.  A stale restored value
        # would be committed to the states table, then picked up by the 5-min
        # short-term compiler and the hourly LTS compiler, producing wrong
        # cumulative sums that persist in History for up to 10 days AND shift
        # the filter_newer_data baseline causing subsequent imports to ingest
        # duplicate/incorrect data.  Correcting here — before async_write_ha_state
        # is called for the first time — ensures the states table never sees
        # the stale value at all.
        try:
            _, last_stat_reading, _ = await get_last_imported_stat(
                self.hass,
                self.meter,
                statistic_id=self._statistic_id,
            )
            if last_stat_reading is None:
                _LOGGER.debug(
                    "Startup reconcile for %s: no LTS stat in DB "
                    "(first run or statistics cleared) — keeping restored state (%s)",
                    self.meter.meter_id,
                    self._attr_native_value,
                )
            elif self._attr_native_value != last_stat_reading:
                _LOGGER.info(
                    "Startup reconcile for %s: restored state (%s) diverges from "
                    "last DB stat (%s) — correcting before first state write",
                    self.meter.meter_id,
                    self._attr_native_value,
                    last_stat_reading,
                )
                self._attr_native_value = last_stat_reading
                self._attr_available = True
            else:
                _LOGGER.debug(
                    "Startup reconcile for %s: restored state (%s) matches "
                    "last DB stat — no correction needed",
                    self.meter.meter_id,
                    self._attr_native_value,
                )
        except RuntimeError:
            # get_instance() or async_add_executor_job() raises RuntimeError
            # when the recorder integration has not finished initialising yet
            # (common during early startup).  The diverge check in
            # _handle_update_locked provides a second line of defence on the
            # first coordinator poll (~15 min).
            _LOGGER.debug(
                "Startup reconcile for %s: recorder not yet initialised "
                "— diverge check in coordinator will cover this",
                self.meter.meter_id,
            )
        except OSError as err:
            # Low-level I/O or socket error — DB connection not yet established
            # or lost between HA start and the first recorder query.
            _LOGGER.debug(
                "Startup reconcile for %s: DB connection error (%s) "
                "— diverge check in coordinator will cover this",
                self.meter.meter_id,
                err,
            )
        except SQLAlchemyError as err:
            # SQLAlchemy-level error (e.g. pool exhausted, schema mismatch,
            # deadlock) that was not already surfaced as an OSError.  Log at
            # WARNING so it surfaces in the log without being fatal.
            # The diverge check in _handle_update_locked still provides a
            # second line of defence on the first coordinator poll (~15 min).
            _LOGGER.warning(
                "Startup reconcile for %s: DB error querying last stat: %s "
                "— diverge check in coordinator will cover this",
                self.meter.meter_id,
                err,
            )

        # Run the carry-forward repair at startup, unconditionally and
        # independently of the coordinator.  If the hourly statistics compiler
        # wrote sum=0 rows while the entity was offline (the -N gal Energy
        # Dashboard symptom), those rows must be overwritten NOW — before the
        # first state write AND without waiting for the coordinator to succeed
        # (which may fail with a transient API error and not retry for 15 min).
        try:
            await self._resolve_effective_last_imported_time()
        except (RuntimeError, OSError, SQLAlchemyError) as err:
            _LOGGER.debug(
                "Startup carry-forward check for %s skipped: %s "
                "— will retry on first coordinator poll",
                self.meter.meter_id,
                err,
            )


class EyeOnWaterTempSensor(SensorEntity):
    """Representation of an EyeOnWater temperature sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_should_poll = False

    def __init__(
        self,
        meter: pyonwater.Meter,
        coordinator: DataUpdateCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()
        self.coordinator = coordinator
        self.meter = meter
        self._uuid = normalize_id(meter.meter_uuid)
        self._id = normalize_id(meter.meter_id)

        self._attr_unique_id = f"{self._uuid}_temperature"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._uuid)},
            name=f"{WATER_METER_NAME} {self._id}",
            model=self.meter.meter_info.reading.model,
            manufacturer=self.meter.meter_info.reading.customer_name,
            hw_version=self.meter.meter_info.reading.hardware_version,
            sw_version=self.meter.meter_info.reading.firmware_version,
        )

    @cached_property
    def native_value(self) -> float | None:
        """Get native value."""
        if (
            self.meter.meter_info.sensors
            and self.meter.meter_info.sensors.endpoint_temperature
        ):
            temp = self.meter.meter_info.sensors.endpoint_temperature
            return cast("float | None", temp.seven_day_min)

        return None

    @callback
    def _state_update(self) -> None:
        """Call when the coordinator has an update."""
        # Invalidate the cached_property so async_write_ha_state reads fresh data
        vars(self).pop("native_value", None)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        self.async_on_remove(self.coordinator.async_add_listener(self._state_update))
