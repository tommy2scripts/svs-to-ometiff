# svs-to-ometiff

Convert Aperio SVS files with private compression tag `33007` (raw YUYV YCbCr 4:2:2) into standards-compliant pyramidal OME BigTIFF.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Why this exists

Some Aperio AT2/GT450 exports store image tiles with TIFF Compression tag `33007`. Those tiles are raw YUYV YCbCr 4:2:2 — not standard JPEG or JPEG 2000 — which breaks most whole-slide and spatial biology tools:

| Tool | Failure mode |
|------|-------------|
| OpenSlide | `Unsupported TIFF compression: 33007` |
| Bio-Formats / `bfconvert` | JPEG-family decode failure |
| QuPath | Fails through OpenSlide/Bio-Formats backends |
| libvips | Fails on unsupported compression `33007` |

`svs-to-ometiff` decodes that YUYV tile payload and writes standards-compliant OME BigTIFF with RGB tiles and pyramid levels.

## Validation status

**This is an experimental, research-oriented tool.** It has been validated on a limited set of Aperio SVS files using compression code `33007`.

Before using converted files in production workflows, verify output compatibility in your target tools (QuPath, Fiji/Bio-Formats, tifffile, napari, Xenium Explorer, or downstream spatial transcriptomics pipelines).

See [docs/validation_protocol.md](docs/validation_protocol.md) for the current validation record and protocol.

## Supported inputs

**Supported:**
- Aperio SVS files with TIFF compression code `33007`
- RGB output as pyramidal OME BigTIFF with SubIFD linkage

**Not supported:**
- General SVS conversion (JPEG/JPEG 2000 variants — use OpenSlide or Bio-Formats)
- Philips, Hamamatsu, Leica, or other WSI formats
- Diagnostic or clinical use

## Resource requirements

The converter uses disk-backed temporary arrays (numpy memmaps) located beside the output file. This keeps peak RAM low but requires free disk space:

- The final OME-TIFF
- Temporary full-resolution RGB data (width × height × 3 bytes)
- Temporary pyramid level data (smaller by ~factor² per level)

A 40k × 40k pixel slide (~5 GB full-res RGB) will need roughly **10–15 GB** of temporary disk space during conversion and produce a ~5 GB OME-TIFF.

For best performance, run conversions on a drive with a fast scratch SSD. A future `--tmp-dir` option is planned.

## Installation

```bash
pip install svs-to-ometiff
```

**Compressed output** (LZW, zlib, deflate) works out of the box — the `imagecodecs` library is included as a core dependency.

**GUI** (optional Flask-based web UI):

```bash
pip install "svs-to-ometiff[gui]"
svs-to-ometiff-gui
```

## Quick start

```bash
# Inspect source metadata first
svs-to-ometiff-inspect input.svs

# Default pyramidal conversion (3 levels, uncompressed)
svs-to-ometiff input.svs output.ome.tiff

# Single-resolution (no pyramid)
svs-to-ometiff input.svs output.ome.tiff --num-levels 1

# With LZW compression
svs-to-ometiff input.svs output.ome.tiff --compression lzw
```

## Verify output

```bash
# Verify OME structure
svs-to-ometiff-verify output.ome.tiff --min-levels 3
```

Successful output:
```
[PASS] output.ome.tiff
OME: yes
BigTIFF: yes
Levels: 3
Level shapes: [(39858, 39599, 3), (19929, 19799, 3), (9964, 9899, 3)]
Dtype: uint8
```

## CLI reference

| Option | Default | Description |
|--------|---------|-------------|
| `--tile-size` | `512` | Output tile size (must be divisible by 16) |
| `--compression` | `none` | `none`, `lzw`, `zlib`, or `deflate` |
| `--num-levels` | `3` | Pyramid levels (1 for single-resolution) |
| `--downsample-factor` | `2` | Pyramid spacing between levels |
| `--edge-mode` | `crop` | `crop` or `pad` for odd edge tiles |
| `--image-name` | input stem | OME Image name |
| `--quiet` | — | Suppress progress output |
| `--verbose` | — | Print detailed tile-level progress |

## How it works

1. **Metadata**: Reads TIFF headers to validate compression `33007` and extract dimensions, tile geometry, MPP.
2. **Decode**: Stream-decodes YUYV tiles to RGB via BT.601 full-range conversion.
3. **Stage**: Writes full-resolution RGB as a disk-backed memmap (low RAM).
4. **Pyramid**: Builds lower resolution levels out-of-core by block averaging.
5. **Write**: Writes tiled OME BigTIFF with SubIFD pyramid linkage.

Write is **atomic** — a failed conversion won't overwrite an existing output.

## Python API

```python
from svs_to_ometiff import convert, ConvertConfig

# Preferred: typed config object
config = ConvertConfig(
    input_svs="slide.svs",
    output_ometiff="slide.ome.tiff",
    tile_size=512,
    compression=None,
    num_levels=3,
)
result = convert(config)
print(f"Output: {result['output_path']} ({result['output_size_bytes'] / 1e9:.2f} GB)")

# Legacy: positional arguments
result = convert("slide.svs", "slide.ome.tiff", num_levels=3)
```

## GUI

An experimental Flask-based web GUI is available:

```bash
pip install "svs-to-ometiff[gui]"
svs-to-ometiff-gui
```

The GUI provides a browser interface at `http://127.0.0.1:8765` with:
- File path input (with auto-resolve for filenames)
- Progress streaming via SSE
- Configurable compression and pyramid settings

## Troubleshooting

**"Error converting SVS file: svs-to-ometiff only supports Aperio compression 33007"**
→ Your SVS uses standard JPEG (Compression 7) or JPEG 2000 (33003/33005). Use OpenSlide or Bio-Formats instead.

**"Failed to write compressed OME-TIFF because imagecodecs is missing"**
→ Install `imagecodecs`: `pip install imagecodecs`. If compilation fails, use `--compression none`.

**"Conversion fails with disk space error"**
→ The converter needs temp space for full-resolution RGB data (~width × height × 3 bytes) plus pyramid levels. Ensure the output drive has 2–3× the final file size free. See [Resource requirements](#resource-requirements).

## Development

```bash
git clone https://github.com/tommy2scripts/svs-to-ometiff.git
cd svs-to-ometiff
pip install -e ".[dev]"
python -m pytest
```

## License

MIT. See [LICENSE](LICENSE).

## Citation

If you use this tool in published work, please cite the repository:

```
Tommy Tran. svs-to-ometiff: Convert Aperio compression-33007 SVS to
pyramidal OME-TIFF. https://github.com/tommy2scripts/svs-to-ometiff
```
