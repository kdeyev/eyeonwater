from __future__ import annotations

import datetime
import json
import logging
from typing import Any, Dict
import urllib.parse
from aiohttp import ClientSession
from tenacity import retry, retry_if_exception_type
import datetime

from voluptuous.validators import Boolean

__author__ = "Konstantin Deev"
__email__ = "kn.deev@gmail.com"
__version__ = "0.0.1"


BASE_HOSTNAME = "eyeonwater.com"
BASE_URL = "https://" + BASE_HOSTNAME + "/"
AUTH_ENDPOINT = "account/signin"
DASHBOARD_ENDPOINT = "/dashboard/"

MEASUREMENT_GALLONS = "GAL"
MEASUREMENT_KILOGALLONS = "KGAL"
MEASUREMENT_CUBICMETERS = "CM"

METER_ID_FIELD = "meter_id"
METER_READ_FIELD = "meter_read"
NEW_LATEST_READ_FIELD = "new_latest_read"
READ_UNITS_FIELD = "read_units"
READ_AMOUNT_FIELD = "read_amount"
HAS_LEAK_FIELD = "has_leak"

TOKEN_EXPIRATION = datetime.timedelta(minutes=15)

_LOGGER = logging.getLogger(__name__)



class EyeOnWaterException(Exception):
    """Base exception for more specific exceptions to inherit from."""

    ...


class EyeOnWaterAuthError(EyeOnWaterException):
    """Exception for authentication failures.
    Either wrong username or wrong password."""

    ...


class EyeOnWaterRateLimitError(EyeOnWaterException):
    """Exception for reaching the ratelimit.
    Either too many login attempts or too many requests."""

    ...


class EyeOnWaterAuthExpired(EyeOnWaterException):
    """Exception for when a token is no longer valid."""

    ...


class EyeOnWaterAPIError(EyeOnWaterException):
    """General exception for unknown API responses."""

    ...


def extract_json(line, prefix):
    line = line[line.find(prefix) + len(prefix):]
    line = line[:line.find(";")]
    return json.loads(line)

class Meter:
    meter_prefix = "var new_barInfo = "
    info_prefix = "AQ.Views.MeterPicker.meters = "

    def __init__(self, meter_id: str, meter_info: Dict[str, Any], metric_measurement_system: bool):
        self.meter_id = meter_id
        self.meter_info = meter_info
        self.metric_measurement_system = metric_measurement_system
        self.native_unit_of_measurement = "m\u00b3" if self.metric_measurement_system else "gal"
        self.reading_data = None
        
    async def read_meter(self, client: Client) -> Dict[str, Any]:
        """Triggers an on-demand meter read and returns it when complete."""
        _LOGGER.debug("Requesting meter reading")

        path = DASHBOARD_ENDPOINT + urllib.parse.quote(client.account.username)

        # Trigger an on-demand meter read.
        data = await client.request(
            method="get",
            path=path
        )

        return self._parse_reading_data(data)

    def _parse_reading_data(self, data) -> Dict[str, Any]:
        lines = data.split("\n")

        meter_index = None
        for line in lines:
            if Meter.info_prefix in line:
                meter_infos = extract_json(line, Meter.info_prefix)
                meter_index = next(i for i, v in enumerate(meter_infos) if v[METER_ID_FIELD] == self.meter_id)
                self.meter_info = meter_infos[meter_index]

        if meter_index is None:
            raise EyeOnWaterAPIError("Cannot find meter info")

        for line in lines:
            if Meter.meter_prefix in line:
                meters_read = extract_json(line, Meter.meter_prefix)
                self.reading_data = meters_read[METER_READ_FIELD][meter_index][NEW_LATEST_READ_FIELD]
             
        return self.reading_data

    @property
    def attributes(self):
        return self.meter_info

    @property
    def has_leak(self) -> bool:
        if HAS_LEAK_FIELD not in self.meter_info:
            raise EyeOnWaterAPIError(f"Cannot find {HAS_LEAK_FIELD} field")
        return self.meter_info[HAS_LEAK_FIELD] == "true"

    @property
    def reading(self):
        """Returns the latest meter reading in gal."""
        if READ_UNITS_FIELD not in self.reading_data:
            raise EyeOnWaterAPIError("Cannot find read units in reading data")
        read_unit = self.reading_data[READ_UNITS_FIELD]
        amount = float(self.reading_data[READ_AMOUNT_FIELD])
        if self.metric_measurement_system:    
            if read_unit.upper() == MEASUREMENT_CUBICMETERS:
                pass
            else:
                raise EyeOnWaterAPIError(f"Unsupported measurement unit: {read_unit}")
        else:
            if read_unit.upper() == MEASUREMENT_KILOGALLONS:
                amount = amount * 1000
            elif read_unit.upper() == MEASUREMENT_GALLONS:
                pass
            else:
                raise EyeOnWaterAPIError(f"Unsupported measurement unit: {read_unit}")
        return amount


class Account:
    def __init__(self, eow_hostname: str, username: str, password: str, metric_measurement_system: bool):
        self.eow_hostname = eow_hostname
        self.username = username
        self.password = password
        self.metric_measurement_system = metric_measurement_system

    async def fetch_meters(self, client: "Client"):
        """Returns a list of the meters associated with the account"""
        path = DASHBOARD_ENDPOINT + urllib.parse.quote(self.username)
        data = await client.request(path=path, method="get")

        meters = []
        lines = data.split("\n")
        for line in lines:
            if Meter.info_prefix in line:
                meter_infos = extract_json(line, Meter.info_prefix)
                for meter_info in meter_infos:
                    if METER_ID_FIELD not in meter_info:
                        raise EyeOnWaterAPIError(f"Cannot find {METER_ID_FIELD} field")
                
                    meter_id = meter_info[METER_ID_FIELD]
                    
                    meter = Meter(meter_id=meter_id, meter_info=meter_info, metric_measurement_system=metric_measurement_system)
                    meters.append(meter)

        return meters  


class Client:
    def __init__(
        self, websession: ClientSession, account: "Account",
    ):
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
        """Helper method to make API calls against the eow API."""
        await self.authenticate()
        resp = await self.websession.request(
            method,
            f"{BASE_URL}{path}",
            cookies=self.cookies,
            **kwargs,
            # ssl=self.ssl_context,
        )
        if resp.status == 401:
            _LOGGER.debug("Authentication token expired; requesting new token")
            self.authenticated = False
            await self.authenticate()
            raise EyeOnWaterAuthExpired

        # Since API call did not return a 400 code, update the token_expiration.
        self._update_token_expiration()

        data = await resp.text()
        return data

    async def authenticate(self):
        if not self.token_valid:
            _LOGGER.debug("Requesting login token")

            resp = await self.websession.request(
                "POST",
                f"{BASE_URL}{AUTH_ENDPOINT}",
                data={
                    "username": self.account.username,
                    "password": self.account.password,
                },
            )

            if resp.status == 400:
                raise EyeOnWaterAuthError("Username or password was not accepted")

            if resp.status == 403:
                raise EyeOnWaterRateLimitError(
                    "Reached ratelimit or brute force protection"
                )

            self.cookies = resp.cookies
            self._update_token_expiration()
            self.authenticated = True
            _LOGGER.debug("Successfully retrieved login token")



    @property
    def token_valid(self):
        if self.authenticated or (datetime.datetime.now() < self.token_expiration):
            return True

        return False
