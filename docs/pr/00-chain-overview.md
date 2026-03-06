# Stacked-PR Chain Overview — eyeonwater Hardening & Feature Expansion

This document maps the `feature/unified-sensor-hardening` monolithic PR (#149) to a
**5-deep stacked-branch chain**, mirroring the review strategy used for
[kdeyev/pyonwater#46](https://github.com/kdeyev/pyonwater/pull/46).

---

## Chain Diagram

```markdown
kdeyev/eyeonwater:master  (bc17084 — v2.6.0)
│
├─ chore/toolchain-modernization           PR A  ← merge to master immediately
│     (zero-behavior toolchain changes)
│
└─ feat/statistics-integrity-engine        PR TBD  ← requires pyonwater 0.4.0
      (statistics_tools.py + statistic_helper.py rewrite)
      │
      └─ feat/coordinator-hardening        PR TBD
            (concurrent reads, empty-response fallback)
            │
            └─ feat/unified-sensor         PR TBD  (largest; pyonwater 0.4.0 required)
                  (EyeOnWaterUnifiedSensor, service actions, config flow)
                  │
                  └─ chore/tests-and-docs  PR TBD
                        (205-test suite, README, DEVELOPER_GUIDE, CHANGELOG)
```

---

## PR Summary Table

| # | Branch | Base | Core Commits | Files (key) | pyonwater |
| --- | --- | --- | --- | --- | --- |
| A | `chore/toolchain-modernization` | `master` | `ba2dbc8` `be4e657` | `pyproject.toml` `.pre-commit-config.yaml` `.github/workflows/` | 0.3.22 |
| B | `feat/statistics-integrity-engine` | PR A | `c6d6fc1` | `statistic_helper.py` `statistics_tools.py` (new) `const.py` | **0.4.0** |
| C | `feat/coordinator-hardening` | PR B | `d85aecd` | `coordinator.py` `const.py` `manifest.json` | **0.4.0** |
| D | `feat/unified-sensor` | PR C | `c226735` `edc115e` `5b3c5fd` | `sensor.py` `binary_sensor.py` `__init__.py` `config_flow.py` `services.yaml` `strings.json` | **0.4.0** |
| E | `chore/tests-and-docs` | PR D | `3cce814` `9fff13c` | `tests/` `docs/` `README.md` `CHANGELOG.md` | **0.4.0** |

---

## Commit-to-Branch Mapping

All commits are from `feature/unified-sensor-hardening` relative to `master`
(`bc17084`).  They are listed oldest-first.

### PR A — `chore/toolchain-modernization`

| SHA | Message | Notes |
| --- | --- | --- |
| `ba2dbc8` | chore: consolidate toolchain config into pyproject.toml | Migrates `ruff.toml` → `pyproject.toml [tool.ruff]`, removes `mypy.ini`, removes standalone `.flake8` |
| `be4e657` | ci: update pre-commit hooks and GitHub Actions workflow | ruff `v0.0.286` → `v0.12.9`, black `23.7.0` → `25.1.0`, mypy `v1.5.1` → `v1.14.0` |
| `cbeca5a` | fix: align pyonwater 0.3.22, add test dep group, explicit asyncio_mode=strict | pyproject.toml test-dep group, `asyncio_mode = "strict"` |
| `b99fd26` | chore: update poetry.lock and fix docs typo | poetry.lock refresh |

Fixup passes through: `cb5cf6b` (pre-commit format pass against this branch's pyproject.toml).

**This PR has no pyonwater 0.4.0 dependency and can be merged to `master` immediately.**

---

### PR B — `feat/statistics-integrity-engine`

| SHA | Message | Notes |
| --- | --- | --- |
| `c6d6fc1` | feat: statistics integrity engine — carry-forward repair, monotonicity, and compiler contamination fixes | Full `statistic_helper.py` rewrite; new `statistics_tools.py` |

Key new exports in `statistic_helper.py`:

- `centralized_import_statistics` — single LTS import entry point (consumption + cost)
- `async_write_carry_forward_stats` — detects/repairs sum=0 compiler rows
- `async_get_highest_sum_stat` — max-sum anchor (uncorrupted baseline)
- `async_get_stat_just_before` — backfill overlap base detection
- `async_delete_statistics_after`, `async_delete_all_short_term_statistics`, `async_delete_entity_states`
- `convert_statistic_data` — integrates `enforce_monotonic_total(clamp_min=None)`
- `convert_cost_statistic_data` — parallel cost LTS rows

New module `statistics_tools.py`:

- `MonotonicViolation` / `MonotonicValidationResult` dataclasses
- `validate_monotonic_sums` — batched LTS scan for sum regressions
- `delete_statistics`, `resolve_statistic_id`

Changed constants in `const.py`: `STATISTICS_VALIDATION_BATCH_SIZE`, `MAX_VIOLATION_LOG_DISPLAY`, `COST_STAT_SUFFIX`.

**Requires pyonwater 0.4.0** (`enforce_monotonic_total`, `filter_points_after`).

---

### PR C — `feat/coordinator-hardening`

| SHA | Message | Notes |
| --- | --- | --- |
| `d85aecd` | feat: coordinator hardening — API resilience, empty-response fallback, and startup reconciliation | |
| `373784f` | fix: add energy to after_dependencies in manifest.json (hassfest) | |
| `1f0f0b6` | fix: correct manifest key order and version indentation (hassfest) | |

Key changes in `coordinator.py`:

- `read_meters` → concurrent via `asyncio.gather` (`_read_single_meter`)
- Empty-response fingerprint fallback (`"json_invalid"` / `"EOF while parsing"`) retries with `days_to_load=1`
- `import_historical_data` gains `force_overwrite`, `purge_states` kwargs
- Per-meter `try/except` in import loop
- `resolve_price_from_energy_manager` helper (reads HA Energy Manager for water source price)

`manifest.json`: adds `"after_dependencies": ["energy"]`.

---

### PR D — `feat/unified-sensor`

| SHA | Message | Notes |
| --- | --- | --- |
| `c226735` | feat: unified single-sensor architecture, UI options, service actions, and pyonwater upgrade | Largest commit |
| `5b3c5fd` | fix: populate binary sensor state immediately on startup when coordinator has fresh data | |
| `edc115e` | feat: auto-resolve price from HA Energy Dashboard; remove custom cost option UI | |
| `ed9297b` | fix: resolve hassfest CI validation errors | |
| `b6ccc01` | fix: add type annotations across production components | |
| `cb5cf6b` | fix: pre-commit formatting — black reformats, trailing whitespace, eof newline | |
| `deb77fd` | ci: require pyonwater==0.4.0; document failing Tests workflow in PR.md | Sets CI requirement; intentionally breaks `Tests` workflow until pyonwater 0.4.0 lands on PyPI |

Key changes:

- `sensor.py`: replaces `EyeOnWaterSensor(CoordinatorEntity)` with `EyeOnWaterUnifiedSensor(RestoreEntity)` — one sensor per meter, `TOTAL_INCREASING`, carries-forward LTS on startup
- `binary_sensor.py`: MRO fix (`CoordinatorEntity, BinarySensorEntity, RestoreEntity`), type annotations, startup state population
- `config_flow.py`: `EyeOnWaterOptionsFlow`, `is_matching`, typed params, `METRIC_SYSTEM` country display
- `__init__.py`: 5 service handlers (`import_historical_data`, `replay_scenario`, `validate_statistics_monotonic`, `read_meter`, `reset_statistics`)
- `services.yaml`: full service schema for all 5 services
- `strings.json`: `services:` block, options flow strings
- `const.py`: all service-name constants, `CLIENT_TIMEOUT`, `DEBOUNCE_COOLDOWN`

---

### PR E — `chore/tests-and-docs`

| SHA | Message | Notes |
| --- | --- | --- |
| `3cce814` | chore: comprehensive test suite, CI pipeline, linting, and developer tooling | 205 tests, 78% coverage |
| `9fff13c` | test: fix capture_entities in test_binary_sensor, minor test_init update | |

Test files added:

| File | Tests | Focus |
| --- | --- | --- |
| `test_sensor.py` | 18 | Unified sensor state machine, `extra_state_attributes` cache |
| `test_coordinator.py` | 19 | Error matrix, empty-response fallback, import/purge flows |
| `test_binary_sensor.py` | 31 | Flag sensor setup, state updates, entity restore |
| `test_statistic_helper.py` | 42 | Unit conversion, ID normalisation, `convert_*`, cost helpers |
| `test_statistics_tools.py` | 25 | `MonotonicViolation`, `validate_monotonic_sums`, delete helpers |
| `test_integration.py` | varies | End-to-end import pipeline, backfill overlap, multi-meter |
| `test_edge_cases.py` | varies | DST boundaries, leap year, unicode IDs, out-of-order timestamps |
| `test_performance.py` | varies | Large series timing, memory regression |
| `test_config_flow.py` | varies | Credential validation, options flow, country→hostname |
| `test_const.py` / `test_imports.py` / `test_init.py` / `test_system_health.py` | varies | Contract/smoke |

Docs added:

- `docs/DEVELOPER_GUIDE.md` — architecture, Mermaid data-flow diagram, compiler timing risk
- `docs/CUSTOM_COST_OPTION.md` — cost stat setup, Energy Dashboard wiring
- `README.md` — unified sensor setup, service reference, cost override section
- `CHANGELOG.md` — v2.7.0-dev entry

---

## pyonwater Dependency Matrix

| PR | Can merge to master today? | Reason |
| --- | --- | --- |
| A `chore/toolchain-modernization` | ✅ **Yes** | No pyonwater API changes; uses 0.3.22 |
| B `feat/statistics-integrity-engine` | ⏳ After pyonwater 0.4.0 published | Imports `enforce_monotonic_total`, `filter_points_after` |
| C `feat/coordinator-hardening` | ⏳ After PR B | Imports from PR B's helpers |
| D `feat/unified-sensor` | ⏳ After PR C | Imports `AggregationLevel` (pyonwater 0.4.0) |
| E `chore/tests-and-docs` | ⏳ After PR D | Tests the full stack |

**Suggested merge order:**

1. Merge `kdeyev/pyonwater#46` → publish `pyonwater==0.4.0` to PyPI
2. Merge PR A immediately (no dependency)
3. Open PRs B–E as stacked chain; merge in order B → C → D → E once 0.4.0 is published

---

## CI Status (as of PR #149 tip `1f0f0b6`)

| Workflow | Status | Notes |
| --- | --- | --- |
| `hassfest` | ✅ Passing | manifest.json valid |
| `pre-commit` | ✅ Passing | ruff, black, mypy, codespell all green |
| `Tests` | ❌ Known failure | `pyonwater==0.4.0` not yet on PyPI |

---

## Branch Creation Commands

To materialise the chain from the current `feature/unified-sensor-hardening` branch:

```bash
BASE=master
REPO=/home/jshessen/Development/GitHub/eyeonwater
cd "$REPO"

# ── PR A ──────────────────────────────────────────────────────────────────────
git checkout -b chore/toolchain-modernization "$BASE"
git cherry-pick ba2dbc8 be4e657 cbeca5a b99fd26

# ── PR B ──────────────────────────────────────────────────────────────────────
git checkout -b feat/statistics-integrity-engine chore/toolchain-modernization
git cherry-pick c6d6fc1

# ── PR C ──────────────────────────────────────────────────────────────────────
git checkout -b feat/coordinator-hardening feat/statistics-integrity-engine
git cherry-pick d85aecd 373784f 1f0f0b6

# ── PR D ──────────────────────────────────────────────────────────────────────
git checkout -b feat/unified-sensor feat/coordinator-hardening
git cherry-pick c226735 5b3c5fd edc115e ed9297b b6ccc01 cb5cf6b deb77fd

# ── PR E ──────────────────────────────────────────────────────────────────────
git checkout -b chore/tests-and-docs feat/unified-sensor
git cherry-pick 3cce814 9fff13c
```

> **Note:** Due to the interleaved nature of fixup commits, cherry-picks may encounter
> minor conflicts (particularly in `pyproject.toml` and `manifest.json`).  Resolve by
> keeping the most complete/final version of each changed section.

---

## Key Architectural Decisions

### Why `sensor.water_meter_*` not `eyeonwater:water_meter_*`?

PR D shifts the statistic ID from the `eyeonwater:` external-statistics namespace to the
`sensor.` recorder namespace.  This allows `TOTAL_INCREASING` state-class cost calculation
to work natively in the Energy Dashboard without a separate external-statistic entity.

### Why split statistics engine from coordinator?

`statistic_helper.py` is a pure HA-recorder interface layer with no EyeOnWater API
dependency.  Reviewing it independently (PR B) lets the maintainer verify the DB math
before evaluating the API-facing coordinator changes (PR C).

### Why is PR A independent?

`chore/toolchain-modernization` contains zero runtime behaviour changes (cfg file
consolidation, pre-commit version bumps, CI workflow additions).  Merging it early
reduces diff noise in all subsequent PRs and unblocks the CI pipeline improvements.

---

## Generated from feature/unified-sensor-hardening (tip: 1f0f0b6) against master (bc17084)
