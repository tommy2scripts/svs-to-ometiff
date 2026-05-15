
## Plan Generation Learnings (2026-05-15)

### Plan Structure
- Created `.sisyphus/plans/svs-to-ometiff-v0.7.0.md` (512 lines)
- No existing plan files were found in the repo (no `svs-to-ometiff-release.md`)
- Based the format on the writing-plans skill template adapted for Sisyphus orchestrator usage
- Plans directory had to be created: `mkdir -p .sisyphus/plans/`

### Scope Decisions
- 4 features IN scope (derived from task description, which narrowed the original gap analysis):
  1. ConvertConfig serialization (was MUST #3 in decisions.md)
  2. Graceful shutdown signal handling (was SHOULD #5 in decisions.md)
  3. JPEG/JPEG 2000 compression support (was MUST #1 in decisions.md)
  4. Large-file integration tests (was SHOULD #6 in decisions.md)
- Parallel tile decoding (MUST #2) deferred to v0.8.0 per task instructions
- Multi-format WSI (SHOULD #4) deferred to v0.8.0
- OpenAPI/Swagger (COULD #7) deferred to v0.8.0

### Key Source Files Mapped
- config.py (49 lines): _SUPPORTED_COMPRESSION tuple at line 8, ConvertConfig at line 11
- converter.py (317 lines): _LEGACY_CONFIG_DEFAULTS at line 23, _coerce_convert_config at line 76
- cli.py (150 lines): click.Choice at line 41, main() at line 90
- batch.py (174 lines): mirror of cli.py structure
- writer.py (249 lines): write_pyramidal_ometiff_from_levels at line 125
- GUI: models.py (68 lines), serve.py (403 lines), services.py (322 lines)
- tests/helpers.py (56 lines): write_synthetic_33007_svs()

### Guardrails Enforced
- NO new dependencies (all features use stdlib or existing deps)
- NO CLI breaking changes
- NO pipeline architecture changes
- 112 existing tests must pass throughout
- Default compression remains zlib

### Execution Wave Design
- Wave 1: Tasks 1+2 (parallel) — Config serialization + Signal handling are independent
- Wave 2: Task 3 — JPEG/JPEG2000 builds on stable foundation from Wave 1
- Wave 3: Task 4 — Large-file tests validate all features end-to-end
- Final: F1-F4 reviewers run in parallel to verify completeness

### Agent Strategies
- T1 (quick): Simple serialization methods on existing dataclass
- T2 (unspecified-high): Cross-cutting signal handling across multiple files
- T3 (unspecified-high): Touches config, writer, CLI, batch, GUI, and converter
- T4 (unspecified-high): Test-only but complex synthetic fixture generation
- F1-F3 (deep): Oracles need thorough codebase understanding
- F4 (unspecified-high): Hands-on QA execution
