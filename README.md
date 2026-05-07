# svs-to-ometiff

Convert Aperio SVS files with private compression tag `33007` into OME BigTIFF.

[![PyPI](https://img.shields.io/pypi/v/svs-to-ometiff.svg)](https://pypi.org/project/svs-to-ometiff/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: Experimental](https://img.shields.io/badge/status-experimental-orange.svg)](#validation-status)

> ⚠️ **Experimental:** This converter has structural validation on one real Aperio
> `33007` SVS file and synthetic pixel-level tests. Manual visual review and
> multi-scanner validation are still limited. Do not use converted output for
> diagnostic decisions.

## At a glance

| Question | Answer |
| --- | --- |
| Primary use | Convert Aperio SVS `Compression=33007` to RGB OME BigTIFF |
| Default output | Pyramidal OME BigTIFF (no compression by default) |
| Validated profile | `--compression none --num-levels 3 --tile-size 512` (these are the defaults) |
| Memory model | Streamed tile decode plus disk-backed RGB pyramid levels |
| Current validation | Synthetic tests plus one real lung H&E SVS structural check |
| Not for | JPEG/JPEG 2000 SVS, diagnostic use, unvalidated scanners |

## Contents

- [Why this exists](#why-this-exists)
- [Install](#install)
- [Quick start](#quick-start)
- [CLI options](#cli-options)
- [Programmatic use](#programmatic-use)
- [How it works](#how-it-works)
- [Verify an output](#verify-an-output)
- [Validation status](#validation-status)
- [Limitations](#limitations)
- [Downstream compatibility goals](#downstream-compatibility-goals)
- [Troubleshooting](#troubleshooting)
- [Web GUI](#web-gui)
- [Development](#development)
- [How to help validate](#how-to-help-validate)

## Why this exists

Some Aperio AT2/GT450 exports store `.svs` image tiles with TIFF Compression
tag `33007`. In the validation files seen so far, those tiles are not standard
JPEG/JPEG 2000 payloads. They are raw YUYV YCbCr 4:2:2 bytes where each
two-pixel pair is stored as `[Y0, U, Y1, V]`.

That private compression tag can block common whole-slide and spatial biology
tools before registration or image review starts.

| Tool | Typical failure mode |
| --- | --- |
| OpenSlide | `Unsupported TIFF compression: 33007` |
| Bio-Formats / `bfconvert` | Attempts JPEG-family decoding and fails on scanlines |
| QuPath | Fails through OpenSlide/Bio-Formats backends |
| libvips | Fails on unsupported compression `33007` |

`svs-to-ometiff` decodes that YUYV tile payload and writes a standards-oriented
OME BigTIFF with RGB tiles and optional pyramid levels.

## Install

```bash
pip install svs-to-ometiff
```

Development install from GitHub:

```bash
pip install git+https://github.com/tommy2scripts/svs-to-ometiff.git
```

Developer tools:

```bash
pip install "svs-to-ometiff[dev]"
```

### Compression dependency note

Compressed output (`lzw`, `zlib`, or `deflate`) depends on `imagecodecs` through
`tifffile`. A normal package install declares `imagecodecs` as a dependency.

The default output compression is `none` (uncompressed), so `imagecodecs` is only
needed when you explicitly choose a compression scheme:

```bash
svs-to-ometiff input.svs output.ome.tiff --compression lzw
```

Uncompressed output is larger but is the safest fallback for compatibility and debugging.

## Quick start

Optional source check before converting:

```bash
python - <<'PY'
import tifffile

with tifffile.TiffFile("input.svs") as tif:
    print("compression:", tif.pages[0].tags["Compression"].value)
    print("shape:", tif.pages[0].shape)
PY
```

Continue only if the source compression is `33007`.

Default pyramidal conversion:

```bash
svs-to-ometiff input.svs output.ome.tiff
```

Known-good conservative command from the real-file structural validation:

```bash
svs-to-ometiff input.svs output.ome.tiff \
  --num-levels 3 \
  --compression none \
  --tile-size 512
```

Single-resolution output, useful when the downstream tool does not need a pyramid:

```bash
svs-to-ometiff input.svs output.ome.tiff --num-levels 1
```

Run as a module:

```bash
python -m svs_to_ometiff input.svs output.ome.tiff
```

## CLI options

| Option | Default | Use when |
| --- | --- | --- |
| `--tile-size` | `512` | You need a different square output tile size |
| `--compression` | `none` | Choose `lzw`, `zlib`, `deflate`, or `none` |
| `--num-levels` | `3` | Reduce levels for faster conversion or use `1` for single-resolution output |
| `--downsample-factor` | `2` | Change pyramid spacing between levels |
| `--edge-mode` | `crop` | Use `pad` if you prefer padded borders over cropped odd edges |
| `--image-name` | input stem | Override the OME `Image` name |
| `--quiet` | off | Suppress progress output |
| `--verbose` | off | Print detailed progress, including every source tile row |

## Programmatic use

```python
from svs_to_ometiff import ConvertConfig, convert

# Simple kwargs interface
convert("input.svs", "output.ome.tiff", verbose=True)

# Typed config for pipelines
config = ConvertConfig(
    input_svs="slide.svs",
    output_ometiff="slide.ome.tiff",
    compression=None,  # Equivalent to --compression none
    num_levels=3,
    tile_size=512,
    verbose=True,
)
convert(config)
```

## How it works

The converter uses a streamed, disk-backed path by default:

1. Read SVS metadata and validate that the source uses Compression tag `33007`.
2. Iterate source tiles without decoding the whole slide into a single Python array.
3. Decode each raw YUYV YCbCr 4:2:2 tile to RGB using BT.601-style conversion.
4. Stage level 0 and derived pyramid levels as disk-backed NumPy memmaps near the output path.
5. Write a tiled OME BigTIFF, linking pyramid levels through TIFF SubIFDs.
6. Replace the destination only after a successful write, so a failed conversion
   does not overwrite an existing output file.

This lowers Python heap pressure compared with building the entire
full-resolution pyramid in memory. It does not remove the need for disk space:
temporary RGB pyramid levels plus the final OME-TIFF can be large.

## Verify an output

Run this after every real conversion:

```bash
python - <<'PY'
import tifffile

path = "output.ome.tiff"
with tifffile.TiffFile(path) as tif:
    assert tif.is_ome, "missing OME metadata"
    assert tif.is_bigtiff, "expected BigTIFF output"
    levels = tif.series[0].levels
    assert len(levels) >= 1, "missing image level"
    assert levels[0].shape[-1] == 3, "expected RGB output"
    print("verified", path)
    print("levels:", [level.shape for level in levels])
    print("subifds:", len(tif.pages[0].pages))
PY
```

At minimum, also review a thumbnail visually before using the converted image
for registration or handoff.

For the current validation checklist and real-file record, see
[`docs/validation_protocol.md`](docs/validation_protocol.md).

## Validation status

### Current evidence

| Claim | Evidence | Confidence |
| --- | --- | --- |
| YUYV decoder produces expected RGB on controlled inputs | Unit tests for grayscale, color tint, clipping, and synthetic tile reconstruction | Medium |
| Synthetic compression-33007 SVS converts end-to-end | Integration tests with known pixel values | Medium |
| OME BigTIFF structure is readable | `tifffile` opens output as OME BigTIFF with pyramid levels | Medium-high |
| SubIFD pyramid linkage works | `tifffile.TiffFile.series[0].levels` enumerates levels | Medium-high |
| Single-resolution output works | `--num-levels 1` uses the same generalized writer path | Medium |
| Disk-backed path is exercised | Synthetic memory profiling tests and memmap-vs-in-memory pyramid parity tests | Medium |
| Real SVS structural conversion works | One Aperio `33007` lung H&E SVS converted to 3-level uncompressed OME BigTIFF | Single file |

### Real-file validation snapshot

| Field | Result |
| --- | --- |
| Source | `67174_PT_Lung.svs` |
| Compression | `33007` |
| Dimensions | `39599 x 39858` px |
| Source tiles | `256 x 256`, `24180` tiles |
| Command | `--num-levels 3 --compression none --tile-size 512` |
| Output levels | `(39858, 39599, 3)`, `(19929, 19799, 3)`, `(9964, 9899, 3)` |
| Output structure | `is_bigtiff=True`, `is_ome=True`, `2` SubIFDs |
| Output size | `5.86 GiB` / `6.30 GB` |
| Peak RSS in local run | `1.91 GB` from `/usr/bin/time -l` |
| Visual review | Pending manual thumbnail review |

### Still open

| Area | Status |
| --- | --- |
| Other Aperio scanner models | Not tested |
| Other AT2/GT450 firmware/export settings | Not tested |
| Other tissues, stains, IHC, IF, or special stains | Not tested |
| Xenium Explorer H&E overlay workflow | Planned, not completed |
| Space Ranger / Visium image input workflow | Intended, not completed |
| Color accuracy vs. vendor/reference decoder | Not validated |
| Multi-file reproducibility | One real file tested |

## Limitations

- Handles only Aperio Compression tag `33007` with the observed raw YUYV tile payload.
- Does not handle standard JPEG SVS (`Compression=7`); use OpenSlide, libvips,
  or Bio-Formats for those.
- Does not handle JPEG 2000 SVS variants such as `33003` or `33005`.
- Does not validate color fidelity against a scanner profile or reference decoder.
- Does not recover from malformed, truncated, or corrupted tiles.
- Requires substantial free disk space near the output path for temporary memmaps
  and final OME-TIFF output.
- RSS and runtime vary with OS page cache, disk speed, pyramid level count, tile
  size, and compression codec behavior.

## Downstream compatibility goals

Outputs are intended to be ordinary tiled OME BigTIFF files for tools that can
consume OME-TIFF pyramids, including:

- Xenium Ranger / Xenium Explorer H&E registration and overlay workflows
- Space Ranger image inputs after OME-TIFF conversion
- QuPath
- napari through `tifffile`
- HALO and other OME-TIFF-aware pathology viewers

These are compatibility goals, not a completed validation matrix. Please verify
your own downstream import before relying on a converted slide.

## Troubleshooting

| Symptom | Likely cause | What to try |
| --- | --- | --- |
| `input uses compression 7` | Standard JPEG SVS, not Aperio `33007` | Use OpenSlide/libvips/Bio-Formats instead |
| `pip install imagecodecs` error during write | Compression encoder unavailable in active Python env | Install `imagecodecs` or rerun with `--compression none` |
| Output is very large | Default is uncompressed (`--compression none`) | Use `--compression lzw` if `imagecodecs` is available |
| Conversion uses lots of disk | Disk-backed RGB pyramid levels plus final output | Use fewer `--num-levels`, ensure free disk space near output |
| Downstream viewer is slow | Large uncompressed BigTIFF or many levels | Try compressed output or fewer levels after validation |

## Web GUI

A separate experimental Flask GUI is available as `svs-to-ometiff-gui`:

```bash
pip install svs-to-ometiff-gui
svs-to-ometiff-gui
```

It opens a local browser UI at `http://127.0.0.1:8765` with drag-and-drop
upload, progress streaming, and expandable settings.

> 📌 **Note:** The GUI is separate from this core CLI package.

## Development

```bash
git clone git@github.com:tommy2scripts/svs-to-ometiff.git
cd svs-to-ometiff
pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
```

Strict local memory checks can be enabled manually:

```bash
SVS_OMETIFF_STRICT_MEMORY=1 python -m pytest tests/test_memory.py -v -s
```

## How to help validate

If you have Aperio SVS files with Compression tag `33007`, please test and
report the outcome through GitHub Issues. Useful details include:

- scanner model and firmware, if known
- tissue type and stain
- source dimensions and tile size
- source TIFF Compression tag
- exact conversion command
- output structural check results
- whether visual review or downstream import passed

## License

MIT. See [LICENSE](LICENSE).
