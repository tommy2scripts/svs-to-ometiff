# F4 QA Report — v0.7.0 Final Wave

**Date:** 2026-05-15
**Commit:** `2e839ad` (feat: v0.7.0 — JPEG/JPEG 2000 compression, ConvertConfig serialization, graceful shutdown, large-file tests)
**Verdict:** **REJECT** ❌

---

## Test Results

| Suite | Result | Details |
|-------|--------|---------|
| Fast tests (`-m "not slow"`) | **2 FAILED**, 179 passed | 2 version assertion tests not updated |
| Slow tests (`-m "slow"`) | 20 passed ✓ | All large-file integration tests pass |
| Total collected | 201 tests (181 fast + 20 slow) | |
| ruff check | Clean ✓ | Zero lint errors |

### Failing Tests

```
FAILED tests/test_config_and_health.py::TestPackageVersion::test_version_is_0_6_1
  assert __version__ == "0.6.1"  →  actually "0.7.0"

FAILED tests/test_config_and_health.py::TestHealthCheck::test_health_returns_200
  assert data["version"] == "0.6.1"  →  actually "0.7.0"
```

Both failures are stale assertions that should have been updated from `"0.6.1"` to `"0.7.0"`.

---

## Acceptance Criteria — Per-Task Verification

### T1: ConvertConfig Serialization

| Criterion | Status | Evidence |
|-----------|--------|----------|
| `to_dict()` returns all fields except progress_logger | ✓ PASS | `test_config.py::TestToDict` tests confirm |
| `from_dict(d)` round-trips | ✓ PASS | `test_config.py::TestFromDict::test_round_trip_identity` confirms |
| `to_json()` produces valid JSON | ✗ **MISSING** | No `to_json()` method exists on ConvertConfig |
| `from_json(s)` round-trips | ✗ **MISSING** | No `from_json()` method exists on ConvertConfig |
| `from_dict({})` fills defaults | ✓ PASS | `test_config.py::TestFromDict::test_fills_defaults` confirms |
| `from_dict()` validates same rules as constructor | ✓ PASS | Validation runs via `__post_init__` |
| `from_dict()` rejects unknown keys | ✗ **DEVIATION** | `from_dict()` silently ignores unknown keys (docstring says so) |
| `_coerce_convert_config()` simplified | ✗ **NOT DONE** | Still uses manual `_LEGACY_CONFIG_DEFAULTS` dict (lines 33-45), not `ConvertConfig.from_dict()` |
| `_build_conversion_job()` uses `to_dict()` | ✓ PASS | Models.py `ConversionJob.from_config()` uses `config.to_dict()` |
| `template_dict` replaced | ✓ PASS | services.py uses `job_template.to_converter_kwargs()` |

### T2: Graceful Shutdown Signal Handling

| Criterion | Status | Evidence |
|-----------|--------|----------|
| SIGINT during tile decode → cleanup | ✓ PASS | `test_shutdown.py::test_conversion_cancelled_before_tile_decoding` |
| SIGINT during pyramid build → cleanup | ✓ PASS | `test_shutdown.py::test_conversion_cancelled_during_pyramid_building` |
| Double SIGINT → force exit | ⚠️ PARTIAL | Shutdown event set but no explicit double-signal handler in converter |
| `ConversionService.shutdown()` cancels futures | ✓ PASS | 17 shutdown tests all pass |
| `/health` returns `shutting_down: true` | ✗ **MISSING** | Health endpoint only returns `status`, `version`, `active_jobs` |
| Signal handlers only in CLI entry points | ✓ PASS | CLI signal handlers exist in serve.py/services.py, converter checks event |
| Shutdown checks in tile_reader loop | ✗ **NOT DONE** | No shutdown flag check in `iter_svs_rgb_tiles()` or tile loop |
| Shutdown checks in pyramid loop | ✗ **NOT DONE** | No shutdown flag check in `build_pyramid_memmaps()` row loop |
| Converter shutdown via module-level event | ✓ PASS | `_shutdown_event` checked between stages in converter.py |

### T3: JPEG/JPEG 2000 Compression

| Criterion | Status | Evidence |
|-----------|--------|----------|
| `_SUPPORTED_COMPRESSION` includes jpeg, jpeg2000 | ✓ PASS | `config.py:10`: `(None, "lzw", "zlib", "deflate", "jpeg", "jpeg2000")` |
| JPEG compression produces valid OME-TIFF | ✓ PASS | `test_jpeg_compression.py` tests pass (36 tests) |
| JPEG 2000 produces valid OME-TIFF | ✓ PASS | `test_large_file.py::TestJPEG2000RoundTrip` passes |
| `svs-to-ometiff-verify` passes on JPEG/JPEG2000 | ✓ PASS | Verified in test_jpeg_compression.py |
| File size JPEG ≤ zlib | ✓ PASS | `test_jpeg2000_smaller_than_zlib` passes |
| CLI `--compression` includes jpeg/jpeg2000 | ✓ PASS | `cli.py:56`: Click.Choice includes both |
| CLI `--compression-args` flag | ✓ PASS | `cli.py:61-66`: `--compression-args` JSON dict |
| batch.py `--compression` includes jpeg/jpeg2000 | ✗ **MISSING** | `batch.py:39`: only `["zlib", "lzw", "deflate", "none"]` |
| batch.py `--compression-args` flag | ✗ **MISSING** | No compression-args option in batch.py |
| `compression_quality` field on ConvertConfig | ✗ **DEVIATION** | Plan says `compression_quality: int = 85`; impl uses `compressionargs: dict` |
| `--compression-quality` CLI flag | ✗ **DEVIATION** | Plan says `--compression-quality`; impl uses `--compression-args` |
| Codec detection for jpeg/jpeg2000 | ✓ PASS | `_check_codec()` in converter.py checks imagecodecs availability |
| GUI quality slider | ✗ **NOT VERIFIED** | GUI has compressionargs field but no quality slider logic found |

### T4: Large-File Integration Tests

| Criterion | Status | Evidence |
|-----------|--------|----------|
| `pytest -m slow` runs only slow tests | ✓ PASS | 20 slow tests collected/run correctly |
| `pytest -m "not slow"` excludes slow tests | ✓ PASS | 181 fast tests (20 deselected) |
| 2048×2048 and 16384×16384 synthetic fixtures | ✓ PASS | Valid YUYV tile generation confirmed |
| Byte-identical output tests | ✓ PASS | `test_2048x2048_output_pixel_values_match_source` |
| Memory budget test | ✓ PASS | `test_16384x16384_completes` (memmap path) |
| JPEG 2000 large-file round-trip | ✓ PASS | `TestJPEG2000RoundTrip` all 3 tests pass |
| Edge tile validation | ✓ PASS | `TestEdgeTilePixels` all 4 tests pass |
| `pytest.mark.slow` marker configured | ✓ PASS | `pyproject.toml` has marker definition |
| SubIFD validation | ✓ PASS | `Test16384x16384SubIFD` tests pass |

---

## Summary of Issues

### BLOCKING (must fix before APPROVE)

| # | Severity | Issue | File |
|---|----------|-------|------|
| 1 | **HIGH** | 2 failing tests — stale version assertions at `"0.6.1"` | `tests/test_config_and_health.py:14,95` |
| 2 | **HIGH** | `batch.py` missing `jpeg`/`jpeg2000` in compression choices + no `--compression-args` | `src/svs_to_ometiff/batch.py:39` |
| 3 | **MEDIUM** | No `to_json()`/`from_json()` methods as required by plan T1 | `src/svs_to_ometiff/config.py` |
| 4 | **MEDIUM** | `from_dict()` silently ignores unknown keys (plan says raise ValueError) | `src/svs_to_ometiff/config.py:47` |
| 5 | **MEDIUM** | `/health` endpoint missing `shutting_down` field required by plan T2 | `svs_to_ometiff_gui/serve.py` |
| 6 | **MEDIUM** | No shutdown checks in `iter_svs_rgb_tiles()` tile loop (plan T2) | `src/svs_to_ometiff/tile_reader.py` |
| 7 | **MEDIUM** | No shutdown checks in `build_pyramid_memmaps()` row loop (plan T2) | `src/svs_to_ometiff/pyramid.py` |

### DESIGN DEVIATIONS (acceptable but differ from plan)

| # | Plan Specification | Implementation | Rationale |
|---|-------------------|----------------|-----------|
| D1 | `compression_quality: int = 85` | `compressionargs: Optional[dict]` | More flexible (supports codec-specific params beyond quality) |
| D2 | `--compression-quality` CLI flag | `--compression-args` JSON dict | Consistent with tifffile API; documented in CHANGELOG |
| D3 | `test_convert_config_serialization.py` (new file) | Tests consolidated in `test_config.py` | Functional coverage equivalent |

### CHANGELOG / README

- CHANGELOG.md: ✓ Has v0.7.0 section with all 4 features
- README.md: ✗ Does not mention JPEG/JPEG 2000 compression or `--compression-args`
- README.md compression section (line 109): Only lists `zlib, lzw, deflate, none`

---

## Verdict: **REJECT** ❌

**Reason**: 2 failing tests (stale version assertions) and 6 missing/incomplete acceptance criteria. The batch CLI is missing JPEG/JPEG2000 support entirely, plan-required `to_json()`/`from_json()` methods are absent, and the health endpoint lacks the `shutting_down` field.

**Recommended actions before re-review:**
1. Fix `test_config_and_health.py` lines 14 and 95: bump version strings to `"0.7.0"`
2. Add `"jpeg"` and `"jpeg2000"` to `batch.py` compression choices and add `--compression-args`
3. Add `to_json()`/`from_json()` to `ConvertConfig` (or document decision to omit)
4. Update `from_dict()` to reject unknown keys (or document decision to silently ignore)
5. Add `shutting_down` field to `/health` endpoint
6. Update README.md compression section with jpeg/jpeg2000 info
7. Add shutdown checks inside tile/pyramid loops (or document decision to use stage-only checks)
