# Home Assistant integration for EyeOnWater

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub stars](https://img.shields.io/github/stars/kdeyev/eyeonwater?style=social)](https://github.com/kdeyev/eyeonwater)
[![GitHub Release](https://img.shields.io/github/v/release/kdeyev/eyeonwater)](https://github.com/kdeyev/eyeonwater/releases)
[![GitHub License](https://img.shields.io/github/license/kdeyev/eyeonwater)](LICENSE)
[![Tests](https://img.shields.io/github/actions/workflow/status/kdeyev/eyeonwater/tests.yml?label=tests)](https://github.com/kdeyev/eyeonwater/actions/workflows/tests.yml)

Track your **water usage** directly in Home Assistant using the [EyeOnWater](https://eyeonwater.com) service. This integration imports accurate hourly meter readings into HA's Energy Dashboard — including **historical data** and optional **cost tracking**.

![watermeter](https://github.com/kdeyev/eyeonwater/blob/master/img/watermeter.png?raw=true)

### Key Features

- **Energy Dashboard integration** — hourly water consumption statistics with full history
- **Water cost tracking** — multiply usage by your unit price for cost statistics
- **Historical data import** — backfill days/weeks/months of data on demand
- **Diagnostic sensors** — temperature, flow, battery, and signal strength
- **US & Canada support** — works with `eyeonwater.com` and `eyeonwater.ca`

## 📖 Documentation

| Guide | Description |
|-------|-------------|
| **[Installation](docs/installation.md)** | Install via HACS or manually |
| **[Configuration](docs/configuration.md)** | Set up credentials, sensors, and options |
| **[Energy Dashboard](docs/energy-dashboard.md)** | Add water consumption to HA Energy |
| **[Historical Data & Architecture](docs/historical-data.md)** | Import past data — how retroactive statistics work |
| **[Water Cost Tracking](docs/cost-tracking.md)** | Track water costs in the Energy Dashboard |
| **[Upgrading to v2.6](docs/migration-v2.6.md)** | Breaking changes and migration steps |
| **[Troubleshooting](docs/troubleshooting.md)** | Common issues and solutions |

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

## Water Cost Tracking

The integration can publish **external cost statistics** (`eyeonwater:water_cost_xxxxx`) alongside the water usage statistics. This lets the Energy Dashboard correlate water consumption with cost on the same historical timeline.

### How It Works

- When a **unit price** is configured, every imported water data point is multiplied by the price to produce a cumulative cost statistic.
- Cost statistics use the same hourly granularity as water usage — they are retroactive and accurate, not real-time estimates.
- The currency is automatically set from your Home Assistant configuration (`Settings` → `General` → `Currency`).
- Both the regular import (every polling cycle) and the `import_historical_data` service produce cost statistics.

### Configuration

1. Go to `Settings` → `Devices & Services` → **EyeOnWater**.
2. Click **Configure** on your integration entry.
3. Enter your **water unit price** — the cost per unit of water (e.g., `0.005` for $0.005 per gallon).
4. Click **Submit**.

Once configured, cost statistics will appear as `eyeonwater:water_cost_xxxxx` and can be selected in the Energy Dashboard.

> **Tip:** You can update the unit price at any time through the same Configure menu. Future imports will use the new price. To recalculate historical cost with a new price, use the `import_historical_data` service.

## Import Historical Data

The integration can import historical water usage data after installation.

1. Go to `Developer Tools` → `Actions`.
2. Select the `EyeOnWater: import_historical_data` service.
3. Choose how many days of historical data you want to import.
4. The import may take some time depending on the number of days.

![import-historical-data](https://github.com/kdeyev/eyeonwater/blob/master/img/import-historical-data.png?raw=true)

## Upgrading to v2.6.0

<details>
<summary>⚠️ Breaking changes — click to expand migration guide</summary>

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

</details>

## Architecture: How Statistics Work

This integration uses Home Assistant's **external statistics** API (`async_add_external_statistics`) to import accurate hourly water usage data from EyeOnWater.

### The Problem

EyeOnWater reports water meter readings **retroactively** — data for 12 PM–6 PM may only become available at 6 PM. Home Assistant's statistics system assumes sensor state updates always represent "now." When a sensor with `state_class` has retroactive data imported for the same statistic ID, HA produces **negative value spikes** due to conflicting sum timelines.

### The Solution

The integration uses **external statistics** under a separate `eyeonwater:` namespace, completely independent from HA's automatic statistics pipeline:

| Component       | ID                             | Purpose                                                           |
| --------------- | ------------------------------ | ----------------------------------------------------------------- |
| Live sensor     | `sensor.water_meter_xxxxx`     | Real-time meter reading display                                   |
| Water statistic | `eyeonwater:water_meter_xxxxx` | **Energy Dashboard** — accurate hourly usage                      |
| Cost statistic  | `eyeonwater:water_cost_xxxxx`  | **Energy Dashboard** — accurate hourly cost (requires unit price) |

The live sensor has no `state_class`, so HA does not auto-compile statistics for it. All water usage and cost statistics come exclusively from the integration's retroactive imports — no conflicts, no negative values.

### HA Core Tracking

The underlying limitation (no support for retroactive/delayed sensor data) is discussed upstream:

- [home-assistant/architecture#964](https://github.com/home-assistant/architecture/discussions/964) — Delayed data sensors
