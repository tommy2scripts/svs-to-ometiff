
## QA Issues Found (2026-05-15 F4 Review)

### Blocking Issues
1. **Stale version assertions** — `test_config_and_health.py:14,95` assert `__version__ == "0.6.1"` → should be `"0.7.0"`
2. **batch.py missing JPEG support** — No `jpeg`/`jpeg2000` in compression choices; no `--compression-args`
3. **Missing `to_json()`/`from_json()`** — Plan T1 required but not implemented
4. **`from_dict()` ignores unknown keys** — Plan says should raise ValueError
5. **`/health` missing `shutting_down`** — Plan T2 required field
6. **No intra-loop shutdown checks** — Only between-stage checks in converter.py, not in tile/pyramid loops

### Non-Blocking
- README doesn't document JPEG/JPEG2000 compression options
- `compression_quality` → `compressionargs` design deviation (acceptable, more flexible)
- `--compression-quality` → `--compression-args` naming deviation (acceptable, consistent with tifffile)

