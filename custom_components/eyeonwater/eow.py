"""EyeOnWater API integration."""
from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING, Any
import urllib.parse

from dateutil import parser
import pytz
from tenacity import retry, retry_if_exception_type

if TYPE_CHECKING:
    from aiohttp import ClientSession

AUTH_ENDPOINT = "account/signin"
DASHBOARD_ENDPOINT = "/dashboard/"
SEARCH_ENDPOINT = "/api/2/residential/new_search"
CONSUMPTION_ENDPOINT = "/api/2/residential/consumption?eow=True"

MEASUREMENT_GALLONS = "GAL"
MEASUREMENT_100_GALLONS = "100 GAL"
MEASUREMENT_10_GALLONS = "10 GAL"
MEASUREMENT_CF = ["CF", "CUBIC_FEET"]
MEASUREMENT_CCF = "CCF"
MEASUREMENT_KILOGALLONS = "KGAL"
MEASUREMENT_CUBICMETERS = ["CM", "CUBIC_METER"]

METER_UUID_FIELD = "meter_uuid"
READ_UNITS_FIELD = "units"
READ_AMOUNT_FIELD = "full_read"

TOKEN_EXPIRATION = datetime.timedelta(minutes=15)

_LOGGER = logging.getLogger(__name__)


class EyeOnWaterException(Exception):
    """Base exception for more specific exceptions to inherit from."""


class EyeOnWaterAuthError(EyeOnWaterException):
    """Exception for authentication failures.

    Either wrong username or wrong password.
    """


class EyeOnWaterRateLimitError(EyeOnWaterException):
    """Exception for reaching the ratelimit.

    Either too many login attempts or too many requests.
    """


class EyeOnWaterAuthExpired(EyeOnWaterException):
    """Exception for when a token is no longer valid."""


class EyeOnWaterAPIError(EyeOnWaterException):
    """General exception for unknown API responses."""


class EyeOnWaterResponseIsEmpty(EyeOnWaterException):
    """API answered correct but there is not content to parse."""


class Meter:
    """Class represents meter object."""

    meter_prefix = "var new_barInfo = "
    info_prefix = "AQ.Views.MeterPicker.meters = "

    def __init__(
        self,
        meter_uuid: str,
        meter_info: dict[str, Any],
        metric_measurement_system: bool,
    ) -> None:
        """Initialize the meter."""
        self.meter_uuid = meter_uuid
        self.meter_id = meter_info["meter_id"]

        self.meter_info = None

        self.metric_measurement_system = metric_measurement_system
        self.native_unit_of_measurement = (
            "m\u00b3" if self.metric_measurement_system else "gal"
        )
        self.reading_data = None

        self.last_historical_data = []

    async def read_meter(self, client: Client, days_to_load=3) -> dict[str, Any]:
        """Triggers an on-demand meter read and returns it when complete."""
        _LOGGER.debug("Requesting meter reading")

        query = {"query": {"terms": {"meter.meter_uuid": [self.meter_uuid]}}}
        data = await client.request(path=SEARCH_ENDPOINT, method="post", json=query)
        data = json.loads(data)
        meters = data["elastic_results"]["hits"]["hits"]
        if len(meters) > 1:
            msg = "More than one meter reading found"
            raise Exception(msg)

        self.meter_info = meters[0]["_source"]
        self.reading_data = self.meter_info["register_0"]

        try:
            historical_data = await self.get_historical_datas(
                days_to_load=days_to_load, client=client
            )
            if not self.last_historical_data:
                self.last_historical_data = historical_data
            elif (
                historical_data
                and historical_data[-1]["reading"]
                > self.last_historical_data[-1]["reading"]
            ):
                # Take newer data
                self.last_historical_data = historical_data
            elif historical_data[-1]["reading"] == self.last_historical_data[-1][
                "reading"
            ] and len(historical_data) > len(self.last_historical_data):
                # If it the same date - take more data
                self.last_historical_data = historical_data

        except EyeOnWaterResponseIsEmpty:
            self.last_historical_data = []

    @property
    def attributes(self):
        """Define attributes."""
        return self.meter_info

    def get_flags(self, flag) -> bool:
        """Define flags."""
        flags = self.reading_data["flags"]
        if flag not in flags:
            msg = f"Cannot find {flag} field"
            raise EyeOnWaterAPIError(msg)
        return flags[flag]

    @property
    def reading(self):
        """Returns the latest meter reading in gal."""
        reading = self.reading_data["latest_read"]
        if READ_UNITS_FIELD not in reading:
            msg = "Cannot find read units in reading data"
            raise EyeOnWaterAPIError(msg)
        read_unit = reading[READ_UNITS_FIELD]
        read_unit_upper = read_unit.upper()
        amount = float(reading[READ_AMOUNT_FIELD])
        amount = self.convert(read_unit_upper, amount)
        return amount

    def convert(self, read_unit_upper, amount):
        if self.metric_measurement_system:
            if read_unit_upper in MEASUREMENT_CUBICMETERS:
                pass
            else:
                raise EyeOnWaterAPIError(
                    f"Unsupported measurement unit: {read_unit_upper}"
                )
        else:
            if read_unit_upper == MEASUREMENT_KILOGALLONS:
                amount = amount * 1000
            elif read_unit_upper == MEASUREMENT_100_GALLONS:
                amount = amount * 100
            elif read_unit_upper == MEASUREMENT_10_GALLONS:
                amount = amount * 10
            elif read_unit_upper == MEASUREMENT_GALLONS:
                pass
            elif read_unit_upper == MEASUREMENT_CCF:
                amount = amount * 748.052
            elif read_unit_upper in MEASUREMENT_CF:
                amount = amount * 7.48052
            else:
                raise EyeOnWaterAPIError(
                    f"Unsupported measurement unit: {read_unit_upper}"
                )
        return amount

    async def get_historical_datas(self, days_to_load: int, client: Client):
        """Retrieve historical data for today and past N days."""

        today = datetime.datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        date_list = [today - datetime.timedelta(days=x) for x in range(0, days_to_load)]
        date_list.reverse()

        # TODO: identify missing days and request only missing dates.

        _LOGGER.info(
            f"requesting historical statistics for {self.meter_uuid} on {date_list}"
        )

        statistics = []

        for date in date_list:
            _LOGGER.info(
                f"requesting historical statistics for {self.meter_uuid} on {date}"
            )
            try:
                statistics += await self.get_historical_data(date=date, client=client)
            except EyeOnWaterResponseIsEmpty:
                continue

        return statistics

    async def get_historical_data(self, date: datetime, client: Client):
        """Retrieve the historical hourly water readings for a requested day"""

        if self.metric_measurement_system:
            units = "CM"
        else:
            units = self.native_unit_of_measurement.upper()

        query = {
            "params": {
                "source": "barnacle",
                "aggregate": "hourly",
                "units": units,
                "combine": "true",
                "perspective": "billing",
                "display_minutes": True,
                "display_hours": True,
                "display_days": True,
                "date": date.strftime("%m/%d/%Y"),
                "furthest_zoom": "hr",
                "display_weeks": True,
            },
            "query": {"query": {"terms": {"meter.meter_uuid": [self.meter_uuid]}}},
        }
        data = await client.request(
            path=CONSUMPTION_ENDPOINT, method="post", json=query
        )
        data = json.loads(data)

        key = f"{self.meter_uuid},0"
        if key not in data["timeseries"]:
            raise EyeOnWaterResponseIsEmpty("Response is empty")

        timezone = data["hit"]["meter.timezone"][0]
        timezone = pytz.timezone(timezone)

        data = data["timeseries"][key]["series"]
        statistics = []
        for d in data:
            response_unit = d["display_unit"].upper()
            statistics.append(
                {
                    "dt": timezone.localize(parser.parse(d["date"])),
                    "reading": self.convert(response_unit, d["bill_read"]),
                }
            )

        statistics.sort(key=lambda d: d["dt"])

        return statistics


class Account:
    """Class represents account object."""

    def __init__(
        self,
        eow_hostname: str,
        username: str,
        password: str,
        metric_measurement_system: bool,
    ) -> None:
        """Initialize the account."""
        self.eow_hostname = eow_hostname
        self.username = username
        self.password = password
        self.metric_measurement_system = metric_measurement_system

    async def fetch_meters(self, client: Client):
        """List the meters associated with the account."""
        path = DASHBOARD_ENDPOINT + urllib.parse.quote(self.username)
        data = await client.request(path=path, method="get")

        meters = []
        lines = data.split("\n")
        for line in lines:
            if Meter.info_prefix in line:
                meter_infos = client.extract_json(line, Meter.info_prefix)
                for meter_info in meter_infos:
                    if METER_UUID_FIELD not in meter_info:
                        msg = f"Cannot find {METER_UUID_FIELD} field"
                        raise EyeOnWaterAPIError(
                            msg,
                        )

                    meter_uuid = meter_info[METER_UUID_FIELD]

                    meter = Meter(
                        meter_uuid=meter_uuid,
                        meter_info=meter_info,
                        metric_measurement_system=self.metric_measurement_system,
                    )
                    meters.append(meter)

        return meters


class Client:
    """Class represents client object."""

    def __init__(
        self,
        websession: ClientSession,
        account: Account,
    ) -> None:
        """Initialize the client."""
        self.base_url = "https://" + account.eow_hostname + "/"
        self.websession = websession
        self.account = account
        self.cookies = None
        self.authenticated = False
        self.token_expiration = datetime.datetime.now()
        self.user_agent = None

    def _update_token_expiration(self):
        self.token_expiration = datetime.datetime.now() + TOKEN_EXPIRATION

    @retry(retry=retry_if_exception_type(EyeOnWaterAuthExpired))
    async def request(
        self,
        path: str,
        method: str,
        **kwargs,
    ):
        """Make API calls against the eow API."""
        await self.authenticate()
        resp = await self.websession.request(
            method,
            f"{self.base_url}{path}",
            cookies=self.cookies,
            **kwargs,
        )
        if resp.status == 403:
            _LOGGER.error("Reached ratelimit")
            raise EyeOnWaterRateLimitError("Reached ratelimit")
        elif resp.status == 401:
            _LOGGER.debug("Authentication token expired; requesting new token")
            self.authenticated = False
            await self.authenticate()
            raise EyeOnWaterAuthExpired

        # Since API call did not return a 400 code, update the token_expiration.
        self._update_token_expiration()

        data = await resp.text()

        if resp.status != 200:
            _LOGGER.error(f"Request failed: {resp.status} {data}")
            raise EyeOnWaterException(f"Request failed: {resp.status} {data}")

        return data

    async def authenticate(self):
        """Authenticate the client."""
        if not self.token_valid:
            _LOGGER.debug("Requesting login token")

            resp = await self.websession.request(
                "POST",
                f"{self.base_url}{AUTH_ENDPOINT}",
                data={
                    "username": self.account.username,
                    "password": self.account.password,
                },
            )

            if "dashboard" not in str(resp.url):
                _LOGGER.warning("METER NOT FOUND!")
                msg = "No meter found"
                raise EyeOnWaterAuthError(msg)

            if resp.status == 400:
                msg = f"Username or password was not accepted by {self.base_url}"
                raise EyeOnWaterAuthError(msg)

            if resp.status == 403:
                msg = "Reached ratelimit"
                raise EyeOnWaterRateLimitError(msg)

            self.cookies = resp.cookies
            self._update_token_expiration()
            self.authenticated = True
            _LOGGER.debug("Successfully retrieved login token")

    def extract_json(self, line, prefix):
        """Extract JSON response."""
        line = line[line.find(prefix) + len(prefix) :]
        line = line[: line.find(";")]
        return json.loads(line)

    @property
    def token_valid(self):
        """Validate the token."""
        if self.authenticated or (datetime.datetime.now() < self.token_expiration):
            return True

        return False
