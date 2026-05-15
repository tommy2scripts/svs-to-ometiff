# svs-to-ometiff v0.7.0 — Gap Analysis & Scope Definition

**Date:** 2026-05-15
**Baseline:** v0.6.1 (28 Python files, ~4,711 LOC, 112 tests passing)

---

## 1. Scope Definition

### IN SCOPE (MUST)
1. **JPEG/JPEG 2000 compression support** — Add `jpeg` and `jpeg2000` to output compression options
2. **Parallel tile decoding and pyramid building** — Multi-threaded source tile decoding and pyramid level construction
3. **ConvertConfig serialization** — `to_dict()` / `from_dict()` on ConvertConfig

### IN SCOPE (SHOULD)
4. **Multi-format WSI input support** — Extend tile_reader to handle non-33007 SVS compressions (JPEG, JPEG 2000 tiles)
5. **Graceful shutdown signal handling** — SIGINT/SIGTERM handlers for CLI and GUI
6. **Large-file integration tests** — Real-WSI or large synthetic test fixtures

### IN SCOPE (COULD)
7. **OpenAPI/Swagger docs for Flask GUI** — Self-documenting REST API

### OUT OF SCOPE
- Non-Aperio WSI formats (NDPI, MRXS, DICOM-WSI) — v0.8.0+
- Lossless JPEG-LS compression (not supported by tifffile)
- GPU-accelerated tile decoding
- Cloud storage I/O (S3, GCS)
- Output to formats other than OME-TIFF

---

## 2. Feature 1: JPEG/JPEG 2000 Compression (MUST)

### Current State
- `config.py` line 8: `_SUPPORTED_COMPRESSION = (None, "lzw", "zlib", "deflate")`
- `config.py` lines 40-48: Explicitly rejects `jpeg2000` with tailored error message
- `cli.py` line 41: `click.Choice(["zlib", "lzw", "deflate", "none"])`
- `batch.py` line 39: Same restricted choice
- `writer.py` line 121: `write_pyramidal_ometiff_from_levels()` passes `compression` straight to `tifffile.TiffWriter.write()`
- `pyproject.toml` line 37: `imagecodecs>=2022.2.22` is already a dependency
- CHANGELOG v0.5.0: JPEG 2000 was formerly advertised but unsupported — removed from UI

### What tifffile Supports
Both `jpeg` and `jpeg2000` are valid compression values for TiffWriter. `imagecodecs` provides the codec backends. Additional parameters:
- JPEG: `compressionargs={'level': 95}` for quality control (0-100, default 75)
- JPEG 2000: `compressionargs={'level': 50}` for quality, plus `tile` size conventions

### Implementation Plan
1. Add `"jpeg"` and `"jpeg2000"` to `_SUPPORTED_COMPRESSION` in `config.py`
2. Add `--compression-quality` CLI option (int, 0-100, applicable only to `jpeg`/`jpeg2000`)
3. Propagate `compressionargs` through `write_pyramidal_ometiff_from_levels()` → `tifffile.TiffWriter.write()`
4. Update CLI `--compression` choices: add `jpeg`, `jpeg2000`
5. Update batch CLI mirror
6. Update GUI compression selector

### Injection Points
| File | Lines | Change |
|------|-------|--------|
| `config.py` | 8 | Add `"jpeg"`, `"jpeg2000"` to tuple |
| `config.py` | 18-26 | Add `compression_quality: int = 85` field |
| `config.py` | 40-48 | Remove jpeg2000 rejection, validate quality |
| `cli.py` | 41 | Add choices |
| `cli.py` | 89-100 | Add `--compression-quality` option |
| `batch.py` | 39 | Add choices |
| `batch.py` | 69-75 | Add `--compression-quality` option |
| `writer.py` | 125-249 | Accept and pass `compressionargs` |
| `converter.py` | 23-34, 270-281 | Wire `compression_quality` → `compressionargs` |
| GUI models.py | 12-36 | Add `compression_quality` field |
| GUI serve.py | 87-125 | Wire quality in `_build_conversion_job` |

### Acceptance Criteria
- [ ] `convert(config, compression="jpeg", compression_quality=95)` produces valid OME-TIFF with JPEG-compressed tiles
- [ ] `convert(config, compression="jpeg2000", compression_quality=50)` produces valid OME-TIFF with JPEG 2000 tiles
- [ ] `svs-to-ometiff-verify` passes on JPEG and JPEG 2000 outputs
- [ ] File size with `compression="jpeg"` is smaller than `compression="zlib"` for same input
- [ ] `compression_quality=0` produces smallest files, `compression_quality=100` produces largest
- [ ] `compression_quality` is ignored (no-op) for `zlib`, `lzw`, `deflate`, `none`
- [ ] CLI `--compression-quality` requires `--compression jpeg` or `jpeg2000` (validation error otherwise)
- [ ] Backwards-compatible: all existing defaults (`zlib`, no quality) unchanged
- [ ] GUI shows quality slider only when JPEG/JPEG2000 selected

### Test Strategy
- **Unit:** `ConvertConfig` validation with/without compression_quality
- **Unit:** `_validate` rejects `compression_quality` with non-JPEG compression
- **Unit:** Writer `compressionargs` propagation (inspect output with tifffile)
- **Integration:** Full pipeline with synthetic SVS → JPEG output → verify
- **Integration:** Full pipeline with synthetic SVS → JPEG2000 output → verify
- **Regression:** All 112 existing tests continue to pass

### Risk Assessment
- **HIGH:** JPEG 2000 output compatibility — many TIFF readers (including some Bio-Formats builds) lack JPEG 2000 codec. Mitigation: document prominently, offer `svs-to-ometiff-verify` for validation.
- **MEDIUM:** `imagecodecs` JPEG2000 backend (`openjpeg`) may have memory limits on large tiles. Mitigation: test with 1024×1024 tiles on large images, document known limits.
- **LOW:** JPEG compression is lossy. Already documented — same as any TIFF.
- **LOW:** Quality parameter propagation through tifffile → imagecodecs chain may vary by codec version. Mitigation: pin `imagecodecs>=2022.2.22` already in pyproject.toml.

### Dependencies
- `imagecodecs` (already in pyproject.toml)
- `tifffile` (already in pyproject.toml)

---

## 3. Feature 2: Parallel Tile Decoding & Pyramid Building (MUST)

### Current State — Single-Threaded Bottlenecks
- **`tile_reader.py` lines 198-237:** Double-nested loop decodes tiles sequentially: 1 thread reads+decodes → writes to memmap
- **`yuyv_decoder.py` lines 14-99:** Pure NumPy, no I/O inside decode — CPU-bound per tile, embarrassingly parallel
- **`pyramid.py` lines 115-192:** `build_pyramid_memmaps()` processes rows sequentially; each row depends on previous level's strip, no cross-row dependency within a level
- **`converter.py` lines 134-157:** `_stage_level0_memmap()` calls `iter_svs_rgb_tiles()` and writes to memmap single-threaded
- **`writer.py` lines 110-123:** `_iter_padded_tiles()` yields tiles sequentially; `tifffile.TiffWriter.write()` accepts tile iterators (potentially consumer-side parallel)

### Bottleneck Profile (estimated for 100K×100K WSI)
| Phase | Est. Time (single-thread) | Parallelizable? |
|-------|--------------------------|-----------------|
| Tile read + YUYV decode | 70% | YES — tiles independent |
| Memmap write (level 0) | 5% | Thread-safe if written by tile index |
| Pyramid level build | 20% | YES — rows within a level are independent |
| OME-TIFF write | 5% | Limited — tifffile writes sequentially to single file |

### Parallelization Strategy

#### Phase A: Parallel Tile Decoding (highest ROI)
- Replace `iter_svs_rgb_tiles()` sequential loop with `concurrent.futures.ThreadPoolExecutor`
- Worker pool reads raw bytes from tifffile filehandle (shared handle, thread-safe per-tile seek+read)
- Decode YUYV → RGB in worker thread
- Write result to memmap slice (numpy memmap writes are thread-safe for non-overlapping slices)
- Use `OrderedDict` or tile-index-based placement to maintain deterministic output
- Configurable worker count: `--workers N` (default: `os.cpu_count()`)

#### Phase B: Parallel Pyramid Building
- Within each pyramid level, split rows into batches
- Process batches via `ThreadPoolExecutor`
- Write to shared memmap (non-overlapping row slices)
- Level N+1 must wait for level N to complete (sequential across levels)

#### Phase C: Parallel Tile Writing (lower priority)
- `_iter_padded_tiles()` can yield from parallel tile extraction
- `tifffile.TiffWriter.write()` consumes iterator sequentially — parallel benefit limited
- Evaluate after Phase A+B; may not justify complexity

### Injection Points
| File | Lines | Change |
|------|-------|--------|
| `config.py` | 18-26 | Add `workers: int = 0` field (0=auto) |
| `tile_reader.py` | 175-237 | Refactor `iter_svs_rgb_tiles` → parallel |
| `converter.py` | 134-157 | `_stage_level0_memmap` uses parallel reader |
| `pyramid.py` | 115-192 | `build_pyramid_memmaps` parallel row processing |
| `cli.py` | 89-100 | Add `--workers` option |
| `batch.py` | 69-75 | Add `--workers` option |
| GUI models.py | 12-36 | Add `workers` field |
| GUI serve.py | 87-125 | Wire `workers` in `_build_conversion_job` |

### Acceptance Criteria
- [ ] `convert(config, workers=4)` completes faster than `workers=1` on 4+ core machine (at least 2× speedup for tile decode phase)
- [ ] Output is byte-identical to single-threaded conversion (deterministic tile placement)
- [ ] `workers=0` (auto) selects `os.cpu_count()` or reasonable default
- [ ] Memory usage does not exceed `1.5×` single-threaded peak (not proportional to workers)
- [ ] 112 existing tests pass (all using `workers=1` default to avoid flakiness)
- [ ] Progress logging still works correctly with parallel execution
- [ ] Memmap file handles are properly closed on error (no leaked file descriptors)
- [ ] GUI `ProcessPoolExecutor` parallelism (inter-job) does not conflict with `ThreadPoolExecutor` parallelism (intra-job)

### Test Strategy
- **Unit:** `tile_reader` with 1, 2, 4 workers produces same tile order/placement (by-index not by-yield-order)
- **Unit:** `build_pyramid_memmaps` with parallel rows produces same pixel values as sequential
- **Unit:** `_stage_level0_memmap` with parallel tiles produces same level 0 content
- **Integration:** Full pipeline with `workers=4` → output identical to `workers=1`
- **Performance:** Benchmark on synthetic 4096×4096 SVS, assert wall-clock improvement
- **Thread safety:** Run with `threading` stress-test (100 iterations, random worker counts)

### Risk Assessment
- **HIGH:** Thread safety of `tifffile.filehandle` — seek+read from multiple threads on same file handle. Mitigation: use per-thread file handles (`open(svs_path, 'rb')` independent handles) or mutex-protect the shared handle. Per-thread handles are simpler and safe.
- **MEDIUM:** `numpy.memmap` thread safety — writes to non-overlapping slices should be thread-safe in CPython due to GIL, but need verification on free-threaded Python. Mitigation: test on CPython 3.12 (GIL) and 3.13t (free-threaded), document known-safe versions.
- **MEDIUM:** Deterministic output requirement — parallel tile decode may complete in non-deterministic order. Mitigation: assign tiles to memmap by index (not yield order), use fixed tile placement.
- **LOW:** Progress callback thread safety — `_log()` writes to stderr and calls optional callback. Mitigation: use `threading.Lock` around progress output.

### Dependencies
- `concurrent.futures` (stdlib, no new dependency)
- `threading` (stdlib)
- `os` (stdlib)

---

## 4. Feature 3: ConvertConfig Serialization (MUST)

### Current State
- `config.py`: `ConvertConfig` is a frozen dataclass, no serialization methods
- `converter.py` lines 23-34: `_LEGACY_CONFIG_DEFAULTS` dict duplicates ConvertConfig fields
- `converter.py` lines 76-103: `_coerce_convert_config()` manually maps kwargs ↔ ConvertConfig
- GUI `services.py` lines 299-306: Manual `template_dict` construction for cross-process pickling
- GUI `serve.py` lines 106-114: Constructs a temporary `ConvertConfig` purely for validation, then builds a `ConversionJob` separately — data duplicated

### What's Needed
1. `ConvertConfig.to_dict()` — serialize frozen dataclass to plain dict (JSON-serializable)
2. `ConvertConfig.from_dict(d: dict) -> ConvertConfig` — create config from dict
3. `ConvertConfig.to_json()` / `ConvertConfig.from_json(s: str)` — JSON convenience methods
4. Replace ad-hoc dict construction in `_coerce_convert_config()`, `_build_conversion_job()`, and `services.py` with canonical methods

### Injection Points
| File | Lines | Change |
|------|-------|--------|
| `config.py` | 11-49 | Add `to_dict()`, `from_dict()`, `to_json()`, `from_json()` |
| `converter.py` | 23-34 | Replace `_LEGACY_CONFIG_DEFAULTS` with `ConvertConfig.from_dict()` fallback |
| `converter.py` | 76-103 | Simplify `_coerce_convert_config()` using serialization |
| GUI serve.py | 87-125 | Replace dual construction with `ConvertConfig.to_dict()` → `ConversionJob` |
| GUI services.py | 299-306 | Replace `template_dict` with `ConvertConfig.to_dict()` |

### Acceptance Criteria
- [ ] `ConvertConfig.to_dict()` returns dict with all fields (including defaults)
- [ ] `ConvertConfig.from_dict(d)` round-trips: `from_dict(cfg.to_dict()) == cfg`
- [ ] `ConvertConfig.to_json()` produces valid JSON string
- [ ] `ConvertConfig.from_json(s)` round-trips
- [ ] `from_dict()` validates same rules as constructor (fail-fast)
- [ ] `from_dict()` accepts partial dict, fills defaults for missing keys
- [ ] `ProgressLogger` is excluded from serialization (not JSON-serializable)
- [ ] Backwards-compatible: `convert("input.svs", "output.ome.tiff", **kwargs)` still works
- [ ] All 112 existing tests pass

### Test Strategy
- **Unit:** `to_dict()` produces expected keys and types
- **Unit:** `from_dict()` round-trip identity
- **Unit:** `from_dict()` with partial dict → defaults filled
- **Unit:** `from_dict()` validation rejects invalid values
- **Unit:** JSON serialization/deserialization round-trip
- **Unit:** `ProgressLogger` excluded from `to_dict()` output
- **Integration:** `convert(ConvertConfig.from_dict(serialized))` produces same result

### Risk Assessment
- **LOW:** `ProgressLogger` is callable type → not JSON-serializable → must be excluded from serialization. Users re-creating config from dict must separately provide progress_logger. Mitigation: document that `progress_logger` is excluded, `from_dict()` sets it to `None`.
- **LOW:** Backwards compatibility with legacy `convert(input, output, **kwargs)` API. Mitigation: `_coerce_convert_config()` unchanged in behavior, only simplified internally.

---

## 5. Feature 4: Multi-Format WSI Input Support (STRETCH)

### Current State
- Only compression 33007 (YUYV) supported
- `converter.py` line 191-195: hard rejection of non-33007
- `tile_reader.py` lines 150-173: `_decode_tile_payload()` only handles YUYV
- `yuyv_decoder.py`: Entirely YUYV-specific
- `inspect.py` line 40: `convertible = compression == 33007`

### What's Needed
Aperio SVS files can use other TIFF compressions visible to standard tifffile reading:
- Compression 7 (JPEG) — standard JPEG tiles, decodable via `tifffile.TiffPage.asarray()`
- Compression 33003/33004 (JPEG 2000) — decodable via `imagecodecs` + `tifffile`
- Compression 1 (uncompressed) — raw RGB tiles

### Approach
1. **Dispatch Layer:** In `iter_svs_rgb_tiles()`, read compression tag from metadata, dispatch to:
   - Compression 33007 → existing YUYV path
   - Compression 7 → `page.asarray()` or `imagecodecs.jpeg_decode()`
   - Compression 33003/33004 → `imagecodecs.jpeg2000_decode()` + color transform
   - Compression 1 → raw RGB cast
2. **Renamed module:** `yuyv_decoder.py` → `tile_decoder.py` with dispatch function
3. **Remove hard rejection:** `converter.py` line 191-195 accepts supported compressions

### Acceptance Criteria
- [ ] SVS with compression 7 (JPEG) converts correctly
- [ ] SVS with compression 33003/33004 (JPEG 2000) converts correctly
- [ ] SVS with compression 1 (uncompressed) converts correctly
- [ ] `svs-to-ometiff-inspect` shows convertible=true for supported non-33007 files
- [ ] Error message for truly unsupported compressions is informative
- [ ] All existing 33007 tests pass (no regression)

### Risk Assessment
- **HIGH:** JPEG 2000 color space — Aperio JPEG 2000 uses YCbCr, may need color transform (similar to YUYV but different matrix). Mitigation: research Aperio JPEG 2000 color space, use tifffile built-in decoding if possible.
- **HIGH:** Test data availability — need real SVS files with different compressions. Mitigation: generate synthetic multi-compression TIFF files using tifffile for testing.
- **MEDIUM:** Performance — JPEG/JPEG2000 tile decode via imagecodecs may have different performance profile than custom YUYV decoder. Mitigation: benchmark, use parallel decode from Feature 2.

---

## 6. Feature 5: Graceful Shutdown Signal Handling (SHOULD)

### Current State
- No signal handlers registered
- CLI: SIGINT causes immediate termination, temp files left behind
- GUI: ProcessPoolExecutor jobs can be orphaned on server shutdown
- `pyramid.py` lines 198-273: `cleanup_pyramid_memmaps()` has retry logic, but only called in normal error paths

### What's Needed
1. Register `signal.signal(signal.SIGINT, handler)` and `signal.SIGTERM`
2. Handler sets `threading.Event` or atomic flag
3. Long-running loops check flag periodically
4. On shutdown: flush memmaps, close file handles, delete temp files
5. GUI: `ConversionService.shutdown()` method cancels pending futures, waits for completion (with timeout), cleans up

### Injection Points
| File | Lines | Change |
|------|-------|--------|
| `converter.py` | 134-317 | Add shutdown flag checks in loops |
| `tile_reader.py` | 175-237 | Add shutdown flag check in tile loop |
| `pyramid.py` | 150-181 | Add shutdown flag check in row loop |
| GUI services.py | 198-268 | Add `shutdown()` method |
| CLI main() | (new) | Register signal handlers |

### Acceptance Criteria
- [ ] SIGINT during tile decode → temp files cleaned, non-zero exit
- [ ] SIGINT during pyramid build → temp files cleaned, non-zero exit
- [ ] SIGTERM during write → temp file removed, output not corrupted (temp file, not target)
- [ ] GUI `/health` returns `shutting_down: true` during shutdown
- [ ] Double SIGINT (second signal) → force exit (prevent hang)

### Test Strategy
- **Unit:** Signal handler sets flag, loops respect it
- **Integration:** Send SIGINT to running process, verify temp dir removed
- **Integration:** GUI shutdown with active job → no orphaned processes

---

## 7. Feature 6: OpenAPI/Swagger Docs for Flask GUI (COULD)

### Current State
- 8 Flask routes in `serve.py`, all undocumented beyond inline comments
- No request/response schemas
- No API versioning

### What's Needed
1. Add `flasgger` or `flask-swagger-ui` dependency
2. Annotate routes with YAML docstrings (Flask-RESTX style) or decorators
3. Expose `/api/docs` endpoint

### Acceptance Criteria
- [ ] `/api/docs` serves interactive Swagger UI
- [ ] All 8 routes documented with request/response examples
- [ ] Error responses (400, 404, 409, 500) documented

### Risk Assessment
- **LOW:** Adding documentation-only dependency, no functional changes
- **LOW:** Decorator-based docs may conflict with existing route decorators — use YAML docstring approach

---

## 7. Feature 7: Large-File Integration Tests (SHOULD)

### Current State
- `tests/helpers.py`: `write_synthetic_33007_svs()` creates small (16×16 to 256×256) synthetic SVS files
- All 112 tests use synthetic data
- No tests with real WSI files (>1 GB)
- Test suite runs in seconds

### What's Needed
1. Generate synthetic large SVS files (4096×4096, 8192×8192) for integration tests
2. Add `pytest.mark.slow` marker for large-file tests
3. Add CI configuration to exclude slow tests by default
4. Test end-to-end pipeline on large synthetic files
5. Test parallel decoding performance with large files
6. Test memory usage stays within bounds

### Acceptance Criteria
- [ ] `pytest -m slow` runs large-file tests
- [ ] Large-file tests verify byte-identical output between single/multi-threaded
- [ ] Large-file tests verify RAM stays under `estimate_peak_ram_bytes() * 1.2`
- [ ] CI excludes slow tests (add `-m "not slow"` to CI config)
- [ ] Test helper generates valid 8192×8192 synthetic SVS with YUYV tiles

### Test Strategy
- **Integration:** `test_large_file_parallel_consistency` — 4096×4096 SVS, compare workers=1 vs workers=4
- **Integration:** `test_large_file_memory_budget` — 8192×8192 SVS, assert RSS < estimate
- **Integration:** `test_large_file_jpeg_compression` — large SVS → JPEG output → verify

---

## 8. Backwards Compatibility Requirements

### Immutable APIs
- `convert(config_or_input_svs, output_ometiff, **kwargs)` — both calling conventions must work
- All CLI entry points (`svs-to-ometiff`, `svs-to-ometiff-batch`, etc.) — no flag removals, no positional argument changes
- Default compression remains `zlib`
- Default tile size remains 1024
- Default pyramid remains 6 levels, factor 2, crop edge mode
- `ConvertConfig` frozen dataclass — remains frozen
- `build_ome_xml()` signature unchanged
- `write_pyramidal_ometiff()` signature unchanged (delegates to `write_pyramidal_ometiff_from_levels()` which gets new kwargs)

### Permitted Changes
- Adding new optional keyword arguments (with defaults maintaining current behavior)
- Adding new CLI flags (`--compression-quality`, `--workers`)
- Adding new methods on existing classes (`to_dict()`, `from_dict()`)
- Refactoring internal loops (parallel execution with same output)
- Adding new compression option strings to existing `--compression` flag

---

## 9. Assumptions

1. **tifffile + imagecodecs JPEG/JPEG2000:** The `tifffile.TiffWriter.write(compression="jpeg", compressionargs={'level': 90})` API works as documented and produces valid output readable by Bio-Formats. Assumption needs verification with Bio-Formats test.
2. **Thread safety of tifffile file handles:** Separate file handles (one per thread) are safe for seek+read. Shared file handles with `threading.Lock` are safe. This needs explicit testing.
3. **NumPy memmap thread safety:** NumPy ≥1.21 memmap writes to non-overlapping slices are thread-safe under CPython GIL. This holds for CPython 3.12 but may break on free-threaded Python 3.13t.
4. **Aperio JPEG 2000 color space:** Assumes YCbCr color space for compression 33003/33004. This matches the YUYV precedent but needs validation against real files.
5. **Platform support:** Parallel features tested on macOS (darwin) and Linux. Windows may have different memmap/filehandle behavior — explicit Windows CI testing required.
6. **`imagecodecs` availability:** Already in dependencies. Users who install from source must have `imagecodecs` for JPEG/JPEG2000 compression. `compression=none` remains available without `imagecodecs`.

---

## 10. Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| JPEG 2000 reader incompatibility | HIGH | Document prominently; `verify` tool validates output; offer fallback re-compression guide |
| Thread-safety bugs causing nondeterministic output | HIGH | Output hash comparison test; byte-identical assertion between workers=1 and workers=N |
| memmap thread safety on free-threaded Python (3.13t) | MEDIUM | Lock-based fallback detected at runtime; document supported Python versions |
| Large-file test CI timeout | MEDIUM | Mark tests as `slow`; exclude from default CI; run on dedicated runner |
| imagecodecs version mismatch JPEG2000 behavior | MEDIUM | Pin `imagecodecs>=2022.2.22` already; add version check in `config._validate` |
| Real SVS test data unavailability for multi-format | HIGH | Generate synthetic multi-compression TIFF files using tifffile; test with tifffile→verify→tifffile round-trip |
| Breaking GUI with new CompressionJob fields | LOW | Add fields with defaults matching current behavior; progressive enhancement |
| `ProgressLogger` callable serialization | LOW | Exclude from `to_dict()`; `from_dict()` sets to None; document |

---

## 11. Edge Cases to Handle

### Compression
- `compression="jpeg"` with `compression_quality=0` → valid? (Yes, tifffile accepts 0-100)
- `compression="jpeg"` with `compression_quality=200` → validation error
- `compression="zlib"` with `compression_quality=90` → warning (quality ignored), or validation error?
- `compression=None` (none) → `compressionargs` must be None/empty
- Single-tile image (smaller than tile_size) + JPEG/JPEG2000 → tile padding creates compression artifacts at edges
- Very small image (e.g., 50×50) → still produces valid OME-TIFF with JPEG compression

### Parallelism
- Single-core machine (`os.cpu_count() == 1`) → workers=1, no overhead
- `workers=0` → auto-detect; should never spawn 0 threads
- `workers=100` on 4-core machine → allow it (user knows best), but document overhead
- Thread pool exhaustion during error → all threads must be joined/stopped before cleanup
- Memory-constrained environment → parallel workers × tile_size × tile_size × 3 per worker may exceed RAM
- Very small image (1 tile) → parallel decode should not spawn workers (overhead > benefit)

### Config Serialization
- `from_dict({})` → all defaults, valid config (except required `input_svs`, `output_ometiff`)
- `from_dict()` with unknown keys → ignore or error? (Should error for strictness)
- `ProgressLogger` in dict → excluded from `to_dict()`, ignored in `from_dict()`
- Circular references → not possible with dataclass, but validate
- Very large integers (beyond int32) → Python int handles this

### Multi-Format
- SVS with mixed compression across pages → reject gracefully
- SVS with 0 tiles → edge case in tile_reader, currently raises error
- SVS with non-square tiles → already handled by tile_reader
- SVS larger than 4GB → BigTIFF handling already supported via tifffile

### Signal Handling
- SIGINT during signal handler → double-signal force exit
- SIGTERM during temp file cleanup → best-effort cleanup, warn on next run
- Windows `CTRL_CLOSE_EVENT` → different signal model, needs testing
- Signal during ProcessPoolExecutor shutdown → terminate pool, clean up

### WSI Format Detection
- SVS extension but non-SVS content → `tifffile.TiffFile` raises error, handle gracefully
- Non-.svs extension but valid SVS content → detect by TIFF header, not extension
- Corrupted TIFF → tifffile raises `TiffFileError`, already caught by CLI
