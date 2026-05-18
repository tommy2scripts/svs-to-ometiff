"""Static checks for browser path handling copy and helpers."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_gui_warns_browser_drag_drop_may_only_provide_filename() -> None:
    html = (
        ROOT / "svs_to_ometiff_gui" / "templates" / "index.html"
    ).read_text(encoding="utf-8")

    assert "Browser drag-and-drop cannot expose full local paths" in html
    assert "Use <strong>Browse</strong>" in html


def test_gui_path_helper_accepts_windows_drive_and_unc_paths() -> None:
    js = (
        ROOT / "svs_to_ometiff_gui" / "static" / "js" / "app.js"
    ).read_text(encoding="utf-8")

    assert "function hasAbsoluteLikePath" in js
    assert "[a-zA-Z]:" in js
    assert "\\\\" in js
    assert "file.name" in js
