# Release Checklist

Follow this checklist for every release of `svs-to-ometiff`.

## Pre-release

- [ ] `git status --short --branch` is clean.
- [ ] `python3 -m pytest -q` passes.
- [ ] `python3 -m ruff check .` passes.
- [ ] `rm -rf dist && python3 -m build` passes.
- [ ] `python3 -m twine check dist/*` passes.
- [ ] `python3 -m svs_to_ometiff --version` matches `pyproject.toml`.
- [ ] `CHANGELOG.md` has a dated entry for this release.
- [ ] README validation status is honest and current.
- [ ] If publishing GUI, core `svs-to-ometiff>=0.4.0` is already on PyPI.

## Tagging

- [ ] Tag only the exact release commit.
- [ ] Do not move a pushed tag unless intentionally repairing a failed release.
- [ ] Use `git tag -a vX.Y.Z -m "vX.Y.Z"`.
- [ ] Push with `git push origin main --tags`.

## Post-release

- [ ] Verify PyPI page renders README correctly.
- [ ] Fresh-venv install from PyPI works.
- [ ] `svs-to-ometiff-inspect`, `svs-to-ometiff`, and `svs-to-ometiff-verify`
  work on synthetic fixture or documented sample.
