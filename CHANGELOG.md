# Changelog

## 2.6.0 (Unreleased)

### ⚠️ Breaking Changes

- **Statistic ID format changed:** The water usage statistic ID has changed from `sensor.eyeonwater:water_meter_xxxxx` to `eyeonwater:water_meter_xxxxx`. The source changed from `recorder` to `eyeonwater`. **You must reconfigure your Energy Dashboard and re-import historical data after upgrading.** See the [migration guide](README.md#migration-steps) for details.
- **Statistics API changed:** The integration now uses `async_add_external_statistics` instead of `async_import_statistics`, which eliminates negative water usage spikes caused by HA's internal statistics pipeline conflicting with retroactive data imports ([#30](https://github.com/kdeyev/eyeonwater/issues/30)).
- **Live sensor no longer has `state_class`:** The `sensor.water_meter_xxxxx` entity no longer carries a `state_class` attribute. This prevents HA from auto-compiling statistics for it, which was the root cause of the negative spikes. The sensor is now display-only; all statistics come from the external `eyeonwater:` statistic.

### Added

- 10 new diagnostic sensor entities (created only when the meter provides the data):
  - **Temperature sensors:** 7-day min, 7-day avg, 7-day max, latest avg (°C)
  - **Flow sensors:** usage this week, last week, this month, last month (meter's native unit)
  - **Battery sensor:** battery level (%)
  - **Signal sensor:** signal strength (dB)
- Description-based sensor pattern (`EyeOnWaterSensorDescription`) for cleaner sensor definitions.
- Conditional `StatisticMeanType.NONE` support for newer HA Core versions.

### Removed

- `EyeOnWaterStatistic` sensor entity — statistics are now imported directly by the coordinator, no dedicated sensor entity needed.

### Fixed

- Negative water usage values in Energy Dashboard ([#30](https://github.com/kdeyev/eyeonwater/issues/30)).
