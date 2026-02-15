# Home Assistant integration for EyeOnWater service

1. Follow [instruction](https://hacs.xyz/docs/faq/custom_repositories/) for adding a custom git repository to your HA.

Add `https://github.com/kdeyev/eyeonwater` as Repository and select the `Integration` category.

![add-repository](https://github.com/kdeyev/eyeonwater/blob/master/img/add-repository.png?raw=true)

2. Add EyeOnWater integration following [HACS instructions](https://github.com/hacs/integration)

Follow the configuration dialog and use your username and password, which you use to log in on eyeonwater.
Pay attention to that integration uses some of your HA configurations:
- `Country` is used for identification if `eyeonwater.ca` should be used.
- `Unit System` is used for switching between Metric and US customary measurement systems

![configuration](https://github.com/kdeyev/eyeonwater/blob/master/img/configuration.png?raw=true)

3. After successful initialization you should see the integration card appear:

![integration-card](https://github.com/kdeyev/eyeonwater/blob/master/img/integration-card.png?raw=true)

![watermeter](https://github.com/kdeyev/eyeonwater/blob/master/img/watermeter.png?raw=true)

![watermeter-graph](https://github.com/kdeyev/eyeonwater/blob/master/img/watermeter-graph.png?raw=true)

4. Go to `Settings`->`Dashboards`->`Energy` configuration.

You should be able to choose your water meter in the Water Consumption. Select the external statistic named **"Water Meter xxxxx Statistic"** (with the `eyeonwater:` prefix) — this is the one populated with accurate hourly data from EyeOnWater.

5. Have fun and watch your utilities in the Energy Dashboard.

![energy-dashboard](https://github.com/kdeyev/eyeonwater/blob/master/img/energy-dashboard.png?raw=true)

Pay attention that EyeOnWater publishes the meter reading once in several hours (even when they accumulate the meter reading once in several minutes). So data may come with a delay of several hours.

# Import historical data
The integration allows to import of historical water data usage after it was installed.
- Go to `Developer Tools` -> Servies`.
- Enter the `EyeOnWater: import_historical_data` service name.
- Choose how many days of historical data you want to import.
- Pay attention that the import may take some time.
![import-historical-data](https://github.com/kdeyev/eyeonwater/blob/master/img/import-historical-data.png?raw=true)


# Architecture: How Statistics Work

This integration uses Home Assistant's **external statistics** API (`async_add_external_statistics`) to import accurate hourly water usage data from EyeOnWater.

## The Problem with Standard Statistics

EyeOnWater reports water meter readings **retroactively**: data for 12 PM–6 PM may only become available at 6 PM. Home Assistant's sensor statistics system has no native support for retroactive data — it assumes sensor state updates always represent "now."

When a sensor has `state_class = total_increasing`, HA's recorder automatically compiles statistics every 5 minutes by calculating deltas between consecutive state changes. If an integration also imports retroactive historical data for the **same statistic ID**, HA sees two conflicting sum timelines — the auto-compiled deltas and the retroactively imported cumulative readings — producing **massive negative spikes** equal to the full lifetime meter reading.

## The Solution

This integration avoids the conflict by using **external statistics** with a separate namespace:

| Component | Statistic ID | Source | Purpose |
|-----------|-------------|--------|---------|
| Live sensor | `sensor.water_meter_xxxxx` | HA auto-compiles | Real-time display |
| External statistic | `eyeonwater:water_meter_xxxxx` | Integration imports via `async_add_external_statistics` | **Energy Dashboard** (accurate hourly usage) |

Because external statistics use the `eyeonwater:` source prefix, they are completely independent from HA's automatic `compile_statistics()` pipeline. The integration imports retroactive data without any conflict, and negative values never appear.

### How It Works

1. The **live sensor** (`sensor.water_meter_xxxxx`) still has `state_class = total_increasing` and provides real-time meter readings.
2. On each coordinator update, the integration fetches historical data from the EyeOnWater API and imports only new data points as **external statistics** under the `eyeonwater:water_meter_xxxxx` ID.
3. For the **Energy Dashboard**, select the `eyeonwater:water_meter_xxxxx` statistic — this contains the accurate hourly usage data.

### HA Core Tracking

The underlying limitation in HA Core (no support for retroactive/delayed sensor data) is discussed upstream:
- [home-assistant/architecture#964](https://github.com/home-assistant/architecture/discussions/964) — Delayed data sensors
