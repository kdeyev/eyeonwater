"""EyeOnWater coordinator."""

import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import UpdateFailed
from pyonwater import (
    Account,
    Client,
    EyeOnWaterAPIError,
    EyeOnWaterAuthError,
    Meter,
)

from .const import COST_STAT_SUFFIX, WATER_METER_NAME
from .statistic_helper import (
    async_delete_all_short_term_statistics,
    async_delete_entity_states,
    async_delete_statistics_after,
    centralized_import_statistics,
    get_entity_statistic_id,
    normalize_id,
)

_LOGGER = logging.getLogger(__name__)


class EyeOnWaterData:
    """Coordinates API data retrieval and refresh cycles."""

    def __init__(
        self,
        hass: HomeAssistant,
        account: Account,
    ) -> None:
        """Initialize the data coordinator."""
        self.account = account
        websession = aiohttp_client.async_get_clientsession(hass)
        self.client = Client(websession, account)
        self.meters: list[Meter] = []
        self.hass = hass

    async def setup(self) -> None:
        """Fetch all of the user's meters."""
        self.meters = await self.account.fetch_meters(self.client)
        _LOGGER.debug("Discovered %i meter(s)", len(self.meters))

    async def read_meters(self, days_to_load: int = 3) -> list[Meter]:
        """Read each meter and retain only new data since last import.

        Meters are read concurrently to improve performance with multiple meters.
        The meter list is immutable during this operation - list changes during
        reads are deferred until the next refresh cycle.
        """
        # Snapshot meter list to ensure consistent reads
        meters_snapshot = list(self.meters)

        # Create concurrent tasks for reading each meter
        tasks = [
            self._read_single_meter(meter, days_to_load) for meter in meters_snapshot
        ]

        # Execute all meter reads concurrently
        await asyncio.gather(*tasks)

        return self.meters

    async def _read_single_meter(
        self,
        meter: Meter,
        days_to_load: int,
    ) -> None:
        """Read a single meter from the API.

        Filtering to new-only data points is the sensor's responsibility;
        the coordinator's role is simply to fetch and store the full API
        payload.

        When the API returns an empty body ("") for one or more historical
        dates, older pyonwater versions raise EyeOnWaterAPIError (newer ones
        raise EyeOnWaterResponseIsEmpty, which is silently skipped inside the
        library).  To stay resilient regardless of which pyonwater version is
        installed, we detect the empty-response fingerprint in the error
        message and retry with a 1-day window so that at least today's data
        is fetched even if older dates are unavailable.

        Args:
            meter: The meter to read from the API.
            days_to_load: Number of days of historical data to retrieve.

        Raises:
            UpdateFailed: If API calls fail (re-raised from coordinator).

        """
        try:
            await meter.read_meter_info(client=self.client)
            await meter.read_historical_data(
                client=self.client,
                days_to_load=days_to_load,
            )
        except EyeOnWaterAuthError as error:
            raise UpdateFailed(error) from error
        except EyeOnWaterAPIError as error:
            error_str = str(error)
            # Older pyonwater versions raise EyeOnWaterAPIError (instead of the
            # newer EyeOnWaterResponseIsEmpty) when the API returns "" or "null"
            # for a date with no data.  This manifests as a "json_invalid" /
            # "EOF while parsing" Pydantic error.  Rather than failing the
            # entire coordinator cycle, fall back to a single-day fetch so we
            # can still collect today's data if it's available.
            if "json_invalid" in error_str or "EOF while parsing" in error_str:
                _LOGGER.warning(
                    "Historical data fetch for meter %s failed due to empty API "
                    "response on one or more dates (pyonwater version may not "
                    "include the empty-response fix). Retrying with 1-day "
                    "window to capture today's data. Error: %s",
                    meter.meter_id,
                    error,
                )
                try:
                    await meter.read_historical_data(
                        client=self.client,
                        days_to_load=1,
                    )
                except EyeOnWaterAPIError as fallback_error:
                    # Today also has no data yet — not a coordinator failure.
                    _LOGGER.warning(
                        "1-day fallback for meter %s also returned no data "
                        "(%s) — no new readings this cycle",
                        meter.meter_id,
                        fallback_error,
                    )
            else:
                raise UpdateFailed(error) from error

    async def import_historical_data(
        self,
        days: int,
        *,
        force_overwrite: bool = False,
        purge_states: bool = False,
        price_per_unit: float | None = None,
        currency: str = "USD",
    ) -> None:
        """Import historical data from the past N days.

        Args:
            days: Number of days of history to import
            force_overwrite: If True, reimport all data (overwrites existing)
            purge_states: If True, purge the entity's state history after import.
            price_per_unit: Rate in *currency* per unit-of-volume.  When set,
                a parallel cost LTS stat is also imported, enabling per-hour
                cost attribution via the Energy Dashboard ``stat_cost`` field.
            currency: ISO 4217 currency code for cost metadata (default "USD").

        """
        for meter in self.meters:
            try:
                _LOGGER.info("Updating meter info for %s", meter.meter_id)
                await meter.read_meter_info(client=self.client)
                _LOGGER.info("Meter %s info: reading=%s", meter.meter_id, meter.reading)

                _LOGGER.info(
                    "Reading %d days of historical data for %s",
                    days,
                    meter.meter_id,
                )
                data = await meter.read_historical_data(
                    client=self.client,
                    days_to_load=days,
                )
                _LOGGER.info(
                    "API returned %i data points (dates: %s to %s)",
                    len(data),
                    data[0].dt if data else None,
                    data[-1].dt if data else None,
                )

                # Log reading range before processing
                if data:
                    readings = [dp.reading for dp in data]
                    min_reading = min(readings)
                    max_reading = max(readings)
                    _LOGGER.info(
                        "Raw API reading range: min=%.2f, max=%.2f, "
                        "first=%.2f, last=%.2f",
                        min_reading,
                        max_reading,
                        readings[0],
                        readings[-1],
                    )

                # Log import intent (force_overwrite mode logs warning)
                if force_overwrite:
                    _LOGGER.warning(
                        "Force overwrite mode: importing all %i points "
                        "(may overwrite existing data)",
                        len(data),
                    )
                else:
                    _LOGGER.info("Importing %i historical data points", len(data))
                prepared_data = data

                if not prepared_data:
                    _LOGGER.info("No data to import for %s", meter.meter_id)
                    continue

                # Use centralized import helper - handles fresh last_db_sum from DB
                # and ensures monotonic consistency across all import sources
                statistic_id = get_entity_statistic_id(meter.meter_id)
                meter_name = f"{WATER_METER_NAME} {normalize_id(meter.meter_id)}"

                await centralized_import_statistics(
                    self.hass,
                    meter,
                    prepared_data,
                    statistic_id,
                    meter_name,
                    price_per_unit=price_per_unit,
                    currency=currency,
                )

                if purge_states:
                    cost_stat_id = f"{statistic_id}{COST_STAT_SUFFIX}"
                    _LOGGER.info(
                        "Purging stale statistics and state history for %s "
                        "(and cost entity %s) to prevent sum=0 contamination "
                        "beyond import range",
                        statistic_id,
                        cost_stat_id,
                    )
                    # Delete any LTS / short-term rows written by HA's recorder
                    # AFTER our last import point.  Those rows may carry sum=0
                    # (recorder restart artifact) and would show as a huge
                    # negative consumption bar in the Energy Dashboard.
                    last_import_dt = prepared_data[-1].dt
                    await async_delete_statistics_after(
                        self.hass,
                        statistic_id,
                        last_import_dt,
                    )
                    await async_delete_statistics_after(
                        self.hass,
                        cost_stat_id,
                        last_import_dt,
                    )
                    # The cost stat has no valid backing entity — all short-term
                    # rows are compiled from the EnergyCostSensor state, which
                    # oscillates between $0 and a correct value during startup.
                    # A state drop to $0 on a TOTAL_INCREASING entity renders as
                    # a negative bar in the History view even after the states
                    # table is cleaned.  Wipe every short-term row so the History
                    # view falls back to the correct LTS rows we just imported.
                    await async_delete_all_short_term_statistics(
                        self.hass,
                        cost_stat_id,
                    )
                    # Purge the states table for the meter entity so the chart
                    # doesn't blend sub-hourly states with LTS hour-bucket values.
                    await self.hass.services.async_call(
                        "recorder",
                        "purge_entities",
                        {"entity_id": [statistic_id], "keep_days": 0},
                        blocking=True,
                    )
                    # For the cost stat, HA's EnergyCostSensor (auto-created by
                    # the Energy Dashboard "current price" config) shares the
                    # same entity_id and writes $0 state entries to the states
                    # table on each rate/consumption update.  These accumulate
                    # between imports and show as "Source: History" $0 entries
                    # in the History hybrid view.
                    # We cannot use purge_entities here — it causes the
                    # EnergyCostSensor to immediately write a new $0 / last_reset=now
                    # entry on the next state restore.  Instead, do a direct SQL
                    # delete on the states table which bypasses entity machinery.
                    await async_delete_entity_states(self.hass, cost_stat_id)
                    _LOGGER.info(
                        "State history and stale statistics purged for %s "
                        "(cost entity %s: states table cleaned via direct SQL)",
                        statistic_id,
                        cost_stat_id,
                    )

            except (EyeOnWaterAPIError, EyeOnWaterAuthError):
                _LOGGER.exception("Failed to import historical data")
