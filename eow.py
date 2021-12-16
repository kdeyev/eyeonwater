from __future__ import annotations

import datetime
import logging
import urllib.parse
import re
from aiohttp import ClientSession
from tenacity import retry, retry_if_exception_type
import datetime

BASE_HOSTNAME = "eyeonwater.com"
BASE_URL = "https://" + BASE_HOSTNAME + "/"
# BASE_ENDPOINT = BASE_URL + "api"
AUTH_ENDPOINT = "account/signin"
DASHBOARD_ENDPOINT = "/dashboard/"
# LATEST_OD_READ_ENDPOINT = "/usage/latestodrread"
# METER_ENDPOINT = "/meter"
# OD_READ_ENDPOINT = "/ondemandread"

USER_AGENT_TEMPLATE = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/85.0.{BUILD}.{REV} Safari/537.36"
)
CLIENT_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}

API_ERROR_KEY = "errormessage"
TOKEN_EXPIRED_KEY = "message"
TOKEN_EXPIRED_VALUE = "Invalid Token"

API_ERROR_RESPONSES = {
    "ERR-USR-USERNOTFOUND": "user not found",
    "ERR-USR-INVALIDPASSWORDERROR": "password is not correct",
}

OD_READ_RETRY_TIME = 15
TOKEN_EXPRIATION = datetime.timedelta(minutes=15)

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


__author__ = "Konstantin Deev"
__email__ = "kn.deev@gmail.com"
__version__ = "0.0.1"

_LOGGER = logging.getLogger(__name__)


class Meter:
    regex =  r"^(.*){\"new_latest_read\": {\"read_time\": \"(.*)\", \"read_units\": \"(.*)\", \"read_amount\": \"(\d+\.\d+)\", \"read_date\": \"(.*)\"}(.*)$"
    pattern = re.compile(regex)


    def __init__(self, meter_id: str, address: str):
        self.meter_id = meter_id
        # self.esiid = esiid
        self.address = address
        self.reading_data = None

        
    async def read_meter(self, client: Client) -> float:
        """Triggers an on-demand meter read and returns it when complete."""
        _LOGGER.debug("Requesting meter reading")

        path = DASHBOARD_ENDPOINT + urllib.parse.quote(client.account.username)

        # Trigger an on-demand meter read.
        data = await client.request(
            method="get",
            path=path
        )

        return self.parse_reading_data(data)

    def parse_reading_data(self, data):
        lines = data.split("\n")
        for line in lines:
            match = re.match(Meter.pattern, line)
            if match:
                gr = match.groups()
                self.reading_data = float(gr[3])
                return self.reading_data
            
        self.reading_data = None
        raise EyeOnWaterAPIError("Cannot parse the server response")

class Account:
    regex =  r"^(.*){\"display_address\": \"(.*)\", \"account_id\": \"(.*)\", \"meter_uuid\": \"(.*)\", \"meter_id\": \"(.*)\", \"city\": \"(.*)\", \"location_name\": \"(.*)\", \"has_leak\": (.*), \"state\": \"(.*)\", \"serial_number\": \"(.*)\", \"utility_uuid\": \"(.*)\", \"page\": (.*), \"zip_code\": \"(.*)\"}(.*)$"
    # regex =  r"^(.*)\"meter_id\": \"(.*)\", (.*)$"
    pattern = re.compile(regex)

    # AQ.Views.MeterPicker.meters = [{"display_address": "4510 HUNTWOOD HILLS LN", "account_id": "60634-6340122703", "meter_uuid": "5214483767293934848", "meter_id": "200010108", "city": "KATY", "location_name": "4510 HUNTWOOD HILLS LN", "has_leak": false, "state": "TX", "serial_number": "200010108", "utility_uuid": "5214483767290840517", "page": 1, "zip_code": "77450"}];

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

    async def fetch_meters(self, client: "Client"):
        """Returns a list of the meters associated with the account"""
        path = DASHBOARD_ENDPOINT + urllib.parse.quote(self.username)
        data = await client.request(path=path, method="get")

        meters = []
        lines = data.split("\n")
        for line in lines:
            match = re.match(Account.pattern, line)
            if match:
                gr = match.groups()

                meter_id = gr[4]
                address = gr[1]
                
                meter = Meter(meter_id, address)
                meters.append(meter)

        # for meter_data in json_response["data"]:
        #     address = meter_data["address"]
        #     meter = meter_data["meterNumber"]
        #     esiid = meter_data["esiid"]
        #     meter = Meter(meter, esiid, address)
        #     meters.append(meter)

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
        self.token_expiration = datetime.datetime.now() + TOKEN_EXPRIATION

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

