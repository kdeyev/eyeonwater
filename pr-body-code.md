## v2.7.0 — Configurable Display Unit, Cost Statistics Fixes, CI Upgrades

### Features
- **Configurable display unit**: Users can select their preferred water unit (gallons, liters, cubic meters, cubic feet) in the integration options flow. The selected unit is used for Energy Dashboard statistics.
- **Volume conversion**: Added `volume_conversion_factor()` and `_TO_CUBIC_METERS` mapping for accurate unit conversion in statistics.

### Fixes
- **Cost statistics**: Removed `unit_class: "monetary"` from cost statistics metadata (was incorrectly set).
- **Sensor state class**: Removed `_attr_state_class` from sensor entity — the integration uses external statistics architecture, so state_class is not applicable.

### CI / Tooling
- Upgraded GitHub Actions: `actions/checkout@v4`, `actions/setup-python@v5`
- CI now uses Python 3.13
- Consolidated ruff config: removed deprecated `PD901` rule
- Removed redundant `ruff.toml` (config consolidated into `pyproject.toml`)

### Changed files
- `custom_components/eyeonwater/` — config_flow, const, coordinator, sensor, statistic_helper, strings, translations
- `manifest.json` — version bump to 2.7.0
- `tests/` — updated coordinator, sensor, and statistic_helper tests
- `.github/workflows/` — hassfest.yaml, pre-commit.yml
- `pyproject.toml` — ruff config cleanup
