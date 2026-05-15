# Learnings - svs-to-ometiff v0.6.1 Release

## Task 1: Pre-flight Checks (2026-05-15)

### Key Findings
- Tag v0.6.1 is an **annotated tag** (not lightweight). The tag object hash is `49e75d5`, which points to commit `b7c0e79`.
- Version is correctly set to "0.6.1" in both `pyproject.toml` and `__init__.py`.
- All project URLs in pyproject.toml use HTTPS format (no SSH URLs in project files).
- Git remote uses SSH (`git@github.com:tommy2scripts/svs-to-ometiff.git`) — this is standard/expected for git operations and not flagged as an issue.
- No secrets were detected in git history (no API keys, tokens, or passwords).
- No blobs larger than 10MB found in git history.
- LICENSE file is present (1084 bytes, MIT-style).

### Git Remote Info
- Remote: `origin`
- URL: `git@github.com:tommy2scripts/svs-to-ometiff.git` (SSH)
- Repo currently private
- PyPI has v0.4.1 only
