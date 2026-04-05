# Upgrading to v2.6.0

Version 2.6.0 introduces breaking changes to how water usage statistics are stored. **You must reconfigure your Energy Dashboard and re-import historical data after upgrading.**

## What Changed

| | Before (≤ 2.5.x) | After (2.6.0+) |
|---|---|---|
| Statistic ID | `sensor.eyeonwater:water_meter_xxxxx` | `eyeonwater:water_meter_xxxxx` |
| Source | `recorder` | `eyeonwater` |
| API | `async_import_statistics` | `async_add_external_statistics` |

The old approach conflicted with Home Assistant's internal statistics pipeline, causing **negative water usage spikes** ([#30](https://github.com/kdeyev/eyeonwater/issues/30)). See the [Architecture section](historical-data.md#architecture-how-retroactive-statistics-work) for a full explanation.

## Migration Steps

### 1. Update the integration

Update to v2.6.0 via HACS (or replace the `custom_components/eyeonwater` folder manually).

### 2. Restart Home Assistant

Go to **Settings** → **System** → **Restart**.

### 3. Reconfigure the Energy Dashboard

1. Go to **Settings** → **Dashboards** → **Energy**.
2. In **Water Consumption**, **remove** the old statistic entry (it referenced the `sensor.eyeonwater:` prefix).
3. **Add** the new `eyeonwater:water_meter_xxxxx` statistic.

### 4. Re-import historical data

1. Go to **Developer Tools** → **Services**.
2. Call **EyeOnWater: import_historical_data** with the desired number of days.
3. Wait for the import to complete.

### 5. Clean up old statistics (optional)

If orphaned statistics appear under **Developer Tools** → **Statistics** as "no longer provided by the integration," you can safely delete them.

## New in v2.6.0

- **10 diagnostic sensors** — temperature, flow, battery, and signal strength (see [Configuration](configuration.md)).
- **Water cost tracking** — configure a unit price to get cost statistics (see [Cost Tracking](cost-tracking.md)).
- **External statistics** — no more negative spikes in the Energy Dashboard.
