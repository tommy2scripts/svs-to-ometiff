# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
