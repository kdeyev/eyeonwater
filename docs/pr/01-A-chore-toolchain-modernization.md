# PR: chore/toolchain-modernization → master

## Summary

Consolidates all toolchain configuration into `pyproject.toml`, removes standalone
`mypy.ini`, `ruff.toml`, and `.flake8` files, bumps pre-commit hook versions, and
refreshes the poetry lockfile.  Applies the resulting formatting pass across production
code and existing test stubs.

**This PR contains zero runtime behaviour changes.**  It is safe to merge to `master`
immediately, independently of pyonwater 0.4.0.

---

## Target branch

`master` — base: `bc17084` (v2.6.0)

## CI Status

| Workflow | Result |
| ---------- | -------- |
| `pre-commit` | ✅ Passing |
| `Tests` | ✅ Passing |
| `hassfest` (validate) | ✅ Passing |

---

## Commits

| SHA | Message |
| ----- | --------- |
| `58b8917` | chore: modernize toolchain — consolidate config into pyproject.toml, update pre-commit hooks |

---

## Files changed (23 files, +5 566 −533)

| File | Change |
| ------ | -------- |
| `pyproject.toml` | Absorbs `[tool.ruff]`, `[tool.mypy]`, `[tool.black]` sections; adds `[tool.pytest.ini_options]` with `asyncio_mode = "strict"` and test-dep group |
| `ruff.toml` | **Deleted** — config moved to `pyproject.toml` |
| `mypy.ini` | **Deleted** — config moved to `pyproject.toml` |
| `.flake8` | Retained (empty placeholder) for legacy tooling compat |
| `.pre-commit-config.yaml` | ruff `v0.0.286` → `v0.12.9`, black `23.7.0` → `25.1.0`, mypy `v1.5.1` → `v1.14.0` |
| `.github/workflows/tests.yml` | Adds `python-version: "3.13"` matrix entry |
| `.gitignore` | Adds `.vscode/`, `*.code-workspace` |
| `poetry.lock` | Full lockfile refresh for updated dep versions |
| `custom_components/eyeonwater/__init__.py` | Type annotations; RUF006 fix (store `asyncio.create_task` return value) |
| `custom_components/eyeonwater/binary_sensor.py` | Type annotations; `DeviceInfo` import moved to `homeassistant.helpers.device_registry` |
| `custom_components/eyeonwater/config_flow.py` | `MappingProxyType` wrapping; `ConfigFlowResult` return type on `async_step_user` |
| `custom_components/eyeonwater/const.py` | Minor: adds `py.typed` marker reference |
| `custom_components/eyeonwater/coordinator.py` | Return type annotations |
| `custom_components/eyeonwater/sensor.py` | `RestoreEntity` base; type annotations; null guards |
| `custom_components/eyeonwater/statistic_helper.py` | `StatisticMeanType` try/except guard; `# type: ignore` comments; `MappingProxyType` wrapping |
| `custom_components/eyeonwater/system_health.py` | Type annotations |
| `tests/conftest.py` | Adds `asyncio_mode = "strict"` marker; `unit=NativeUnits.GAL` on `FakeDataPoint` |
| `tests/test_*.py` (5 stubs) | `+1` line each — trailing newline normalisation |
| `docs/pr/00-chain-overview.md` | **New** — stacked-PR chain overview document |

---

## Key changes

### Toolchain consolidation

```toml
# pyproject.toml (new sections)
[tool.ruff]
line-length = 120
select = ["ALL"]
...

[tool.mypy]
python_version = "3.13"
strict = true
...

[tool.pytest.ini_options]
asyncio_mode = "strict"
```

### mypy 1.14.0 compliance fixes

The bump from mypy 1.5.1 → 1.14.0 surfaced 35 new type errors across 7 files.  All
were resolved without `# type: ignore` except two unavoidable HA internal-API sites:

```python
# statistic_helper.py — StatisticMetaData(**kwargs) returns Any
return StatisticMetaData(**kwargs)  # type: ignore[typeddict-item, no-any-return]
```

### ruff RUF006 fix

```python
# __init__.py — before
asyncio.create_task(_start_listener(hass, entry, coordinator))

# after
_task = asyncio.create_task(_start_listener(hass, entry, coordinator))
entry.async_on_unload(lambda: _task.cancel())
```

---

## Notes

- All 52 existing tests pass.
- `pre-commit` exits 0 (ruff, black, mypy, codespell all clean).
- No pyonwater API changes; continues to use `^pyonwater==0.3.22`.
- **Safe to merge to `master` now**, without waiting for pyonwater 0.4.0.
