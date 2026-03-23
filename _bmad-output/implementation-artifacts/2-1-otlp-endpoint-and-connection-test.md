# Story 2.1: OTLP endpoint and connection test

Status: done

## Story

As a Snowflake administrator (Maya),
I want to enter the OTLP gRPC endpoint and run a connection test before saving,
So that I know the destination is reachable and avoid saving a broken configuration.

## Acceptance Criteria

1. **Given** I am on the Splunk settings page, Export settings tab, **When** I see the page layout, **Then** the page shows `st.tabs(["Export settings"])` with an OTLP endpoint card inside `st.container(border=True)`.

2. **Given** the Export settings tab is displayed, **When** I enter an OTLP endpoint (e.g. `otelcol.israelcentral.cloudapp.azure.com:4317` or `https://collector.example.com:4317`) in the text input, **Then** the endpoint value is stored in `st.session_state` and the "Test connection" button is enabled.

3. **Given** I have entered an endpoint and click "Test connection", **When** the app executes the connection test, **Then** the app updates the outbound access configuration for the entered endpoint (placeholder network rule + app specification, using the pre-created external access integration), then a stored procedure performs a real gRPC channel readiness probe to that endpoint over TLS and returns a structured result (success/failure with diagnostic message).

4. **Given** the connection test succeeds (gRPC channel reaches READY state), **Then** I see a green success alert ("Connection successful") and the "Save settings" button becomes enabled.

5. **Given** the connection test fails, **Then** I see an error alert with an actionable diagnostic message (e.g. "Connection timed out — check that the endpoint is reachable" or "TLS handshake failed — certificate verification error") and "Save settings" remains disabled.

6. **Given** the connection test has not been run or has failed, **Then** "Save settings" is disabled (grayed out).

7. **Given** I click "Clear", **Then** the endpoint field is reset, test result is cleared, and "Save settings" returns to disabled.

8. **Given** the EAI app specification has not been approved by the consumer yet, **When** I click "Test connection", **Then** I see an informative message explaining that the external access request must be approved before the test can proceed, with guidance on where to approve it.

## Tasks / Subtasks

- [x] **Task 1: Splunk settings page UI** (AC: 1, 2, 4, 5, 6, 7, 8)
  - [x] 1.1 Replace the placeholder `splunk_settings.py` with the Export settings tab layout
  - [x] 1.2 Build the OTLP endpoint card (`st.container(border=True)`) with `st.text_input`, "Test connection" and "Clear" buttons
  - [x] 1.3 Add a placeholder Certificate card (empty `st.container(border=True)` with "Certificate (optional)" header and a note that it will be implemented in Story 2.2)
  - [x] 1.4 Build the footer section with "Save settings" button (disabled until test succeeds; save logic deferred to Story 2.3)
  - [x] 1.5 Implement `st.session_state` management for endpoint value, test result, and button states
  - [x] 1.6 Render success/error feedback using `st.success`/`st.error` callouts
  - [x] 1.7 Handle the "app specification not approved" state with a clear `st.warning` message

- [x] **Task 2: Dynamic outbound access provisioning stored procedure** (AC: 3, 8)
  - [x] 2.1 Create `app/python/provision_egress.py` with the handler function
  - [x] 2.2 Implement dynamic provisioning logic: parse endpoint → normalize `host:port` → `ALTER NETWORK RULE` → `ALTER APPLICATION SET SPECIFICATION` (the EAI object itself remains constant)
  - [x] 2.3 Handle first-time provisioning semantics (placeholder host still configured) vs. update (endpoint changed)
  - [x] 2.4 Return a structured JSON result: `{provisioned: bool, host_port: str, specification_changed: bool, needs_approval: bool, message: str}`

- [x] **Task 3: gRPC connection test stored procedure** (AC: 3, 4, 5)
  - [x] 3.1 Create `app/python/connection_test.py` with the handler function
  - [x] 3.2 Implement the gRPC channel readiness probe using `grpc.secure_channel` + `grpc.channel_ready_future` (reference: `grpc_test/otlp_grpc_probe.py`)
  - [x] 3.3 Parse the endpoint string, extract host and port, handle common format issues
  - [x] 3.4 Use Snowflake default CA bundle for TLS (custom PEM support deferred to Story 2.2)
  - [x] 3.5 Classify failures into diagnostic buckets: invalid endpoint format, timeout, TLS failure, DNS/network, refused, external access not approved
  - [x] 3.6 Return a structured JSON result: `{success: bool, message: str, details: str}`

- [x] **Task 4: Register SPs and EAI infrastructure in setup.sql** (AC: 3)
  - [x] 4.1 Add placeholder network rule (`_internal.otlp_egress_rule`) with `TYPE = HOST_PORT`, `MODE = EGRESS`
  - [x] 4.2 Add EAI (`otlp_egress_eai`) referencing the network rule
  - [x] 4.3 Add initial app specification (`ALTER APPLICATION SET SPECIFICATION otlp_egress_spec`)
  - [x] 4.4 Add `CREATE OR REPLACE PROCEDURE` DDL for provisioning SP (`app_public.provision_otlp_egress`) — `EXECUTE AS OWNER`
  - [x] 4.5 Add `CREATE OR REPLACE PROCEDURE` DDL for connection test SP (`app_public.test_otlp_connection`) — with `EXTERNAL_ACCESS_INTEGRATIONS = (otlp_egress_eai)`
  - [x] 4.6 Grant USAGE on both SPs to `app_admin`

- [x] **Task 5: Wire UI to stored procedures** (AC: 3, 4, 5, 8)
  - [x] 5.1 On "Test connection" click: first call `provision_otlp_egress(endpoint)`, then call `test_otlp_connection(endpoint)`
  - [x] 5.2 Parse the SP return values and update `st.session_state` with the result
  - [x] 5.3 Show `st.spinner` during the provisioning + test execution
  - [x] 5.4 If provisioning returns `needs_approval: true`, or the connection test returns an approval-related diagnostic, show `st.warning` with approval instructions instead of a generic failure message

- [x] **Task 6: Add SP handler files to snowflake.yml** (AC: 3)
  - [x] 6.1 Add `app/python/` to artifacts mapping so handler files are staged

## Dev Notes

### Architecture: Streamlit + Stored Procedure split

The connection test **must** run in a stored procedure, not in Streamlit. `grpcio` depends on native `.so` files which are not supported in the Streamlit runtime (warehouse runtime for Native Apps). The Streamlit page collects user input and displays results; the SPs perform the actual gRPC probe and EAI provisioning.

### Dynamic EAI provisioning — the correct architecture

**The user-entered endpoint must drive the outbound access configuration at test time.** This is not deferred to a later epic — it is a core requirement for the connection test to function. Without the correct network rule allowing egress to the target host:port, the gRPC probe will fail.

**How it works (Snowflake Native App pattern, per docs):**

1. **`setup.sql`** creates placeholder infrastructure:
   ```sql
   -- Placeholder network rule — will be altered at runtime with the real endpoint
   CREATE OR REPLACE NETWORK RULE _internal.otlp_egress_rule
       TYPE = HOST_PORT
       MODE = EGRESS
       VALUE_LIST = ('placeholder.invalid:4317');

   -- EAI referencing the network rule — stays the same name, rule contents change
   CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION otlp_egress_eai
       ALLOWED_NETWORK_RULES = (_internal.otlp_egress_rule)
       ENABLED = TRUE;

   -- App specification — declares the host:port for consumer approval
   ALTER APPLICATION SET SPECIFICATION otlp_egress_spec
       TYPE = EXTERNAL_ACCESS
       LABEL = 'OTLP gRPC Export'
       DESCRIPTION = 'Connect to the configured OTLP/gRPC collector endpoint for telemetry export'
       HOST_PORTS = ('placeholder.invalid:4317');
   ```

2. **At runtime** — when admin clicks "Test connection":
   - `app_public.provision_otlp_egress(endpoint)` SP runs (EXECUTE AS OWNER):
     ```sql
     ALTER NETWORK RULE _internal.otlp_egress_rule SET VALUE_LIST = ('<host>:<port>');
     ALTER APPLICATION SET SPECIFICATION otlp_egress_spec
         TYPE = EXTERNAL_ACCESS
         LABEL = 'OTLP gRPC Export'
         DESCRIPTION = 'Connect to the configured OTLP/gRPC collector endpoint for telemetry export'
         HOST_PORTS = ('<host>:<port>');
     ```
   - This updates the network rule and the app specification to allow egress to the new endpoint.
   - If the HOST_PORTS value changed, the app specification sequence number increments and requires consumer re-approval.

3. **Consumer approval:**
   - The consumer (Snowflake admin = the same person configuring the app) must approve the app specification via Snowsight or SQL: `ALTER APPLICATION <app_name> APPROVE SPECIFICATION otlp_egress_spec SEQUENCE_NUMBER <N>;`
   - The EAI is **not usable** until the specification is approved (per [Snowflake docs](https://docs.snowflake.com/en/developer-guide/native-apps/requesting-app-specs-eai)).
   - The connection test SP must handle this case gracefully.

4. **After approval** — the connection test SP executes the gRPC probe through the provisioned EAI.

**Key insight:** The EAI name (`otlp_egress_eai`) and SP reference (`EXTERNAL_ACCESS_INTEGRATIONS = (otlp_egress_eai)`) stay constant. The runtime change is to the underlying network rule plus the application specification. This means the connection test SP never needs to be recreated when the endpoint changes.

**Docs references:**
- [ALTER NETWORK RULE](https://docs.snowflake.com/en/sql-reference/sql/alter-network-rule) — `SET VALUE_LIST` replaces the current identifiers (not additive)
- [ALTER APPLICATION SET SPECIFICATION](https://docs.snowflake.com/en/sql-reference/sql/alter-application-set-app-spec) — changing `HOST_PORTS` increments sequence number
- [Request EAIs with app specifications](https://docs.snowflake.com/en/developer-guide/native-apps/requesting-app-specs-eai) — full Native App EAI pattern

### Provisioning SP: `app_public.provision_otlp_egress`

This SP parses the endpoint, updates the network rule, and sets the app specification. It must run as OWNER to have the privileges needed to alter these objects.

```python
import json

def provision_egress(session, endpoint: str) -> str:
    """Provision EAI for the given OTLP endpoint."""
    host, port = _parse_endpoint(endpoint)
    host_port = f"{host}:{port}"

    session.sql(
        f"ALTER NETWORK RULE _internal.otlp_egress_rule SET VALUE_LIST = ('{host_port}')"
    ).collect()

    session.sql(f"""
        ALTER APPLICATION SET SPECIFICATION otlp_egress_spec
            TYPE = EXTERNAL_ACCESS
            LABEL = 'OTLP gRPC Export'
            DESCRIPTION = 'Connect to the configured OTLP/gRPC collector endpoint for telemetry export'
            HOST_PORTS = ('{host_port}')
    """).collect()

    return json.dumps({"provisioned": True, "message": f"EAI provisioned for {host_port}"})
```

This is illustrative — the actual implementation must handle errors, validate inputs (no SQL injection via endpoint string — use strict allow-list validation before any dynamic SQL), and report whether the app spec changed in a way that requires consumer approval.

### Approval handling contract

The story should not require a fragile pre-check that perfectly predicts approval state before the first probe. The implementation is acceptable if it follows this contract:

1. Provisioning returns whether the requested `host:port` changed the app specification and therefore may require approval.
2. If the requested endpoint matches the already-approved endpoint, the UI proceeds directly to the gRPC probe.
3. If approval is still required, the user sees a dedicated approval message rather than a generic network failure.
4. The UI must not proceed as if the test passed until either:
   - provisioning indicates no approval is needed and the probe succeeds, or
   - the user approves the updated specification and retries successfully.

### Connection test SP: `app_public.test_otlp_connection`

**Call pattern (from Streamlit):**
```python
# Step 1: Provision EAI for the endpoint
prov_result = json.loads(session.call("app_public.provision_otlp_egress", endpoint))

# Step 2: Run the connection test
if prov_result.get("provisioned"):
    test_result = json.loads(session.call("app_public.test_otlp_connection", endpoint))
```

### Reference implementation: `grpc_test/otlp_grpc_probe.py`

The existing probe in `grpc_test/otlp_grpc_probe.py` implements the exact gRPC channel readiness pattern needed. Key code to adapt:

- `probe_approach_b()` — opens `grpc.secure_channel`, subscribes to connectivity state changes, waits for READY
- `grpc.ssl_channel_credentials(root_certificates=root_pem)` for TLS — in Story 2.1 use default certs (no custom PEM yet), so pass `grpc.ssl_channel_credentials()` without arguments to use the system trust store
- Timeout handling — the probe uses a configurable timeout (default 5s); the SP should use a similar timeout
- Diagnostic classification — the probe distinguishes: timeout (TRANSIENT_FAILURE), TLS handshake failure, DNS resolution failure, connection refused

The SP should mirror this pattern but simplified for the stored procedure context:
1. Parse endpoint → host:port
2. Create `ssl_channel_credentials()` (default CA bundle)
3. Open `secure_channel(target, credentials, options)`
4. `channel_ready_future(channel).result(timeout=timeout_seconds)`
5. Return structured result

### Endpoint format handling

Accept formats: `host`, `host:port`, `https://host`, `https://host:port`. Normalize to raw `host:port` for the gRPC probe and Snowflake network rule. Default port: `4317` if not specified. Reject `http://...` because this story is TLS-only, and reject obviously invalid formats (empty string, whitespace-only, path/query/fragment content, or disallowed characters).

**Critical: Input validation for SQL safety.** The endpoint string is used in SQL statements (`ALTER NETWORK RULE ... VALUE_LIST`). The provisioning SP must strictly validate the endpoint format before generating SQL — hostname characters `[A-Za-z0-9.-]`, optional `:port`, and optional leading `https://` only. Reject any input containing quotes, semicolons, comments, whitespace in the middle, slashes after the host, query strings, or other SQL metacharacters.

### Stored procedure DDL patterns

```sql
-- Provisioning SP — EXECUTE AS OWNER for ALTER NETWORK RULE / ALTER APPLICATION privileges
CREATE OR REPLACE PROCEDURE app_public.provision_otlp_egress(endpoint VARCHAR)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'provision_egress.provision_egress'
IMPORTS = ('/python/provision_egress.py')
EXECUTE AS OWNER;

-- Connection test SP — needs EAI for outbound gRPC
CREATE OR REPLACE PROCEDURE app_public.test_otlp_connection(endpoint VARCHAR)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'grpcio')
HANDLER = 'connection_test.test_connection'
IMPORTS = ('/python/connection_test.py')
EXTERNAL_ACCESS_INTEGRATIONS = (otlp_egress_eai)
EXECUTE AS OWNER;
```

### Splunk settings page layout (Figma-verified)

Verified against Figma node `4495:47505` and screenshot mockup. The page follows UX-DR4.
Figma reference: https://www.figma.com/design/0ieSwN62nwAvR9ybSlvPG5/Snowflake-Native-App-Design?node-id=4495-47505&m=dev

**Component tree:**

```
Splunk Settings (st.header — "Splunk Settings")
└── Export settings (st.tabs, single tab — "Export settings")
    ├── OTLP Export section header
    │   ├── st.subheader("OTLP Export")
    │   └── st.caption("Configure OTLP/gRPC export to your remote OpenTelemetry collector.")
    ├── OTLP endpoint card (st.container(border=True))
    │   ├── "OTLP endpoint (gRPC)" — st.markdown bold or label
    │   ├── st.caption("Maps to OTEL_EXPORTER_OTLP_ENDPOINT.")
    │   ├── st.text_input (placeholder: "host:port, e.g. collector.example.com:4317")
    │   ├── [Test connection] [Clear] — two st.button in st.columns, secondary style
    │   └── st.success("Connection successful") / st.error("...diagnostic...")
    │       OR st.warning("External access approval needed — ...") (AC 8)
    ├── Certificate card (st.container(border=True)) — PLACEHOLDER for Story 2.2
    │   ├── st.markdown("**Certificate (optional)**")
    │   ├── st.caption("Paste a PEM-encoded certificate if your collector uses a
    │   │   private/self-signed certificate. Leave empty to use the system trust
    │   │   store (OTEL_EXPORTER_OTLP_CERTIFICATE).")
    │   └── st.text_area (placeholder showing BEGIN/END CERTIFICATE block, disabled)
    │   └── st.info("Certificate validation will be available in the next update.")
    └── Footer (below a visual separator — st.divider or spacing)
        ├── Status line: "✓ Last test succeeded <time> to <endpoint>" (st.caption with green check emoji)
        ├── Bottom row (st.columns):
        │   ├── Left: "You have unsaved changes." (st.caption, gray)
        │   └── Right: [Reset to defaults] (secondary) + [Save settings] (primary, type="primary")
```

**Figma-confirmed visual details for Streamlit mapping:**

| Design element | Figma spec | Streamlit equivalent |
|---|---|---|
| Page title | "Splunk Settings", 24px medium | `st.header("Splunk Settings")` |
| Tab label | "Export settings", 14px medium, active underline | `st.tabs(["Export settings"])` |
| Section header | "OTLP Export", 18px semibold | `st.subheader("OTLP Export")` |
| Section caption | 14px regular, #717182 | `st.caption(...)` |
| Card containers | White bg, 1px border rgba(0,0,0,0.1), rounded-10px, 25px padding | `st.container(border=True)` |
| Input label | "OTLP endpoint (gRPC)", 14px medium | `st.markdown("**OTLP endpoint (gRPC)**")` |
| Help text | "Maps to OTEL_EXPORTER_OTLP_ENDPOINT.", 12px, #717182 | `st.caption(...)` on text_input or separate |
| Text input | #f3f3f5 bg, monospace font, rounded-8px | `st.text_input(...)` (Streamlit default styling) |
| Buttons | "Test connection", "Clear" — secondary (white bg, border) | `st.button("Test connection")`, `st.button("Clear")` |
| Success alert | Green: bg #f0fdf4, border #b9f8cf, check icon, text rgba(13,84,43,0.9) | `st.success("Connection successful")` |
| Error alert | Red error styling | `st.error("...diagnostic message...")` |
| Certificate header | "Certificate (optional)", 14px semibold | `st.markdown("**Certificate (optional)**")` |
| Certificate help | 12px, #717182, multi-line | `st.caption(...)` |
| Certificate textarea | #f3f3f5 bg, monospace, 192px height, PEM placeholder | `st.text_area(placeholder=..., height=192, disabled=True)` |
| Footer status | "✓" green + gray text + monospace endpoint | `st.caption(...)` with emoji |
| "You have unsaved changes." | 14px, #717182 | `st.caption("You have unsaved changes.")` |
| "Reset to defaults" | Secondary button (white bg, border) | `st.button("Reset to defaults")` |
| "Save settings" | Primary button (dark bg #030213, white text) | `st.button("Save settings", type="primary", disabled=...)` |

**Button layout pattern (Figma-confirmed):**
- "Test connection" and "Clear" are side-by-side in a row with 12px gap. Use `st.columns([auto, auto, expand])` or place two buttons in narrow columns.
- "Reset to defaults" and "Save settings" are right-aligned in the footer. Use `st.columns` with empty left spacer, then two button columns on the right.

**Key behavioral states (from mockup):**
1. **Empty state** — text input empty, "Test connection" and "Clear" shown, no alert, "Save settings" disabled
2. **After successful test** — green `st.success("Connection successful")`, "Save settings" enabled (primary style)
3. **After failed test** — red `st.error(diagnostic_message)`, "Save settings" remains disabled
4. **After "Clear"** — resets to empty state
5. **EAI approval needed** — yellow `st.warning` with instructions, "Save settings" remains disabled

### Session state keys

| Key | Type | Purpose |
|---|---|---|
| `otlp_endpoint` | str | Current endpoint value in the text input |
| `connection_test_result` | dict or None | `{success: bool, message: str}` from last test |
| `connection_test_running` | bool | True while provisioning + test SPs are executing |
| `endpoint_saved` | str or None | Last saved endpoint (from _internal.config, loaded on page init) |
| `eai_needs_approval` | bool | True if provisioning returned needs_approval |

The page should load any existing saved endpoint from `_internal.config` on first render (key: `otlp.endpoint`) if one already exists from a prior configuration. If a saved value exists, populate the text input. The save button remains disabled until a fresh connection test passes — even if the endpoint was previously saved, changing it requires re-testing. Do not add `_internal.config` write logic in this story.

### Consumer approval flow

When the provisioning SP updates `HOST_PORTS` in the app specification, the sequence number increments and requires consumer approval. The EAI is **not usable** until the consumer approves.

**Handling this in the UI:**
- If provisioning indicates approval is required, or the connection test SP fails with an approval-related diagnostic, show:
  ```
  st.warning("External access approval required. Please approve the 'OTLP gRPC Export' 
  specification in the app configuration panel (Snowsight → Data Products → Apps → 
  Splunk Observability → Manage Access).")
  ```
- The admin (who has ACCOUNTADMIN) can approve via Snowsight or SQL.

**For dev mode** (`snow app run -c dev`):
- The developer can approve via Snowsight or SQL using the current specification sequence number produced after provisioning. Do not hardcode the sequence number after the first approval; it increments when `HOST_PORTS` changes.
- Note: the first time the app spec is set during `snow app run`, approval may need to happen before the test works.

**Lifecycle callback (optional enhancement):**
The manifest supports `lifecycle_callbacks.after_specification_change`, which fires asynchronously after the consumer approves or declines a specification. If adopted later, use it to write durable approval state into app-owned tables (for example, storing the latest status of `otlp_egress_spec`) so the Streamlit page can show "approval received" on the next rerun. Do not rely on it to resume the in-flight button click or mutate live `st.session_state` directly. This is optional for the MVP — the simpler approach is to have the user retry after approving.

### What this story does NOT include (explicit scope boundaries)

- **Telemetry source selection, pack enablement, or onboarding task progression** → out of scope for this story, even if older planning artifacts still mention coupled setup flows
- **PEM certificate input and validation** → Story 2.2
- **Persisting config to `_internal.config`** → Story 2.3 (Save button exists in UI but actual write logic is in 2.3)
- **Getting Started hub and task tiles** → Story 2.3
- **Unsaved changes indicator logic** → Story 2.3 (the placeholder text can exist but functional tracking is 2.3)
- **`lifecycle_callbacks.after_specification_change`** callback in `manifest.yml` → optional future enhancement for durable post-approval status tracking, not required for the MVP retry flow

### Story 2.2 Certificate Handling Note

Story 2.2 should replace the provisional PEM text handling with the intended certificate flow:

- Validate pasted PEM content structurally and report actionable certificate diagnostics (for example: parse failure, expiration, unsupported chain, or trust issues).
- Keep certificate material out of config tables, logs, and procedure/query text; use the planned Snowflake Secret-backed approach instead of passing raw PEM values through routine calls.
- Re-test/save gating should treat certificate changes the same as endpoint changes: a previously successful connection test must be invalidated when certificate input changes, and save should remain disabled until the certificate path is validated and the connection test succeeds again.

### Planning artifact caveat

Some older planning artifacts still couple OTLP destination configuration or EAI work with telemetry source selection. Treat that coupling as stale for implementation purposes. For Story 2.1, the source of truth is:

- destination entry and connection test on `Splunk settings` only
- outbound access update only for the tested OTLP endpoint
- no Telemetry sources page changes
- no Getting Started completion logic
- no pack-selection side effects

### Regarding the Save button in this story

The "Save settings" button should exist in the UI and be disabled/enabled based on test results. However, the actual click handler that persists data to `_internal.config` is implemented in Story 2.3. For Story 2.1, clicking "Save settings" can show a `st.info("Save functionality coming in the next story.")` or simply do nothing beyond acknowledging the click. The important behavior is the **disabled state gating** based on test results.

### File changes summary

| File | Action | Purpose |
|---|---|---|
| `app/streamlit/pages/splunk_settings.py` | **Rewrite** | Full Splunk settings page with Export settings tab and connection test UI |
| `app/streamlit/main.py` | **Modify** | Layout/CSS for Snowflake embed (left-align, tab footer, button columns) |
| `app/python/endpoint_parse.py` | **Create** | Shared OTLP endpoint parsing/validation for SPs (and unit tests) |
| `app/python/provision_egress.py` | **Create** | Outbound access provisioning SP handler |
| `app/python/connection_test.py` | **Create** | gRPC connection test SP handler |
| `app/setup.sql` | **Modify** | Network rule, EAI, provisioning + connection-test SP DDL, grants |
| `app/manifest.yml` | No change needed | Already has `manifest_version: 2` and `CREATE EXTERNAL ACCESS INTEGRATION` privilege |
| `snowflake.yml` | **Modify** | Stage `app/python/*.py` handlers and `app/streamlit/pages/*.py` only (avoids staging `__pycache__` / `.pyc`) |
| `pyproject.toml` | **Modify** | `pythonpath` for local pytest imports of `app/python` |
| `tests/test_endpoint_parse.py` | **Create** | Unit tests for endpoint parser |
| `app/environment.yml` | No change needed | Already has `grpcio` |

### Implementation notes (as shipped)

Use this section when implementing Story 2.2 / 2.3.

- **Default OTLP gRPC port:** If the user omits `:port`, `app/python/endpoint_parse.py` defaults to **4317**. Document this in UI help text if users are confused.
- **`test_otlp_connection` signature:** Implemented as `test_otlp_connection(endpoint VARCHAR, cert_pem VARCHAR)` so optional PEM can be passed without changing the procedure name later; empty string uses default trust store in `connection_test.py`.
- **App specification DDL vs. provisioning:** `setup.sql` does **not** include a standalone `ALTER APPLICATION SET SPECIFICATION otlp_egress_spec ...` block. The **first successful run** of `provision_otlp_egress` applies the spec (and subsequent runs update `HOST_PORTS`). If you need an explicit initial spec in `setup.sql` for auditability, treat that as a follow-up change.
- **Packaging:** `snowflake.yml` maps `app/streamlit/pages/*.py` — do not broaden to `pages/*` or Python may stage `__pycache__` artifacts from local dev.
- **Save / test gating:** Changing the endpoint or certificate field clears the last test result (`on_change`); `Save settings` also requires `last_test_success_endpoint` to match the current endpoint string so a stale success cannot enable save after edits.
- **Review / code-review:** State-reset bug fixed during review; certificate material should move to Secret-backed flow in Story 2.2 (see **Story 2.2 Certificate Handling Note** above).

### Testing approach

**Local Streamlit preview (UI only):** Run `cd app && uv run streamlit run streamlit/main.py` to verify page layout, widget behavior, and session state management. The SP calls will fail locally — mock the results in a try/except block for preview mode.

**Deployed app test (full flow):**
1. `snow app run -c dev` to deploy
2. Open the app via `snow app open -c dev`
3. Navigate to Splunk settings
4. Enter `otelcol.israelcentral.cloudapp.azure.com:4317`
5. Click "Test connection"
6. If the app spec needs approval:
   - Approve the current `otlp_egress_spec` sequence number via Snowsight or SQL
   - Click "Test connection" again
7. Verify success result (gRPC channel reaches READY)
8. Enter an invalid endpoint (e.g. `nonexistent.example.com:4317`)
9. Click "Test connection" (this provisions for the new endpoint, may need re-approval)
10. Verify error result with diagnostic message

**SSH collector verification:** Use `ssh otelcol` + `sudo journalctl -u splunk-otel-collector -n 50` to confirm the collector received the test connection attempt (should appear as a new gRPC connection in collector logs).

### Python handler pattern for Snowflake SPs

```python
import grpc
import json

TIMEOUT_SECONDS = 10

def test_connection(session, endpoint: str) -> str:
    """Test OTLP/gRPC connectivity to the given endpoint."""
    host, port = _parse_endpoint(endpoint)
    target = f"{host}:{port}"
    
    credentials = grpc.ssl_channel_credentials()
    channel = grpc.secure_channel(target, credentials)
    try:
        future = grpc.channel_ready_future(channel)
        future.result(timeout=TIMEOUT_SECONDS)
        return json.dumps({"success": True, "message": "Connection successful"})
    except grpc.FutureTimeoutError:
        return json.dumps({
            "success": False,
            "message": "Connection timed out",
            "details": f"Could not reach {target} within {TIMEOUT_SECONDS}s"
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "message": _classify_error(e),
            "details": str(e)
        })
    finally:
        channel.close()
```

This is illustrative — the actual implementation should handle more error cases and provide richer diagnostics per the reference probe.

### Project Structure Notes

- `app/python/provision_egress.py` and `app/python/connection_test.py` are new files in the SP handler module directory. The architecture defines `app/python/` for SP handler modules. These are the first SPs created in the project.
- The `app/python/` directory does not exist yet — create it with an `__init__.py`.
- Verify that `snowflake.yml` maps `app/python/` to the package stage correctly (likely as `/python/` in the stage).

### References

- [Source: _bmad-output/planning-artifacts/architecture.md — OTLP Transport Security (D2), Exporter Topology (D3), Testing Strategy (D5)]
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md — Splunk settings Export settings tab, Connection Card component]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 2 Story 2.1 baseline acceptance criteria; ignore stale coupling to telemetry-source selection]
- [Source: _bmad-output/implementation-artifacts/epic-1-retro-2026-03-17.md — OTLP collector details, TLS cert setup, gRPC probe tooling, readiness assessment]
- [Source: grpc_test/grpc_connectivity_testing_nites.md — Core design decision, Approach A/B, deployment split]
- [Source: grpc_test/otlp_grpc_probe.py — Reference implementation for gRPC readiness probe]
- [Source: Figma node 4495:47505 — Splunk Settings / Export settings tab, verified layout and component specs](https://www.figma.com/design/0ieSwN62nwAvR9ybSlvPG5/Snowflake-Native-App-Design?node-id=4495-47505&m=dev)
- [Snowflake: Request EAIs with app specifications](https://docs.snowflake.com/en/developer-guide/native-apps/requesting-app-specs-eai) — Native App EAI pattern
- [Snowflake: ALTER NETWORK RULE](https://docs.snowflake.com/en/sql-reference/sql/alter-network-rule) — dynamic VALUE_LIST updates
- [Snowflake: ALTER APPLICATION SET SPECIFICATION](https://docs.snowflake.com/en/sql-reference/sql/alter-application-set-app-spec) — app spec for consumer approval
- [Snowflake: CREATE EXTERNAL ACCESS INTEGRATION](https://docs.snowflake.com/en/sql-reference/sql/create-external-access-integration) — EAI DDL reference
- [Snowflake: CREATE NETWORK RULE](https://docs.snowflake.com/en/sql-reference/sql/create-network-rule) — TYPE=HOST_PORT, MODE=EGRESS

## Dev Agent Record

### Agent Model Used

Cursor / Composer (implementation + review cycles).

### Debug Log References

N/A — manual verification in Snowsight after `snow app run --connection dev`.

### Completion Notes List

- Splunk Settings → Export settings: OTLP card, provisional certificate card (basic PEM marker check only), footer with Save disabled until a successful connection test on the **current** endpoint.
- Stored procedures: `app_public.provision_otlp_egress`, `app_public.test_otlp_connection` with `EXTERNAL_ACCESS_INTEGRATIONS = (otlp_egress_eai)`; shared `endpoint_parse` module.
- Consumer must approve external-access app specification when `HOST_PORTS` changes; UI shows `st.warning` with Snowsight path when provisioning reports approval needed.
- `snowflake.yml` stages Streamlit pages as `*.py` only to avoid uploading `__pycache__` / `.pyc` from local runs.

### File List

- `app/streamlit/pages/splunk_settings.py`
- `app/streamlit/main.py`
- `app/python/endpoint_parse.py`
- `app/python/provision_egress.py`
- `app/python/connection_test.py`
- `app/setup.sql`
- `snowflake.yml`
- `pyproject.toml`
- `tests/test_endpoint_parse.py`
- `_bmad-output/implementation-artifacts/2-1-otlp-endpoint-and-connection-test.md` (this story)

### Senior Developer Review (AI)

- **Outcome:** Approve — story acceptance criteria met; state-reset/save gating fixed before mark-done.
- **Follow-ups for Story 2.2:** Replace provisional PEM-in-proc pattern with Snowflake Secret + validation UX; align `test_otlp_connection` inputs with secret references.
- **Follow-ups for Story 2.3:** Wire Save to `_internal.config`; functional unsaved-changes tracking per UX spec.

---

## Change Log

| Date | Change |
|------|--------|
| 2026-03-23 | Story marked **done**; tasks checked off; sprint status synced; Dev Agent Record and implementation handoff notes added. |
