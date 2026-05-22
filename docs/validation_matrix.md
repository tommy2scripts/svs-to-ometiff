# Validation Matrix

This document provides a systematic validation matrix for the `svs-to-ometiff` whole-slide conversion tool, outlining supported scanner types, software configurations, test footprints, and downstream workflow integrations.

> [!WARNING]
> **Non-Diagnostic Disclaimer**
> `svs-to-ometiff` is designed and intended for research use only. The pyramidal OME-TIFF outputs and verification workflows have NOT been cleared, validated, or approved for clinical, diagnostic, or therapeutic use in patients. Independent validation must be performed by the user for all downstream analytical or clinical applications.

---

## 1. Scanner & Format Support Matrix

| Vendor | Instrument Series | Export Software Version | Pixel Compression | Status | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Aperio (Leica)** | Aperio AT2 | eSlide Manager v12+ | TIFF Raw YUYV (`33007`) | **Validated** | Primary target format; fully supported for conversion. |
| **Aperio (Leica)** | Aperio GT450 | GT450 DX v1.0+ | TIFF Raw YUYV (`33007`) | **Validated** | Fully supported; matches the AT2 tile structure. |
| **Aperio (Leica)** | Aperio Scanners | Any | JPEG (`7`) | *Unsupported* | Use standard vendors/OpenSlide for JPEG-encoded SVS slides. |
| **Aperio (Leica)** | Aperio Scanners | Any | JPEG 2000 (`33003`, `33005`) | *Unsupported* | Out of scope; use OpenSlide or vendor converters. |
| **Hamamatsu** | NanoZoomer | Any | NDPI / TIFF | *Unsupported* | Non-Aperio format; out of scope. |
| **Philips** | Ultra Fast | Any | iSyntax / TIFF | *Unsupported* | Non-Aperio format; out of scope. |
| **Leica** | SCN | SCN v1.0+ | SCN / TIFF | *Unsupported* | Out of scope; use Bio-Formats. |

---

## 2. Tested Environments & Platforms

The code has been successfully compiled, linted, and verified across the following environments:

- **Windows 10 & Windows 11 Workstations**: Primary environment for test validation. Tested using both direct Python installations and virtual environments (`venv`).
- **Ubuntu Linux (20.04 / 22.04 LTS)**: Validated in continuous integration pipelines and command-line execution.
- **macOS (Intel & Apple Silicon)**: Verified for local development and unit testing portability.

---

## 3. Real-Data Validation Cohort Summary

The library was hardened and validated against a real-world scientific slide cohort:

* **Cohort size**: 21 Aperio H&E slides.
* **Source Slide Characteristics**:
  * Dimensions: Ranging up to `77,262 x 39,858` pixels (approx. 3 gigapixels).
  * Objective Magnification: `20X`.
  * Physical Pixel Size (MPP): `0.275310798315331 µm/pixel`.
  * Compression Tag: `33007` (YUYV YCbCr 4:2:2).
* **Conversion Execution Findings**:
  * **Pass Rate**: 100% (21/21 succeeded).
  * **File Size Profile**: Output OME-TIFFs ranged from **1.0 GB to 8.1 GB** utilizing default `zlib` compression.
  * **Conversion Latency**: Average runtime of ~196 seconds per 3-gigapixel slide on local SSD workstations.
  * **Verification**: All 21 outputs passed `svs-to-ometiff-verify` checks:
    * Standard OME Metadata compliance: **Pass**
    * TiffFile BigTIFF descriptor: **Pass**
    * Multi-level pyramid structure (6 levels, 5 SubIFDs): **Pass**
    * Physical resolution tag mapping correctness: **Pass**

---

## 4. Downstream Reader Compatibility

| Reader / Viewer | Version Tested | Integration Flow | Support Level | Technical Recommendations |
| :--- | :--- | :--- | :--- | :--- |
| **QuPath** | v0.4.x - v0.5.x | Drag-and-drop or Project URI | **Excellent** | Detected natively as a multi-resolution pyramid; loads tiles dynamically on demand. |
| **Xenium Explorer** | v1.3.x - v2.0+ | H&E Post-Xenium alignment | **Fully Compatible** | Use `--edge-mode crop` to strip empty pad edges and prevent alignment issues. |
| **Fiji (ImageJ)** | v1.54+ | Bio-Formats Plugin | **Compatible** | Ensure the latest Bio-Formats plugin is active for SubIFD OME compliance. |
| **Bio-Formats CLI** | v7.0+ | `showinf` / `bfconvert` | **Compatible** | Parsed successfully as a structured BigTIFF pyramid with valid physical scale metrics. |

---

## 5. Deployment Warnings and Performance Rules

1. **Local SSD for Temp Directories**: Pyramidal reconstruction maps lower resolution levels via disk-backed memmap. Mapped network drives (e.g. `L:\...`) can experience substantial network latency or authentication failures. Always configure `--temp-dir` to point to a fast local SSD (e.g., `C:\temp_convert`).
2. **Preflight Run Requirement**: Keep preflight enabled (the default behaviour) for large slide conversions to ensure disk safety thresholds (`--disk-safety-factor`) are respected before decoders allocate multi-gigabyte files.
3. **Deterministic Output Paths**: When executing batch conversions (`svs-to-ometiff-batch`), ensure input directories do not contain duplicate filenames in separate subdirectories to avoid destination overwrites.
