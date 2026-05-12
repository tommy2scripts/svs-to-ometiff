# Contributing to svs-to-ometiff

## Scope

This tool is focused on Aperio SVS files with compression tag `33007` (raw YUYV YCbCr 4:2:2). Contributions outside this scope — such as JPEG/JPEG 2000 SVS conversion, other WSI formats, or clinical validation — are better suited to general-purpose tools like OpenSlide or Bio-Formats.

## Getting started

```bash
git clone https://github.com/tommy2scripts/svs-to-ometiff.git
cd svs-to-ometiff
pip install -e ".[dev]"
python -m pytest
```

## Before submitting

- [ ] `ruff check src/ tests/` passes
- [ ] `python -m pytest -q` passes
- [ ] New functionality includes tests
- [ ] Public API changes are reflected in `__init__.py` exports
- [ ] CHANGELOG.md has an entry under "Unreleased"

## Testing

Tests use synthetic Aperio-style TIFF fixtures (no real SVS files are committed). The test helper `write_synthetic_33007_svs` in `tests/helpers.py` creates a valid tiled TIFF with compression patched to `33007`.

## Code style

- Line length: 88 (Ruff default)
- Type hints required for all public functions
- Google-style docstrings
- Prefer pathlib over `os.path` where practical
