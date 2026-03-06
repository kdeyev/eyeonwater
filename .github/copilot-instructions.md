# eyeonwater — Project Instructions

## What This Project Is

`eyeonwater` is a Home Assistant custom integration that wraps the `pyonwater` library to expose EyeOnWater water meter data as HA sensors, binary sensors, and long-term statistics. It lives in `custom_components/eyeonwater/` and follows HA integration quality standards.

## Architecture

```
custom_components/eyeonwater/
  __init__.py           # Integration entry point — async_setup_entry, services
  coordinator.py        # DataUpdateCoordinator — single polling source of truth
  sensor.py             # Sensor entities (water usage, cost, etc.)
  binary_sensor.py      # Binary sensor entities (leak alerts, etc.)
  config_flow.py        # Config flow — credentials entry, options flow, reauth
  statistic_helper.py   # Long-term statistics injection into HA recorder
  statistics_tools.py   # Utilities: delete, validate, replay statistics
  const.py              # All constants — DOMAIN, keys, scan intervals, defaults
  strings.json          # Translation source strings
  translations/en.json  # English translations

tests/
  conftest.py           # Shared hass instance, MockConfigEntry fixtures
  test_coordinator.py   # Coordinator update cycle and error handling
  test_sensor.py        # Sensor entity states
  test_binary_sensor.py # Binary sensor entity states
  test_config_flow.py   # Config flow steps and error paths
  test_statistic_helper.py  # Statistics injection
  test_init.py          # Integration setup and service registration
```

## Core HA Integration Conventions

1. **Coordinator is the data source** — entities read exclusively from `coordinator.data`; they never call pyonwater directly.
2. **`async_setup_entry` is the entry point** — YAML-based `async_setup` is deprecated; do not use it.
3. **`async_config_entry_first_refresh()`** must be awaited in `async_setup_entry` to surface initial auth failures cleanly.
4. **Entity unavailability** — entities must become unavailable when `coordinator.last_update_success` is `False`; never leave stale state on coordinator failure.
5. **`CoordinatorEntity` base class** — all entities must inherit from `CoordinatorEntity` to get automatic availability and update handling.
6. **Async-first** — all HA callbacks and setup methods must be `async def`; never block the event loop.
7. **Type annotations required** on every function signature and class attribute; the project runs `mypy strict`.
8. **No inline suppressions** — `# noqa`, `# type: ignore`, `# pylint: disable` require a justification comment. Exception: HA stub gaps (see linter agent for documented patterns).
9. **Translation strings** — every user-visible string goes in `strings.json` and `translations/en.json`; never hardcode UI text.
10. **Constants in `const.py`** — no magic numbers or magic strings inline; use named constants.

## Toolchain

| Tool | Config section | Purpose |
|---|---|---|
| `ruff` | `[tool.ruff.lint]` — `select = ["ALL"]` | Linting — strict, all rules |
| `mypy` | `[tool.mypy]` | Type checking — `strict = true` |
| `black` | `[tool.black]` | Formatting — target py313 |
| `isort` | `[tool.isort]` | Import sorting — black profile |
| `pylint` | `[tool.pylint]` | HA-specific lint rules |
| `pyright` | `[tool.pyright]` | IDE type checking (suppressed HA false positives) |
| `pytest` | `[tool.pytest.ini_options]` | Tests in `tests/`, `asyncio_mode = strict` |
| `pytest-cov` | `[tool.coverage]` | Coverage reporting |
| `pytest-homeassistant-custom-component` | test dep | HA core test harness |

**Note on pyright suppression:** `pyright` has several `"none"` suppressions in `pyproject.toml` for HA multi-inheritance false positives (`reportIncompatibleVariableOverride`, `reportIncompatibleMethodOverride`, etc.). These are documented with justifications — do not remove them without understanding the HA framework root cause.

## pyonwater Dependency

This integration pins `pyonwater` in `pyproject.toml`. When pyonwater releases a new version:
1. Update the pin in both `[tool.poetry.dependencies]` and `[tool.poetry.group.test.dependencies]`
2. Run the full test suite — pyonwater API changes can silently break coordinator data handling
3. Check that all pydantic model fields used in `coordinator.py` still exist

## Test Infrastructure

- Use `MockConfigEntry` — never construct `ConfigEntry` directly
- Mock pyonwater at the boundary: patch `EyeOnWaterClient` or `Account` in `coordinator.py`
- Use `freezegun` or `async_fire_time_changed` for time-dependent statistics tests
- `asyncio_mode = strict` — fixtures must explicitly declare `async` scope

## Agent Roster

When working on multi-step tasks, these specialist agents are available in the Copilot agents dropdown:

| Agent | Activated as | Focus |
|---|---|---|
| Supervisor | `supervisor` | Orchestration, task decomposition |
| Coder | `coder` | Feature implementation, HA patterns |
| Linter | `linter` | ruff ALL, mypy, black, isort, pylint — zero suppression |
| Tester | `tester` | pytest + HA test harness, coverage |
| Auditor | `auditor` | Security, performance, HA-specific NFRs |
| Critic | `critic` | Adversarial review, HA standards enforcement |

**When operating in default Agent mode**, if the user's request involves more than one of: implementation, linting, testing, security review, or code review — suggest switching to the `supervisor` agent to coordinate the work. For single-concern tasks (e.g. "fix this lint error", "write a test for X"), activate the relevant specialist agent directly.
