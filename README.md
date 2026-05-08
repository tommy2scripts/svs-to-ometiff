# svs-to-ometiff GUI

A premium web-based graphical user interface for converting SVS whole-slide images to OME-TIFF format using the `svs_to_ometiff` library.

> **Experimental:** This GUI is experimental and not yet thoroughly tested. Use with caution on production data. Always verify outputs.

## Features

- **Slide Info Preview** — Automatically inspects SVS metadata (dimensions, MPP, magnification, compression, tile count) before conversion
- **Two-Column Layout** — Configuration on the left, live progress on the right
- **Circular Progress Ring** — SVG-based percentage display with real-time updates
- **Live Log Console** — Real-time scrolling log output from the converter
- **Glassmorphism Design** — Premium dark-mode UI with frosted glass panels, gradient accents, and smooth animations
- **Advanced Settings** — Tile size, compression, pyramid levels, downsample factor, edge mode
- **Inter + JetBrains Mono** — Modern typography from Google Fonts
- **Responsive** — Collapses to single-column on narrow viewports

## Requirements

- Python 3.9+
- `pip`

## Installation

Install from the project directory:

```bash
cd /path/to/svs-to-ometiff-gui
pip install -e .
```

This installs the GUI package and its runtime dependencies:

- `svs-to-ometiff>=0.2.0`
- `flask>=2.3`

## Usage

Run the GUI with the console script:

```bash
svs-to-ometiff-gui
```

Or run it as a Python module:

```bash
python -m svs_to_ometiff_gui
```

This will:
1.  Print an experimental warning banner.
2.  Automatically open http://127.0.0.1:8765 in your default browser.
3.  Start the Flask development server.

### Web Interface

1.  **Drag & drop** an `.svs` file onto the drop zone, or click to browse.
2.  The **Input SVS Path** field will be populated with the filename — paste the full path.
3.  A **Slide Info** card will automatically appear showing slide metadata.
4.  The **Output Path** is auto-derived (same directory, `.ome.tiff` extension). You may edit it manually.
5.  (Optional) Click **Advanced Settings** to adjust:
    - **Tile Size** (default: 512)
    - **Compression** (default: lzw; options: lzw, zlib, deflate, none)
    - **Pyramid Levels** (default: 6)
    - **Downsample Factor** (default: 2)
    - **Edge Mode** (default: crop; options: crop, pad)
6.  Click **Convert** to start the conversion.
7.  Monitor progress via the **circular progress ring** and **log console**.
8.  When complete, click **Open Folder** to reveal the output file.

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serves the single-page GUI |
| `/inspect?path=<svs_path>` | GET | Returns slide metadata (dimensions, MPP, magnification, etc.) |
| `/convert` | POST | Starts a conversion, returns a `request_id` for progress tracking |
| `/progress/<request_id>` | GET | SSE stream of conversion progress events |
| `/open_folder` | POST | Opens the output folder in the OS file manager |

## Project Structure

```
svs-to-ometiff-gui/
├── svs_to_ometiff_gui/
│   ├── __init__.py
│   ├── __main__.py           # python -m svs_to_ometiff_gui entry point
│   ├── serve.py              # Flask app with SSE progress + /inspect endpoint
│   └── templates/
│       └── index.html         # Single-page GUI (glassmorphism design)
├── pyproject.toml
├── requirements.txt
└── README.md
```

## License

Same as the `svs_to_ometiff` project.
