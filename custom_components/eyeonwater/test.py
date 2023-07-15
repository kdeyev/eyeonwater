import aiohttp
import asyncio
import datetime

from eow import Account, Client, Meter

async def main():
    account = Account(eow_hostname="eyeonwater.com", username="your EOW login", password="your EOW password", metric_measurement_system=False)
    websession = aiohttp.ClientSession()
    client = Client(websession=websession, account=account)

    await client.authenticate()
        
    meters = await account.fetch_meters(client=client)
    print(f"{len(meters)} meters found")
    for meter in meters:
        now = datetime.datetime.now()
        yesterday = now - datetime.timedelta(days=1)

        data = await meter.get_consumption(date=yesterday.strftime('%m/%d/%Y'), client=client)
        print(data)

        # print(f"meter {meter.meter_uuid} shows {meter.reading}")
        # print(f"meter leaks: {meter.has_leak}")

    await websession.close()
       

loop = asyncio.get_event_loop()
loop.run_until_complete(main())