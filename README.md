# svs-to-ometiff

> **Status: Experimental — single-scanner validation.** This tool has been tested on ONE Aperio SVS file (AT2/GT450 scanner, lung H&E, compression 33007). Generalizability to other scanner models, firmware versions, and tissue types is not yet verified. Downstream tool compatibility is intended but not yet tested end-to-end. See [Validation Status](#validation-status).

Convert Aperio SVS slides using proprietary compression 33007 into standard
pyramidal OME-TIFF.

[![CI](https://github.com/tommytran/svs-to-ometiff/actions/workflows/ci.yml/badge.svg)](https://github.com/tommytran/svs-to-ometiff/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: Experimental](https://img.shields.io/badge/status-experimental-orange.svg)]()

## The Problem

Some Aperio AT2/GT450 whole-slide scanners write `.svs` files with TIFF
Compression tag `33007`. These files are often described as `JP2K-YCbCr`,
`ALT_JPEG`, or JPEG 2000-like, but the tile payload is raw YUYV
YCbCr 4:2:2: each two-pixel pair is stored as `[Y0, U, Y1, V]`.

Because 33007 is not a standard TIFF/JPEG/JPEG 2000 compression codec, common
spatial biology tools may fail before the image can be used for Xenium or
Visium registration. The failures below have been observed in the validation
context described in [Validation Status](#validation-status).

| Tool | What fails | Typical error message |
| --- | --- | --- |
| OpenSlide | Refuses the private compression tag | `Unsupported TIFF compression: 33007` |
| Bio-Formats / bfconvert | Treats tiles as JPEG-family data | `Cannot read JPEG scanlines` |
| QuPath | Delegates decoding through OpenSlide/Bio-Formats | `Unsupported TIFF compression: 33007` |
| libvips | Cannot decode private-compression tile payloads | `vips2tiff: unsupported compression 33007` |

## Installation

```bash
# Not yet on PyPI — install from source:
pip install -e ".[dev]"
```

For basic use (no dev dependencies):

```bash
pip install -e .
```

## Usage

```bash
svs-to-ometiff input.svs output.ome.tiff
```

Verify the output:

```bash
python - <<'PY'
import tifffile

with tifffile.TiffFile("output.ome.tiff") as tif:
    print("is_ome:", tif.is_ome)
    print("is_bigtiff:", tif.is_bigtiff)
    print("levels:", len(tif.series[0].levels))
    for index, level in enumerate(tif.series[0].levels):
        print(index, level.shape)
PY
```

Programmatic use:

```python
from svs_to_ometiff import convert

convert("input.svs", "output.ome.tiff", verbose=True)
```

## How It Works

The converter does three things:

1. Decodes each Aperio 33007 tile from YUYV YCbCr 4:2:2 to RGB with BT.601
   full-range color conversion.
2. Reassembles the full-resolution RGB image and builds a downsampled pyramid
   by block averaging.
3. Writes a BigTIFF OME-TIFF with tiled storage and SubIFD-linked pyramid
   levels for downstream viewer compatibility.

## Limitations

- Only Aperio compression `33007` is handled. Standard JPEG, JPEG 2000, LZW,
  and tiled TIFF/SVS files should be opened with standard tools.
- The full-resolution RGB image and generated pyramid are held in RAM. As a
  rule of thumb, peak memory is about `width * height * 3 * 1.65` bytes for a
  six-level 2x pyramid, plus TIFF writer buffers. A 40,000 x 40,000 slide
  typically needs 8-12 GB; very large slides can exceed 30 GB.
- The CLI estimates peak RAM before decoding and prints a warning above 30 GB.
- The expected source tile width must be even because YUYV 4:2:2 shares chroma
  across two horizontal pixels.
- Known affected scanner families include Aperio AT2 and Aperio GT450 exports
  from Leica/Aperio workflows. Firmware and export settings vary by site, so
  verify the source TIFF Compression tag is `33007` before relying on this
  converter.

## What this does NOT do

- Does **not** handle JPEG-compressed SVS (compression tag `7`) — use libvips or OpenSlide for those
- Does **not** handle JPEG 2000-compressed SVS (compression tag `33003` or `33005`)
- Does **not** validate color fidelity against a reference scanner profile
- Has **not** been tested on frozen sections, IHC, or fluorescence slides
- Does **not** recover from malformed or truncated tiles — may crash on corrupted SVS files

## Downstream Compatibility

Outputs are intended to be pyramidal OME-TIFF files for downstream workflows
such as:

- Xenium Ranger and Xenium Explorer H&E registration/overlay workflows
- Space Ranger image inputs after OME-TIFF conversion
- QuPath
- napari through `tifffile`
- HALO and other OME-TIFF aware pathology viewers

## Verification

At minimum, verify structure and a visual thumbnail before using the output in
registration:

```bash
python - <<'PY'
import tifffile

path = "output.ome.tiff"
with tifffile.TiffFile(path) as tif:
    assert tif.is_ome, "missing OME metadata"
    assert tif.is_bigtiff, "expected BigTIFF output"
    levels = tif.series[0].levels
    assert len(levels) >= 2, "missing pyramid levels"
    assert levels[0].shape[-1] == 3, "expected RGB output"
    print("verified", path, "levels:", [level.shape for level in levels])
PY
```

For pixel-level validation in a pipeline, sample known tissue coordinates from
the source slide and compare RGB values after conversion. The decoder clips RGB
conversion results to `0..255`, so out-of-range chroma values should not wrap
around in the output.

## Validation Status

### What has been tested

| Claim | Evidence | Confidence |
|---|---|---|
| YUYV decoder produces structurally correct RGB | Unit tests (grayscale, color tint, clipping); visual inspection of H&E tile | Medium |
| OME-TIFF output passes tifffile validation | `is_ome=True`, `is_bigtiff=True`, 6 pyramid levels detected | Medium-high |
| Pyramid SubIFD linkage works in tifffile | `tifffile.TiffFile.series[0].levels` enumerates all 6 levels | Medium-high |
| Synthetic 33007 SVS → valid OME-TIFF end-to-end | `test_integration.py` passes with known pixel values | Medium |
| Works on real SVS file | 67174_PT_Lung.svs (AT2/GT450, lung SCC, post-Xenium H&E, 3.2 GB) | Single file |

### What has NOT been tested (open questions)

| Claim | Status |
|---|---|
| Other Aperio scanner models (CS2, Versa, AT Turbo) | Not tested |
| Other firmware versions of AT2/GT450 | Not tested |
| Other tissue types or stains (IHC, IF, special stains) | Not tested |
| Xenium Explorer H&E overlay workflow | **Planned, not yet performed** |
| STalign registration to Xenium DAPI section | **Planned, not yet performed** |
| Color accuracy vs. reference decoder (cross-validation) | Not performed — visual inspection only |
| Multi-file reproducibility | Only one file tested |

### How to help validate

If you have access to Aperio SVS files with compression tag 33007 from different scanners or tissue types, please test the converter and report results (success or failure) via GitHub Issues. Include the scanner model, firmware version if known, and a `tifffile` tag dump of the source file.

## License

MIT. See [LICENSE](LICENSE).
