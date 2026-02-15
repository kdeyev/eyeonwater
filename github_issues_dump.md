# EyeOnWater GitHub Issues Dump

> Scraped: February 14, 2026
> Repository: https://github.com/kdeyev/eyeonwater
> Total: 7 Open, 57 Closed (64 issues total)
> Open PRs: #126 (Remove Statistics workaround), #87 (Feature/unit tests - Draft)

---

## TABLE OF CONTENTS

- [OPEN ISSUES](#open-issues)
  - [#134 - HA 2026.11 warning: async_import_statistics missing mean_type](#134---ha-202611-warning-async_import_statistics-missing-mean_type)
  - [#129 - The entity no longer has a state class](#129---the-entity-no-longer-has-a-state-class)
  - [#128 - EyeonWater fails on HA 2025.2.4](#128---eyeonwater-fails-on-ha-202524)
  - [#127 - Value for Water_Meter & Water_Meter_Statistic are the same?](#127---value-for-water_meter--water_meter_statistic-are-the-same)
  - [#124 - Eye on water shows usage for entire day in 1 hour?](#124---eye-on-water-shows-usage-for-entire-day-in-1-hour)
  - [#114 - "The entity no longer has a state class"](#114---the-entity-no-longer-has-a-state-class-1)
  - [#112 - HA 2024.10: permanent warning about state class not existing](#112---ha-202410-permanent-warning-about-state-class-not-existing)
- [CLOSED ISSUES (Key Issues with Details)](#closed-issues-key-issues-with-details)
- [CLOSED ISSUES (Summary List)](#closed-issues-summary-list)
- [KEY THEMES & RECURRING PROBLEMS](#key-themes--recurring-problems)

---

## OPEN ISSUES

### #134 - HA 2026.11 warning: async_import_statistics missing mean_type
- **Status:** Open
- **Author:** greasy1997
- **Opened:** ~January 2026
- **Comments:** 0
- **Labels:** None

**Description:**
Home Assistant 2026.11 introduced a change in `async_import_statistics` requiring a `mean_type` parameter. The EyeOnWater integration calls `async_import_statistics` without `mean_type`, which causes this warning:

```
Detected that custom integration 'eyeonwater' doesn't specify mean_type when
calling async_import_statistics at custom_components/eyeonwater/sensor.py, line
162: async_import_statistics(self.hass, metadata, statistics). This will stop
working in Home Assistant 2026.11.
```

**Steps to reproduce:**
1. Enable EyeOnWater integration
2. Enable statistics for the water meter sensor
3. Restart Home Assistant 2026.11 or higher
4. Observe warning in logs

**Expected behavior:** The integration should specify `mean_type` when calling `async_import_statistics`.

**Environment:** HA version: 2026.01, EyeOnWater version: 2.5.15

**Analysis:** This is a straightforward API compatibility fix. The `async_import_statistics` call in `sensor.py` line 162 needs to include the `mean_type` parameter.

---

### #129 - The entity no longer has a state class
- **Status:** Open
- **Author:** hrana
- **Opened:** May 31, 2025
- **Comments:** 3
- **Labels:** None
- **Duplicates:** #114, #112

**Description:**
Persistent repair warning in HA:
```
The entity no longer has a state class
We have generated statistics for 'Water Meter xxxx Statistic'
(sensor.water_meter_xxxx_statistic) in the past, but it no longer has a state class,
therefore, we cannot track long term statistics for it anymore.
```

Running HA 2025.5.3. Has 10 thumbs-up reactions.

**Developer Response (kdeyev, ~2 weeks ago):**
> LTDR: state_class was removed intentionally.
>
> EyeOnWater reports water meter readings retroactively, and HomeAssistant makes an effort to calculate the water usage between readings. TLDR HomeAssistant does not have great support for sensors with retrospective readings.
>
> That's why we have 2 different sensors:
> - `sensor.water_meter_xxxxx` ← standard HASS sensor with standard behavior
> - `sensor.water_meter_xxxxx_statistics` ← manually crafted one with right water usage. Use this one for the dashboard. HASS complains "Entity not defined" and it's ok, this one is our way to prevent HASS recalculating the usage.

**Analysis:** This is the CORE architectural issue of the integration. The "statistic" sensor deliberately has no `state_class` to prevent HA from trying to recalculate usage statistics from cumulative readings (which causes negative values). But this triggers a persistent repair warning in HA 2024.10+. Workaround: use Spook HACS integration to ignore the repair.

---

### #128 - EyeonWater fails on HA 2025.2.4
- **Status:** Open
- **Author:** stamandr
- **Opened:** Feb 14, 2025
- **Comments:** 5

**Description:**
```
Setup failed for custom integration 'eyeonwater': Requirements for eyeonwater
not found: ['pyonwater==0.3.1'].
```

**Discussion:** User khogggit reported same issue on HA 2025.6.3 (Jun 2025). kdeyev suggested using latest version (pyonwater==0.3.1 is very old). khogggit confirmed loading pyonwater 2.5.15 through HACS but had trouble getting the configuration dialog to open.

**Analysis:** Likely a stale cached version issue. The integration manifest may have referenced an old pyonwater version.

---

### #127 - Value for Water_Meter & Water_Meter_Statistic are the same?
- **Status:** Open
- **Author:** ElDingo424
- **Opened:** Jan 24, 2025
- **Comments:** 1

**Description:**
Both `water_meter` and `water_meter_statistic` sensors show the exact same value (>1 million gallons lifetime usage) instead of giving usage over a period. When using the power flow card, both give lifetime values.

**Developer Response (kdeyev):**
Same explanation as #129 - use `sensor.water_meter_xxxxx_statistics` for the dashboard. The standard sensor shows cumulative readings; the statistics sensor imports retroactive usage properly.

---

### #124 - Eye on water shows usage for entire day in 1 hour?
- **Status:** Open
- **Author:** jonofmac
- **Opened:** Jan 7, 2025
- **Comments:** 15
- **Key issue with deep technical discussion**

**Description:**
The eyeonwater integration shows the entire day's water usage at midnight for each day, instead of distributing it hourly like the EyeOnWater web portal does.

**Root Cause Analysis (by jonofmac):**
- EyeOnWater website updates once per day (not every hour)
- The integration only looks at the LATEST value returned, aggregating all datapoints together
- pyonwater library CAN pull hourly data for past days
- The `_state_update` method in sensor.py passes the current reading to HA, which bunches all data into one timestamp

**Code snippet from sensor.py analyzed:**
```python
@callback
def _state_update(self):
    self._available = self.coordinator.last_update_success
    if self._available:
        self._state = self.meter.reading
        if not self.meter.last_historical_data:
            raise NoDataFound(msg)
        self._last_historical_data = filter_newer_data(
            self.meter.last_historical_data,
            self._last_imported_time,
        )
        if self._last_historical_data:
            self.import_historical_data()
            self._last_imported_time = self._last_historical_data[-1].dt
    self.async_write_ha_state()
```

**Beta Testing History:**
- v2.5.15-beta.1: Removed workaround completely → caused negative water consumption
- v2.5.15-beta.9: Works as expected for kdeyev
- jonofmac: Saw some erroneous datapoints initially but stabilized after several days
- mdb17 (Dec 2025): Still only getting updates 2-3 times a day
- kohenkatz: Expected behavior - meter only "phones home" 2-4 times a day, but should fill in last 6-24 hours each time

**Key Insight (kdeyev):**
> Setting `SensorStateClass.TOTAL_INCREASING` notifies HA that the meter usage needs to be calculated from integral readings. The problem is: eyeonwater releases readings retroactively. To have detailed usage, I had to use a HA backdoor to import meter usage retroactively. This interferes with HA's readings→usage calculation.

---

### #114 - "The entity no longer has a state class"
- **Status:** Open
- **Author:** dhuddle
- **Opened:** Nov 18, 2024
- **Comments:** 5
- **Duplicate of:** #112
- **Related PR:** #125 (Added a state class to the statistic sensor - Closed)

**Description:**
Same repair warning as #129 and #112. Running v2.5.12 on HA 2024.11.2. Can hit delete, but the error reappears.

**Community Discussion:**
- Multiple users confirmed (+1 from whitema, chester512)
- ThirteenTX: "There is no fix as this is how the integration has to work to have historical data from the polling"
- ThirteenTX workaround: Install Spook HACS integration to block the repair notification
- jonofmac: Created PR #125 adding `state_class` to the statistic sensor, but discovered it causes HA to glitch and multi-count things (negative water usage)

**Developer Response (kdeyev):**
> LTDR: state_class was removed intentionally. [Same explanation as #129]

---

### #112 - HA 2024.10: permanent warning about state class not existing
- **Status:** Open
- **Author:** arpitgupta
- **Opened:** Oct 3, 2024
- **Comments:** 9
- **Related:** #114, #129, #30

**Description:**
Permanent repair alert appeared after upgrading to HA 2024.10. Shows the "no longer has a state class" warning.

**Developer Response (kdeyev, Oct 22, 2024):**
> I apologize I'm super busy with my main job right now.
> TLDR: This error/warning message is absolutely harmless, and can be safely ignored.
> Will try to find a solution later, it may require some patching on the HA Core side.

**Workaround (utkashd, Mar 2025):**
Use Spook integration to suppress the repair:
1. Install Spook via HACS
2. Developer Tools → Actions → run `repairs.ignore_all`

**Latest response (kdeyev, ~2 weeks ago):**
> LTDR: state_class was removed intentionally. [Same explanation about two sensors]

---

## CLOSED ISSUES (Key Issues with Details)

### #133 - Historical data fetch fails (2.5.15)
- **Status:** Closed (completed)
- **Author:** JustinAiken
- **Opened:** Aug 25, 2025
- **Comments:** 2

**Error:**
```
Unexpected EOW response 1 validation error for HistoricalData
Invalid JSON: EOF while parsing a value at line 1 column 0
```

The pyonwater library's `read_historical_data_one_day` received an empty response from the EyeOnWater API. kdeyev asked the user to run pyonwater's `example.py` directly. Closed without resolution (user didn't follow up).

---

### #131 - Fails to set up with '10 CF' billing unit
- **Status:** Closed (completed)
- **Author:** lokesh-sg
- **Opened:** Jul 28, 2025
- **Comments:** 1

**Issue:** City of Manteca uses `"10 CF"` as billing unit, which wasn't in the enum list. Response data:
```json
"bill_display_units": "10 CF"
```

**Fix:** Added `'10 CF'` to valid units in pyonwater. Fixed in v2.5.15.

---

### #107 - Meter and Statistic Unavailable
- **Status:** Closed (completed)
- **Author:** zackaryssmith
- **Opened:** May 31, 2024
- **Comments:** 17

**Two separate errors:**
1. `HomeAssistantError: Invalid statistic_id` - The meter UUID contained special characters (e.g., `200010106+2019-07-15`) causing the statistic_id to be invalid
2. `AttributeError: 'NoneType' object has no attribute 'endpoint_temperature'` - The `sensors` field was `None` for some meters, but code assumed it existed

**Root Cause:** Meter IDs with special characters (`+`, `-`) caused entity ID validation to fail. The pyonwater output showed `sensors=None` for some meters.

**Fix:** Added `valid_entity_id()` check and ID normalization. Fixed in v2.5.7 (via beta v2.5.8-beta.7).

---

### #109 - Detected blocking call to open with args with HA 2024.9
- **Status:** Closed (completed)
- **Author:** arpitgupta
- **Opened:** Sep 15, 2024
- **Comments:** 8

**Warning:**
```
Detected blocking call to open with args inside the event loop by custom integration 'eyeonwater'
at custom_components/eyeonwater/coordinator.py, line 43: await meter.read_historical_data(
(offender: /usr/local/lib/python3.12/site-packages/pytz/__init__.py, line 108: return open(filename, 'rb'))
```

**Root Cause:** The `pytz` library does a synchronous file open (`open(filename, 'rb')`) inside the async event loop when reading timezone data during `read_historical_data`.

**Fix:** Wrapped the blocking call. Fixed in v2.5.12 (via beta v2.5.12-beta.1). However, bsp9493 reported the release version still had the issue (possibly a packaging error in the release).

---

### #90 - negative daily usage equals to lifetime usage
- **Status:** Closed (completed)
- **Author:** nijhawank
- **Opened:** Jan 29, 2024
- **Comments:** 31
- **Labels:** bug

**Description:**
Since update to 2.4, intermittent huge negative usage equal to lifetime water usage. The issue autocorrects and manifests again after some hours. The spike shifts around over time.

**Root Cause:** In v2.4.0, a workaround for the HA Core statistics import bug was removed. When HA sees retroactive statistics being imported alongside its own calculated statistics from the `state_class=TOTAL_INCREASING` sensor, it miscalculates the delta, producing a negative spike equal to the full meter reading.

**Resolution:**
- v2.5.0: Workaround restored (removing `state_class` from the statistics sensor)
- v2.6.0-beta.1: Attempted to remove workaround again → negative values returned immediately
- Conclusion: The HA Core bug is still present. The workaround (two sensors, one without state_class) is required.
- Fix for existing bad data: Delete statistics entity in Developer Tools → Statistics, then reimport

**This is the foundational issue that explains the entire two-sensor architecture.**

---

### #82 - No history imported w/ import_historical_data service
- **Status:** Closed (completed)
- **Author:** some-guy-23
- **Opened:** Nov 11, 2023
- **Comments:** 9
- **Labels:** help wanted

**Description:** When calling `import_historical_data` service, no historical data appears. Debug logs showed `4439 data points will be imported` but data never appeared in HA statistics.

**Key Info:** The data was fetched correctly from EOW but failed to import into HA. Could be related to the long-term vs short-term statistics distinction in HA. Maximum history shown was 31 days (matching the recorder days setting).

---

### #44 - Report an import_statistics issue to HA Core
- **Status:** Closed (completed)
- **Author:** kdeyev (owner)
- **Opened:** Aug 22, 2023
- **Comments:** 7
- **Labels:** bug

**Description:** Meta-issue to report the import_statistics problem to HA Core. Referenced HA Core PR `home-assistant/core#100239` and discussion `home-assistant/architecture#964` as potential solutions.

ParkerAnderson9 reported that with HA 2023.10.1, using the normal sensor (non-statistic) worked correctly for the energy dashboard. But bsp9493 noted that the statistic sensor is still needed for granular (hourly) data.

---

### #30 - Rogue negative value in energy dashboard
- **Status:** Closed (completed)
- **Author:** bsp9493
- **Opened:** Aug 18, 2023
- **Comments:** 91 (!)
- **Labels:** bug

**THE key issue in the project's history.** The most current reading in the energy dashboard was a huge negative value equal to the meter reading.

**Investigation Timeline:**
- v2.0.1-beta.2: Added debug logging
- v2.0.1-beta.3: Fix for debug logging ("dict has no attribute start")
- kdeyev identified: data points were never sorted, causing wrong import
- v2.0.1-beta.6: Sorting fix, looked good initially but negative values returned
- Root cause identified: HA's `async_import_statistics` with `state_class=TOTAL_INCREASING` causes HA to recalculate deltas from imported cumulative readings, generating negative spikes
- Workaround: Removed `state_class` from the sensor that imports statistics
- v2.0.5: Working consistently
- v2.2.0: PR #58 "Add second sensor for historical data" - the architecture of having two sensors was born here

**Key architectural decision:**
> The workaround with undefined state_class seems to work stable. We will have both a "real-time" sensor and a "historical" sensor. Historical should have an undefined state_class.

---

### #2 - Loading more granular historical data
- **Status:** Closed (completed)
- **Author:** gulo101
- **Opened:** Sep 22, 2022
- **Comments:** 46

**THE foundational feature request.** EyeOnWater reads meters every 15 minutes but only makes data available several times a day. HA sensor API doesn't allow modifying sensor values in the past.

**Key discoveries:**
- andrewchumchal found `async_add_external_statistics` API in HA Core
- kdeyev implemented statistics import using this API (PR #22)
- disforw identified meter_uuid vs meter_id mismatch causing `Invalid statistic_id`
- Letters in meter_id caused case sensitivity issues (entity-id lowercase vs statistic-id uppercase)

**This issue spawned the entire historical data import system and the two-sensor architecture.**

---

## CLOSED ISSUES (Summary List)

| # | Title | Key Info |
|---|-------|----------|
| #123 | eyeonwater does not work with HA 2025.1 | 4 comments, pyonwater compatibility |
| #122 | Error: Fetching Meters Failed\No model_validate | 5 comments, pydantic v2 migration |
| #119 | set up failed - unable to install pyonwater==0.3.11 after HA 2025.1.0 | 4 comments, package version |
| #118 | Error Setting Up - Validation Errors | 5 comments, pydantic validation |
| #117 | [Bug] Setup failed (on beta 2025.1.b0/b1/b2) | 9 comments, HA 2025.1 breaking changes |
| #116 | Can't add integration | 2 comments |
| #113 | Detected blocking call to open with args | 6 comments, pytz blocking |
| #111 | Not collecting any stats after update to 2.5.10 | 1 comment |
| #110 | Unable to add repository | 2 comments |
| #104 | Issue on Integration Setup | 1 comment, bug |
| #99 | Value is not a valid enumeration member - Setup failure | 16 comments, unit enum |
| #98 | The state class '' of this entity is not supported | 2 comments |
| #95 | EyeOnWater data: list index out of range | 2 comments |
| #92 | multiple database issues | 7 comments, bug |
| #88 | Logging error when debug logs are enabled | 1 comment, bug |
| #85 | list index out of range | 5 comments |
| #77 | Units issue: cf | 9 comments, bug, CF unit support |
| #71 | Integration Cannot Be Loaded or Deleted | 3 comments |
| #69 | 2.3.0 data value incorrect for metric | 12 comments, bug, metric units |
| #67 | DeviceInfo Import error | 2 comments, bug, HA API change |
| #65 | Permission error | 5 comments |
| #63 | Unsupported measurement unit: CCF | 7 comments, enhancement |
| #49 | 2.0.4 - Unexpected EOW response validation errors | 2 comments, bug |
| #43 | Restore state class of Sensor and create HistoricalSensor | 3 comments, enhancement |
| #42 | README is not up to date | 1 comment, documentation |
| #40 | Hosting eow.py in pypi | 3 comments, enhancement → pyonwater |
| #39 | Add service for importing historical data of specific dates range | enhancement |
| #34 | Migrate to ha-historical-sensor | closed |
| #31 | Failed to connect when installing | 8 comments |
| #29 | KeyError: recorder_instance [SOLVED] | 2 comments, bug |
| #27 | Version 1.1 errors after a reboot | 10 comments |
| #26 | Multi meter | 3 comments |
| #25 | Error Setting up binary_sensor.eyeonwater | 1 comment |
| #24 | Repository description | closed |
| #21 | Cubic_meter missing unit of measure | 2 comments |
| #20 | Mind if I jump onboard? | 6 comments, disforw joins as collaborator |
| #18 | Unsupported measurement unit error | 2 comments |
| #17 | Error setting up entry | 3 comments |
| #16 | Index Out of Range | 10 comments |
| #15 | incompatible parsing for multiple meters | 4 comments |
| #14 | Support for HomeAssistant v2023.3 | 1 comment |
| #13 | Unsupported Units CF | 2 comments |
| #12 | Adding eow to Utility | 4 comments |
| #11 | Unsupported measurement unit: cm | 6 comments |
| #8 | Does not appear to pulling data | 15 comments |
| #7 | do not appear to be receiving water data | 6 comments |
| #3 | Eye On Water Entities Not Supported in New Core 2022.11.x Energy Dashboard | 4 comments |
| #1 | EyeOnWater custom component is empty | 3 comments |

---

## KEY THEMES & RECURRING PROBLEMS

### 1. THE CORE ARCHITECTURAL CHALLENGE: Retroactive Data Import (#2, #30, #44, #90, #112, #114, #124, #129)

**The fundamental problem:** EyeOnWater reports water meter readings **retroactively** (data for 12PM-6PM becomes available at 6PM). HomeAssistant does NOT natively support sensors that update historical data.

**Current architecture (two-sensor workaround):**
- `sensor.water_meter_xxxxx` — Standard HA sensor with `state_class=TOTAL_INCREASING`. HA calculates usage from cumulative readings. Low granularity (data appears bunched at polling time).
- `sensor.water_meter_xxxxx_statistic` — Custom sensor WITHOUT `state_class`. Uses `async_import_statistics()` to retroactively import hourly usage data. This bypasses HA's automatic statistics calculation.

**Why state_class is removed from the statistic sensor:**
When `state_class` is set, HA tries to calculate statistics from the sensor's state changes. But since the integration also imports statistics retroactively via `async_import_statistics()`, HA double-counts the usage and produces massive negative spikes equal to the full meter reading.

**Side effects of this workaround:**
- HA 2024.10+ shows a persistent repair warning: "The entity no longer has a state class"
- Users are confused by having two sensors
- The statistic sensor shows as "Entity not defined" in some HA views

**Potential solutions discussed:**
- HA Core PR `home-assistant/core#100239` (historical sensor support)
- HA Architecture Discussion `home-assistant/architecture#964`
- PR #126 (Remove Statistics workaround) — still open, testing
- PR #137 (Feature/Expose unified sensor UI) — recently merged/proposed

### 2. Unit/Enum Validation Failures (#13, #18, #63, #77, #99, #131)

Recurring issue where new billing units from different utilities cause setup failures:
- `CF`, `CCF`, `10 CF`, `cm`, `CUBIC_FEET`, `GALLONS`, etc.
- Each new utility may use a different billing unit format
- Fix is always adding the new unit to the pyonwater enum

### 3. HA Version Breaking Changes (#14, #67, #109, #113, #117, #119, #122, #123, #128, #134)

The integration frequently breaks with HA updates:
- HA 2023.3: Sensor API changes
- HA 2024.9: Blocking call detection (pytz opens files synchronously)
- HA 2024.10: State class repair warning
- HA 2025.1: pydantic v2 migration, pyonwater package changes
- HA 2025.2: Requirements not found
- HA 2026.11: `async_import_statistics` requires `mean_type`

### 4. Negative/Rogue Values in Energy Dashboard (#30, #90, #92)

When HA recalculates statistics from a `TOTAL_INCREASING` sensor alongside retroactively imported statistics, it generates negative spikes. The workaround is removing `state_class` from the statistic sensor.

### 5. Invalid statistic_id (#2, #107)

Meter IDs with special characters (`+`, `-`, uppercase letters) fail HA's entity ID validation when used as statistic IDs. Fixed by normalizing IDs.

### 6. Historical Data Import Issues (#2, #82)

Users report that `import_historical_data` service finds data points but they don't appear in HA. Potentially related to long-term vs short-term statistics distinction.

---

## OPEN PULL REQUESTS

### PR #126 - Remove Statistics workaround
- **Author:** kdeyev
- **Opened:** Jan 7, 2025
- **Status:** Open
- **1 comment**

Attempts to remove the two-sensor workaround by restoring `state_class` to the sensor. Previous attempts (v2.4.0, v2.6.0-beta.1) caused negative values to return. This PR is for ongoing testing.

### PR #87 - Feature/unit tests
- **Author:** kdeyev
- **Opened:** Jan 27, 2024
- **Status:** Draft
- **No comments**

Adding unit tests for the integration.

### PR #137 - Feature/Expose unified sensor UI
- **Author:** jshessen
- **Opened:** ~3 days ago (Feb 2026)
- **Status:** Merged (recently)

Referenced from issue #30.

---

## KEY PEOPLE

- **kdeyev** — Repository owner, main developer
- **disforw** — Collaborator (joined via #20), contributed to pyonwater, multi-meter support
- **bsp9493** — Very active tester, provides detailed feedback
- **arpitgupta** — Frequent reporter of HA compatibility issues
- **jonofmac** — Deep technical analysis of the data import architecture (#124)
- **ParkerAnderson9** — Helped debug the negative values issue (#30)
- **ThirteenTX** — Active community member, Spook workaround suggestion
- **kohenkatz** — Recent community contributor helping with answers

---

## HA CORE REFERENCES

- `async_import_statistics()` — The HA Core API used to import retroactive statistics. Located in `homeassistant/components/recorder/statistics.py`
- `async_add_external_statistics()` — Alternative API for external statistics (referenced in early discussions)
- `home-assistant/core#100239` — PR for historical sensor support
- `home-assistant/architecture#964` — Architecture discussion on delayed data sensors
- `home-assistant/core#101490` — Fix in HA 2023.10.1 related to statistics import
- `home-assistant/core#95641` — DeviceInfo import location change
