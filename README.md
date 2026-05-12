# svs-to-ometiff GUI

[![PyPI](https://img.shields.io/pypi/v/svs-to-ometiff-gui.svg)](https://pypi.org/project/svs-to-ometiff-gui/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A web-based GUI for converting Aperio SVS whole-slide images (compression `33007`) to pyramidal OME-TIFF. Powered by [`svs-to-ometiff`](https://pypi.org/project/svs-to-ometiff/).

## Quick start

```bash
pip install svs-to-ometiff-gui
svs-to-ometiff-gui
# Opens http://127.0.0.1:8765 in your browser
```

## Features

- **Slide Info Preview** — inspects SVS metadata (dimensions, MPP, magnification, compression) before conversion
- **Batch Processing** — queue multiple SVS files with individual and overall progress
- **Live Progress** — SVG circular progress ring and scrolling log console with real-time updates
- **Advanced Settings** — tile size, compression, pyramid levels, downsample factor, edge mode
- **Glassmorphism UI** — dark-mode interface with frosted glass panels and gradient accents
- **Concurrent-safe** — process-pool isolation via `ProcessPoolExecutor`; failed jobs don't block the queue

## Supported inputs

**Supported:**
- Aperio SVS files with TIFF compression code `33007` (raw YUYV YCbCr 4:2:2)
- RGB output as pyramidal OME BigTIFF with SubIFD linkage

**Not supported:**
- JPEG/JPEG 2000 SVS variants — use OpenSlide or Bio-Formats for those
- Philips, Hamamatsu, Leica, or other WSI formats
- Diagnostic or clinical use

## Installation

From PyPI (recommended):

```bash
pip install svs-to-ometiff-gui
```

From source:

```bash
git clone https://github.com/tommy2scripts/svs-to-ometiff.git
cd svs-to-ometiff
pip install -e .
```

Dependencies: `svs-to-ometiff>=0.5.0`, `flask>=2.3`.

## Usage

```bash
svs-to-ometiff-gui
# or: python -m svs_to_ometiff_gui
```

This opens `http://127.0.0.1:8765` with the web interface.

### Single file

1. Drag-and-drop an `.svs` file, or paste the full path
2. Slide metadata auto-populates (dimensions, compression, MPP)
3. Output path auto-derived (same directory, `.ome.tiff` extension)
4. Click **Convert**

### Batch mode

1. Switch to **Batch Mode** tab
2. Paste multiple full paths (one per line)
3. Optionally set an output directory
4. Click **Convert** — files process sequentially with per-file progress

### Advanced settings

| Setting | Default | Notes |
|---------|---------|-------|
| Tile Size | 1024 | Optimized for 10x Xenium |
| Compression | zlib | Options: zlib, lzw, deflate, none |
| Pyramid Levels | 6 | Includes full resolution |
| Downsample Factor | 2 | Spacing between pyramid levels |
| Edge Mode | crop | `crop` or `pad` for boundary tiles |

## API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Single-page web GUI |
| `/inspect?path=<svs_path>` | GET | Slide metadata (JSON) |
| `/convert` | POST | Start single conversion → `request_id` |
| `/convert/batch` | POST | Start batch conversion → `request_id` |
| `/progress/<request_id>` | GET | SSE stream of progress events |
| `/open_folder` | POST | Opens output folder in OS file manager |

## Troubleshooting

**"Input SVS path does not exist"**
→ Use the absolute path. On macOS: right-click file in Finder, hold Option, choose "Copy as Pathname."

**"Only supports Aperio compression 33007"**
→ Your SVS uses JPEG (Compression 7) or JPEG 2000 (33003/33005). Use OpenSlide or Bio-Formats.

**Server fails to start (port in use)**
→ Set `SVS_GUI_PORT=8766 svs-to-ometiff-gui` to use an alternate port.

## Project structure

```
svs-to-ometiff/
├── src/svs_to_ometiff/       # Core library + CLI
├── svs_to_ometiff_gui/       # Flask app + services
│   ├── templates/index.html  # Single-page UI
│   └── static/               # CSS/JS assets
├── tests/                    # pytest suite (58 tests)
├── pyproject.toml
└── README.md
```

## License

MIT. See [LICENSE](LICENSE).
