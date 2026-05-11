# svs-to-ometiff

Convert Aperio SVS files with private compression tag `33007` (YUYV raw YCbCr 4:2:2) into pyramidal OME BigTIFF.

[![PyPI](https://img.shields.io/pypi/v/svs-to-ometiff.svg)](https://pypi.org/project/svs-to-ometiff/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Why

Some Aperio AT2/GT450 exports store image tiles with TIFF Compression tag `33007`. Those tiles are raw YUYV YCbCr 4:2:2 — not standard JPEG or JPEG 2000 — which breaks most whole-slide and spatial biology tools:

| Tool | Failure mode |
|---|---|
| OpenSlide | `Unsupported TIFF compression: 33007` |
| Bio-Formats / `bfconvert` | JPEG-family decode failure |
| QuPath | Fails through OpenSlide/Bio-Formats backends |
| libvips | Fails on unsupported compression `33007` |

`svs-to-ometiff` decodes that YUYV tile payload and writes standards-compliant OME BigTIFF with RGB tiles and pyramid levels.

## Install

```bash
pip install svs-to-ometiff
```

For compressed output (`lzw`, `zlib`, `deflate`):

```bash
pip install "svs-to-ometiff[lzw]"
```

## Quick start

```bash
# Default pyramidal conversion
svs-to-ometiff input.svs output.ome.tiff

# Single-resolution (no pyramid)
svs-to-ometiff input.svs output.ome.tiff --num-levels 1

# With LZW compression
svs-to-ometiff input.svs output.ome.tiff --compression lzw
```

## Options

| Option | Default | Description |
|---|---|---|
| `--tile-size` | `512` | Output tile size (must be divisible by 16) |
| `--compression` | `none` | `none`, `lzw`, `zlib`, or `deflate` |
| `--num-levels` | `3` | Pyramid levels (1 for single-resolution) |
| `--downsample-factor` | `2` | Pyramid spacing between levels |
| `--edge-mode` | `crop` | `crop` or `pad` for odd edge tiles |
| `--image-name` | input stem | OME Image name |

## How it works

1. Validates source uses Compression tag `33007`
2. Stream-decodes YUYV tiles to RGB via BT.601 conversion
3. Builds pyramid levels as disk-backed memmaps
4. Writes tiled OME BigTIFF with SubIFD pyramid linkage

Write is atomic — a failed conversion won't overwrite an existing output.

## Verification

```bash
# Inspect source metadata before converting
svs-to-ometiff-inspect input.svs

# Verify output structure after converting
svs-to-ometiff-verify output.ome.tiff --min-levels 3
```

## Programmatic use

```python
from svs_to_ometiff import convert

# Simple kwargs
convert("input.svs", "output.ome.tiff")

# Typed config
from svs_to_ometiff import ConvertConfig
config = ConvertConfig(
    input_svs="slide.svs",
    output_ometiff="slide.ome.tiff",
    num_levels=3,
)
convert(config)
```

## Limitations

- Handles only Compression tag `33007` (raw YUYV payload)
- Does not handle standard JPEG SVS (`Compression=7`) — use OpenSlide or Bio-Formats
- Does not handle JPEG 2000 SVS variants (`33003`, `33005`)
- Requires substantial free disk space for temporary memmaps and final output

## Development

```bash
git clone https://github.com/tommy2scripts/svs-to-ometiff.git
cd svs-to-ometiff
pip install -e ".[dev]"
python -m pytest
```

## License

MIT. See [LICENSE](LICENSE).
