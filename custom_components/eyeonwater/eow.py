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
__version__ = "0.0.2"


AUTH_ENDPOINT = "account/signin"
DASHBOARD_ENDPOINT = "/dashboard/"
SEARCH_ENDPOINT = "/api/2/residential/new_search"

MEASUREMENT_GALLONS = "GAL"
MEASUREMENT_100_GALLONS = "100 GAL"
MEASUREMENT_10_GALLONS = "10 GAL"
MEASUREMENT_CF = "CF"
MEASUREMENT_CCF = "CCF"
MEASUREMENT_KILOGALLONS = "KGAL"
MEASUREMENT_CUBICMETERS = "CM"

METER_UUID_FIELD = "meter_uuid"
READ_UNITS_FIELD = "units"
READ_AMOUNT_FIELD = "full_read"
HAS_LEAK_FIELD = "Leak"

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

    def __init__(self, meter_uuid: str, meter_info: Dict[str, Any], metric_measurement_system: bool):
        self.meter_uuid = meter_uuid
        self.meter_info = meter_info
        self.metric_measurement_system = metric_measurement_system
        self.native_unit_of_measurement = "m\u00b3" if self.metric_measurement_system else "gal"
        self.reading_data = None
        
    async def read_meter(self, client: Client) -> Dict[str, Any]:
        """Triggers an on-demand meter read and returns it when complete."""
        _LOGGER.debug("Requesting meter reading")

        query = {"query":{"terms":{"meter.meter_uuid":[self.meter_uuid]}}}
        data = await client.request(path=SEARCH_ENDPOINT, method="post", json=query)
        data = json.loads(data)
        meters = data["elastic_results"]["hits"]["hits"]
        if len(meters) > 1:
            raise Exception("More than one meter reading found")

        self.meter_info = meters[0]["_source"]
        self.reading_data = self.meter_info["register_0"]

    @property
    def attributes(self):
        return self.meter_info

    @property
    def has_leak(self) -> bool:
        flags = self.reading_data["flags"]
        if HAS_LEAK_FIELD not in flags:
            raise EyeOnWaterAPIError(f"Cannot find {HAS_LEAK_FIELD} field")
        return flags[HAS_LEAK_FIELD]

    @property
    def reading(self):
        """Returns the latest meter reading in gal."""
        reading = self.reading_data["latest_read"]
        if READ_UNITS_FIELD not in reading:
            raise EyeOnWaterAPIError("Cannot find read units in reading data")
        read_unit = reading[READ_UNITS_FIELD]
        amount = float(reading[READ_AMOUNT_FIELD])
        if self.metric_measurement_system:    
            if read_unit.upper() == MEASUREMENT_CUBICMETERS:
                pass
            else:
                raise EyeOnWaterAPIError(f"Unsupported measurement unit: {read_unit}")
        else:
            if read_unit.upper() == MEASUREMENT_KILOGALLONS:
                amount = amount * 1000
            elif read_unit.upper() == MEASUREMENT_100_GALLONS:
                amount = amount * 100
            elif read_unit.upper() == MEASUREMENT_10_GALLONS:
                amount = amount * 10
            elif read_unit.upper() == MEASUREMENT_GALLONS:
                pass
            elif read_unit.upper() == MEASUREMENT_CCF:
                amount = amount * 748.052
            elif read_unit.upper() == MEASUREMENT_CF:
                amount = amount * 7.48052
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
                    if METER_UUID_FIELD not in meter_info:
                        raise EyeOnWaterAPIError(f"Cannot find {METER_UUID_FIELD} field")
                
                    meter_uuid = meter_info[METER_UUID_FIELD]
                    
                    meter = Meter(meter_uuid=meter_uuid, meter_info=meter_info, metric_measurement_system=self.metric_measurement_system)
                    meters.append(meter)

        return meters  


class Client:
    def __init__(
        self, websession: ClientSession, account: "Account",
    ):
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
        """Helper method to make API calls against the eow API."""
        await self.authenticate()
        resp = await self.websession.request(
            method,
            f"{self.base_url}{path}",
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
                f"{self.base_url}{AUTH_ENDPOINT}",
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
