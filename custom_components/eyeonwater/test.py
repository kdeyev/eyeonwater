"""Code for testing EOW access with pyonwater package."""

import asyncio
import logging

import aiohttp
from pyonwater import Account, Client

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


async def main():
    """Async main."""
    account = Account(
        eow_hostname="eyeonwater.com",
        username="",
        password="",
        metric_measurement_system=False,
    )
    websession = aiohttp.ClientSession()
    client = Client(websession=websession, account=account)

    await client.authenticate()

    meters = await account.fetch_meters(client=client)
    _LOGGER.info("%i meters found", {len(meters)})
    for meter in meters:
        await meter.read_meter(client=client)
        _LOGGER.info("meter %s shows %f", meter.meter_uuid, meter.reading)
        _LOGGER.info("meter %s info %s", meter.meter_uuid, meter.meter_info.json())

        for d in meter.last_historical_data:
            _LOGGER.info("%d-%f", d["dt"], d["reading"])

    await websession.close()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
