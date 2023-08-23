import asyncio

import aiohttp

from pyonwater import Account, Client


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
        await meter.read_meter(client=client)
        print(f"meter {meter.meter_uuid} shows {meter.reading}")
        print(f"meter {meter.meter_uuid} info {meter.meter_info}")

        for d in meter.last_historical_data:
            print(str(d["dt"]), d["reading"])

    await websession.close()


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
