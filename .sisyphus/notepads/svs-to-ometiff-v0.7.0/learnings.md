# F3: Security & Scope Fidelity — Learnings

## Date: 2026-05-15

## Key Findings

1. **Version bump test sync**: When bumping package version, remember to search for
   hardcoded version strings in tests. `test_version_is_0_6_1` and
   `test_health_returns_200` in `test_config_and_health.py` assert the exact
   version string and must be updated together with `__init__.py`.

2. **Test file naming is flexible**: The plan specified `test_config_serialization.py`
   and `test_signal_handling.py` but implementation used `test_config.py` (expanded)
   and `test_shutdown.py`. The content is correct; naming is non-critical.

3. **release.yml was added outside plan scope**: The manual release dispatch workflow
   (`.github/workflows/release.yml`) was added as infrastructure commits before the
   feature commits. It's purely CI infrastructure and doesn't affect application code
   or the guardrail spirit.

4. **Signal handler gating works**: `_is_running_under_pytest()` using
   `PYTEST_CURRENT_TEST` env var correctly prevents signal handlers from installing
   during test runs. Verified in `test_shutdown.py`.

5. **imagecodecs stays optional for JPEG 2000**: The dependency was already present
   (pre-v0.6.x). JPEG 2000 is detected at runtime via `hasattr(imagecodecs, attr)`.

## Guardrail Summary
- 11/13: PASS
- 2/13: PASS with advisory notes (release.yml creation, version test assertions)
