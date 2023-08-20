import asyncio
import datetime

import aiohttp
from eow import Account, Client


async def main():
    account = Account(
        eow_hostname="eyeonwater.com",
        username="your EOW login",
        password="your EOW password",
        metric_measurement_system=False,
    )
    websession = aiohttp.ClientSession()
    client = Client(websession=websession, account=account)

    await client.authenticate()

    meters = await account.fetch_meters(client=client)
    print(f"{len(meters)} meters found")
    for meter in meters:
        today = datetime.datetime.now().replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        data = await meter.get_historical_data(
            client=client,
            units="GAL",
            date=today,
        )
        for d in data:
            print(str(d["dt"]), d["reading"])

        await meter.read_meter(client=client)
        print(f"meter {meter.meter_uuid} shows {meter.reading}")
        print(f"meter {meter.meter_uuid} info {meter.meter_info}")

    await websession.close()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
