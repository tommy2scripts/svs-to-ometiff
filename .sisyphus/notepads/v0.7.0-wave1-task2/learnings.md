# Learnings — Wave 1, Task 2: Graceful Shutdown

## Files Modified
- `svs_to_ometiff_gui/serve.py` — signal handlers (Werkzeug SIGINT, gunicorn SIGTERM)
- `svs_to_ometiff_gui/services.py` — ConversionService.shutdown(), worker signal handlers, dispatch timeout
- `src/svs_to_ometiff/converter.py` — module-level _shutdown_event, _ConversionCancelled, 3 checkpoints
- `tests/test_shutdown.py` — 17 new tests

## Patterns Used
- `threading.Event` for SSE dispatch shutdown signaling (non-blocking timeout loop)
- `ProcessPoolExecutor.shutdown(wait=False, cancel_futures=True)` for worker termination
- Module-level `_shutdown_event` in converter.py — each worker process has its own copy
- Signal handlers in worker processes (`_install_worker_signal_handlers()`) set converter's event
- Gunicorn detection: `"gunicorn" in os.environ.get("SERVER_SOFTWARE", "")` + argv check
- Pytest detection: `"PYTEST_CURRENT_TEST" in os.environ`
- SIGINT handler in main() re-sends signal after cleanup for Werkzeug to handle
- SSE queues unblocked with sentinel error events during shutdown
- Multiprocessing queue unblocked with `("__shutdown__", "shutdown", {})` sentinel
- `os._exit(0)` in gunicorn SIGTERM handler for clean worker exit

## Key Design Decisions
1. `_shutdown_event` is module-level in converter.py — workers set it via signal handler, convert() checks it between stages
2. dispatch thread uses `queue.get(timeout=0.5)` instead of blocking get — allows periodic shutdown check
3. `cancel_futures=True` — Python 3.9+ only, matches project requirements
4. Signal handlers NOT installed during pytest (gunicorn handler skips, main() handler skips)
5. `_ConversionCancelled` is a private exception — handled separately from conversion errors, triggers temp cleanup

## Test Count
- 17 new tests (all pass)
- 145 total (128 existing + 17 new)
