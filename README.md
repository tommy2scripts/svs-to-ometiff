# svs-to-ometiff

[![PyPI](https://img.shields.io/pypi/v/svs-to-ometiff.svg)](https://pypi.org/project/svs-to-ometiff/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Convert Aperio SVS whole-slide images that use TIFF compression code `33007`
to pyramidal OME-TIFF. The package includes a command-line interface, a batch
converter, inspection and verification helpers, and a local Flask GUI.

> Experimental: this project is not validated for diagnostic or clinical use.
> Outputs should be independently verified before use in research workflows.

## Quick start

Use this workflow for most slides:

```bash
pip install svs-to-ometiff
svs-to-ometiff-inspect slide.svs
svs-to-ometiff slide.svs slide.ome.tiff --temp-dir local_tmp
svs-to-ometiff-verify slide.ome.tiff --min-levels 6
```

For a folder of slides:

```bash
svs-to-ometiff-batch slides/ --output-dir converted/ --temp-dir local_tmp
```

Windows example with full paths:

```powershell
mkdir C:\svs_to_ometiff_tmp
svs-to-ometiff-batch "C:\path\to\slides" `
  --output-dir "C:\path\to\converted" `
  --temp-dir "C:\svs_to_ometiff_tmp"
```

Before running a large batch:

- Confirm every source reports `Compression: 33007` and `Convertible: yes`.
- Write outputs to a separate folder, not the source slide folder.
- Use a local SSD temp directory with plenty of free disk space.
- Verify outputs before using them downstream.

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

On Windows, user-level installs may place command-line scripts somewhere like
`%APPDATA%\Python\Python313\Scripts`. If `svs-to-ometiff` is not found after
installing, either add that scripts directory to `PATH`, run the `.exe` by full
path, or use the module form:

```powershell
python -m svs_to_ometiff slide.svs slide.ome.tiff
```

## Common commands

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

Recommended workflow:

```bash
svs-to-ometiff-inspect input.svs
svs-to-ometiff input.svs output.ome.tiff \
  --tile-size 1024 \
  --compression zlib \
  --num-levels 6 \
  --edge-mode crop
svs-to-ometiff-verify output.ome.tiff --min-levels 6
```

Batch-convert a directory or glob:

```bash
svs-to-ometiff-batch slides/ --output-dir converted/
svs-to-ometiff-batch "/data/**/*.svs" --compression zlib
```

Batch conversion reads each source `.svs` file and writes a new
`<stem>.ome.tiff` file. It does not modify, overwrite, or delete the original
SVS files. Choose an `--output-dir` outside the source directory if you want a
clear separation between source slides and converted outputs. If multiple
inputs would write the same destination filename, batch mode fails before
starting any conversion.

Verify an output OME-TIFF:

```bash
svs-to-ometiff-verify slide.ome.tiff --min-levels 3
```

## Recommended settings

Compression options are `zlib`, `lzw`, `deflate`, and `none`. The default is
`zlib`; use `none` for maximum compatibility and larger output files.

Whole-slide conversion can require substantial disk I/O and temporary storage.
The converter uses disk-backed arrays for pyramid construction, but large slides
can still need many gigabytes of free disk space and enough RAM for tile buffers,
writer buffers, and the operating-system page cache. Start with one conversion
at a time and verify available space before processing a batch.

For Xenium-style workflows, use `--edge-mode crop` unless you specifically need
to preserve padded edge dimensions.

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

Current validation is still limited, but now includes both synthetic fixtures
and real Windows workstation runs. The converter includes unit and integration
tests built from synthetic Aperio-style TIFF fixtures, and has been manually
validated on real Aperio compression-33007 H&E slides from AT2/GT450-style
exports, including Xenium prescreening slides. It has not been validated for
diagnostic workflows, broad scanner coverage, color management, or regulatory
use.

**Xenium Explorer compatibility:** The converter produces pyramidal OME-TIFF
output with SubIFD linkage, configured for compatibility with Xenium Explorer
post-Xenium H&E alignment workflows. Output has been verified with QuPath and
Bio-Formats-compatible viewers. Validate in Xenium Explorer before production use.

### Real-data validation notes

Validation performed on Windows with `svs-to-ometiff-batch v0.7.0`:

- Standalone Aperio SVS, compression `33007`, `77262 x 39858` px, `20X`,
  `0.275310798315331` um/px
- Xenium H&E prescreening batch: 21 SVS files inspected; all reported
  `Compression: 33007` and `Convertible: yes`
- Batch outputs written to a separate local output directory with a local temp
  directory; source `.svs` files were left unchanged
- Batch result: 21 converted, 0 failed; all 21 outputs passed
  `svs-to-ometiff-verify` with OME yes, BigTIFF yes, 6 levels, 5 SubIFDs,
  `1024 x 1024` tiles, `uint8`, and physical pixel size preserved at
  `0.275310798315331` um/px
- Observed output sizes on real files ranged from about 1.0 GB to 8.1 GB with
  default zlib compression

### Pre-release validation checklist

- [ ] Run `svs-to-ometiff-inspect slide.svs` to confirm compression 33007
- [ ] Run `svs-to-ometiff slide.svs slide.ome.tiff`
- [ ] Run `svs-to-ometiff-verify slide.ome.tiff --min-levels 6`
- [ ] Open in QuPath or Bio-Formats-compatible viewer
- [ ] Inspect visual alignment with source slide
- [ ] Test in downstream workflow (e.g., Xenium Explorer alignment)

## Troubleshooting

**Windows setup**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
svs-to-ometiff-gui
```

**Recommended Windows conversion workflow**

Use a local temp directory, especially when reading from or writing to mapped
network drives:

```powershell
mkdir C:\svs_to_ometiff_tmp
svs-to-ometiff input.svs output.ome.tiff `
  --tile-size 1024 `
  --compression zlib `
  --num-levels 6 `
  --edge-mode crop `
  --temp-dir C:\svs_to_ometiff_tmp
svs-to-ometiff-verify output.ome.tiff --min-levels 6
```

When possible, convert with temporary files on a local SSD, verify the output,
open it in QuPath as a sanity check, and then copy the final OME-TIFF back to
the server. Final acceptance for post-Xenium work should be successful import
and alignment in Xenium Explorer.

**Windows field note: mapped drives and user installs**

Mapped drives such as `L:` can be session-specific on Windows. A scheduled task,
service account, remote shell, or sandboxed terminal may not see the same drive
letters as an interactive Explorer window. If `svs-to-ometiff-batch` cannot find
a mapped-drive path, use the underlying UNC path or remap the drive in the same
session before running the converter.

Example real-file Windows validation with `svs-to-ometiff-batch v0.7.0`:

- Source: Aperio SVS, compression `33007`, `77262 x 39858` px, `20X`,
  `0.275310798315331` um/px
- Command shape: `svs-to-ometiff-batch input.svs --output-dir converted
  --temp-dir local_tmp`
- Output: OME BigTIFF, zlib compression, 6 pyramid levels, `1024 x 1024` tiles,
  5 SubIFDs
- Verified level shapes: `(39858, 77262, 3)`, `(19929, 38631, 3)`,
  `(9964, 19315, 3)`, `(4982, 9657, 3)`, `(2491, 4828, 3)`,
  `(1245, 2414, 3)`
- Runtime and storage observed on local Windows workstation: about 196 seconds,
  final output about 6.58 GB

Example Xenium prescreening batch run:

- Input set: 21 `.svs` files in one local folder
- Inspection: all files reported `Compression: 33007` and `Convertible: yes`
- Command shape: `svs-to-ometiff-batch input_folder --output-dir converted
  --temp-dir local_tmp`
- Output behavior: one `<stem>.ome.tiff` file per source SVS, written to the
  requested output directory
- Verification command: `svs-to-ometiff-verify converted/<stem>.ome.tiff`
- Batch result: 21 succeeded, 0 failed in about 45 minutes on a Windows
  workstation
- Verification result: all 21 outputs passed OME BigTIFF structural
  verification

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

### Improvement backlog

Recommended hardening before broad unattended production batches:

- Add `--skip-existing` and `--force` to batch mode so reruns cannot silently
  replace already validated OME-TIFF outputs.
- Add clearer Windows diagnostics when a drive-letter path such as `L:\...` is
  unavailable in the current shell or service session.
- Estimate required temp and output disk space before starting each conversion,
  and fail early when free space is clearly insufficient.
- Emit a machine-readable batch manifest with input path, output path, source
  dimensions, compression, conversion status, output size, and verification
  status.
- Add an optional batch `--verify` mode that runs `svs-to-ometiff-verify` after
  each successful conversion and records the result.
- Add a conservative `--jobs` option only after disk-space checks and output
  overwrite policy controls are in place; on typical Windows workstations, one
  or two jobs should be the practical upper bound for large whole-slide images.

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
