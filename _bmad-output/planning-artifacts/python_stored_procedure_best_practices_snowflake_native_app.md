# Python Stored Procedure Best Practices for Snowflake Native App / Snowpark Runtime

## Purpose

This note captures practical guidance for Python stored procedures that run inside a Snowflake Native App. It is meant to guide future Epic 5 pipeline work that will import `app/python/otlp_export.py` and similar shared modules.

Some points below are grounded in Snowflake documentation. Others are project-tested operational guidance based on Cortex research, local validation, and real Snowflake runtime behavior. Treat platform-behavior details such as warm reuse frequency, NAT idle windows, and memory overhead as empirical guidance rather than contractual guarantees.

## Runtime Baseline

- Stored procedures in this app target Python 3.13.
- Streamlit remains on Python 3.11 and resolves dependencies from `app/environment.yml`.
- Do not infer stored procedure package availability from the Streamlit environment file.
- For Snowpark code in stored procedures, use the latest `snowflake-snowpark-python` version available for Python 3.13 in `SNOWFLAKE.INFORMATION_SCHEMA.PACKAGES`.
- As of 2026-04-03, the latest available `snowflake-snowpark-python` version for Python 3.13 is `1.48.0`.

## Correctness

### Module-Level State and Warm Reuse

- Module-level globals can survive across stored procedure invocations on the same warm warehouse node.
- Warm reuse is best-effort only. The sandbox may be recycled at any time, including after suspend/resume, scaling events, node rebalancing, or memory pressure.
- Every code path that uses a module-level singleton must tolerate a cold start and rebuild the singleton when it is missing.
- Do not assume state survives across SQL sessions.

### Thread Safety

- Treat module-level globals as shared mutable state.
- Protect init, swap, and close paths with `threading.Lock`.
- For read-hot paths, capture the shared reference into a local variable before use. This avoids a race where another thread closes or replaces the object between the `None` check and the method call.
- If the client library itself is thread-safe for method calls, lock only the init/swap path, not every call.

### Process Termination Model

- Do not rely on `atexit`, `__del__`, or background-thread cleanup for correctness.
- Prefer synchronous work before handler return.
- Avoid daemon-thread-based processors for telemetry export in short-lived handlers.
- Do not shut down reusable cached clients on the normal success path; reserve shutdown for explicit teardown, idle eviction, or configuration changes.

### Secrets and `_snowflake`

- Read Snowflake secrets in the stored procedure entrypoint, not in reusable library modules.
- Import `_snowflake` lazily inside the handler so local tests can still import the module.
- Pass resolved secret values, such as PEM strings, into library functions as normal Python arguments.

### External Network Access

- Outbound access requires an `EXTERNAL_ACCESS_INTEGRATIONS` binding in the procedure DDL.
- Use `SECRETS = (...)` for credential or certificate access when needed.
- TLS-only transport should be enforced in validation and initialization code.
- Treat missing EAI wiring as a deployment/configuration failure mode that blocks outbound connectivity.

## Performance

### Cold Start and Imports

- Cold starts pay for Python interpreter initialization plus all module imports.
- Keep top-level imports limited to packages used on every invocation.
- Lazily import rare-path dependencies such as `_snowflake`.
- Favor module-level reusable client construction for expensive network clients and exporters.

### Reusable Client Construction

- Build one exporter or client per signal type, not per batch.
- Cache the initialized endpoint and credential fingerprint alongside the client.
- Rebuild when the endpoint changes, the PEM fingerprint changes, or the client has been idle longer than the configured eviction window.

### Synchronous Export

- In Snowflake SP sandboxes, synchronous `export(batch)` is the deterministic pattern.
- Background processors can lose buffered data when the handler returns.
- Let the caller own retry policy; the shared export module should surface explicit success or failure.

### Memory and Allocation

- Keep large datasets in Snowflake when possible.
- For future collectors, use chunked materialization such as `to_pandas_batches()` instead of loading large result sets into memory at once.
- Avoid long-lived caches of large Python objects.
- Small micro-optimizations are acceptable when they keep the hot path simpler:
  - store immutable channel options as a tuple
  - avoid repeated `.strip().encode(...)` on the same string
  - avoid repeated rebuilding of stable derived values

### Logging

- Module-level `logging.getLogger(__name__)` is fine.
- Keep exception logging out of hot loops.
- Log at lifecycle boundaries and real error points, not per-row or per-item in tight loops.

## Operational Guidance

### Testability

- Keep library modules Snowflake-agnostic when possible.
- Use a thin stored procedure adapter that reads secrets, parses config, calls the library, and returns JSON.
- In unit tests, patch local builder/helper functions rather than deep SDK internals where possible.
- Reset module-level state between tests.

### Retry and Failure Behavior

- Let shared transport modules return explicit success/failure values.
- Let caller-side pipeline code decide whether to retry, classify failure, or record terminal state.
- Keep reasonable transport timeouts to avoid hanging the handler indefinitely.

### Future Configurability

- Fixed transport timeouts are acceptable for MVP when a single value is operationally safe.
- If future production pipelines need different timeout tuning by environment or endpoint, add a dedicated configuration surface instead of widening a low-level module ad hoc.
- For this project, a future enhancement could expose OTLP export timeout tuning through the Splunk settings UX rather than embedding multiple timeout knobs directly into early pipeline stories.

## Checklist for Future Pipeline Stories

- [ ] Module-level client initialization is guarded and rebuild-safe.
- [ ] Shared mutable state is protected with `threading.Lock`.
- [ ] `_snowflake` is only imported inside Snowflake-specific entrypoints.
- [ ] Procedure DDL includes the required `EXTERNAL_ACCESS_INTEGRATIONS` and `SECRETS`.
- [ ] Export path is synchronous and returns explicit success/failure.
- [ ] Reused clients are not shut down on the normal success path.
- [ ] Endpoint and credential changes trigger a clean rebuild.
- [ ] Tests cover success, failure, and exception paths.
- [ ] Logging is helpful but not chatty in hot loops.
