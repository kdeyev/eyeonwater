"""EyeOnWater coordinator."""

import logging
from typing import TYPE_CHECKING

from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from pyonwater import (
    Account,
    Client,
    DataPoint,
    Meter,
)

from .const import CONF_DISPLAY_UNIT, CONF_PREFER_NEW_SEARCH, CONF_UNIT_PRICE
from .statistic_helper import (
    convert_cost_statistic_data,
    convert_statistic_data,
    filter_newer_data,
    get_cost_statistic_metadata,
    get_ha_native_unit_of_measurement,
    get_last_imported_time,
    get_statistic_metadata,
    volume_conversion_factor,
)

if TYPE_CHECKING:
    import datetime

_LOGGER = logging.getLogger(__name__)


class EyeOnWaterData:
    """Manages coordinatation of API data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        account: Account,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the data coordintator."""
        self.account = account
        self._config_entry = config_entry
        websession = aiohttp_client.async_get_clientsession(hass)
        self.client = Client(websession, account)
        self.meters: list[Meter] = []
        self.hass = hass
        self._last_imported_times: dict[str, datetime.datetime | None] = {}

    async def setup(self) -> None:
        """Fetch all of the user's meters."""
        prefer_new_search = self._config_entry.options.get(
            CONF_PREFER_NEW_SEARCH,
            False,
        )
        _LOGGER.debug(
            "Setting up meters (prefer_new_search=%s)",
            prefer_new_search,
        )
        self.meters = await self.account.fetch_meters(
            self.client,
            prefer_new_search=prefer_new_search,
        )
        _LOGGER.debug("Discovered %i meter(s)", len(self.meters))

        for meter in self.meters:
            _LOGGER.debug(
                "Meter: id=%s, uuid=%s, unit=%s",
                meter.meter_id,
                meter.meter_uuid,
                meter.native_unit_of_measurement,
            )
            self._last_imported_times[meter.meter_id] = await get_last_imported_time(
                self.hass,
                meter,
            )

    async def read_meters(self, days_to_load: int = 3) -> list[Meter]:
        """Read each meter."""
        for meter in self.meters:
            try:
                await meter.read_meter_info(client=self.client)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning(
                    "Failed to refresh meter info for %s, using cached data: %s",
                    meter.meter_id,
                    exc,
                )

            try:
                await meter.read_historical_data(
                    client=self.client,
                    days_to_load=days_to_load,
                )
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning(
                    "Failed to read historical data for %s: %s",
                    meter.meter_id,
                    exc,
                )

            try:
                self._import_meter_statistics(meter)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning(
                    "Failed to import statistics for %s: %s",
                    meter.meter_id,
                    exc,
                )

        return self.meters

    def _get_display_unit(self) -> str | None:
        """Return configured display unit, or None for meter native."""
        return self._config_entry.options.get(CONF_DISPLAY_UNIT) or None

    def _get_volume_factor(self, meter: Meter) -> float:
        """Return conversion factor from meter native unit to display unit."""
        display_unit = self._get_display_unit()
        if not display_unit:
            return 1.0
        native_unit = get_ha_native_unit_of_measurement(
            meter.native_unit_of_measurement,
        )
        return volume_conversion_factor(native_unit, display_unit)

    def _import_meter_statistics(self, meter: Meter) -> None:
        """Filter and import new historical data points for a meter."""
        if not meter.last_historical_data:
            _LOGGER.debug("No historical data for meter %s", meter.meter_id)
            return

        last_imported = self._last_imported_times.get(meter.meter_id)
        new_data = filter_newer_data(meter.last_historical_data, last_imported)

        if not new_data:
            return

        _LOGGER.info(
            "%i data points will be imported for meter %s",
            len(new_data),
            meter.meter_id,
        )
        factor = self._get_volume_factor(meter)
        statistics = convert_statistic_data(new_data, factor)
        metadata = get_statistic_metadata(meter, self._get_display_unit())
        async_add_external_statistics(self.hass, metadata, statistics)

        self._import_cost_statistics(meter, new_data)

        self._last_imported_times[meter.meter_id] = new_data[-1].dt

    def _import_cost_statistics(
        self,
        meter: Meter,
        data: list[DataPoint],
    ) -> None:
        """Import cost statistics if unit_price is configured."""
        unit_price = self._config_entry.options.get(CONF_UNIT_PRICE)
        if not unit_price or unit_price <= 0:
            return

        currency = self.hass.config.currency
        if not currency:
            _LOGGER.warning("No currency configured in HA, skipping cost statistics")
            return

        cost_statistics = convert_cost_statistic_data(data, unit_price)
        cost_metadata = get_cost_statistic_metadata(meter, currency)
        async_add_external_statistics(self.hass, cost_metadata, cost_statistics)
        _LOGGER.info(
            "%i cost data points imported (price=%s %s)",
            len(cost_statistics),
            unit_price,
            currency,
        )

    async def import_historical_data(self, days: int) -> None:
        """Import historical data for all meters."""
        if days <= 0:
            _LOGGER.warning("import_historical_data called with days=%d; skipping", days)
            return

        for meter in self.meters:
            try:
                data = await meter.read_historical_data(
                    client=self.client,
                    days_to_load=days,
                )
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning(
                    "Failed to read historical data for meter %s: %s",
                    meter.meter_id,
                    exc,
                )
                continue

            if not data:
                _LOGGER.info("No historical data returned for meter %s", meter.meter_id)
                continue

            _LOGGER.info(
                "%i historical data points will be imported for meter %s",
                len(data),
                meter.meter_id,
            )
            try:
                factor = self._get_volume_factor(meter)
                statistics = convert_statistic_data(data, factor)
                metadata = get_statistic_metadata(meter, self._get_display_unit())
                async_add_external_statistics(self.hass, metadata, statistics)

                self._import_cost_statistics(meter, data)

                if data:
                    self._last_imported_times[meter.meter_id] = data[-1].dt
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning(
                    "Failed to import statistics for meter %s: %s",
                    meter.meter_id,
                    exc,
                )
