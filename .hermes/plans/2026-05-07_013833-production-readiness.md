# svs-to-ometiff Production Readiness Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. In `/work`, dispatch a fresh subagent per task, then run spec-compliance review first and code-quality review second before proceeding.

**Goal:** Move `svs-to-ometiff` from an alpha proof-of-concept into a safer, releasable, production-oriented package for Aperio `Compression=33007` SVS to OME BigTIFF conversion.

**Architecture:** Keep the core converter small and CLI-first. Production readiness should focus on safe defaults, version/release correctness, repeatable validation, packaging reliability, CI gates, and explicit boundaries around the separate GUI package. Avoid large rewrites unless tests expose a real blocker.

**Tech Stack:** Python 3.9+, `numpy`, `tifffile`, `imagecodecs`, `click`, `pytest`, `ruff`, `hatchling`, GitHub Actions, PyPI trusted publishing.

---

## Current Context / Assumptions

Repository verified by read-only inspection:

- Active repo: `/Users/tommytran/Downloads/python_paper/svs_ome_automated/svs_to_ometiff`
- Git toplevel: `/Users/tommytran/Downloads/python_paper/svs_ome_automated/svs_to_ometiff`
- Active branch during planning: `gui-readme-ci-followup`
- Current status during planning: clean
- Remote: `git@github.com:tommy2scripts/svs-to-ometiff.git`
- HEAD: `7a411ac docs: polish README for v0.4.0`
- `v0.4.0` tag points to older commit `7e417b9...`, not current README-polish HEAD.
- `pyproject.toml` package version: `0.4.0`
- `src/svs_to_ometiff/__init__.py` version: `0.4.0`
- `src/svs_to_ometiff/cli.py` hardcodes CLI version/warning: `0.4.0`
- CI exists at `.github/workflows/ci.yml` and tests Python `3.9` through `3.13`.
- Core package has 23 tracked files, including `LICENSE`.
- README is honest about experimental status and one-real-file structural validation.
- Separate GUI work exists in an extracted PyPI source workspace, not in this repo as a clean standalone repo.

Assumptions for production readiness:

- Keep the package pre-1.0 / alpha until broader real-file validation is complete.
- Do not claim diagnostic or clinical readiness.
- Prefer safe defaults over smaller output files where production users might run the tool blindly.
- Treat the GUI as a companion release, not a blocker for core CLI production readiness.

---

## Production Readiness Definition

The repo is production-ready enough for controlled research/internal use when:

- [ ] Clean install from built wheel works in a fresh environment.
- [ ] CLI and programmatic API expose consistent version metadata.
- [ ] Defaults are safe and match the documented validated profile, or docs clearly mark non-safe defaults.
- [ ] Users can inspect source SVS metadata before converting.
- [ ] Users can verify output OME-TIFF structure after converting.
- [ ] Unit, integration, memory, lint, build, and package checks pass locally and in CI.
- [ ] CI blocks broken builds and validates wheel/sdist metadata.
- [ ] Release tagging and PyPI publish flow are deterministic.
- [ ] README, validation protocol, and release notes do not overclaim validation.
- [ ] GUI packaging is either explicitly out-of-scope or spun into a real repo/release track.

---

## Proposed Approach

Execute in four milestones:

1. **Release correctness and safe defaults** — stop version drift; decide and implement conservative defaults.
2. **Validation UX** — add first-class inspect/verify commands so production users do not rely only on README snippets.
3. **CI/package/release hardening** — add build/twine checks, version checks, tag hygiene, and release checklist docs.
4. **GUI boundary cleanup** — choose a standalone GUI repo or document it as separate companion package work.

Each task below is scoped to be delegated to a focused subagent during `/work`.

---

## Files Likely To Change

Core package:

- `pyproject.toml`
- `README.md`
- `.github/workflows/ci.yml`
- `src/svs_to_ometiff/__init__.py`
- `src/svs_to_ometiff/cli.py`
- `src/svs_to_ometiff/config.py`
- `src/svs_to_ometiff/converter.py`
- `src/svs_to_ometiff/tile_reader.py`
- `src/svs_to_ometiff/writer.py`
- `src/svs_to_ometiff/verify.py` — likely new
- `src/svs_to_ometiff/inspect.py` or `src/svs_to_ometiff/metadata.py` — likely new
- `tests/test_release_metadata.py` — likely new
- `tests/test_cli.py` — likely new or split from `tests/test_validation.py`
- `tests/test_inspect_verify.py` — likely new
- `tests/test_integration.py`
- `tests/test_streaming_writer.py`

Docs/release:

- `docs/validation_protocol.md`
- `docs/release_checklist.md` — likely new
- `docs/real_file_validation_template.md` — likely new
- `CHANGELOG.md` — likely new
- `.github/dependabot.yml` — optional new

Plan-only file already created:

- `.hermes/plans/2026-05-07_013833-production-readiness.md`

---

# Implementation Tasks

## Milestone 0 — Pre-flight and Branch Hygiene

### Task 0.1: Confirm correct repo and create work branch

**Objective:** Start execution from the correct nested repo and avoid committing GUI or parent-repo artifacts accidentally.

**Files:**

- No source changes expected.

**Steps for `/work`:**

1. Run:

   ```bash
   git rev-parse --show-toplevel
   git status --short --branch
   git tag --points-at HEAD
   git rev-list -n 1 v0.4.0 || true
   ```

2. Expected:

   - Toplevel equals `/Users/tommytran/Downloads/python_paper/svs_ome_automated/svs_to_ometiff`.
   - Status is clean except possible `.hermes/plans/...` if not yet committed.

3. Create branch only if clean:

   ```bash
   git checkout -B production-readiness-0.4.1
   ```

4. Commit this plan if desired:

   ```bash
   git add .hermes/plans/2026-05-07_013833-production-readiness.md
   git commit -m "docs: add production readiness plan"
   ```

**Verification:**

```bash
git status --short --branch
git branch --show-current
```

Expected branch: `production-readiness-0.4.1`.

---

## Milestone 1 — Release Metadata and Safe Defaults

### Task 1.1: Add release metadata consistency tests

**Objective:** Prevent version drift between `pyproject.toml`, package `__version__`, CLI `--version`, and visible experimental warning copy.

**Files:**

- Create: `tests/test_release_metadata.py`
- Modify if needed: `src/svs_to_ometiff/cli.py`
- Modify if needed: `src/svs_to_ometiff/__init__.py`

**Test to add:**

```python
"""Release metadata consistency tests."""

from pathlib import Path
import re

from click.testing import CliRunner

import svs_to_ometiff
from svs_to_ometiff.cli import main as cli_main


def _pyproject_version() -> str:
    text = Path("pyproject.toml").read_text()
    match = re.search(r'^version = "([^"]+)"', text, flags=re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_package_version_matches_pyproject() -> None:
    assert svs_to_ometiff.__version__ == _pyproject_version()


def test_cli_version_matches_package_version() -> None:
    result = CliRunner().invoke(cli_main, ["--version"])

    assert result.exit_code == 0
    assert svs_to_ometiff.__version__ in result.output


def test_experimental_warning_mentions_package_version(tmp_path) -> None:
    missing = tmp_path / "missing.svs"
    output = tmp_path / "out.ome.tiff"

    result = CliRunner().invoke(cli_main, [str(missing), str(output)])

    assert result.exit_code != 0
    assert f"v{svs_to_ometiff.__version__}" in result.stderr
```

**Run to verify failure first:**

```bash
python -m pytest tests/test_release_metadata.py -v
```

Expected: likely FAIL if current hardcoded values do not stay centralized in future.

**Implementation guidance:**

- Keep `__version__` in `src/svs_to_ometiff/__init__.py` as the runtime source of truth.
- In `src/svs_to_ometiff/cli.py`, import `__version__` and replace hardcoded `0.4.0` in:
  - `_print_experimental_warning()`
  - `@click.version_option(...)`

Example:

```python
from svs_to_ometiff import __version__

@click.version_option(version=__version__, prog_name="svs-to-ometiff")
```

**Verification:**

```bash
python -m pytest tests/test_release_metadata.py -v
python -m pytest -q
python -m ruff check .
```

**Commit:**

```bash
git add src/svs_to_ometiff/cli.py tests/test_release_metadata.py
git commit -m "test: enforce release metadata consistency"
```

---

### Task 1.2: Decide and implement production-safe defaults

**Objective:** Align CLI/config/programmatic defaults with the safest validated production profile, unless an explicit decision is made to preserve current alpha defaults.

**Recommended decision:** Change defaults to the conservative real-file validation profile before the next release:

- `compression=None` / CLI `--compression none`
- `num_levels=3`
- `tile_size=512`
- `downsample_factor=2`

Rationale: Current default `lzw` can fail when `imagecodecs` is unavailable, and current `num_levels=6` is slower/heavier than the one-real-file validated profile.

**Files:**

- Modify: `src/svs_to_ometiff/config.py`
- Modify: `src/svs_to_ometiff/converter.py`
- Modify: `src/svs_to_ometiff/cli.py`
- Modify: `README.md`
- Modify: `tests/test_integration.py`
- Create or modify: `tests/test_cli.py`

**Tests to add before implementation:**

```python
from click.testing import CliRunner

from svs_to_ometiff import ConvertConfig
from svs_to_ometiff.cli import main as cli_main


def test_convert_config_defaults_match_validated_profile() -> None:
    config = ConvertConfig("input.svs", "output.ome.tiff")

    assert config.tile_size == 512
    assert config.compression is None
    assert config.num_levels == 3
    assert config.downsample_factor == 2


def test_cli_help_shows_safe_defaults() -> None:
    result = CliRunner().invoke(cli_main, ["--help"])

    assert result.exit_code == 0
    assert "--compression" in result.output
    assert "none" in result.output
    assert "--num-levels" in result.output
    assert "3" in result.output
```

**Implementation guidance:**

- In `src/svs_to_ometiff/config.py`:

  ```python
  compression: Optional[str] = None
  num_levels: int = 3
  ```

- In `src/svs_to_ometiff/converter.py`, update `_LEGACY_CONFIG_DEFAULTS`:

  ```python
  "compression": None,
  "num_levels": 3,
  ```

- In `src/svs_to_ometiff/cli.py`, update click defaults:

  ```python
  @click.option(
      "--compression",
      default="none",
      type=click.Choice(["lzw", "zlib", "deflate", "none"]),
      show_default=True,
      help="TIFF compression scheme. Use 'none' for maximum compatibility.",
  )

  @click.option(
      "--num-levels",
      default=3,
      type=int,
      show_default=True,
      help="Number of pyramid levels, including full resolution.",
  )
  ```

- Update README “At a glance” and CLI option table so defaults are not contradictory.

**Verification:**

```bash
python -m pytest tests/test_cli.py tests/test_integration.py -v
python -m pytest -q
python -m ruff check .
```

**Commit:**

```bash
git add src/svs_to_ometiff/config.py src/svs_to_ometiff/converter.py src/svs_to_ometiff/cli.py README.md tests/test_cli.py tests/test_integration.py
git commit -m "feat: default conversions to validated safe profile"
```

---

### Task 1.3: Validate numeric CLI/config parameters before heavy work

**Objective:** Fail fast for invalid `tile_size`, `num_levels`, `downsample_factor`, and `edge_mode` before opening large files or allocating memmaps.

**Files:**

- Modify: `src/svs_to_ometiff/config.py`
- Modify: `src/svs_to_ometiff/converter.py`
- Modify: `src/svs_to_ometiff/cli.py`
- Create or modify: `tests/test_config.py`
- Modify: `tests/test_validation.py`

**Tests to add first:**

```python
import pytest

from svs_to_ometiff import ConvertConfig


@pytest.mark.parametrize("tile_size", [0, -1, 10])
def test_config_rejects_invalid_tile_size(tile_size: int) -> None:
    with pytest.raises(ValueError, match="tile_size"):
        ConvertConfig("in.svs", "out.ome.tiff", tile_size=tile_size)


@pytest.mark.parametrize("num_levels", [0, -1])
def test_config_rejects_invalid_num_levels(num_levels: int) -> None:
    with pytest.raises(ValueError, match="num_levels"):
        ConvertConfig("in.svs", "out.ome.tiff", num_levels=num_levels)


@pytest.mark.parametrize("downsample_factor", [0, 1, -2])
def test_config_rejects_invalid_downsample_factor(downsample_factor: int) -> None:
    with pytest.raises(ValueError, match="downsample_factor"):
        ConvertConfig("in.svs", "out.ome.tiff", downsample_factor=downsample_factor)
```

**Implementation guidance:**

- Add `__post_init__` to frozen dataclass using `object.__setattr__` only if normalization is required.
- Reject:
  - `tile_size <= 0`
  - `tile_size % 16 != 0`
  - `num_levels < 1`
  - `downsample_factor < 2`
  - unsupported `compression` not in `{None, "lzw", "zlib", "deflate"}`

**Verification:**

```bash
python -m pytest tests/test_config.py -v
python -m pytest -q
python -m ruff check .
```

**Commit:**

```bash
git add src/svs_to_ometiff/config.py tests/test_config.py tests/test_validation.py
git commit -m "feat: validate conversion configuration early"
```

---

## Milestone 2 — First-Class Inspect and Verify UX

### Task 2.1: Add source SVS inspection helper and CLI command

**Objective:** Let users confirm source compression/dimensions/tile metadata before conversion without writing output.

**Files:**

- Create: `src/svs_to_ometiff/inspect.py` or `src/svs_to_ometiff/metadata.py`
- Modify: `pyproject.toml`
- Create: `tests/test_inspect.py`
- Modify: `README.md`

**Preferred API:**

```python
def inspect_svs(path: str) -> dict[str, object]:
    """Return source SVS metadata relevant to conversion readiness."""
```

**Console script:**

In `pyproject.toml`:

```toml
[project.scripts]
svs-to-ometiff = "svs_to_ometiff.cli:main"
svs-to-ometiff-inspect = "svs_to_ometiff.inspect:main"
```

**Tests to add first:**

```python
from click.testing import CliRunner

from helpers import write_synthetic_33007_svs
from svs_to_ometiff.inspect import inspect_svs, main


def test_inspect_svs_reports_required_metadata(tmp_path) -> None:
    source = tmp_path / "synthetic.svs"
    write_synthetic_33007_svs(source, width=32, height=24)

    metadata = inspect_svs(str(source))

    assert metadata["compression"] == 33007
    assert metadata["width"] == 32
    assert metadata["height"] == 24
    assert metadata["convertible"] is True


def test_inspect_cli_prints_convertible_status(tmp_path) -> None:
    source = tmp_path / "synthetic.svs"
    write_synthetic_33007_svs(source, width=32, height=24)

    result = CliRunner().invoke(main, [str(source)])

    assert result.exit_code == 0
    assert "Compression: 33007" in result.output
    assert "Convertible: yes" in result.output
```

**Implementation guidance:**

- Reuse `read_svs_metadata()` from `src/svs_to_ometiff/tile_reader.py`.
- Do not decode tiles in inspect mode.
- Print concise text by default.
- Optional `--json` flag can be added if easy, but do not overbuild.

**Verification:**

```bash
python -m pytest tests/test_inspect.py -v
python -m pytest -q
python -m ruff check .
```

**Commit:**

```bash
git add src/svs_to_ometiff/inspect.py pyproject.toml tests/test_inspect.py README.md
git commit -m "feat: add source SVS inspection command"
```

---

### Task 2.2: Add output OME-TIFF verification helper and CLI command

**Objective:** Turn README verification snippet into a tested command for real production handoff.

**Files:**

- Create: `src/svs_to_ometiff/verify.py`
- Modify: `pyproject.toml`
- Create: `tests/test_verify.py`
- Modify: `README.md`
- Modify: `docs/validation_protocol.md`

**Preferred API:**

```python
def verify_ometiff(path: str, *, min_levels: int = 1) -> dict[str, object]:
    """Validate basic OME BigTIFF RGB/pyramid structure and return summary."""
```

**Console script:**

In `pyproject.toml`:

```toml
svs-to-ometiff-verify = "svs_to_ometiff.verify:main"
```

**Tests to add first:**

```python
from click.testing import CliRunner
import numpy as np
import pytest

from svs_to_ometiff.verify import verify_ometiff, main
from svs_to_ometiff.writer import write_pyramidal_ometiff


def test_verify_ometiff_accepts_valid_rgb_ome_pyramid(tmp_path) -> None:
    output = tmp_path / "valid.ome.tiff"
    pyramid = [
        np.zeros((32, 32, 3), dtype=np.uint8),
        np.zeros((16, 16, 3), dtype=np.uint8),
    ]
    write_pyramidal_ometiff(str(output), pyramid, 0.5, compression=None, verbose=False)

    summary = verify_ometiff(str(output), min_levels=2)

    assert summary["is_ome"] is True
    assert summary["is_bigtiff"] is True
    assert len(summary["levels"]) == 2


def test_verify_cli_reports_pass(tmp_path) -> None:
    output = tmp_path / "valid.ome.tiff"
    pyramid = [np.zeros((16, 16, 3), dtype=np.uint8)]
    write_pyramidal_ometiff(str(output), pyramid, 0.5, compression=None, verbose=False)

    result = CliRunner().invoke(main, [str(output)])

    assert result.exit_code == 0
    assert "PASS" in result.output
```

**Implementation guidance:**

- Use `tifffile.TiffFile(path)`.
- Check:
  - `tif.is_ome`
  - `tif.is_bigtiff`
  - `tif.series` exists
  - `series[0].levels` length >= `min_levels`
  - each level has RGB shape `(Y, X, 3)`
  - level 0 dtype is `uint8`
- Return dict with `levels`, `is_ome`, `is_bigtiff`, `subifds`, `dtype`.
- CLI should exit nonzero on failed checks.

**Verification:**

```bash
python -m pytest tests/test_verify.py -v
python -m pytest -q
python -m ruff check .
```

**Commit:**

```bash
git add src/svs_to_ometiff/verify.py pyproject.toml tests/test_verify.py README.md docs/validation_protocol.md
git commit -m "feat: add OME-TIFF verification command"
```

---

### Task 2.3: Add end-to-end CLI smoke test using inspect -> convert -> verify

**Objective:** Validate the production path a user will actually follow.

**Files:**

- Create or modify: `tests/test_cli_end_to_end.py`

**Test to add:**

```python
from click.testing import CliRunner

from helpers import write_synthetic_33007_svs
from svs_to_ometiff.cli import main as convert_main
from svs_to_ometiff.inspect import main as inspect_main
from svs_to_ometiff.verify import main as verify_main


def test_cli_inspect_convert_verify_flow(tmp_path) -> None:
    source = tmp_path / "synthetic.svs"
    output = tmp_path / "synthetic.ome.tiff"
    write_synthetic_33007_svs(source, width=32, height=32)

    inspect_result = CliRunner().invoke(inspect_main, [str(source)])
    assert inspect_result.exit_code == 0
    assert "Convertible: yes" in inspect_result.output

    convert_result = CliRunner().invoke(
        convert_main,
        [str(source), str(output), "--compression", "none", "--num-levels", "2", "--quiet"],
    )
    assert convert_result.exit_code == 0
    assert output.exists()

    verify_result = CliRunner().invoke(verify_main, [str(output), "--min-levels", "2"])
    assert verify_result.exit_code == 0
    assert "PASS" in verify_result.output
```

**Verification:**

```bash
python -m pytest tests/test_cli_end_to_end.py -v
python -m pytest -q
python -m ruff check .
```

**Commit:**

```bash
git add tests/test_cli_end_to_end.py
git commit -m "test: cover production CLI inspect-convert-verify flow"
```

---

## Milestone 3 — Packaging, CI, and Release Hardening

### Task 3.1: Add build and package metadata checks to CI

**Objective:** Ensure every PR proves the package builds and passes metadata checks before merge/release.

**Files:**

- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`

**Implementation guidance:**

- Add dev dependencies:

  ```toml
  dev = [
      "pytest>=7.0",
      "ruff>=0.1.0",
      "psutil>=5.9",
      "build>=1.0",
      "twine>=5.0",
  ]
  ```

- Update CI build job:

  ```yaml
  - name: Build wheel and sdist
    run: |
      python -m pip install --upgrade pip
      python -m pip install build twine
      python -m build
      python -m twine check dist/*
  ```

- Add explicit minimal permissions at workflow top:

  ```yaml
  permissions:
    contents: read
  ```

- Keep release job with:

  ```yaml
  permissions:
    id-token: write
    contents: write
  ```

**Verification:**

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
rm -rf dist
python -m build
python -m twine check dist/*
```

**Commit:**

```bash
git add pyproject.toml .github/workflows/ci.yml
git commit -m "ci: validate package build metadata"
```

---

### Task 3.2: Add release checklist and changelog

**Objective:** Make release/publish steps deterministic and avoid moving tags accidentally.

**Files:**

- Create: `CHANGELOG.md`
- Create: `docs/release_checklist.md`
- Modify: `README.md`

**Release checklist content should include:**

```markdown
# Release Checklist

## Pre-release

- [ ] `git status --short --branch` is clean.
- [ ] `python -m pytest -q` passes.
- [ ] `python -m ruff check .` passes.
- [ ] `rm -rf dist && python -m build` passes.
- [ ] `python -m twine check dist/*` passes.
- [ ] `python -m svs_to_ometiff --version` matches `pyproject.toml`.
- [ ] `CHANGELOG.md` has a dated entry.
- [ ] README validation status is honest and current.
- [ ] If publishing GUI, core `svs-to-ometiff>=0.4.0` is already on PyPI.

## Tagging

- [ ] Tag only the exact release commit.
- [ ] Do not move a pushed tag unless intentionally repairing a failed release.
- [ ] Use `git tag -a vX.Y.Z -m "vX.Y.Z"`.
- [ ] Push with `git push origin main --tags`.

## Post-release

- [ ] Verify PyPI page renders README.
- [ ] Fresh-venv install from PyPI works.
- [ ] `svs-to-ometiff-inspect`, `svs-to-ometiff`, and `svs-to-ometiff-verify` work on synthetic fixture or documented sample.
```

**Verification:**

```bash
python - <<'PY'
from pathlib import Path
for path in ["CHANGELOG.md", "docs/release_checklist.md", "README.md"]:
    text = Path(path).read_text()
    assert "svs-to-ometiff" in text.lower() or path == "CHANGELOG.md"
print("docs smoke ok")
PY
python -m pytest -q
```

**Commit:**

```bash
git add CHANGELOG.md docs/release_checklist.md README.md
git commit -m "docs: add release checklist and changelog"
```

---

### Task 3.3: Add a fresh-wheel install smoke test script

**Objective:** Catch packaging mistakes that editable installs hide.

**Files:**

- Create: `scripts/smoke_install.sh`
- Modify: `docs/release_checklist.md`
- Modify: `.gitignore` if needed

**Script content:**

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROOT}/.smoke-venv"

rm -rf "${VENV}" "${ROOT}/dist"
python -m build --outdir "${ROOT}/dist"
python -m venv "${VENV}"
"${VENV}/bin/python" -m pip install --upgrade pip
"${VENV}/bin/python" -m pip install "${ROOT}"/dist/*.whl
"${VENV}/bin/svs-to-ometiff" --version
"${VENV}/bin/svs-to-ometiff-inspect" --help
"${VENV}/bin/svs-to-ometiff-verify" --help
```

**Verification:**

```bash
chmod +x scripts/smoke_install.sh
./scripts/smoke_install.sh
```

**Commit:**

```bash
git add scripts/smoke_install.sh docs/release_checklist.md .gitignore
git commit -m "test: add fresh wheel install smoke check"
```

---

### Task 3.4: Reconcile `v0.4.0` tag vs current README-polish HEAD

**Objective:** Avoid a confusing release state where the PyPI/package tag does not include current README polish.

**Files:**

- Likely no source files.
- Possibly `CHANGELOG.md` if a new `0.4.1` release is selected.
- Possibly `pyproject.toml` / `src/svs_to_ometiff/__init__.py` if bumping.

**Decision gate:**

Choose one:

1. **Do not move `v0.4.0`; release new `v0.4.1`.** Recommended if `v0.4.0` was already pushed or published.
2. **Move `v0.4.0`; only if it was never published and user explicitly approves tag rewrite.** Not recommended by default.

**Recommended execution:**

- Bump to `0.4.1` after production-hardening tasks pass.
- Add changelog entry for `0.4.1`.
- Tag `v0.4.1` on the final release commit.

**Verification before tagging:**

```bash
git tag --points-at HEAD
python -m pytest -q
python -m ruff check .
rm -rf dist
python -m build
python -m twine check dist/*
```

**Commit if bumping:**

```bash
git add pyproject.toml src/svs_to_ometiff/__init__.py CHANGELOG.md
git commit -m "chore: prepare v0.4.1 release"
```

---

## Milestone 4 — Validation Evidence and Documentation

### Task 4.1: Add real-file validation record template

**Objective:** Make it easy to collect more real `Compression=33007` evidence without committing large/private SVS files.

**Files:**

- Create: `docs/real_file_validation_template.md`
- Modify: `docs/validation_protocol.md`
- Modify: `README.md`

**Template content should include:**

```markdown
# Real File Validation Record

## Source

- Anonymized ID:
- Scanner model:
- Firmware/export settings, if known:
- Tissue/stain:
- Source dimensions:
- Source tile size:
- Compression tag:
- MPP:

## Command

```bash
svs-to-ometiff input.svs output.ome.tiff --compression none --num-levels 3 --tile-size 512
```

## Structural Output

- `tif.is_ome`:
- `tif.is_bigtiff`:
- level shapes:
- SubIFD count:
- output size:
- peak RSS:

## Visual Review

- thumbnail generated:
- no obvious channel swap:
- no tiled seams:
- no major color artifacts:
- reviewer/date:

## Downstream Import

- tool:
- version:
- result:
- notes:
```

**Verification:**

```bash
python - <<'PY'
from pathlib import Path
p = Path("docs/real_file_validation_template.md")
text = p.read_text()
for needle in ["Compression tag", "Visual Review", "Downstream Import"]:
    assert needle in text
print("template ok")
PY
```

**Commit:**

```bash
git add docs/real_file_validation_template.md docs/validation_protocol.md README.md
git commit -m "docs: add real-file validation record template"
```

---

### Task 4.2: Add visual thumbnail review utility or documented recipe

**Objective:** Support the current validation gap: “Visual review pending manual thumbnail review.”

**Files:**

- Option A create: `src/svs_to_ometiff/thumbnail.py`
- Option A modify: `pyproject.toml`
- Option A create: `tests/test_thumbnail.py`
- Option B docs-only: `docs/validation_protocol.md`

**Recommended YAGNI choice:** Start docs-only unless user wants a generated thumbnail command.

**Docs recipe:**

```bash
python - <<'PY'
import tifffile
from PIL import Image

with tifffile.TiffFile("output.ome.tiff") as tif:
    level = tif.series[0].levels[-1].asarray()
Image.fromarray(level).save("output_thumbnail.png")
PY
```

**Caveat:** Adding Pillow as a dependency just for thumbnail export may be unnecessary. Prefer docs-only or an optional extra if implemented.

**Verification:**

```bash
python -m pytest -q
python -m ruff check .
```

**Commit:**

```bash
git add docs/validation_protocol.md README.md
git commit -m "docs: add visual thumbnail review recipe"
```

---

## Milestone 5 — GUI Boundary / Companion Release

### Task 5.1: Decide GUI packaging path

**Objective:** Avoid loose extracted PyPI GUI work becoming production confusion.

**Known state:**

- GUI source workspace exists at:
  `/Users/tommytran/Downloads/python_paper/svs_ome_automated/svs_to_ometiff_gui_work/source/svs_to_ometiff_gui-0.1.0`
- Prepared artifacts exist for `svs-to-ometiff-gui==0.1.1`.
- There is no confirmed accessible standalone GitHub repo at `tommy2scripts/svs-to-ometiff-gui`.
- GUI `0.1.1` should not be published until core `svs-to-ometiff>=0.4.0` is available on the target package index or install docs require GitHub core install first.

**Options:**

1. **Standalone GUI repo** — recommended if GUI should remain separate.
   - Create new GitHub repo `tommy2scripts/svs-to-ometiff-gui`.
   - Import cleaned `0.1.1` source as initial commit.
   - Add CI/build/release similar to core.

2. **Monorepo under this repo** — recommended if one release train is easier.
   - Add `packages/svs-to-ometiff-gui/`.
   - Keep core package at root.
   - Add separate CI jobs.

3. **Out-of-scope for core** — fastest for core production release.
   - README says GUI is separate and experimental.
   - Core release proceeds independently.

**Recommended decision:** Option 1 after core PyPI release is fixed.

**Files in core repo if documenting only:**

- Modify: `README.md`
- Create: `docs/gui_release_notes.md` or link to future repo.

**Verification:**

```bash
python -m pytest -q
python -m ruff check .
```

**Commit:**

```bash
git add README.md docs/gui_release_notes.md
git commit -m "docs: clarify GUI companion package status"
```

---

# Final Integration Review

After all selected tasks are complete, dispatch a final integration reviewer with this context:

```text
Review the full svs-to-ometiff production-readiness branch.
Check:
- Version metadata consistency.
- Safe defaults align across CLI/config/README/tests.
- Inspect/verify CLI commands work and are documented.
- CI/build/twine checks are configured correctly.
- Release checklist prevents tag/PyPI mistakes.
- Experimental validation caveats remain honest.
- No GUI workspace artifacts or large SVS/OME files were committed.
Return APPROVED or REQUEST_CHANGES with blockers only.
```

Then run locally:

```bash
python -m pytest -q
python -m ruff check .
rm -rf dist
python -m build
python -m twine check dist/*
python -m svs_to_ometiff --version
```

If `scripts/smoke_install.sh` was added:

```bash
./scripts/smoke_install.sh
```

Expected:

- All tests pass.
- Ruff passes.
- Wheel and sdist build.
- Twine check passes.
- CLI version matches package version.
- Fresh-wheel smoke test passes.

---

# Risks / Tradeoffs

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Changing defaults from `lzw`/6 to `none`/3 changes output size and behavior | Larger default files, fewer pyramid levels | Do before 1.0; document clearly; users can opt into LZW/6 |
| Adding inspect/verify commands increases surface area | More tests/docs to maintain | Keep APIs small and reuse existing metadata/writer code |
| PyPI core version lag blocks GUI install | GUI publish confusion | Publish core first or document GitHub core install path |
| Tag `v0.4.0` is behind current README polish | Release provenance confusion | Prefer new `v0.4.1` instead of moving old tag |
| Real-file validation remains limited | Users may overtrust output | Keep experimental warnings; require visual/manual validation |
| CI cannot include private real SVS files | Real-world coverage limited | Add record templates and collect anonymized metadata/logs |

---

# Open Questions Before `/work`

1. Should core CLI defaults change to the conservative validated profile (`compression none`, `num_levels 3`) now?
   - Recommended: yes, before any wider release.

2. Should the next release be `0.4.1` instead of moving `v0.4.0`?
   - Recommended: yes, do not rewrite a pushed/published tag.

3. Should GUI become a standalone repo or stay out-of-scope until core is on PyPI?
   - Recommended: standalone repo after core PyPI release succeeds.

4. Should thumbnail generation become a CLI command or remain a docs recipe?
   - Recommended: docs recipe first to avoid adding Pillow dependency.

---

# `/work` Execution Order

Recommended first `/work` batch:

1. Task 1.1 — release metadata consistency tests.
2. Task 1.2 — safe defaults decision/implementation.
3. Task 1.3 — early config validation.
4. Task 2.1 — inspect command.
5. Task 2.2 — verify command.
6. Task 2.3 — inspect-convert-verify integration test.
7. Task 3.1 — build/twine CI hardening.
8. Task 3.2 — release checklist/changelog.
9. Task 3.4 — version bump/tag strategy for `0.4.1`.
10. Final integration review.

Defer until after core release:

- Task 5.1 GUI standalone repo/release path.

---

# Completion Criteria

This plan is complete when:

- [ ] All selected tasks have commits.
- [ ] Final integration reviewer approves.
- [ ] `python -m pytest -q` passes.
- [ ] `python -m ruff check .` passes.
- [ ] `python -m build` passes.
- [ ] `python -m twine check dist/*` passes.
- [ ] Fresh-wheel smoke test passes if added.
- [ ] README and docs preserve experimental/non-diagnostic caveats.
- [ ] Release checklist is followed for the next tag/PyPI publish.
