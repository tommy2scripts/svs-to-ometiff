# svs-to-ometiff

[![PyPI](https://img.shields.io/pypi/v/svs-to-ometiff.svg)](https://pypi.org/project/svs-to-ometiff/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Convert Aperio SVS whole-slide images that use TIFF compression code `33007`
to pyramidal OME-TIFF. The package includes a command-line interface, a batch
converter, inspection and verification helpers, and a local Flask GUI.

> Experimental: this project is not validated for diagnostic or clinical use.
> Outputs should be independently verified before use in research workflows.

## Why this exists

Some Aperio AT2/GT450 SVS exports store image tiles as raw YUYV YCbCr 4:2:2
under TIFF compression tag `33007`. These files may not decode through common
OpenSlide, Bio-Formats, or standard `tifffile` paths. `svs-to-ometiff` decodes
that specific tile payload and writes RGB pyramidal OME BigTIFF with SubIFD
levels.

## Supported inputs

Supported:

- Aperio SVS files with TIFF compression code `33007`
- Raw YUYV YCbCr 4:2:2 tile payloads observed in Aperio AT2/GT450 exports
- RGB output as pyramidal OME BigTIFF

Not supported:

- JPEG or JPEG 2000 SVS variants, including compression codes `7`, `33003`, or
  `33005`
- Philips, Hamamatsu, Leica, or other non-Aperio WSI formats
- Diagnostic, clinical, or regulated use

Use `svs-to-ometiff-inspect` before conversion to confirm whether a file is in
scope.

## Install

From PyPI:

```bash
pip install svs-to-ometiff
```

From source:

```bash
git clone https://github.com/tommy2scripts/svs-to-ometiff.git
cd svs-to-ometiff
pip install -e ".[dev]"
```

Runtime dependencies are `numpy`, `tifffile`, `imagecodecs`, `click`, and
`flask`.

## Command-line usage

Inspect a source SVS without decoding tiles:

```bash
svs-to-ometiff-inspect slide.svs
```

Convert one file:

```bash
svs-to-ometiff slide.svs slide.ome.tiff
```

Convert with explicit settings:

```bash
svs-to-ometiff slide.svs slide.ome.tiff \
  --tile-size 1024 \
  --compression zlib \
  --num-levels 6 \
  --downsample-factor 2 \
  --edge-mode crop
```

Batch-convert a directory or glob:

```bash
svs-to-ometiff-batch slides/ --output-dir converted/
svs-to-ometiff-batch "/data/**/*.svs" --compression zlib
```

Verify an output OME-TIFF:

```bash
svs-to-ometiff-verify slide.ome.tiff --min-levels 3
```

Compression options are `zlib`, `lzw`, `deflate`, and `none`. The default is
`zlib`; use `none` for maximum compatibility and larger output files.

Whole-slide conversion can require substantial disk I/O and temporary storage.
The converter uses disk-backed arrays for pyramid construction, but large slides
can still need many gigabytes of free disk space and enough RAM for tile buffers,
writer buffers, and the operating-system page cache. Start with one conversion
at a time and verify available space before processing a batch.

## GUI usage

Start the local web interface:

```bash
svs-to-ometiff-gui
```

The server opens `http://127.0.0.1:8765` by default.

GUI features:

- slide metadata preview before conversion
- single-file and batch conversion
- live progress events and log output
- configurable tile size, compression, pyramid levels, downsample factor, and
  edge handling
- local file browsing on the server host

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SVS_GUI_HOST` | `127.0.0.1` | Flask bind host |
| `SVS_GUI_PORT` | `8765` | Flask bind port |
| `SVS_GUI_TILE_SIZE` | `1024` | GUI conversion tile size |
| `SVS_GUI_COMPRESSION` | `zlib` | GUI conversion compression |
| `SVS_GUI_NUM_LEVELS` | `6` | GUI pyramid levels |
| `SVS_GUI_DOWNSAMPLE` | `2` | GUI downsample factor |
| `SVS_GUI_EDGE_MODE` | `crop` | GUI edge mode |
| `SVS_GUI_MAX_JOBS` | `1` | Maximum conversion workers |

Security note: the GUI can read and write files that are accessible to the
server process. Keep the default `127.0.0.1` host for local use. If you bind to
`0.0.0.0` or run the Docker setup, restrict network and volume access.

## Docker

The Docker setup is intended for local use. By default, Compose binds the GUI to
`127.0.0.1:5000` and mounts only `./data` into the container:

```bash
mkdir -p data
docker compose up --build
```

Open `http://127.0.0.1:5000` and place or mount input slides under `./data`.
Do not expose the container directly on a public network without authentication,
TLS, and a deliberately restricted data volume.

## Python API

```python
from svs_to_ometiff import ConvertConfig, convert, inspect_svs, verify_ometiff

info = inspect_svs("slide.svs")
if info["convertible"]:
    result = convert(
        ConvertConfig(
            input_svs="slide.svs",
            output_ometiff="slide.ome.tiff",
            tile_size=1024,
            compression="zlib",
            num_levels=6,
            downsample_factor=2,
            edge_mode="crop",
        )
    )
    verification = verify_ometiff("slide.ome.tiff", min_levels=3)
```

## Validation status

Current validation is limited. The converter includes unit and integration
tests built from synthetic Aperio-style TIFF fixtures, and has been manually
validated on one real Aperio compression-33007 file. It has not been validated
for diagnostic workflows, broad scanner coverage, color management, or
regulatory use.

Before relying on outputs, verify:

- `svs-to-ometiff-verify` passes
- the expected number of pyramid levels are present
- image dimensions match the source
- visual content aligns with the source slide in an independent viewer
- downstream tools can open the OME-TIFF

## Troubleshooting

**`Convertible: no` or "only supports Aperio compression 33007"**

The source file is outside this tool's supported scope. For JPEG, JPEG 2000, or
other WSI formats, use OpenSlide, Bio-Formats, or a vendor-supported converter.

**Input path not found in the GUI**

Use an absolute path. On macOS, right-click the file in Finder, hold Option, and
choose "Copy ... as Pathname".

**Compressed output fails**

Make sure `imagecodecs` is installed. If compression still fails, retry with
`--compression none`.

**The GUI port is already in use**

```bash
SVS_GUI_PORT=8766 svs-to-ometiff-gui
```

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
python -m build
python -m twine check dist/*
```

Project layout:

```text
svs-to-ometiff/
├── src/svs_to_ometiff/       # Core library and CLI commands
├── svs_to_ometiff_gui/       # Flask GUI, services, static assets
├── tests/                    # Synthetic fixture tests
├── pyproject.toml
└── README.md
```

## Citation

If you use this software in published research, cite the metadata in
[CITATION.cff](CITATION.cff).

## License

MIT. See [LICENSE](LICENSE).
