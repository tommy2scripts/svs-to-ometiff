# Gemini Handoff: svs-to-ometiff Hardening

Repository: <https://github.com/tommy2scripts/svs-to-ometiff>

Local path used by Codex:

```text
C:\Users\ttran\Desktop\AZ_HE_tracker\svs-to-ometiff
```

## Current State

The latest GitHub version was treated as the source of truth because the user
works from multiple computers.

Phase 0 and Phase 1 were completed, committed, and pushed to `main`.

Latest pushed `main` commit:

```text
6e4bdb5 Add safe resumable batch manifests
```

Current PR branch:

```text
phase2-disk-preflight
```

Current pushed branch commit:

```text
1f4e511 Add single-file disk preflight
```

This handoff document is intended to be committed on the same
`phase2-disk-preflight` branch after the Phase 2 implementation commit. If it
has been pushed, Gemini can treat the branch itself as the complete handoff
context.

PR creation URL:

```text
https://github.com/tommy2scripts/svs-to-ometiff/pull/new/phase2-disk-preflight
```

The GitHub CLI (`gh`) was not installed locally, so Codex pushed the branch but
did not create the pull request directly.

## Completed Work

### Phase 0: Baseline Audit

Added:

```text
docs/engineering_audit.md
```

This documents the current architecture, CLI commands, risks, test gaps, and
recommended implementation sequence.

### Phase 1: Batch Safety and Resumability

Added safe batch behavior:

- `--skip-existing`
- `--force`
- `--manifest PATH`
- `--verify`
- `--verify-existing`
- `--continue-on-error`
- `--fail-fast`

Important behavior:

- Batch conversion no longer overwrites existing outputs unless `--force` is
  provided.
- `--skip-existing` records skipped files in the manifest.
- `--verify` records verification status in the manifest.
- Conflicting `--continue-on-error` and `--fail-fast` flags fail cleanly.
- JSON manifest writes are atomic.

Primary files changed in Phase 1:

```text
README.md
src/svs_to_ometiff/batch.py
src/svs_to_ometiff/batch_manifest.py
tests/test_batch_plan.py
tests/test_batch_safety.py
docs/engineering_audit.md
```

Validation before pushing Phase 1:

```text
python -m ruff check .
python -m pytest
python -m build
python -m twine check dist\*
```

Result:

```text
232 passed
```

### Phase 2 Started: Disk-Space Preflight

Branch:

```text
phase2-disk-preflight
```

Implemented first PR-sized Phase 2 slice:

- New pure estimation/check module: `src/svs_to_ometiff/preflight.py`
- Single-file CLI now runs preflight by default before conversion.
- Added `--preflight-only`.
- Added `--no-preflight`.
- Added `--disk-safety-factor FLOAT`, default `1.3`.
- Preflight uses the same temp directory as conversion:
  `--temp-dir` or the system temp directory.
- `--preflight-only` reports estimates and exits without writing output.
- `--no-preflight` bypasses the check.
- Conflicting `--preflight-only` and `--no-preflight` fails through Click usage
  handling.

Primary files changed in the Phase 2 branch:

```text
README.md
src/svs_to_ometiff/cli.py
src/svs_to_ometiff/preflight.py
tests/test_cli_preflight.py
tests/test_cli_temp_dir.py
tests/test_preflight.py
```

Validation after Phase 2 branch work:

```text
python -m pytest tests\test_preflight.py tests\test_cli_preflight.py tests\test_cli_temp_dir.py
python -m ruff check src\svs_to_ometiff\preflight.py src\svs_to_ometiff\cli.py tests\test_preflight.py tests\test_cli_preflight.py tests\test_cli_temp_dir.py
python -m ruff check .
python -m pytest
python -m build
python -m twine check dist\*
```

Results:

```text
focused tests: 16 passed
full tests: 241 passed
ruff: passed
build: passed
twine check: passed
```

## Important Project Constraints

The user wants this to become a reliable internal scientific imaging utility for
converting selected Aperio SVS files, especially compression `33007`, into
pyramidal OME-TIFF / BigTIFF outputs suitable for QuPath, Bio-Formats-style
viewers, and Xenium Explorer post-Xenium H&E alignment workflows.

Do not overstate compatibility. Use language like:

```text
Designed for Xenium Explorer post-Xenium H&E alignment workflows and validated
on tested Aperio compression-33007 slides. Users should confirm import and
alignment in Xenium Explorer for each production workflow.
```

Do not claim Xenium Explorer validation unless it was actually tested.

Keep changes incremental and PR-sized. Preserve current CLI behavior unless the
change is clearly justified. Favor tests alongside implementation.

## Recommended Next Goal

Finish Phase 2 in a follow-up PR or extend the current PR if desired:

1. Add disk preflight integration to the batch command.
2. Record preflight pass/fail details in the batch manifest.
3. Make preflight failures resumable with `--continue-on-error`.
4. Ensure `--preflight-only` for batch does not create output files.
5. Add tests for batch preflight:
   - batch preflight passes with mocked disk usage
   - batch preflight fails before conversion when space is insufficient
   - `--continue-on-error` records preflight failure and continues
   - `--fail-fast` stops on first preflight failure
   - manifest includes preflight estimates/errors

Suggested next branch name:

```text
phase2-batch-preflight
```

Suggested next PR title:

```text
Add batch disk preflight and manifest reporting
```

## Later Phases From Original Plan

After Phase 2 is stable:

1. Phase 3: stronger source-aware verification
2. Phase 4: HTML QC report
3. Phase 5: OME-XML and metadata hardening
4. Phase 6: documentation and validation matrix
5. Phase 7: optional performance and maintainability improvements

## Manual Validation Still Required

Routine tests use synthetic/small fixtures. The following still need real lab
validation:

- Real Aperio compression-33007 SVS inspection
- Large SVS conversion on Windows
- Verify generated OME-TIFF / BigTIFF
- Open output in QuPath
- Import/alignment workflow in Xenium Explorer, if available

Do not claim clinical, diagnostic, or universal WSI-converter validity.
