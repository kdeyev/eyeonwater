# Changelog

## 2.7.12

First stable release since 2.7.8. Everything below shipped through the 2.7.9–2.7.12 betas.

### Added

- Three new binary sensors, all **disabled by default** so existing installations are unaffected ([#178](https://github.com/kdeyev/eyeonwater/pull/178)):
  - **Encoder Leak** — secondary leak indicator reported by the encoder
  - **Endpoint Reading Missed** — the meter endpoint failed to report on schedule
  - **Device Alert** — general device-level alert
- **Reauthentication flow.** When credentials stop being accepted, Home Assistant now prompts for a new password instead of leaving the integration broken. Previously the only recovery was deleting and re-adding it.

### Fixed

- **Setup failed completely for meters that omit the `flags` field** ([#179](https://github.com/kdeyev/eyeonwater/issues/179)). The field was mandatory in the API model, so one missing key produced a validation error and the account got no entities at all.
- **One malformed meter no longer takes down a whole account.** Meters that cannot be parsed are skipped with a warning; healthy meters on the same account still load. If every meter fails, the error is still raised.
- **Authentication failures are no longer silent** ([#180](https://github.com/kdeyev/eyeonwater/issues/180)). An unauthenticated session makes meter discovery return an empty list rather than an error, so setup used to complete "successfully" with zero entities and nothing in the UI indicating a problem. Discovering no meters now fails setup with an explanatory message.
- **Misleading diagnostics.** A 33 KB login page was logged as `Response: 200 (0 bytes)`, and `Successfully retrieved login token` was printed even when the login had failed. Both made the above far harder to diagnose.
- **Multi-day historical imports** now use the pyonwater export path ([#167](https://github.com/kdeyev/eyeonwater/pull/167)).
- **Historical data** uses the meter's own timezone when deciding which day is "today".

### Changed

- `pyonwater` 0.3.32 → **0.3.37**.
- The CI test workflow was pinned to `pyonwater==0.3.22`, four versions behind the shipped requirement, so tests did not run against the version users actually receive. All version pins now agree.

### Known issues

- **Login is broken for some accounts** ([#180](https://github.com/kdeyev/eyeonwater/issues/180)). EyeOnWater appears to be migrating authentication to a new identity provider, and the current login method stops working once an account is migrated. This release makes that failure visible and recoverable, but does **not** fix it. Investigation is ongoing.

---

> Entries for 2.6.1 through 2.7.11 were not recorded here at the time.
> See [GitHub Releases](https://github.com/kdeyev/eyeonwater/releases) for those versions.

---

## 2.6.0

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
