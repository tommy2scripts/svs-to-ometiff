# Architecture Cleanup: Progress, Batch Planning, and Config Shape Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Make the codebase more testable and AI-navigable by deepening three Modules: structured progress events, batch planning, and GUI conversion configuration.

**Architecture:** Preserve public CLI/API behavior while moving duplicated or brittle policy behind deeper core Modules. Use `CONTEXT.md` domain language. Keep GUI and CLI as Adapters over core conversion behavior.

**Tech Stack:** Python 3.9+, pytest, Click, Flask, multiprocessing `ProcessPoolExecutor`, tifffile/imagecodecs.

---

## Guardrails

- Use TDD for production code changes.
- Keep public command names and current CLI/API behavior stable.
- Keep multiprocessing worker inputs pickle-safe.
- Prefer one authoritative Module per policy.
- Do not broaden format support; this cleanup is architectural only.

## Verification Baseline

Before changes, the current suite passes:

```bash
pytest -q
# Expected: 213 passed
```

---

## Phase 1: Structured Progress Seam

### Task 1.1: Pin structured progress dispatch behavior

**Objective:** Add a focused test proving GUI worker progress prefers structured percent/phase fields over message parsing.

**Files:**
- Modify: `tests/test_estimate_percent.py`
- Reference: `src/svs_to_ometiff_gui/services.py`

**Steps:**
1. Add a test that simulates the worker callback behavior with `percent=37.5` and `phase="custom_phase"` while the message text contains no parseable percent.
2. Run the test and verify RED if helper extraction is needed, or verify current callback code path with a minimal worker-free helper if already possible.
3. Implement the smallest helper if needed in `services.py` to normalize callback events.
4. Run:

```bash
pytest tests/test_estimate_percent.py -v
```

**Expected:** New structured event test passes.

### Task 1.2: Extract progress event normalization

**Objective:** Give GUI worker code one local helper for turning converter callback inputs into SSE/DB event dicts.

**Files:**
- Modify: `src/svs_to_ometiff_gui/services.py`
- Test: `tests/test_estimate_percent.py`

**Target behavior:**
- `message` is always preserved.
- `percent` kwarg wins when present.
- If `percent` is absent, use `estimate_percent(message)` as a legacy Adapter.
- `phase` is preserved when present.
- Batch fields are added by caller, not inferred from message text.

**Run:**

```bash
pytest tests/test_estimate_percent.py -v
pytest tests/test_services_start_conversion.py -v
```

### Task 1.3: Use structured progress helper in single and batch workers

**Objective:** Remove duplicated callback event-building logic from `_run_single_conversion_worker` and `_run_batch_conversion_worker`.

**Files:**
- Modify: `src/svs_to_ometiff_gui/services.py`
- Test: `tests/test_services_start_conversion.py`

**Run:**

```bash
pytest tests/test_services_start_conversion.py -v
pytest tests/test_routes.py -v
```

### Task 1.4: Add/verify structured progress emission from core stages

**Objective:** Ensure core stages emit structured fields for setup, tile decoding, pyramid construction, writing, complete, and cleanup warning.

**Files:**
- Review/modify as needed:
  - `src/svs_to_ometiff/converter.py`
  - `src/svs_to_ometiff/tile_reader.py`
  - `src/svs_to_ometiff/pyramid.py`
  - `src/svs_to_ometiff/writer.py`
- Tests:
  - existing synthetic conversion/progress tests or a new focused test if no coverage exists

**Run:**

```bash
pytest tests/test_estimate_percent.py -v
pytest tests/test_api.py -v
pytest -q
```

---

## Phase 2: Shared Batch Planning Module

### Task 2.1: Pin current batch planning behavior

**Objective:** Add tests for output path planning and duplicate collision detection before moving implementation.

**Files:**
- Create: `tests/test_batch_plan.py`

**Behaviors to test:**
- Same-folder output path: `slide.svs` -> `slide.ome.tiff`.
- Explicit output directory path.
- Duplicate stems from different source folders collide in the same output directory.
- Casefold-normalized paths collide.

**Run:**

```bash
pytest tests/test_batch_plan.py -v
```

**Expected RED:** Import fails because `svs_to_ometiff.batch_plan` does not exist.

### Task 2.2: Create core batch planning Module

**Objective:** Add one authoritative core Module for batch output policy.

**Files:**
- Create: `src/svs_to_ometiff/batch_plan.py`
- Test: `tests/test_batch_plan.py`

**Public surface, minimal:**
- `output_path_for_input(svs_path: str, output_dir: Optional[str]) -> str`
- `normalized_output_path(path: str) -> str`
- `find_duplicate_output_paths(files: list[str], output_dir: Optional[str]) -> dict[str, list[str]]`

**Run:**

```bash
pytest tests/test_batch_plan.py -v
```

### Task 2.3: Route CLI batch through shared Module

**Objective:** Delete duplicated batch planning helpers from CLI batch implementation.

**Files:**
- Modify: `src/svs_to_ometiff/batch.py`
- Test: existing batch-related coverage

**Run:**

```bash
pytest tests/test_cli_temp_dir.py -v
pytest tests/test_batch_plan.py -v
```

### Task 2.4: Route GUI batch through shared Module

**Objective:** Delete duplicated GUI batch planning helpers while preserving GUI-specific error formatting.

**Files:**
- Modify: `src/svs_to_ometiff_gui/services.py`
- Test:
  - `tests/test_routes.py`
  - `tests/test_services_start_conversion.py`
  - `tests/test_batch_plan.py`

**Run:**

```bash
pytest tests/test_routes.py -v
pytest tests/test_services_start_conversion.py -v
pytest tests/test_batch_plan.py -v
```

---

## Phase 3: ConvertConfig / GUI Model Shape Cleanup

### Task 3.1: Pin GUI conversion config mapping

**Objective:** Ensure GUI request/model mapping preserves conversion options and is pickle-safe before refactor.

**Files:**
- Modify: `tests/test_models.py`
- Reference:
  - `src/svs_to_ometiff_gui/models.py`
  - `src/svs_to_ometiff/config.py`

**Behaviors to test:**
- `ConversionJob.to_converter_kwargs()` maps to converter-compatible kwargs.
- Compression `"none"` normalizes through `ConvertConfig` correctly.
- `compressionargs` survives mapping.
- Returned kwargs are pickle-safe.

**Run:**

```bash
pytest tests/test_models.py -v
```

### Task 3.2: Make `ConversionJob` wrap normalized conversion configuration

**Objective:** Reduce duplication between GUI job fields and `ConvertConfig` while preserving worker submission behavior.

**Files:**
- Modify: `src/svs_to_ometiff_gui/models.py`
- Test: `tests/test_models.py`

**Constraints:**
- Preserve `ConversionJob(...)` construction compatibility where routes/tests use it.
- Keep `to_converter_kwargs()` stable for workers unless all call sites are changed in the same task.
- Do not remove public `convert()` legacy compatibility.

**Run:**

```bash
pytest tests/test_models.py -v
```

### Task 3.3: Reduce duplicate validation in route job construction

**Objective:** Let `ConvertConfig` remain the authoritative conversion validation shape and make route code thinner.

**Files:**
- Modify: `src/svs_to_ometiff_gui/serve.py`
- Test:
  - `tests/test_gui_params.py`
  - `tests/test_routes.py`

**Run:**

```bash
pytest tests/test_gui_params.py -v
pytest tests/test_routes.py -v
```

### Task 3.4: Final integration verification

**Objective:** Confirm all three architecture cleanup phases preserve behavior.

**Run:**

```bash
ruff check .
pytest -q
```

**Expected:** Ruff clean and full test suite passing.

---

## Completion Checklist

- [ ] `CONTEXT.md` exists and defines domain terms used in architecture discussions.
- [ ] Structured progress events are the primary GUI progress Seam.
- [ ] Text parsing remains only as a legacy Adapter.
- [ ] Batch output planning exists in one core Module.
- [ ] CLI and GUI use the shared batch planning Module.
- [ ] `ConvertConfig` is clearly authoritative for conversion option validation.
- [ ] GUI job shape no longer adds unnecessary conversion semantic duplication.
- [ ] Full test suite passes.
- [ ] Ruff passes.
