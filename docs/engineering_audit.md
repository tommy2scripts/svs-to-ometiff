# Engineering Audit

Phase 0 audit for `svs-to-ometiff` at GitHub `main` commit `3c49506`.

This note documents the current architecture and the next implementation
sequence for hardening the project as an internal scientific imaging utility.
It intentionally avoids behavior changes except for keeping existing tests
portable across supported development platforms.

## Current Architecture

The project is a Python package with a `src/` layout:

- `src/svs_to_ometiff/` contains the core conversion library and CLI entry
  points.
- `src/svs_to_ometiff_gui/` contains the local Flask GUI, background worker
  service, SQLite job persistence, and static assets.
- `tests/` contains synthetic SVS/OME-TIFF fixtures and CLI, GUI, conversion,
  verification, cleanup, and large-fixture integration tests.
- `.github/workflows/` contains CI and release workflows.

The core conversion path is:

1. `ConvertConfig` in `config.py` validates user-facing conversion options.
2. `read_svs_metadata()` in `tile_reader.py` reads TIFF page 0 geometry,
   source tile layout, compression, MPP, and magnification.
3. `convert()` in `converter.py` rejects non-33007 compression, stages level 0
   as a disk-backed memmap, builds lower pyramid levels, and calls the writer.
4. `iter_svs_rgb_tiles()` reads tile payloads and decodes raw YUYV data via
   `yuyv_decoder.py`.
5. `build_pyramid_memmaps()` in `pyramid.py` creates lower RGB pyramid levels
   on disk.
6. `write_pyramidal_ometiff_from_levels()` in `writer.py` writes an atomic
   temporary OME BigTIFF and replaces the requested output path after success.
7. `verify_ometiff()` in `verify.py` performs structural OME BigTIFF checks.

## Current CLI Commands

Configured in `pyproject.toml`:

- `svs-to-ometiff`: single-file conversion implemented by `cli.py`.
- `svs-to-ometiff-batch`: batch conversion implemented by `batch.py`.
- `svs-to-ometiff-verify`: structural output verification implemented by
  `verify.py`.
- `svs-to-ometiff-inspect`: lightweight SVS metadata inspection implemented by
  `inspect.py`.
- `svs-to-ometiff-gui`: local Flask GUI implemented by
  `svs_to_ometiff_gui.serve`.

The single-file CLI currently supports tile size, compression,
compression-args, pyramid levels, downsample factor, edge mode, image name,
quiet/verbose logging, and temp directory selection.

The batch CLI currently supports input glob or directory expansion,
deterministic output naming, output collision detection, compression options,
compression-args, pyramid settings, quiet/verbose logging, and temp directory
selection. It does not yet provide rerun policy flags, manifest output,
verification integration, or resumability.

## Separation of Responsibilities

- Conversion semantics live in `converter.py` and `ConvertConfig`.
- Batch output naming and collision detection are shared through
  `batch_plan.py`.
- Source metadata parsing lives in `tile_reader.py`.
- OME-XML construction and TIFF writing live in `writer.py`.
- Pyramid construction and temp memmap cleanup live in `pyramid.py`.
- Verification lives in `verify.py`.
- The GUI uses `ConversionJob` as an adapter around `ConvertConfig` and
  delegates background execution to `ConversionService`.

This separation is a reasonable base for incremental hardening. The most
important next step is adding durable batch execution records without pushing
manifest logic into `converter.py`.

## Metadata and OME-XML

SVS metadata is read from the first TIFF page:

- Dimensions come from `page0.shape`.
- Source tile width and height come from `page0.tilewidth` and
  `page0.tilelength`.
- Compression comes from the `Compression` TIFF tag.
- MPP and AppMag are parsed from the Aperio `ImageDescription` string.
- Tile offsets and byte counts are checked against the expected tile grid.

OME-XML is currently built manually in `writer.build_ome_xml()`. The image name
is escaped with `xml.sax.saxutils.quoteattr`, and MPP is required to be positive.
The XML includes RGB `uint8` pixels, physical size X/Y in `um`, optional
instrument/objective metadata when magnification is present, and a single
`TiffData` entry for IFD 0.

## Pyramid and SubIFD Writing

The writer uses `tifffile.TiffWriter(..., bigtiff=True)`.

- Level 0 is written with `subifds=len(levels)-1`.
- Lower levels are written with `subfiletype=1`.
- Levels are tiled, RGB, and padded at tile edges to satisfy TIFF tile shape
  requirements.
- The output is written to a hidden temporary file in the output directory and
  then atomically replaced into the final destination with `Path.replace()`.

Atomic final replacement is good for partial-write safety, but it also means an
existing output can currently be overwritten by single-file and batch conversion
without an explicit `--force` policy.

## Temp Files and Output Replacement

Conversion creates a dedicated temporary directory under `tempfile.gettempdir()`
or the user-provided `--temp-dir`. Level 0 and lower pyramid levels are memmap
files in that directory. Cleanup explicitly flushes/closes memmaps, runs
garbage collection, and retries deletion for Windows file-handle behavior.

Current gaps:

- No preflight estimate checks that temp and output volumes have enough free
  space before conversion starts.
- Cleanup warnings are returned after successful conversion, but there is no
  structured manifest or log file to preserve them for batch runs.
- Existing final outputs can be replaced unless future CLI policy prevents it.

## Current Risks

- Batch reruns are not safe by default because existing outputs can be replaced
  without `--force`.
- Batch failures are only summarized in terminal output; there is no durable
  per-file manifest for partial runs.
- There is no `--skip-existing` behavior for resumable large batches.
- Verification is structural and output-only; it does not yet compare source
  dimensions, source MPP, or sampled image content.
- Disk-space failures can occur late, after expensive decode/pyramid work.
- OME-XML is manually assembled and should be parser-validated for edge cases.
- README language still includes some stronger compatibility phrasing than is
  ideal for Xenium workflows; future docs should use "designed for" and
  "validated on tested data" language.
- The GUI batch path does not yet expose manifest, preflight, verification, or
  QC report functionality.

## Current Test Gaps

Existing coverage is strong for synthetic conversion, JPEG/JPEG 2000 codec
options, cleanup behavior, GUI request validation, output collision detection,
and structural verification. Remaining gaps for the requested hardening:

- Existing-output policy: default no-overwrite, `--skip-existing`, and
  `--force`.
- Manifest serialization and deterministic status values.
- Batch continuation/fail-fast behavior and partial failure reporting.
- Disk-space estimation and mocked `shutil.disk_usage` preflight checks.
- Source-aware verification for dimension and MPP comparison.
- Deep verification checks for empty output or excessive black padding.
- JSON verification output and strict-mode warning escalation.
- HTML QC report generation and safe escaping.
- OME-XML parse validation for special image names, missing MPP, invalid MPP,
  and large dimensions.
- Documentation artifacts for validation matrix and release checklist.

## Proposed Implementation Sequence

1. **Phase 1: Batch safety and manifest**
   - Add `BatchManifestRecord` and JSON manifest serialization in a new module.
   - Add `--skip-existing`, `--force`, `--manifest`, `--verify`,
     `--continue-on-error`, and `--fail-fast` to batch CLI.
   - Make no-overwrite the default for batch outputs.
   - Keep conversion core unchanged.

2. **Phase 2: Disk-space preflight**
   - Add a pure `preflight.py` estimator with byte/GB helpers and disk checks.
   - Add `--no-preflight`, `--preflight-only`, and `--disk-safety-factor`.
   - Start with CLI integration; add GUI integration later.

3. **Phase 3: Source-aware verification**
   - Introduce a structured verification result and check records.
   - Preserve current output-only verification behavior.
   - Add optional `--source`, `--deep`, `--json`, tolerance, and strict flags.

4. **Phase 4: HTML QC report**
   - Generate standalone HTML from verification/source/output metadata.
   - Embed small thumbnails when feasible and safe.
   - Include warnings, failures, version, runtime, and non-diagnostic disclaimer.

5. **Phase 5: OME-XML hardening**
   - Parse generated XML in tests and validate special-character handling.
   - Keep manual XML unless a dependency such as `ome-types` clearly pays for
     itself.

6. **Phase 6: Documentation and validation matrix**
   - Update README workflow and conservative Xenium language.
   - Add `docs/validation_matrix.md` and `docs/release_checklist.md`.

7. **Phase 7: Optional maintainability/performance**
   - Consider serial-safe progress/logging improvements first.
   - Add batch parallelism only after disk and overwrite safety are stable.

## Baseline Validation

Commands run after syncing local `main` to GitHub `origin/main`:

```powershell
git fetch origin
git pull --ff-only origin main
python -m ruff check .
python -m pytest
```

Results:

- `ruff check .`: passed.
- Initial `pytest`: 221 passed, 3 failed on Windows due platform-specific path
  separator expectations in `tests/test_batch_plan.py`.
- After making those assertions platform-neutral, `pytest
  tests/test_batch_plan.py`: 5 passed.
- Final full-suite `python -m pytest`: 224 passed.
