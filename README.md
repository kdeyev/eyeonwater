# Home Assistant integration for EyeOnWater service

## ⚠️ Breaking Change in v2.6.0

Version 2.6.0 changes how water usage statistics are stored. If you are upgrading from a previous version, **you must reconfigure your Energy Dashboard and re-import historical data**.

### What Changed

| | Before (≤ 2.5.x) | After (2.6.0+) |
|---|---|---|
| Statistic ID | `sensor.eyeonwater:water_meter_xxxxx` | `eyeonwater:water_meter_xxxxx` |
| Source | `recorder` | `eyeonwater` |
| API | `async_import_statistics` | `async_add_external_statistics` |

The old approach conflicted with Home Assistant's internal statistics pipeline, causing **negative water usage spikes** ([#30](https://github.com/kdeyev/eyeonwater/issues/30)). The new approach uses HA's external statistics API under a dedicated `eyeonwater:` namespace, eliminating these conflicts entirely.

### Migration Steps

1. **Update** the integration to v2.6.0 via HACS.
2. **Restart** Home Assistant.
3. **Reconfigure the Energy Dashboard:**
   - Go to `Settings` → `Dashboards` → `Energy`.
   - In **Water Consumption**, remove the old statistic entry.
   - Add the new `eyeonwater:water_meter_xxxxx` statistic.
4. **Re-import historical data:**
   - Go to `Developer Tools` → `Services`.
   - Call `EyeOnWater: import_historical_data` with the desired number of days.
5. *(Optional)* Delete the old orphaned statistics via `Developer Tools` → `Statistics` if they appear as "no longer provided."

### New Diagnostic Sensors

v2.6.0 also adds 10 new diagnostic sensor entities (created only when the meter provides the data):

- **Temperature:** 7-day min, 7-day avg, 7-day max, latest avg
- **Flow:** usage this week, last week, this month, last month
- **Battery:** battery level (%)
- **Signal:** signal strength (dB)

---

## Installation

1. Follow the [instructions](https://hacs.xyz/docs/faq/custom_repositories/) for adding a custom git repository to your HA.

   Add `https://github.com/kdeyev/eyeonwater` as Repository and select the `Integration` category.

   ![add-repository](https://github.com/kdeyev/eyeonwater/blob/master/img/add-repository.png?raw=true)

2. Add the EyeOnWater integration following [HACS instructions](https://github.com/hacs/integration).

   Follow the configuration dialog and use the username and password you use to log in on eyeonwater.

   The integration uses some of your HA configurations:
   - **Country** — determines whether `eyeonwater.ca` should be used.
   - **Unit System** — switches between Metric and US customary measurement systems.

   ![configuration](https://github.com/kdeyev/eyeonwater/blob/master/img/configuration.png?raw=true)

3. After successful initialization you should see the integration card:

   ![integration-card](https://github.com/kdeyev/eyeonwater/blob/master/img/integration-card.png?raw=true)

   ![watermeter](https://github.com/kdeyev/eyeonwater/blob/master/img/watermeter.png?raw=true)

   ![watermeter-graph](https://github.com/kdeyev/eyeonwater/blob/master/img/watermeter-graph.png?raw=true)

## Energy Dashboard Setup

Go to `Settings` → `Dashboards` → `Energy` configuration.

In the **Water Consumption** section, select the `eyeonwater:water_meter_xxxxx` statistic — this is the one populated with accurate hourly data from EyeOnWater.

> **Note:** EyeOnWater publishes meter readings once every few hours (even though readings are accumulated every few minutes), so data may appear with a delay.

![energy-dashboard](https://github.com/kdeyev/eyeonwater/blob/master/img/energy-dashboard.png?raw=true)

## Import Historical Data

The integration can import historical water usage data after installation.

1. Go to `Developer Tools` → `Services`.
2. Select the `EyeOnWater: import_historical_data` service.
3. Choose how many days of historical data you want to import.
4. The import may take some time depending on the number of days.

![import-historical-data](https://github.com/kdeyev/eyeonwater/blob/master/img/import-historical-data.png?raw=true)

## Architecture: How Statistics Work

This integration uses Home Assistant's **external statistics** API (`async_add_external_statistics`) to import accurate hourly water usage data from EyeOnWater.

### The Problem

EyeOnWater reports water meter readings **retroactively** — data for 12 PM–6 PM may only become available at 6 PM. Home Assistant's statistics system assumes sensor state updates always represent "now." When a sensor with `state_class` has retroactive data imported for the same statistic ID, HA produces **negative value spikes** due to conflicting sum timelines.

### The Solution

The integration uses **external statistics** under a separate `eyeonwater:` namespace, completely independent from HA's automatic statistics pipeline:

| Component | ID | Purpose |
|-----------|-------------|---------|
| Live sensor | `sensor.water_meter_xxxxx` | Real-time meter reading display |
| External statistic | `eyeonwater:water_meter_xxxxx` | **Energy Dashboard** — accurate hourly usage |

The live sensor has no `state_class`, so HA does not auto-compile statistics for it. All statistics come exclusively from the integration's retroactive imports — no conflicts, no negative values.

### HA Core Tracking

The underlying limitation (no support for retroactive/delayed sensor data) is discussed upstream:
- [home-assistant/architecture#964](https://github.com/home-assistant/architecture/discussions/964) — Delayed data sensors
