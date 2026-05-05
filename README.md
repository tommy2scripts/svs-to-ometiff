# svs-to-ometiff GUI

A web-based graphical user interface for converting SVS whole-slide images to OME-TIFF format using the `svs_to_ometiff` library.

> **Experimental:** This GUI is experimental and not yet thoroughly tested. Use with caution on production data. Always verify outputs.

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

1.  **Drag & drop** an `.svs` file onto the drop zone, or click the drop zone to use a file dialog.
2.  The **Input SVS Path** field will be populated automatically.
3.  The **Output Path** is auto-derived (same directory, `.ome.tiff` extension). You may edit it manually.
4.  (Optional) Click the gear icon to expand **Advanced Settings** and adjust:
    - **Tile Size** (default: 512)
    - **Compression** (default: lzw; options: lzw, zlib, deflate, none)
    - **Levels** (default: 6)
    - **Downsample Factor** (default: 2)
5.  Click **Convert** to start the conversion.
6.  Monitor progress via the progress bar and status text.
7.  When complete, click **Open Output Folder** to reveal the output file.

## Project Structure

```
svs-to-ometiff-gui/
├── svs_to_ometiff_gui/
│   ├── __init__.py
│   ├── __main__.py           # python -m svs_to_ometiff_gui entry point
│   ├── serve.py              # Flask app with SSE progress
│   └── templates/
│       └── index.html         # Single-page GUI (inline CSS/JS)
├── pyproject.toml
├── requirements.txt
└── README.md
```

## License

Same as the `svs_to_ometiff` project.
