---
name: bump-release
description: 'Bump the eyeonwater integration version and trigger the automated GitHub release for HACS distribution. Use this when asked to release, cut a new version, publish to HACS, create a release tag, or bump manifest.json. Covers version-check enforcement, release.yml trigger, HACS pickup, and pyonwater dependency pinning.'
---

# Bump Version and Release — eyeonwater

All releases are automated. The only manual steps are bumping the version in `manifest.json` and merging to `master`.

## Release Flow

```
bump version in custom_components/eyeonwater/manifest.json
        ↓
open PR against master (version-check.yml enforces the bump on every PR)
        ↓
merge to master
        ↓
release.yml detects version change → creates vX.Y.Z tag + GitHub release
        ↓
HACS picks up new release automatically via the GitHub release
```

## Steps

1. **Confirm the branch is ready**
   - All tests pass: `poetry run pytest -q`
   - Pre-commit hooks pass: `poetry run pre-commit run --all-files`
   - `CHANGELOG.md` updated with the changes in this release

2. **Bump the version** in `custom_components/eyeonwater/manifest.json`:
   ```json
   {
     "version": "X.Y.Z"
   }
   ```
   Follow semver. Pre-releases: use `X.Y.Z-beta.N` — `release.yml` marks these as pre-release on GitHub automatically.

3. **Commit the bump**:
   ```bash
   git add custom_components/eyeonwater/manifest.json CHANGELOG.md
   git commit -m "chore: bump version to X.Y.Z"
   ```

4. **Open a PR to `master`** — `version-check.yml` will validate that `manifest.json` version differs from the current `master` version. PRs that don't bump the version will fail this check.

5. **Merge the PR** — `release.yml` runs on push to `master`, compares the new version against the previous commit's `manifest.json`, and creates the tagged release if changed.

## Version Format

The version **only** lives in `manifest.json`. Do not update `pyproject.toml` version for releases — that file tracks the Python package dev tooling version.

- Stable: `2.5.16`
- Pre-release: `2.5.16-beta.1` (release marked pre-release on GitHub; HACS will not auto-update stable users)

## HACS Distribution

eyeonwater is distributed exclusively via HACS. HACS reads the GitHub releases list and picks up new versions automatically once the release.yml workflow creates the tag. No additional publishing step is needed.

## pyonwater Dependency

If this release bumps the minimum `pyonwater` version:
1. Update the `pyonwater` pin in both `[tool.poetry.dependencies]` and `[tool.poetry.group.test.dependencies]` in `pyproject.toml`
2. Run `poetry lock && poetry install`
3. Run the full test suite — pyonwater API changes can silently break coordinator data handling
