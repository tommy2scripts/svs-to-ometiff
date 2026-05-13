# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.1] - 2026-05-12

### Fixed
- **Unified package release**: Publishes the corrected `svs-to-ometiff`
  package with both the core library/CLI and Flask GUI in one wheel.
- **CI dependencies**: Adds Ruff to the development extra so CI linting works
  from a clean install.
- **Source install docs**: Replaces the stale self-dependency in
  `requirements.txt` with the actual runtime dependencies.
- **GUI defaults**: Aligns fallback conversion defaults with the documented
  `zlib` GUI default.

## [0.5.0] - 2026-05-11

### Fixed
- **GUI conversion call**: Fixed `TypeError` caused by passing keyword arguments
  directly to `convert()`. GUI now constructs a `ConvertConfig` and normalizes
  `"none"` compression to `None` before calling `convert()`.
- **`_close_memmaps`**: Replaced fragile `._mmap` private-attribute access with
  `level.close()`, fixing compatibility across numpy versions.
- **`iter_svs_rgb_tiles` progress**: Prints now go to stderr instead of stdout,
  preventing progress output from corrupting piped data.

### Changed
- **Compression options**: Removed the previously advertised but unsupported
  `jpeg2000` option from the CLI, batch CLI, and GUI compression selector.
  Use `zlib`, `lzw`, `deflate`, or `none`; users who specifically need
  JPEG 2000 should recompress outputs with a dedicated TIFF tool after
  conversion.
- **`estimate_peak_ram_bytes`**: Now actually uses `num_levels` and
  `downsample_factor` parameters to compute a more realistic estimate instead of
  returning a flat 1.2× multiplier.
- **`svs-to-ometiff-inspect`**: Now prints metadata for non-33007 files before
  reporting them as non-convertible, making the tool useful for discovery.

### Added
- **PEP 561 `py.typed` markers**: Both packages are now discoverable by type
  checkers (mypy, pyright).
- **Formal test files**: `tests/test_api.py` (6 tests for public API shape) and
  `tests/test_gui_params.py` (5 tests for parameter normalization and edge
  cases).
- **Packaging**: `CITATION.cff`, `CONTRIBUTING.md`, `SECURITY.md` added.
- **README**: Complete rewrite with validation status, supported/unsupported
  inputs, resource requirements, troubleshooting section, verified output
  example, and separate sections for CLI, API, and GUI usage.

## [0.4.1] - 2026-05-07

### Changed
- **Safe defaults**: Changed default conversion profile to `compression=none`,
  `num_levels=3`, `tile_size=512`, `downsample_factor=2`. This is the
  conservative profile validated on real Aperio AT2/GT450 data.
  Previous defaults were `compression=lzw`, `num_levels=6`.
- CLI `--compression` default now shows `none` (was `lzw`).
- `--compression none` avoids `imagecodecs` dependency at runtime.

### Added
- **`svs-to-ometiff-inspect`**: New CLI command to inspect source SVS metadata
  (compression, dimensions, tile size, MPP) before conversion.
- **`svs-to-ometiff-verify`**: New CLI command to verify output OME-TIFF
  structure (OME compliance, BigTIFF, pyramid levels, RGB shape, dtype).
- **Config validation**: `ConvertConfig` now rejects invalid `tile_size`,
  `num_levels`, `downsample_factor`, and unsupported `compression` values
  at construction time (fail-fast).
- **Release metadata tests**: Version consistency enforced between
  `pyproject.toml`, `__version__`, CLI `--version`, and experimental warning.
- End-to-end CLI smoke test covering inspect -> convert -> verify flow.
- CI now runs `twine check dist/*` on every build.
- `docs/release_checklist.md`: Deterministic release/publish steps.
- `docs/real_file_validation_template.md`: Template for collecting
  real-file validation evidence.

### Fixed
- CLI `--version` and experimental warning now use `__version__` dynamically
  instead of hardcoded strings.

### Notes
- This is still an **alpha/experimental** release. Validated on Aperio
  AT2/GT450 compression 33007 only. Not for diagnostic use.
