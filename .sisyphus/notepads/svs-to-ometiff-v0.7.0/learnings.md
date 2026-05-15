
## Plan Generation Learnings (2026-05-15)

### Plan Structure
- Created `.sisyphus/plans/svs-to-ometiff-v0.7.0.md` (512 lines)
- No existing plan files were found in the repo (no `svs-to-ometiff-release.md`)
- Based the format on the writing-plans skill template adapted for Sisyphus orchestrator usage
- Plans directory had to be created: `mkdir -p .sisyphus/plans/`

### Scope Decisions
- 4 features IN scope (derived from task description, which narrowed the original gap analysis):
  1. ConvertConfig serialization (was MUST #3 in decisions.md)
  2. Graceful shutdown signal handling (was SHOULD #5 in decisions.md)
  3. JPEG/JPEG 2000 compression support (was MUST #1 in decisions.md)
  4. Large-file integration tests (was SHOULD #6 in decisions.md)
- Parallel tile decoding (MUST #2) deferred to v0.8.0 per task instructions
- Multi-format WSI (SHOULD #4) deferred to v0.8.0
- OpenAPI/Swagger (COULD #7) deferred to v0.8.0

### Key Source Files Mapped
- config.py (49 lines): _SUPPORTED_COMPRESSION tuple at line 8, ConvertConfig at line 11
- converter.py (317 lines): _LEGACY_CONFIG_DEFAULTS at line 23, _coerce_convert_config at line 76
- cli.py (150 lines): click.Choice at line 41, main() at line 90
- batch.py (174 lines): mirror of cli.py structure
- writer.py (249 lines): write_pyramidal_ometiff_from_levels at line 125
- GUI: models.py (68 lines), serve.py (403 lines), services.py (322 lines)
- tests/helpers.py (56 lines): write_synthetic_33007_svs()

### Guardrails Enforced
- NO new dependencies (all features use stdlib or existing deps)
- NO CLI breaking changes
- NO pipeline architecture changes
- 112 existing tests must pass throughout
- Default compression remains zlib

### Execution Wave Design
- Wave 1: Tasks 1+2 (parallel) — Config serialization + Signal handling are independent
- Wave 2: Task 3 — JPEG/JPEG2000 builds on stable foundation from Wave 1
- Wave 3: Task 4 — Large-file tests validate all features end-to-end
- Final: F1-F4 reviewers run in parallel to verify completeness

### Agent Strategies
- T1 (quick): Simple serialization methods on existing dataclass
- T2 (unspecified-high): Cross-cutting signal handling across multiple files
- T3 (unspecified-high): Touches config, writer, CLI, batch, GUI, and converter
- T4 (unspecified-high): Test-only but complex synthetic fixture generation
- F1-F3 (deep): Oracles need thorough codebase understanding
- F4 (unspecified-high): Hands-on QA execution

## Task 3: JPEG/JPEG 2000 Compression Support

### Implementation Notes

1. **imagecodecs codec detection**: `imagecodecs` uses module-level constants (`JPEG`, `JPEG2K`) as compile-time capability indicators. The `*_check()` functions are FORMAT DETECTION (they check if data *is* that format), NOT capability detection. The `*_encode()` functions segfault on invalid probe data (e.g., raw bytes without proper image dimensions), so `hasattr(imagecodecs, "JPEG")` is the safe approach.

2. **jpeg_encode signature**: Uses `level` parameter (not `quality`) — `level=80` is equivalent to quality 80. Parameters: `data, level, colorspace, outcolorspace, subsampling, optimize, smoothing, lossless, predictor, bitspersample, out`.

3. **jpeg2k_encode signature**: Uses `level` parameter. Parameters: `data, level, codecformat, colorspace, planar, tile, bitspersample, resolutions, reversible, mct, verbose, numthreads, out`.

4. **"none" → None normalization**: Moved from CLI and models.py into `ConvertConfig.__post_init__`. Uses `object.__setattr__` because ConvertConfig is frozen. Happens before `_validate()` so validation runs against normalized value.

5. **Frozen dataclass field mutation**: `object.__setattr__(self, 'compression', None)` is the correct pattern for modifying frozen dataclass fields in `__post_init__`.

### Test Changes Required

6. **Existing tests that assumed jpeg2000 invalid**:
   - `test_config.py:test_validation_runs_on_bad_compression` — changed to "bzip2"
   - `test_config_and_health.py` — 3 tests renamed from `test_jpeg2000_error_*` to `test_unsupported_compression_*`, using "bzip2"
   - `test_routes.py:test_convert_rejects_jpeg2000_compression_at_route_level` — renamed to `test_convert_rejects_unsupported_compression_at_route_level`, using "bzip2"

### monkeypatch Constraints

7. `monkeypatch.delattr(imagecodecs, "JPEG")` does NOT work because imagecodecs has a `__getattr__` that re-exports, causing `hasattr` to still return True via recursion. Solution: monkeypatch by setting `sys.modules["imagecodecs"] = None` to simulate import failure.

## Task 4: Large-File Integration Tests

### Implementation Notes

1. **Synthetic SVS generator vectorisation**: The original `make_known_yuyv_tile()` uses a nested Python loop. For 16384×16384 images (134M pixel pairs), this would be ~15-30s per fixture. Replaced with a vectorised NumPy path (`_make_synthetic_yuyv_data()`) that builds the uint16 YUYV array in one shot: `data[:, 0::2] = y0 | (neutral << 8)`. The legacy byte-level path is still exercised for images ≤64×64 to maintain coverage of the original code path.

2. **YUYV little-endian encoding**: Each uint16 value in the synthetic data encodes a YUYV pixel pair as `U<<8 | Y0` for even columns and `V<<8 | Y1` for odd columns. The decoder reads raw tile bytes directly (bypassing tifffile image decoding), so the uint16 array must produce the exact byte sequence the YUYV decoder expects.

3. **tifffile SubIFD page structure**: When reading back an OME-TIFF with SubIFDs, `tif.pages` has only 1 entry (the main IFD). SubIFD-resident levels are accessed through `tif.series[0].levels` which returns `TiffPageSeries` objects. Each `TiffPageSeries` has a `.keyframe` attribute pointing to the underlying `TiffPage` with `.dataoffsets`, `.tilewidth`, and `.tilelength`.

4. **SubIFD tag access**: The TIFF SubIFD tag is numeric code 330 (not string key `"SubIFD"`). Access via `page0.tags[330].value` returns a tuple of offset integers. `page0.subifds` mirrors this value.

5. **Padded tile transparency**: `TiffPageSeries.asarray()` returns logical (un-padded) image dimensions — padding is transparent to tifffile. To inspect raw padded tile data, use `TiffPage.dataoffsets` + filehandle seek/read and decompress. The edge-tile padding tests verify at the structural level (tile count, metadata validity) rather than raw byte inspection.

6. **Tile count verification**: For each OME-TIFF pyramid level, the expected tile count is `ceil(level_width / tile_size)²`. With tile_size=1024: Level 0 (2048×2048) = 4 tiles, Levels 1-5 (≤1024) = 1 tile each. Level 0 (16384×16384) = 256 tiles, Level 1 (8192) = 64, etc.

7. **Memmap path verification**: The 16384×16384 → ~805 MB RGB conversion exercises the out-of-core memmap path. A successful conversion without OOM proves the streaming path works. The `result["output_size_bytes"]` and `verify_ometiff()` assertions confirm output validity.

8. **JPEG 2000 round-trip**: Lossless JPEG 2000 preserves pixel-level fidelity — `np.testing.assert_array_equal()` confirms identical pixels after compression round-trip. For this synthetic YUYV pattern, JPEG 2000 produces smaller output than zlib.

9. **`pytest.mark.slow` gating**: Marker registered in `pyproject.toml` under `[tool.pytest.ini_options].markers`. Fast tests (`pytest -m "not slow"`) continue at 181. Slow tests (`pytest -m "slow"`) add 20 tests. Full suite: 201 tests.

10. **Module-level `pytestmark`**: `pytestmark = pytest.mark.slow` applied at module level so ALL tests in the file are slow-marked without individual decorators.
