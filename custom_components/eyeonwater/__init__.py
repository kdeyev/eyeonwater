"""EyeOnWater integration."""

import asyncio
import functools
import logging
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import debounce
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dtutil
from pyonwater import AggregationLevel, EyeOnWaterAPIError, EyeOnWaterAuthError, Meter

from .config_flow import create_account_from_config
from .const import (
    CONF_PRICE_ENTITY,
    DATA_COORDINATOR,
    DATA_SMART_METER,
    DEBOUNCE_COOLDOWN,
    DOMAIN,
    IMPORT_HISTORICAL_DATA_DAYS_DEFAULT,
    IMPORT_HISTORICAL_DATA_DAYS_NAME,
    IMPORT_HISTORICAL_DATA_SERVICE_NAME,
    MAX_VIOLATION_LOG_DISPLAY,
    READ_METER_SERVICE_NAME,
    REPLAY_SCENARIO_SERVICE_NAME,
    RESET_STATISTICS_CONFIRM_NAME,
    RESET_STATISTICS_SERVICE_NAME,
    SCAN_INTERVAL,
    VALIDATE_MONOTONIC_SERVICE_NAME,
    WATER_METER_NAME,
)
from .coordinator import EyeOnWaterData
from .statistic_helper import (
    centralized_import_statistics,
    get_entity_statistic_id,
)
from .statistics_tools import (
    delete_statistics,
    resolve_statistic_id,
    validate_monotonic_sums,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(_hass: HomeAssistant, _config: dict[str, Any]) -> bool:
    """Set up the EyeOnWater component."""
    return True


def _resolve_price_per_unit(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> tuple[float | None, str]:
    """Return (price_per_unit, currency) from the configured price entity, if any.

    Reads the live state of the entity stored in the ``price_entity_id`` config
    entry option.  Returns ``(None, currency)`` when no entity is configured,
    or the entity is unavailable / non-numeric.
    """
    currency: str = hass.config.currency or "USD"
    price_entity_id: str = (entry.options.get(CONF_PRICE_ENTITY) or "").strip()
    if not price_entity_id:
        return None, currency
    state_obj = hass.states.get(price_entity_id)
    if state_obj is None or state_obj.state in ("unavailable", "unknown"):
        _LOGGER.warning(
            "Price entity '%s' unavailable — cost statistics skipped for this import",
            price_entity_id,
        )
        return None, currency
    try:
        price = float(state_obj.state)
    except (ValueError, TypeError):
        _LOGGER.warning(
            "Price entity '%s' state '%s' is not numeric — cost statistics skipped",
            price_entity_id,
            state_obj.state,
        )
        return None, currency
    if price <= 0:
        _LOGGER.warning(
            "Price entity '%s' state '%s' is zero/negative — cost statistics skipped",
            price_entity_id,
            state_obj.state,
        )
        return None, currency
    return price, currency


async def _async_update_data(
    eye_on_water_data: EyeOnWaterData,
) -> EyeOnWaterData:
    _LOGGER.info("Coordinator refresh triggered - Fetching latest data")
    await eye_on_water_data.read_meters(days_to_load=3)
    _LOGGER.info("Coordinator refresh complete")
    return eye_on_water_data


def _build_coordinator(
    hass: HomeAssistant,
    eye_on_water_data: EyeOnWaterData,
) -> DataUpdateCoordinator[EyeOnWaterData]:
    return DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="EyeOnWater",
        update_method=functools.partial(_async_update_data, eye_on_water_data),
        update_interval=SCAN_INTERVAL,
        request_refresh_debouncer=debounce.Debouncer(
            hass,
            _LOGGER,
            cooldown=DEBOUNCE_COOLDOWN,
            immediate=True,
        ),
    )


async def _async_import_historical_service(
    call: ServiceCall,
    eye_on_water_data: EyeOnWaterData,
    coordinator: DataUpdateCoordinator[EyeOnWaterData],
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    # Get parameters: days (required/default)
    days: int | None = call.data.get(IMPORT_HISTORICAL_DATA_DAYS_NAME)
    force_overwrite = call.data.get("force_overwrite", False)
    purge_states = call.data.get("purge_states", False)

    # Default days if not provided
    if not days:
        days = IMPORT_HISTORICAL_DATA_DAYS_DEFAULT
        _LOGGER.info("Service handler: using default %s days", days)

    _LOGGER.info(
        "Service handler: importing %s days of historical data "
        "(force_overwrite=%s, purge_states=%s)",
        days,
        force_overwrite,
        purge_states,
    )

    price_per_unit, currency = _resolve_price_per_unit(hass, entry)

    await eye_on_water_data.import_historical_data(
        days,
        force_overwrite=force_overwrite,
        purge_states=purge_states,
        price_per_unit=price_per_unit,
        currency=currency,
    )
    _LOGGER.info("Service handler: requesting coordinator refresh")
    await coordinator.async_request_refresh()
    _LOGGER.info("Service handler: complete")


def _resolve_replay_meter_id(
    call: ServiceCall,
    meters_snapshot: list[Meter],
) -> str | None:
    meter_id = call.data.get("meter_id")
    entity_id = call.data.get("entity_id")
    if not meter_id and entity_id and entity_id.startswith("sensor.water_meter_"):
        meter_id = entity_id.replace("sensor.water_meter_", "")
        meter_id = meter_id.removesuffix("_statistic")

    if meter_id:
        # Validate that the resolved meter_id exists in snapshot
        available_meter_ids = [m.meter_id for m in meters_snapshot]
        if meter_id not in available_meter_ids:
            _LOGGER.error(
                "Replay real payloads: meter %s not found; available meters: %s",
                meter_id,
                available_meter_ids,
            )
            return None
        return meter_id

    if len(meters_snapshot) == 1:
        meter_id = meters_snapshot[0].meter_id
        _LOGGER.info("Replay real payloads: defaulting meter_id to %s", meter_id)
        return meter_id

    _LOGGER.error(
        "Replay real payloads requires meter_id when multiple meters exist",
    )
    return None


def _parse_replay_params(
    call: ServiceCall,
) -> tuple[datetime, datetime, AggregationLevel] | None:
    start_date_str = call.data.get("start_date")
    end_date_str = call.data.get("end_date")
    aggregation_str = call.data.get("aggregation", "HOURLY")

    if not start_date_str or not end_date_str:
        _LOGGER.error("Replay real payloads: start_date and end_date are required")
        return None

    try:
        start_date = dtutil.parse_datetime(start_date_str)
        end_date = dtutil.parse_datetime(end_date_str)
    except ValueError:
        _LOGGER.exception("Replay real payloads: invalid date format")
        return None

    # Validate all date/timezone constraints
    if start_date is None or end_date is None:
        _LOGGER.error("Replay real payloads: start_date and end_date must be valid")
        return None

    # If dates are naive (no timezone), assume Home Assistant's local timezone
    if start_date.tzinfo is None:
        start_date = dtutil.as_local(start_date)
        _LOGGER.debug(
            "Replay real payloads: start_date was naive, converted to local: %s",
            start_date,
        )
    if end_date.tzinfo is None:
        end_date = dtutil.as_local(end_date)
        _LOGGER.debug(
            "Replay real payloads: end_date was naive, converted to local: %s",
            end_date,
        )

    # Validate aggregation level
    agg_names = ["HOURLY"]
    if aggregation_str not in agg_names:
        _LOGGER.error(
            "Replay real payloads: invalid aggregation level: %s. Valid values: %s",
            aggregation_str,
            ", ".join(agg_names),
        )
        return None

    aggregation = AggregationLevel[aggregation_str]
    return start_date, end_date, aggregation


async def _replay_range(
    hass: HomeAssistant,
    eye_on_water_data: EyeOnWaterData,
    meter_id: str,
    aggregation: AggregationLevel,
    start_date: datetime,
    end_date: datetime,
    price_per_unit: float | None = None,
    currency: str = "USD",
) -> tuple[int, int]:
    meter = next(
        (m for m in eye_on_water_data.meters if m.meter_id == meter_id),
        None,
    )
    if meter is None:
        _LOGGER.error("Replay real payloads: meter %s not found", meter_id)
        return 0, 0

    # Calculate number of days to load (inclusive of both start and end)
    days_to_load = int((end_date - start_date).days) + 1

    try:
        points: list[Any] = await meter.read_historical_data(
            client=eye_on_water_data.client,
            days_to_load=days_to_load,
            aggregation=aggregation,
        )

        if not points:
            _LOGGER.info(
                "Replay real payloads: no data found for date range %s to %s",
                start_date.date(),
                end_date.date(),
            )
            return 0, 0

        _LOGGER.info(
            "Replay real payloads: fetched %d points for date range %s to %s",
            len(points),
            start_date.date(),
            end_date.date(),
        )
        total_points = len(points)

        statistic_id = get_entity_statistic_id(meter_id)
        meter_name = f"{WATER_METER_NAME} {meter_id}"

        await centralized_import_statistics(
            hass,
            meter,
            points,
            statistic_id,
            meter_name,
            wait_for_commit=True,
            price_per_unit=price_per_unit,
            currency=currency,
        )
        total_imported = len(points)

    except asyncio.CancelledError:
        _LOGGER.warning(
            "Replay cancelled for date range %s to %s",
            start_date.date(),
            end_date.date(),
        )
        raise
    except (EyeOnWaterAuthError, asyncio.TimeoutError) as error:
        _LOGGER.warning(
            "Replay real payloads: failed to fetch data for date range: %s",
            error,
        )
        return 0, 0

    # Return success if no exception occurred
    return total_points, total_imported


async def _async_replay_scenario(
    call: ServiceCall,
    hass: HomeAssistant,
    eye_on_water_data: EyeOnWaterData,
    coordinator: DataUpdateCoordinator[EyeOnWaterData],
    entry: ConfigEntry,
) -> None:
    """Replay real payloads from specific dates through the import pipeline.

    Snapshots meter list at call time to avoid race conditions during
    long-running replay operations.
    """
    _LOGGER.info("Replay real payloads: validating parameters...")

    # Snapshot meter list to avoid race conditions with coordinator updates
    meters_snapshot = list(eye_on_water_data.meters)

    params = _parse_replay_params(call)
    if not params:
        _LOGGER.error(
            "Replay real payloads failed: check start_date, end_date, "
            "and aggregation parameters. See service documentation for examples.",
        )
        return

    start_date, end_date, aggregation = params
    meter_id = _resolve_replay_meter_id(call, meters_snapshot)
    if not meter_id:
        _LOGGER.error(
            "Replay real payloads failed: unable to resolve meter. "
            "Provide meter_id, entity_id, or ensure single meter account.",
        )
        return

    _LOGGER.info(
        "Replay real payloads: fetching %s data for meter=%s from %s to %s",
        aggregation.value,
        meter_id,
        start_date,
        end_date,
    )

    price_per_unit, currency = _resolve_price_per_unit(hass, entry)

    total_points, total_imported = await _replay_range(
        hass,
        eye_on_water_data,
        meter_id,
        aggregation,
        start_date,
        end_date,
        price_per_unit=price_per_unit,
        currency=currency,
    )

    _LOGGER.info(
        "Replay real payloads: complete (fetched %d points, imported %d)",
        total_points,
        total_imported,
    )

    # Give the database a moment to commit and refresh internal caches
    await asyncio.sleep(0.5)

    # Refresh coordinator to pick up the newly imported statistics
    _LOGGER.info("Replay real payloads: requesting coordinator refresh")
    await coordinator.async_request_refresh()
    _LOGGER.info("Replay real payloads: refresh complete")


async def _async_validate_monotonic(
    call: ServiceCall,
    hass: HomeAssistant,
) -> None:
    statistic_id = resolve_statistic_id(
        statistic_id=call.data.get("statistic_id"),
        entity_id=call.data.get("entity_id"),
        meter_id=call.data.get("meter_id"),
    )
    if not statistic_id:
        _LOGGER.error(
            "validate_monotonic validation requires one of: "
            "statistic_id (e.g., sensor.water_meter_abc123), "
            "entity_id (e.g., sensor.water_meter_abc123), or "
            "meter_id (e.g., 12345). Check service documentation for examples.",
        )
        return

    hours = call.data.get("hours")
    full_scan = call.data.get("full_scan", False)

    results = await validate_monotonic_sums(
        hass,
        statistic_id,
        hours=hours,
        full_scan=full_scan,
    )

    violations = results.violations
    checked = results.checked
    if not violations:
        _LOGGER.info(
            "Monotonic validation OK for %s (checked %d rows)",
            statistic_id,
            checked,
        )
        return

    _LOGGER.warning(
        "Monotonic validation found %d violations for %s (checked %d rows)",
        len(violations),
        statistic_id,
        checked,
    )
    for violation in violations[:MAX_VIOLATION_LOG_DISPLAY]:
        _LOGGER.warning(
            "Violation at %s: %.2f -> %.2f (delta %.2f)",
            violation.start,
            violation.previous_sum,
            violation.current_sum,
            violation.delta,
        )
    if len(violations) > MAX_VIOLATION_LOG_DISPLAY:
        _LOGGER.warning(
            "  ... and %d more violations not shown",
            len(violations) - MAX_VIOLATION_LOG_DISPLAY,
        )


async def _async_read_meter(
    call: ServiceCall,
    eye_on_water_data: EyeOnWaterData,
    coordinator: DataUpdateCoordinator[EyeOnWaterData],
) -> None:
    """Trigger an on-demand meter info read for one or all meters.

    Calls read_meter_info (the SEARCH endpoint) on the target meter(s) to
    fetch the current totalizer value and device attributes.  Historical data
    is NOT re-fetched — use import_historical_data for that.
    """
    meter_id_filter: str | None = call.data.get("meter_id")
    entity_id: str | None = call.data.get("entity_id")

    # Resolve meter_id from entity_id if provided
    if (
        not meter_id_filter
        and entity_id
        and entity_id.startswith("sensor.water_meter_")
    ):
        meter_id_filter = entity_id.replace("sensor.water_meter_", "")
        meter_id_filter = meter_id_filter.removesuffix("_statistic")

    meters_snapshot = list(eye_on_water_data.meters)
    targets = (
        [m for m in meters_snapshot if m.meter_id == meter_id_filter]
        if meter_id_filter
        else meters_snapshot
    )

    if meter_id_filter and not targets:
        _LOGGER.error(
            "read_meter: meter '%s' not found; available meters: %s",
            meter_id_filter,
            [m.meter_id for m in meters_snapshot],
        )
        return

    _LOGGER.info(
        "read_meter: refreshing meter info for %s",
        [m.meter_id for m in targets],
    )

    for meter in targets:
        try:
            await meter.read_meter_info(client=eye_on_water_data.client)
            _LOGGER.info(
                "read_meter: successfully read meter %s",
                meter.meter_id,
            )
        except EyeOnWaterAuthError:
            _LOGGER.exception(
                "read_meter: authentication error for meter %s",
                meter.meter_id,
            )
            return
        except EyeOnWaterAPIError:
            _LOGGER.exception(
                "read_meter: API error for meter %s",
                meter.meter_id,
            )

    _LOGGER.info("read_meter: requesting coordinator refresh")
    await coordinator.async_request_refresh()
    _LOGGER.info("read_meter: complete")


async def _async_reset_statistics(
    call: ServiceCall,
    hass: HomeAssistant,
) -> None:
    confirm = call.data.get(RESET_STATISTICS_CONFIRM_NAME)
    if confirm != "DELETE":
        _LOGGER.error(
            "reset_statistics: confirmation required - set confirm='DELETE' "
            "to proceed. Example: service: eyeonwater.reset_statistics "
            "data: {{ confirm: DELETE, meter_id: '12345' }}",
        )
        return

    statistic_id = resolve_statistic_id(
        statistic_id=call.data.get("statistic_id"),
        entity_id=call.data.get("entity_id"),
        meter_id=call.data.get("meter_id"),
    )
    if not statistic_id:
        _LOGGER.error(
            "reset_statistics requires one of: "
            "statistic_id (e.g., sensor.water_meter_abc123), "
            "entity_id (e.g., sensor.water_meter_abc123), or "
            "meter_id (e.g., 12345).",
        )
        return

    _LOGGER.warning(
        "reset_statistics: DELETING ALL statistics for %s",
        statistic_id,
    )
    deleted = await delete_statistics(hass, statistic_id)
    _LOGGER.warning(
        "reset_statistics: deleted %d rows for %s",
        deleted,
        statistic_id,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eye On Water from a config entry."""
    try:
        _LOGGER.info("Setting up EyeOnWater entry: %s", entry.entry_id)
        account = create_account_from_config(hass, entry.data)
        _LOGGER.info("Created account from config")
        eye_on_water_data = EyeOnWaterData(
            hass,
            account,
        )
        _LOGGER.info("Instantiated EyeOnWaterData coordinator")
        try:
            await eye_on_water_data.client.authenticate()
            _LOGGER.info("Successfully authenticated with EyeOnWater")
        except EyeOnWaterAuthError:
            _LOGGER.exception("Username or password was not accepted")
            return False
        except asyncio.TimeoutError as error:
            _LOGGER.exception("Timeout during authentication")
            raise ConfigEntryNotReady from error

        try:
            await eye_on_water_data.setup()
            _LOGGER.info("Successfully fetched meters")
        except Exception:
            _LOGGER.exception("Fetching meters failed")
            raise
    except Exception as error:
        _LOGGER.exception("Error in async_setup_entry")
        raise ConfigEntryNotReady from error

    _LOGGER.info("Building coordinator")
    coordinator = _build_coordinator(hass, eye_on_water_data)

    _LOGGER.info("Storing coordinator and data in hass.data")
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        DATA_SMART_METER: eye_on_water_data,
    }

    _LOGGER.info("Creating async refresh task")
    hass.async_create_task(coordinator.async_refresh())

    _LOGGER.info("Setting up platform entities")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("Registering service handlers")
    hass.services.async_register(
        DOMAIN,
        IMPORT_HISTORICAL_DATA_SERVICE_NAME,
        functools.partial(
            _async_import_historical_service,
            eye_on_water_data=eye_on_water_data,
            coordinator=coordinator,
            hass=hass,
            entry=entry,
        ),
    )

    hass.services.async_register(
        DOMAIN,
        REPLAY_SCENARIO_SERVICE_NAME,
        functools.partial(
            _async_replay_scenario,
            hass=hass,
            eye_on_water_data=eye_on_water_data,
            coordinator=coordinator,
            entry=entry,
        ),
    )

    hass.services.async_register(
        DOMAIN,
        VALIDATE_MONOTONIC_SERVICE_NAME,
        functools.partial(
            _async_validate_monotonic,
            hass=hass,
        ),
    )

    hass.services.async_register(
        DOMAIN,
        RESET_STATISTICS_SERVICE_NAME,
        functools.partial(
            _async_reset_statistics,
            hass=hass,
        ),
    )

    hass.services.async_register(
        DOMAIN,
        READ_METER_SERVICE_NAME,
        functools.partial(
            _async_read_meter,
            eye_on_water_data=eye_on_water_data,
            coordinator=coordinator,
        ),
    )

    _LOGGER.info("Successfully completed setup")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
