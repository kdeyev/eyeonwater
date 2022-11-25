# Home Assistant integration for EyeOnWater service

1. Follow [instruction](https://hacs.xyz/docs/faq/custom_repositories/) for adding a custom git repository to your HA.

Add `https://github.com/kdeyev/eyeonwater` as Repository and select the "Integration" category.

![add-repository](img/add-repository.png?raw=true)

2. Add EyeOnWater integration following [HACS instructions](https://github.com/hacs/integration)

Follow the configuration dialog: 
- Choose EyeOnWater hostname (choose eyeonwater.com unless you are in Canada).
- Choose the measurement system you prefer to use. "Imperial" will create a water sensor counting gallons, "Metric" will create a water sensor counting cubic meters.
- Use your username and password, which you use to log in on eyeonwater.com

![configuration](img/configuration.png?raw=true)

3. After successful initialization you should see the integration card appear:

![integration-card](img/integration-card.png?raw=true)

![watermeter](img/watermeter.png?raw=true)

![watermeter-graph](img/watermeter-graph.png?raw=true)

4. Got to Setting->Dashboards->Energy configuration.

You should be able to choose your water meter in the Water Consumption

![water-consumption-configuration](img/water-consumption-configuration.png?raw=true)
![water-consumption](img/water-consumption.png?raw=true)

5. Have fun and watch your utilities in the Energy Dashboard.

![energy-dashboard](img/energy-dashboard.png?raw=true)

Pay attention that EyeOnWater publishes the meter reading once in several hours (even when they accumulate the meter reading once in several minutes). It does not correlate with the HA sensors architecture, which will make your consumption graphs look weird. In the image below, the consumption itself is correct, but the distribution in time is wrong - the graph shows 50 gallons of consumption at 8 AM, but actually, 50 gallons were consumed in the time period 4 AM-8 AM.

![water-consumption-graph](img/water-consumption-graph.png?raw=true)
