"""Quality Control HTML report generator for svs-to-ometiff."""

from __future__ import annotations

import base64
import html
import io
from typing import Any, Optional

import numpy as np
import tifffile
from svs_to_ometiff import __version__

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _get_thumbnail_base64(path: str) -> Optional[str]:
    """Extract a thumbnail from the smallest pyramid level of the OME-TIFF."""
    if not HAS_PIL:
        return None
    try:
        with tifffile.TiffFile(path) as tif:
            if not tif.series:
                return None
            levels = tif.series[0].levels
            if not levels:
                return None
            # Get the smallest resolution level
            smallest_level = levels[-1]
            data = smallest_level.asarray()
            
            # Ensure it is RGB uint8
            if data.ndim != 3 or data.shape[2] != 3:
                return None
            if data.dtype != np.uint8:
                data = data.astype(np.uint8)

            # Resize to max 300px bounding box
            h, w = data.shape[:2]
            max_size = 300
            if w > max_size or h > max_size:
                scale = max_size / max(w, h)
                new_w = int(w * scale)
                new_h = int(h * scale)
            else:
                new_w, new_h = w, h

            img = Image.fromarray(data)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        return None


def _build_css(status_glow: str, status_color: str) -> str:
    """Build the CSS block for the HTML report."""
    return f"""<style>
    :root {{
      --bg: #0b0f19;
      --card-bg: #111827;
      --card-border: #1f2937;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --green: #10b981;
      --red: #ef4444;
      --orange: #f59e0b;
      --blue: #3b82f6;
      --radius: 12px;
      --shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.7);
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: 'Inter', sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 2rem 1rem;
    }}

    .container {{
      max-width: 1100px;
      margin: 0 auto;
    }}

    header {{
      display: flex;
      justify-content: flex-start;
      align-items: center;
      gap: 1.5rem;
      margin-bottom: 2rem;
      border-bottom: 1px solid var(--card-border);
      padding-bottom: 1.5rem;
      flex-wrap: wrap;
    }}

    h1, h2, h3 {{
      font-family: 'Outfit', sans-serif;
    }}

    .logo {{
      font-size: 1.5rem;
      font-weight: 700;
      letter-spacing: -0.5px;
      background: linear-gradient(135deg, #60a5fa, #3b82f6);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}

    .badge {{
      padding: 0.5rem 1.5rem;
      border-radius: 9999px;
      font-weight: 700;
      font-family: 'Outfit', sans-serif;
      font-size: 1.1rem;
      border: 1px solid transparent;
      box-shadow: {status_glow};
      background-color: rgba(17, 24, 39, 0.8);
      color: {status_color};
      border-color: {status_color};
    }}

    .grid {{
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 2rem;
    }}

    @media (max-width: 850px) {{
      .grid {{
        grid-template-columns: 1fr;
      }}
    }}

    .card {{
      background-color: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: var(--radius);
      padding: 1.5rem;
      box-shadow: var(--shadow);
      margin-bottom: 2rem;
    }}

    .card-title {{
      font-size: 1.25rem;
      font-weight: 600;
      margin-bottom: 1.25rem;
      color: #ffffff;
      border-bottom: 1px solid var(--card-border);
      padding-bottom: 0.75rem;
    }}

    /* Metadata lists */
    .meta-list {{
      list-style: none;
    }}

    .meta-item {{
      display: flex;
      justify-content: space-between;
      padding: 0.75rem 0;
      border-bottom: 1px solid rgba(31, 41, 55, 0.5);
    }}

    .meta-item:last-child {{
      border-bottom: none;
    }}

    .meta-label {{
      font-weight: 500;
      color: var(--text-muted);
    }}

    .meta-val {{
      font-weight: 600;
      text-align: right;
    }}

    /* Table styles */
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 0.5rem;
    }}

    th, td {{
      padding: 0.75rem;
      text-align: left;
      border-bottom: 1px solid var(--card-border);
    }}

    th {{
      font-weight: 600;
      color: var(--text-muted);
    }}

    /* Thumbnail display */
    .thumbnail-container {{
      background-color: #0d1117;
      border-radius: var(--radius);
      border: 1px dashed var(--card-border);
      padding: 1rem;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 250px;
      position: relative;
    }}

    .thumbnail-img {{
      max-width: 100%;
      max-height: 220px;
      border-radius: 6px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
    }}

    .thumbnail-label {{
      margin-top: 0.75rem;
      font-size: 0.8rem;
      color: var(--text-muted);
      font-weight: 500;
    }}

    .thumbnail-empty-icon {{
      font-size: 3rem;
      margin-bottom: 1rem;
    }}

    .thumbnail-label-hint {{
      font-size: 0.75rem;
      color: var(--orange);
      margin-top: 0.5rem;
    }}

    /* Alerts */
    .alert-section {{
      padding: 1rem;
      border-radius: var(--radius);
      margin-bottom: 1.5rem;
      border-left: 5px solid;
    }}

    .warning-section {{
      background-color: rgba(245, 158, 11, 0.1);
      border-color: var(--orange);
      color: #fef3c7;
    }}

    .error-section {{
      background-color: rgba(239, 68, 68, 0.1);
      border-color: var(--red);
      color: #fee2e2;
    }}

    .alert-section h3 {{
      font-size: 1.1rem;
      margin-bottom: 0.75rem;
      font-weight: 600;
    }}

    .alert-section ul {{
      list-style-type: none;
      padding-left: 0.25rem;
    }}

    .alert-section li {{
      margin-bottom: 0.5rem;
      font-size: 0.95rem;
    }}

    .alert-section li:last-child {{
      margin-bottom: 0;
    }}

    /* JSON code block tab */
    .json-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
    }}

    pre {{
      background-color: #090d16;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 1rem;
      overflow-x: auto;
      font-size: 0.85rem;
      color: #818cf8;
      max-height: 400px;
    }}

    /* Disclaimer footer */
    .disclaimer-card {{
      background-color: rgba(31, 41, 55, 0.2);
      border: 1px solid var(--card-border);
      border-radius: var(--radius);
      padding: 1.25rem;
      text-align: center;
      margin-top: 2rem;
    }}

    .disclaimer-title {{
      font-size: 0.95rem;
      font-weight: 600;
      color: var(--orange);
      margin-bottom: 0.5rem;
    }}

    .disclaimer-text {{
      font-size: 0.85rem;
      color: var(--text-muted);
    }}
  </style>"""


def _build_thumbnail_html(thumbnail_data: Optional[str]) -> str:
    """Build the thumbnail HTML section."""
    if thumbnail_data:
        return (
            f'<div class="thumbnail-container">\n'
            f'  <img src="{thumbnail_data}" class="thumbnail-img" alt="QC Thumbnail" />\n'
            f'  <span class="thumbnail-label">Smallest Pyramid Level</span>\n'
            f'</div>'
        )
    return (
        '<div class="thumbnail-container empty">\n'
        '  <span class="thumbnail-empty-icon">📷</span>\n'
        '  <span>No Thumbnail Available</span>\n'
        '  <span class="thumbnail-label-hint">Install Pillow for embedded thumbnails</span>\n'
        '</div>'
    )


def _build_alerts_html(result: dict[str, Any]) -> tuple[str, str]:
    """Build HTML sections for errors and warnings."""
    warnings_html = ""
    if result.get("warnings"):
        warnings_html += '<div class="alert-section warning-section"><h3>Warnings</h3><ul>'
        for warn in result["warnings"]:
            warnings_html += f"<li>⚠️ {html.escape(warn)}</li>"
        warnings_html += "</ul></div>"

    errors_html = ""
    if result.get("errors"):
        errors_html += '<div class="alert-section error-section"><h3>Errors / Failures</h3><ul>'
        for err in result["errors"]:
            errors_html += f"<li>❌ {html.escape(err)}</li>"
        errors_html += "</ul></div>"

    return warnings_html, errors_html


def _build_geometry_html(result: dict[str, Any]) -> str:
    """Build the pyramid geometry table rows."""
    levels_list = result.get("levels", [])
    levels_rows = ""
    dtype = html.escape(str(result.get("dtype", "uint8")))
    for idx, lvl in enumerate(levels_list):
        lvl_w, lvl_h = lvl[1], lvl[0]
        levels_rows += f"<tr><td>Level {idx}</td><td>{lvl_w} x {lvl_h}</td><td>{dtype}</td></tr>"
    return levels_rows


def _build_json_html(result: dict[str, Any]) -> str:
    """Build the formatted JSON metadata section."""
    import json
    try:
        return html.escape(json.dumps(result, indent=2, sort_keys=True))
    except Exception:
        return html.escape(str(result))


def _build_header_html(escaped_path: str, status_text: str, status_color: str, status_glow: str) -> str:
    """Build the HTML head and page header."""
    css = _build_css(status_glow, status_color)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Quality Control Report - {escaped_path}</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">
  {css}
</head>
<body>
  <div class="container">
    <header>
      <div style="flex-grow: 1;">
        <span class="logo">svs-to-ometiff</span>
        <h2 style="font-size: 1.75rem; font-weight: 700; margin-top: 0.25rem;">Quality Control Report</h2>
      </div>
      <div class="badge">{status_text}</div>
    </header>"""


def _build_conformance_html(escaped_path: str, escaped_source_path: str, escaped_dtype: str, result: dict[str, Any]) -> str:
    """Build the output conformance card."""
    is_ome_color = 'var(--green)' if result.get('is_ome') else 'var(--red)'
    is_ome_text = 'Yes' if result.get('is_ome') else 'No'

    is_bigtiff_color = 'var(--green)' if result.get('is_bigtiff') else 'var(--red)'
    is_bigtiff_text = 'Yes' if result.get('is_bigtiff') else 'No'

    tile_width = result.get('tile_width', 'None')
    tile_height = result.get('tile_height', 'None')

    phys_size = result.get('physical_size_x')
    mpp_text = f"{phys_size:.6f} µm" if phys_size is not None else 'Not Found'

    return f"""
        <div class="card">
          <h2 class="card-title">Output Conformance</h2>
          <ul class="meta-list">
            <li class="meta-item">
              <span class="meta-label">Output Path</span>
              <span class="meta-val" style="word-break: break-all;">{escaped_path}</span>
            </li>
            <li class="meta-item">
              <span class="meta-label">Source Path</span>
              <span class="meta-val" style="word-break: break-all;">{escaped_source_path}</span>
            </li>
            <li class="meta-item">
              <span class="meta-label">Conforms to OME Metadata</span>
              <span class="meta-val" style="color: {is_ome_color};">{is_ome_text}</span>
            </li>
            <li class="meta-item">
              <span class="meta-label">Is BigTIFF Format</span>
              <span class="meta-val" style="color: {is_bigtiff_color};">{is_bigtiff_text}</span>
            </li>
            <li class="meta-item">
              <span class="meta-label">Tile Size</span>
              <span class="meta-val">{tile_width} x {tile_height}</span>
            </li>
            <li class="meta-item">
              <span class="meta-label">Dtype</span>
              <span class="meta-val">{escaped_dtype}</span>
            </li>
            <li class="meta-item">
              <span class="meta-label">Physical pixel size (MPP)</span>
              <span class="meta-val">{mpp_text}</span>
            </li>
          </ul>
        </div>"""


def generate_qc_html(path: str, result: dict[str, Any], source_path: Optional[str] = None) -> str:
    """Generate a premium, responsive standalone HTML QC report."""
    is_pass = result.get("pass", False)
    status_text = "PASS" if is_pass else "FAIL"
    status_color = "var(--green)" if is_pass else "var(--red)"
    status_glow = "0 0 20px rgba(16, 185, 129, 0.2)" if is_pass else "0 0 20px rgba(239, 68, 68, 0.2)"

    thumbnail_data = _get_thumbnail_base64(path)
    thumbnail_html = _build_thumbnail_html(thumbnail_data)

    escaped_path = html.escape(str(path))
    escaped_source_path = html.escape(str(source_path)) if source_path else "None"
    escaped_dtype = html.escape(str(result.get("dtype", "None")))

    warnings_html, errors_html = _build_alerts_html(result)
    levels_rows = _build_geometry_html(result)
    pretty_json = _build_json_html(result)

    return f"""{_build_header_html(escaped_path, status_text, status_color, status_glow)}

    {errors_html}
    {warnings_html}

    <div class="grid">
      <div class="main-column">
        {_build_conformance_html(escaped_path, escaped_source_path, escaped_dtype, result)}

        <div class="card">
          <h2 class="card-title">Pyramid Geometry</h2>
          <table>
            <thead>
              <tr>
                <th>Resolution Level</th>
                <th>Dimensions (W x H)</th>
                <th>Dtype</th>
              </tr>
            </thead>
            <tbody>
              {levels_rows}
            </tbody>
          </table>
        </div>
      </div>

      <div class="sidebar-column">
        <div class="card" style="padding: 1rem;">
          <h2 class="card-title" style="margin-bottom: 0.75rem;">Thumbnail</h2>
          {thumbnail_html}
        </div>

        <div class="card">
          <h2 class="card-title">Converter Metadata</h2>
          <ul class="meta-list">
            <li class="meta-item">
              <span class="meta-label">Tool Version</span>
              <span class="meta-val">v{__version__}</span>
            </li>
            <li class="meta-item">
              <span class="meta-label">QC Execution Status</span>
              <span class="meta-val" style="color: {status_color}; font-weight: 700;">{status_text}</span>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="json-header">
        <h2 class="card-title" style="margin-bottom: 0; border: none; padding: 0;">Raw JSON Metadata</h2>
      </div>
      <pre><code>{pretty_json}</code></pre>
    </div>

    <div class="disclaimer-card">
      <div class="disclaimer-title">Non-Diagnostic Disclaimer</div>
      <div class="disclaimer-text">
        svs-to-ometiff is designed and intended for research use only. 
        The converted pyramidal outputs and verification statuses have NOT been validated, approved, or cleared for clinical, patient, or diagnostic use. 
        Always verify alignments and pixel formats independently for therapeutic pipelines.
      </div>
    </div>
  </div>
</body>
</html>
"""
