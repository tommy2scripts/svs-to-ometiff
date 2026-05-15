# svs-to-ometiff v0.7.0 Implementation Plan

> **For Sisyphus:** Execute tasks in waves. Dispatch each task to a fresh agent. Review between waves.
>
> **For Agents:** Read the acceptance criteria before starting. Each checkbox is a hard requirement.

**Goal:** Ship 4 targeted features: ConvertConfig serialization, graceful shutdown, JPEG/JPEG 2000 compression, and large-file integration tests — without breaking the 112 existing tests.

**Baseline:** v0.6.1 (commit `b7c0e79`), 28 Python files, ~4,711 LOC, 112 tests passing.

**Output:** v0.7.0 release candidate.

**Tech Stack:** Python 3.9-3.13, tifffile, imagecodecs, click, Flask. No new dependencies.

---

## Must Have / Must NOT Have

### Must Have
- [x] `ConvertConfig.to_dict()` and `ConvertConfig.from_dict()` methods with round-trip identity
- [x] SIGINT/SIGTERM handlers clean up temp files and exit non-zero
- [x] `jpeg` and `jpeg2000` compression options produce valid OME-TIFF
- [x] `--compression-quality` CLI flag (0-100, JPEG/JPEG2000 only)
- [x] Large-file integration tests (4096×4096, 8192×8192 synthetic SVS)
- [x] `pytest.mark.slow` marker; CI excludes slow tests by default
- [x] All 112 existing tests continue to pass

### Must NOT Have
- [x] No new PyPI dependencies (stdlib only for new code)
- [x] No CLI breaking changes (no flag removals, no positional arg changes)
- [x] No pipeline architecture changes (converter.py flow unchanged)
- [x] No parallel tile decoding (deferred to v0.8.0)
- [x] No multi-format WSI input support (deferred to v0.8.0)
- [x] No OpenAPI/Swagger docs (deferred to v0.8.0)
- [x] No premature optimization

---

## Pre-Flight Checks (must pass before any task starts)

```bash
# 1. Verify baseline
cd /Users/tommytran/svs2ometiff/svs-to-ometiff
git log --oneline -1               # Expected: b7c0e79
python -m pytest tests/ -x -q       # Expected: 112 passed

# 2. Verify version
grep 'version = "0.6.1"' pyproject.toml   # Expected: match
```

---

## Dependency Matrix

```
         T1 (Serialization)   T2 (Signals)   T3 (JPEG)   T4 (Large Tests)
T1        -                    ✗              ✗           ✗
T2        ✗                    -              ✗           ✗
T3        ✗                    ✗              -           ✓ (test infra)
T4        ✗                    ✗              ✓           -

✗ = no dependency, can run in parallel
✓ = direct dependency
```

---

## Execution Waves

### Wave 1 — Foundations (Tasks 1 + 2, parallel)

| # | Task | Agent Category | Description |
|---|------|---------------|-------------|
| T1 | Config Serialization | `quick` | Add `to_dict()`/`from_dict()`/`to_json()`/`from_json()` to `ConvertConfig` |
| T2 | Graceful Shutdown | `unspecified-high` | SIGINT/SIGTERM handlers, shutdown checks in loops, `ConversionService.shutdown()` |

**T1 and T2 are independent.** Dispatch to two agents simultaneously.

### Wave 2 — Compression (Task 3)

| # | Task | Agent Category | Description |
|---|------|---------------|-------------|
| T3 | JPEG/JPEG 2000 Compression | `unspecified-high` | Extend `_SUPPORTED_COMPRESSION`, add `compression_quality`, update CLI/batch/GUI |

**T3 depends on all previous tests still passing after Wave 1.**

### Wave 3 — Validation (Task 4)

| # | Task | Agent Category | Description |
|---|------|---------------|-------------|
| T4 | Large-File Integration Tests | `unspecified-high` | Synthetic 4096×4096 and 8192×8192 SVS fixtures, `pytest.mark.slow` |

**T4 validates all features together on large files.**

### Final Verification Wave — Reviewers (F1-F4, parallel)

| # | Reviewer | Agent Category | Description |
|---|----------|---------------|-------------|
| F1 | Oracle | `deep` | Goal/constraint verification — did we ship what the plan promised? |
| F2 | Oracle | `deep` | Code quality review — architecture, patterns, naming, DRY |
| F3 | Oracle | `deep` | Security review — temp file safety, signal safety, pickle safety |
| F4 | QA | `unspecified-high` | Hands-on QA — run full test suite, CLI smoke tests, manual GUI check |

**All 4 reviewers run in parallel after Task 4 completes.**

---

---

## Task 1: ConvertConfig Serialization

**Agent Category:** `quick`
**Files:** `src/svs_to_ometiff/config.py`, `src/svs_to_ometiff/converter.py`, `svs_to_ometiff_gui/serve.py`, `svs_to_ometiff_gui/services.py`, `tests/` (new test file)

### Description
Add `to_dict()`, `from_dict()`, `to_json()`, and `from_json()` methods to the frozen `ConvertConfig` dataclass. Replace ad-hoc dict construction in `_coerce_convert_config()`, `_build_conversion_job()`, and `services.py` `template_dict` with canonical serialization. `ProgressLogger` (a `Callable`) is excluded from serialization — it cannot be JSON-serialized and must be set separately via the constructor.

### Acceptance Criteria
- [ ] `ConvertConfig.to_dict()` returns all fields except `progress_logger` as a JSON-serializable dict
- [ ] `ConvertConfig.from_dict(d)` round-trips: `from_dict(cfg.to_dict()) == cfg` (ignoring `progress_logger`)
- [ ] `ConvertConfig.to_json()` produces valid JSON string; `from_json(s)` round-trips
- [ ] `from_dict({})` fills all defaults (except `input_svs`/`output_ometiff` which are required)
- [ ] `from_dict()` validates same rules as constructor (fail-fast on invalid values)
- [ ] `from_dict()` with unknown keys raises `ValueError`
- [ ] `_coerce_convert_config()` in `converter.py:76-102` simplified to use `ConvertConfig.from_dict()` under the hood
- [ ] `_build_conversion_job()` in `serve.py:87-125` uses `ConvertConfig.to_dict()` instead of manual `ConversionJob` construction
- [ ] `template_dict` in `services.py:299-306` replaced with `job_template.to_converter_kwargs()` or `ConvertConfig.to_dict()`
- [ ] All 112 existing tests pass

### Must Do
- Keep `ConvertConfig` frozen (@dataclass(frozen=True))
- `to_dict()` returns a plain `dict[str, Any]` — no nested dataclass objects
- `from_dict()` uses `dataclasses.replace()` style: take a dict, construct a new instance
- Exclude `progress_logger` from `to_dict()`; `from_dict()` sets it to `None` by default
- Add validation: `from_dict()` must reject unknown keys
- Base conversions: `None` → Python `None`, `int` → `int`, `str` → `str`, `bool` → `bool`
- `to_json()` uses `json.dumps()`; `from_json()` uses `json.loads()` then delegates to `from_dict()`

### Must NOT Do
- Do NOT change `ConvertConfig` constructor signature
- Do NOT remove `_LEGACY_CONFIG_DEFAULTS` (still needed for backward compat)
- Do NOT change `_coerce_convert_config()` public behavior
- Do NOT serialize `progress_logger` (it's a callable, not JSON-safe)

### Injection Points (exact line numbers)
| File | Lines | Change |
|------|-------|--------|
| `config.py` | 11-49 | Add `to_dict()`, `from_dict()`, `to_json()`, `from_json()` |
| `converter.py` | 76-102 | Simplify `_coerce_convert_config()` using serialization |
| `serve.py` | 106-114 | Use `ConvertConfig.to_dict()` then `ConversionJob` |
| `services.py` | 299-306 | Replace `template_dict` with `ConvertConfig.to_dict()` |

### Test Strategy
- **Unit:** `test_convert_config_serialization.py` — new test file
  - `test_to_dict_keys` — all expected keys present, `progress_logger` absent
  - `test_round_trip_identity` — `from_dict(to_dict(cfg)) == cfg`
  - `test_from_dict_partial` — partial dict fills defaults
  - `test_from_dict_validation` — invalid values raise `ValueError`
  - `test_from_dict_unknown_key` — extra keys raise `ValueError`
  - `test_json_round_trip` — `from_json(to_json(cfg)) == cfg`
  - `test_progress_logger_excluded` — `progress_logger` not in `to_dict()` output
- **Integration:** Existing `test_models.py`, `test_services_start_conversion.py`, `test_routes.py` continue to pass
- **Regression:** `pytest tests/ -x -q` → 112 existing + new = all pass

---

## Task 2: Graceful Shutdown Signal Handling

**Agent Category:** `unspecified-high`
**Files:** `src/svs_to_ometiff/cli.py`, `src/svs_to_ometiff/converter.py`, `src/svs_to_ometiff/tile_reader.py`, `src/svs_to_ometiff/pyramid.py`, `svs_to_ometiff_gui/services.py`, `svs_to_ometiff_gui/serve.py`, `tests/` (new test file)

### Description
Register `SIGINT` and `SIGTERM` signal handlers that set a `threading.Event` flag. Long-running loops in `iter_svs_rgb_tiles()`, `_stage_level0_memmap()`, and `build_pyramid_memmaps()` check this flag periodically. On shutdown: flush memmaps, close file handles, delete temp files. The GUI `ConversionService` gets a `shutdown()` method that cancels pending futures, waits for completion with timeout, and cleans up. Double-signal (second SIGINT) triggers force exit.

### Acceptance Criteria
- [ ] SIGINT during tile decode → temp dir removed, process exits with code ≠ 0
- [ ] SIGINT during pyramid build → temp dir removed, process exits with code ≠ 0
- [ ] SIGTERM during OME-TIFF write → temp file removed, output file not corrupted
- [ ] Double SIGINT (second signal) → force exit (no hang)
- [ ] `ConversionService.shutdown()` cancels pending futures, joins within 30s timeout
- [ ] GUI `/health` endpoint returns `shutting_down: true` during shutdown
- [ ] Signal handlers are registered only in CLI entry points (not in library `convert()`)
- [ ] All 112 existing tests pass (no signals during test runs)

### Must Do
- Use `signal.signal(signal.SIGINT, handler)` and `signal.SIGTERM` (stdlib, no new dep)
- Use `threading.Event` as the shutdown flag (thread-safe, no atomic needed)
- Check the flag at the start of each loop iteration (tile loop, pyramid row loop)
- On shutdown: call `cleanup_pyramid_memmaps()` + `shutil.rmtree(temp_dir)` + flush open memmaps
- Double-signal: track first signal received, second triggers `os._exit(1)`
- Register handlers only in `cli.py:main()` and `batch.py:main()` — NOT in library code
- GUI: Add `shutdown()` method to `ConversionService` class
- GUI: Set a `_shutting_down` attribute; check in `/health`

### Must NOT Do
- Do NOT register signal handlers inside `convert()` (library function — callers own signal policy)
- Do NOT use `atexit` — signals need explicit cleanup ordering
- Do NOT add new file dependencies (use stdlib: `signal`, `threading`, `atexit`, `shutil`)
- Do NOT change the `convert()` return type or signature

### Injection Points (exact line numbers)
| File | Lines | Change |
|------|-------|--------|
| `converter.py` | 134-157 | Add shutdown flag check in `_stage_level0_memmap()` tile loop |
| `tile_reader.py` | 175-237 | Add shutdown flag check in `iter_svs_rgb_tiles()` tile loop |
| `pyramid.py` | 150-181 | Add shutdown flag check in `build_pyramid_memmaps()` row loop |
| `cli.py` | 90-150 | Register signal handlers, pass shutdown event through config |
| `batch.py` | 82-174 | Register signal handlers |
| `serve.py` | 383-390 | Update `/health` to report `shutting_down` |
| `services.py` | 198-322 | Add `shutdown()` method to `ConversionService` |

### Test Strategy
- **Unit:** `test_signal_handling.py` — new test file
  - `test_shutdown_event_set_on_signal` — signal sets threading.Event
  - `test_loop_respects_shutdown_flag` — tile loop exits early when flag is set
  - `test_double_signal_force_exit` — second signal triggers exit
  - `test_shutdown_cleans_temp_dir` — temp files removed after interrupt
- **Integration:** `test_cleanup.py` — verify cleanup paths called on interrupt
- **Manual:** Run `svs-to-ometiff input.svs output.ome.tiff` → Ctrl+C → verify temp dir gone

---

## Task 3: JPEG/JPEG 2000 Compression Support

**Agent Category:** `unspecified-high`
**Files:** `src/svs_to_ometiff/config.py`, `src/svs_to_ometiff/cli.py`, `src/svs_to_ometiff/batch.py`, `src/svs_to_ometiff/writer.py`, `src/svs_to_ometiff/converter.py`, `svs_to_ometiff_gui/models.py`, `svs_to_ometiff_gui/serve.py`, `tests/` (new/modified test files)

### Description
Add `"jpeg"` and `"jpeg2000"` to `_SUPPORTED_COMPRESSION` in `config.py:8`. Add a `compression_quality: int = 85` field to `ConvertConfig` (valid range 0-100). Propagate `compressionargs` through `write_pyramidal_ometiff_from_levels()` to `tifffile.TiffWriter.write()`. Update CLI `--compression` choices in both `cli.py:41` and `batch.py:39`. Add `--compression-quality` CLI option. Update GUI compression selector and quality slider. Validate that `compression_quality` is only accepted when `compression` is `jpeg` or `jpeg2000`.

### Acceptance Criteria
- [ ] `_SUPPORTED_COMPRESSION` includes `"jpeg"` and `"jpeg2000"` (removed `jpeg2000` rejection from lines 40-46)
- [ ] `ConvertConfig.compression_quality` defaults to 85, validates 0-100
- [ ] `convert(config, compression="jpeg", compression_quality=95)` produces valid OME-TIFF with JPEG-compressed tiles
- [ ] `convert(config, compression="jpeg2000", compression_quality=50)` produces valid OME-TIFF with JPEG 2000 tiles
- [ ] `svs-to-ometiff-verify` passes on JPEG and JPEG 2000 outputs
- [ ] File size with `compression="jpeg"` is ≤ file size with `compression="zlib"` for same input
- [ ] `compression_quality=0` produces smallest files; `compression_quality=100` produces largest
- [ ] `compression_quality` is silently ignored for `zlib`, `lzw`, `deflate`, `none`
- [ ] CLI `--compression-quality` requires `--compression jpeg` or `jpeg2000` (validation error otherwise)
- [ ] CLI `--compression` choices include `jpeg` and `jpeg2000` (both `cli.py` and `batch.py`)
- [ ] Backwards-compatible: default `compression="zlib"` with no quality → unchanged behavior
- [ ] GUI shows quality slider only when JPEG/JPEG2000 selected
- [ ] All 112 existing tests pass

### Must Do
- Add `"jpeg"` and `"jpeg2000"` to the `_SUPPORTED_COMPRESSION` tuple in `config.py:8`
- Remove the `jpeg2000`-specific rejection message in `config.py:41-46`
- Add `compression_quality: int = 85` field to `ConvertConfig` (after `compression`)
- Validate in `_validate()`: `compression_quality` must be 0-100, required only for JPEG/JPEG2000
- Build `compressionargs = {'level': compression_quality}` when compression is jpeg/jpeg2000
- Pass `compressionargs` through `convert()` → `write_pyramidal_ometiff()` → `write_pyramidal_ometiff_from_levels()` → `tifffile.TiffWriter.write()`
- Update `cli.py:41`: `click.Choice(["zlib", "lzw", "deflate", "jpeg", "jpeg2000", "none"])`
- Update `batch.py:39`: same choice extension
- Add `--compression-quality` option to `cli.py` and `batch.py`: `type=click.IntRange(0, 100), default=85`
- Update `ConversionJob` in `models.py` to include `compression_quality`
- Update `_build_conversion_job()` in `serve.py` to read and validate `compression_quality`
- Add runtime codec detection: graceful error if `imagecodecs` lacks JPEG2000 backend

### Must NOT Do
- Do NOT change default compression (stays `"zlib"`)
- Do NOT change the `write_pyramidal_ometiff()` public signature (add `compressionargs` with default `None`)
- Do NOT add new dependencies (`imagecodecs` already in pyproject.toml)
- Do NOT remove the `jpeg2000` error entirely — replace with a check for codec availability
- Do NOT change `compression_quality` validation for non-JPEG cases (silently ignore, don't error)

### Injection Points (exact line numbers)
| File | Lines | Change |
|------|-------|--------|
| `config.py` | 8 | Add `"jpeg"`, `"jpeg2000"` to `_SUPPORTED_COMPRESSION` |
| `config.py` | 18-26 | Add `compression_quality: int = 85` field |
| `config.py` | 40-48 | Replace `jpeg2000` rejection with codec availability check |
| `cli.py` | 41 | Add `"jpeg"`, `"jpeg2000"` to choices |
| `cli.py` | 89-100 | Add `--compression-quality` option |
| `batch.py` | 39 | Add `"jpeg"`, `"jpeg2000"` to choices |
| `batch.py` | 69-75 | Add `--compression-quality` option |
| `writer.py` | 125-249 | Accept optional `compressionargs` parameter, pass to `tif.write()` |
| `converter.py` | 270-281 | Build `compressionargs` dict, pass to writer |
| `models.py` | 12-36 | Add `compression_quality` field |
| `serve.py` | 87-125 | Wire `compression_quality` in `_build_conversion_job()` |

### Test Strategy
- **Unit:** `test_config.py` modifications
  - `test_supported_compression_includes_jpeg` — `"jpeg"` in `_SUPPORTED_COMPRESSION`
  - `test_config_with_compression_quality` — valid quality accepted
  - `test_config_rejects_quality_out_of_range` — >100 or <0 raises ValueError
  - `test_config_quality_ignored_for_zlib` — quality=90 with zlib → no error
- **Integration:** `test_jpeg_compression.py` — new test file
  - `test_jpeg_compression_output` — synthetic SVS → JPEG output → verify with tifffile
  - `test_jpeg2000_compression_output` — synthetic SVS → JPEG2000 output → verify
  - `test_verify_on_jpeg_output` — `svs-to-ometiff-verify` passes
  - `test_file_size_jpeg_vs_zlib` — JPEG output smaller than zlib for same input
  - `test_compression_quality_range` — quality 0 < quality 100 file sizes
- **CLI:** `test_cli_temp_dir.py` modifications
  - `test_cli_compression_quality_flag` — `--compression jpeg --compression-quality 90`
  - `test_cli_compression_quality_requires_jpeg` — `--compression zlib --compression-quality 90` → error
- **GUI:** `test_models.py`, `test_routes.py` updates
- **Regression:** `pytest tests/ -x -q` → all pass (112 + new)

---

## Task 4: Large-File Integration Tests

**Agent Category:** `unspecified-high`
**Files:** `tests/helpers.py`, `tests/` (new test files), `pyproject.toml` (pytest markers)

### Description
Extend `tests/helpers.py:write_synthetic_33007_svs()` to generate large synthetic SVS files (4096×4096 and 8192×8192). Add `pytest.mark.slow` marker to `pyproject.toml`. Create large-file integration tests that validate: (1) byte-identical output between single and multi-threaded paths, (2) peak RAM stays within `estimate_peak_ram_bytes() * 1.2`, (3) JPEG/JPEG2000 compression works on large images, (4) signal shutdown works on large conversions. CI configuration excludes slow tests by default.

### Acceptance Criteria
- [ ] `pytest -m slow` runs only large-file tests
- [ ] `pytest -m "not slow"` excludes large-file tests (default CI behavior)
- [ ] Test helper generates valid 8192×8192 synthetic SVS with YUYV tiles
- [ ] Test: `test_large_file_parallel_consistency` — 4096×4096 SVS, compare single vs future workers=1
- [ ] Test: `test_large_file_memory_budget` — 8192×8192 SVS, assert RSS < estimate × 1.2
- [ ] Test: `test_large_file_jpeg_compression` — 8192×8192 SVS → JPEG output → verify
- [ ] Test: `test_large_file_signal_shutdown` — SIGINT during large conversion → temp files cleaned
- [ ] Edge tiles validated: image dimensions not multiples of 256 produce correct padding in output
- [ ] All 112 existing tests pass (fast tests unaffected)

### Must Do
- Add `markers = ["slow: tests that are slow and excluded from default CI"]` to `pyproject.toml` under `[tool.pytest.ini_options]`
- Extend `write_synthetic_33007_svs()` to accept larger `width`/`height` parameters — keep `tile=(16, 16)` in tifffile for synthetic fixtures but patch compression to 33007
- Use `@pytest.mark.slow` decorator on all large-file test functions
- Large-file tests go in `tests/test_large_file.py` (new file)
- Verify each large-file output with `tifffile.TiffFile` to confirm pyramid structure, compression, tile sizes
- Add `resource.setrlimit` or `tracemalloc` assertions for memory budget tests (stdlib only)
- Use temp files for all large-file test outputs (via `tmp_path` fixture)

### Must NOT Do
- Do NOT add large binary test fixtures to the repo (generate on-the-fly)
- Do NOT run slow tests in the default `pytest tests/` invocation
- Do NOT require real WSI files (>1 GB) — all tests use synthetic data
- Do NOT change existing test helpers in a way that breaks existing fast tests
- Do NOT increase the minimum test runtime for fast tests beyond ~2 seconds

### Injection Points
| File | Lines | Change |
|------|-------|--------|
| `tests/helpers.py` | 30-56 | Extend `write_synthetic_33007_svs()` for large dimensions |
| `tests/test_large_file.py` | (new) | All large-file integration tests |
| `pyproject.toml` | 72-75 | Add `markers` to `[tool.pytest.ini_options]` |

### Test Strategy
- **New file: `tests/test_large_file.py`**
  - `test_large_file_basic_conversion` — 4096×4096 SVS → OME-TIFF → verify with tifffile
  - `test_large_file_jpeg_compression` — 8192×8192 SVS → JPEG output → verify file size and validity
  - `test_large_file_jpeg2000_compression` — 4096×4096 SVS → JPEG2000 → verify
  - `test_large_file_edge_tiles` — 4097×4097 SVS (non-multiple of 256) → verify tile padding
  - `test_large_file_memory_budget` — 8192×8192 SVS → assert RSS stays within estimate
  - `test_large_file_signal_shutdown` — start conversion on 8192×8192, send SIGINT → verify cleanup
- **Runner commands:**
  - `pytest tests/ -m "not slow" -q` → fast tests only (CI default)
  - `pytest tests/ -m "slow" -q` → only large-file tests
  - `pytest tests/ -q` → all tests (fast + slow)

---

---

## Final Verification Wave (F1-F4)

All 4 reviewers run **in parallel** after Task 4 completes. Each reviewer reads the plan, checks against their domain, and produces a pass/fail report.

### F1 — Oracle: Goal/Constraint Verification

**Checker:** Did every Must Have get done? Did anything from Must NOT Have sneak in?

**Acceptance Criteria for F1:**
- [ ] All 4 Must Have features implemented and verified
- [ ] No deferred features (parallelization, multi-format, OpenAPI) present
- [ ] No new dependencies added to pyproject.toml
- [ ] Default compression still `zlib`; CLI flags unchanged
- [ ] All 112 original tests pass + new tests pass
- [ ] Pipeline architecture unchanged (converter.py flow intact)

### F2 — Oracle: Code Quality Review

**Checker:** Architecture, patterns, naming, DRY, test coverage.

**Acceptance Criteria for F2:**
- [ ] No duplicated code across `cli.py` and `batch.py` (shared validation logic)
- [ ] Serialization methods follow dataclass patterns (no manual dict building)
- [ ] Signal handling is contained to CLI layer (not in library `convert()`)
- [ ] Writer `compressionargs` is optional, backward-compatible
- [ ] Test coverage ≥ 90% on new code paths
- [ ] No print() in library code (only `_log()`)
- [ ] Progress logging unaffected by new features

### F3 — Oracle: Security Review

**Checker:** Temp file safety, signal safety, pickle/JSON safety, input validation.

**Acceptance Criteria for F3:**
- [ ] `from_dict()` validates all inputs before constructing `ConvertConfig`
- [ ] `from_json()` does not execute arbitrary code (uses `json.loads`, not `pickle`)
- [ ] Temp files cleaned on all signal paths (SIGINT, SIGTERM, exception)
- [ ] No race condition: temp dir removed before output written
- [ ] GUI `shutdown()` cancels all subprocesses within timeout
- [ ] Double-signal handler does not leave orphaned resources
- [ ] `compression_quality` validated to int 0-100, no overflow

### F4 — QA: Hands-On Execution

**Checker:** Run the full test suite and manual CLI/GUI smoke tests.

**Acceptance Criteria for F4:**
- [ ] `python -m pytest tests/ -x -v` — all tests pass (both fast and slow)
- [ ] `python -m pytest tests/ -m "not slow" -x -v` — fast tests pass
- [ ] `python -m pytest tests/ -m "slow" -x -v` — slow tests pass
- [ ] `svs-to-ometiff --help` shows new `--compression-quality` option
- [ ] `svs-to-ometiff-batch --help` shows new `--compression-quality` option
- [ ] `python -c "from svs_to_ometiff.config import ConvertConfig; c = ConvertConfig('test.svs', 'out.ome.tiff'); print(c.to_dict())"` works
- [ ] `python -c "from svs_to_ometiff.config import ConvertConfig; c = ConvertConfig.from_dict({'input_svs': 't.svs', 'output_ometiff': 'o.ome.tiff'}); print(c)"` works
- [ ] GUI starts and `/health` returns correct status
- [ ] LSP diagnostics clean on all changed files

---

---

## Commit Strategy

**One commit per wave.** Do NOT squash across waves.

```bash
# Wave 1 commit
git add src/svs_to_ometiff/config.py src/svs_to_ometiff/converter.py
git add svs_to_ometiff_gui/serve.py svs_to_ometiff_gui/services.py
git add src/svs_to_ometiff/cli.py src/svs_to_ometiff/tile_reader.py
git add src/svs_to_ometiff/pyramid.py svs_to_ometiff_gui/serve.py
git add tests/
git commit -m "feat: add ConvertConfig serialization and graceful shutdown"

# Wave 2 commit
git add src/svs_to_ometiff/config.py src/svs_to_ometiff/cli.py src/svs_to_ometiff/batch.py
git add src/svs_to_ometiff/writer.py src/svs_to_ometiff/converter.py
git add svs_to_ometiff_gui/models.py svs_to_ometiff_gui/serve.py
git add tests/
git commit -m "feat: add JPEG and JPEG 2000 compression support"

# Wave 3 commit
git add tests/helpers.py tests/test_large_file.py pyproject.toml
git commit -m "test: add large-file integration tests with slow marker"

# Final: version bump
# Update pyproject.toml: version = "0.7.0"
# Update src/svs_to_ometiff/__init__.py: __version__ = "0.7.0"
git add pyproject.toml src/svs_to_ometiff/__init__.py
git commit -m "chore: bump version to 0.7.0"
```

---

## Verification Commands

After all waves complete:

```bash
# 1. Fast test suite (CI default)
python -m pytest tests/ -m "not slow" -x -v

# 2. All tests including large-file
python -m pytest tests/ -x -v

# 3. LSP diagnostics on changed files
# (check: config.py, converter.py, writer.py, cli.py, batch.py,
#         serve.py, services.py, models.py, tile_reader.py, pyramid.py)

# 4. CLI smoke tests
svs-to-ometiff --help
svs-to-ometiff --version
svs-to-ometiff-batch --help

# 5. Import verification
python -c "from svs_to_ometiff.config import ConvertConfig; print('OK')"
python -c "from svs_to_ometiff.converter import convert; print('OK')"

# 6. Check for regressions
python -m pytest tests/ --cov=src/svs_to_ometiff --cov=svs_to_ometiff_gui --cov-report=term

# 7. ruff lint
ruff check src/ tests/ svs_to_ometiff_gui/
```

---

## Definition of Done

All of the following must be true:

1. [ ] **4 tasks complete** — T1 (Serialization), T2 (Signals), T3 (JPEG), T4 (Large-file tests)
2. [ ] **4 reviewers passed** — F1 (Goals), F2 (Quality), F3 (Security), F4 (QA)
3. [ ] **Fast tests pass:** `pytest tests/ -m "not slow" -x -v` → 112 + new = all green
4. [ ] **All tests pass:** `pytest tests/ -x -v` → green including slow tests
5. [ ] **No regressions:** All 112 original tests still pass with unchanged assertions
6. [ ] **CLI backward-compatible:** `svs-to-ometiff input.svs output.ome.tiff` (no extra flags) works identically
7. [ ] **Version bumped:** `pyproject.toml` and `__init__.py` show `0.7.0`
8. [ ] **LSP clean:** Zero diagnostics on all changed files
9. [ ] **ruff clean:** Zero lint errors/warnings
10. [ ] **All commits pushed** to feature branch
11. [ ] **CHANGELOG.md** entry for v0.7.0 with all 4 features listed

---

## Rollback Plan

If any wave fails review:
- **Wave 1 failure:** Revert Wave 1 commits, fix, re-run
- **Wave 2 failure:** Revert Wave 2 commit only (Wave 1 commits remain)
- **Wave 3 failure:** Revert Wave 3 commit only
- **Severe regression:** `git reset --hard b7c0e79` to return to v0.6.1 baseline
