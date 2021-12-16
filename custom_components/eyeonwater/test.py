from http import cookies
import aiohttp
import asyncio

from eow import Account, Client, Meter

async def main():
    account = Account(username="_", password="_")
    websession = aiohttp.ClientSession()
    client = Client(websession=websession, account=account)

    await client.authenticate()
        
    meters = await account.fetch_meters(client=client)
    for meter in meters:
        value = await meter.read_meter(client=client)
        print(f"meter {meter.meter_id} shows {value}")

    await websession.close()
       

loop = asyncio.get_event_loop()
loop.run_until_complete(main())