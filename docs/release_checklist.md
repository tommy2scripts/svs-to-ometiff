# Release Checklist

This checklist defines the required pre-release steps for verifying and packaging new versions of the `svs-to-ometiff` whole-slide converter utility. Follow these steps sequentially before tagging a release or deploying updates to production pipelines.

> [!WARNING]
> **Non-Diagnostic Disclaimer**
> This utility is designed for research use only. Never release a package that implies clinical or diagnostic utility. Ensure that all command interfaces and documentation carry prominent research-use disclaimers.

---

## 1. Local Environment Setup

Activate the standard development environment and clean up previous temporary builds:

```powershell
# Activate local virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade essential dev tooling
python -m pip install --upgrade pip setuptools build twine ruff pytest
```

---

## 2. Code Quality & Formatting Audits

Verify that all source code complies with styling standards. The repository must be completely clean under Ruff static analysis:

```powershell
# Run Ruff linting and style checking
python -m ruff check src/ tests/

# Expected output: "All checks passed!"
```

---

## 3. Automated Test Suite Execution

Run the complete suite of 250+ automated unit and integration tests. No failures are acceptable:

```powershell
# Run full test suite with no cache provider and specific base directory
python -m pytest --basetemp=temp_pytest -p no:cacheprovider -v

# Expected output: "270 passed in XXs"
```

---

## 4. Manual CLI Verification Checks

Verify all core CLI operations using a known valid test slide:

### 1. SVS Metadata Inspection
```powershell
svs-to-ometiff-inspect test_slide.svs
# Confirm: Compression is 33007 and Convertible is report as "yes"
```

### 2. Disk Space Preflight Estimation
```powershell
svs-to-ometiff test_slide.svs test_slide.ome.tiff --preflight-only --temp-dir local_tmp
# Confirm: Displays correct size estimations and pass status without creating output file
```

### 3. Pyramidal Conversion
```powershell
svs-to-ometiff test_slide.svs test_slide.ome.tiff --temp-dir local_tmp --edge-mode crop
# Confirm: Conversion completes with standard progress metrics
```

### 4. Verification & Premium HTML QC Report
```powershell
svs-to-ometiff-verify test_slide.ome.tiff --source test_slide.svs --deep --html qc_report.html
# Confirm: verify command returns exit code 0, output passes all structural checks, and 'qc_report.html' is successfully written to disk.
```

---

## 5. Standalone Web GUI Verification

Manually launch the local web interface and verify basic interactive capabilities:

```powershell
# Launch GUI
svs-to-ometiff-gui
```

- Open `http://127.0.0.1:8765` in a browser.
- Verify that a file path can be successfully input.
- Confirm metadata reads correctly on screen.
- Run a single-file test conversion and verify that the progress bar updates smoothly.

---

## 6. Package Compilation and Distribution Verification

Verify that the project packages correctly and contains all necessary files:

```powershell
# Clean previous build directories
Remove-Item -Recurse -Force dist/, build/, src/*.egg-info/ -ErrorAction SilentlyContinue

# Build distribution packages (wheel and sdist)
python -m build

# Run Twine description validation checks
python -m twine check dist/*

# Expected output: "Checking dist\...: Passed"
```

---

## 7. Version Tagging & Git Flow

Once all of the above steps have completed successfully:

1. Update the version number in `src/svs_to_ometiff/__init__.py`.
2. Commit the version update and write a clean description in `CHANGELOG.md`.
3. Push to `main` and tag the release:
   ```bash
   git add src/svs_to_ometiff/__init__.py CHANGELOG.md
   git commit -m "Bump version to vX.Y.Z"
   git push origin main
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin vX.Y.Z
   ```
