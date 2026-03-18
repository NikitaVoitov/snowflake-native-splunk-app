# OTLP gRPC Connectivity & PEM Validation Design for Snowflake Native App

## 1. Purpose

This document captures the agreed design, capabilities, tradeoffs, and possible approaches for validating OTLP/gRPC endpoint connectivity and user-supplied PEM trust material from a Snowflake Native App.  
The intended execution environment is a Python stored procedure running in Snowflake, with endpoint details and PEM text entered by the user through a Streamlit app in the same Native App.

The goal is to let an implementation agent choose the best coding path without prescribing exact code.

---

## 2. Confirmed findings

- `grpcio` and `cryptography` are available in Snowflake’s supported Python package ecosystem for handler runtimes according to package availability research already performed by the team, and Snowflake documents the `PACKAGES` view as the source for available Python packages and versions. [web:142]
- Streamlit in Snowflake does not support `.so` files, which is important because `grpcio` includes native extensions. [web:137]
- Because of that limitation, the real gRPC connectivity probe should not run inside the Streamlit process. [web:137]
- Snowflake supports outbound connectivity for Python handlers by using external access integrations and associated network rules. [web:143][web:149]

### Implication

The correct deployment split is:

- Streamlit app: collects user input.
- Python stored procedure: performs PEM validation and live OTLP/gRPC connectivity probing.
- Snowflake external access integration: permits outbound connection to the target OTLP endpoint.

---

## 3. Problem statement

We need to verify whether a user-configured OTLP endpoint can accept a real incoming gRPC/TLS client connection, using the same trust material the user provides, **without sending actual telemetry payloads**.

The verification should answer practical questions such as:

- Can the endpoint be reached from Snowflake?
- Does TLS handshake succeed?
- Is the server certificate trusted by the user-supplied PEM?
- Does the gRPC channel become ready?
- Can failures be classified into useful buckets for user diagnostics?

---

## 4. Core design decision

## Preferred design

Use `grpcio` for the actual live OTLP endpoint connectivity check, and use `cryptography` for offline PEM/X.509 parsing and sanity checks. [web:2][web:79]

### Why `grpcio` is preferred for the probe

- Python gRPC exposes `grpc.secure_channel(...)` for creating a TLS-backed client channel and `grpc.ssl_channel_credentials(...)` for supplying PEM-encoded trust material. [web:2]
- Python gRPC exposes `grpc.channel_ready_future(channel)` as a direct way to wait until channel connectivity becomes `READY`. [web:2]
- Python gRPC also exposes channel connectivity state subscription so the implementation can observe state transitions such as `IDLE`, `CONNECTING`, `READY`, `TRANSIENT_FAILURE`, and `SHUTDOWN`, and can force an immediate connect attempt with `try_to_connect=True`. [web:2]
- This maps exactly to the requirement: test real gRPC/TLS connectivity without needing to send telemetry data. [web:2]

### Why the OTLP exporter itself is not the preferred probe primitive

- The Python OTLP exporter is designed around export operations such as `export(...)` and lifecycle operations such as `shutdown()`, rather than a public “connect-only” readiness probe API. [web:24]
- Using the exporter itself as the probe tends to blur transport validation with actual OTLP request behavior, while the requirement here is specifically connection establishment. [web:24][web:2]
- The exporter configuration still matters and should be mirrored by the probe, especially endpoint, TLS settings, timeout, headers, and channel options, so that the probe reflects the real runtime path as closely as possible. [web:24][web:2]

### Decision summary

- Use `grpcio` as the live transport probe.
- Use the same resolved endpoint and TLS-related configuration that the OTLP exporter will later use.
- Use the OTLP exporter only for real telemetry flow after connectivity precheck succeeds.

---

## 5. Candidate approaches

## Approach A — Pure gRPC/TLS readiness probe

### Description

Open a secure gRPC channel to the OTLP endpoint using the user-supplied PEM as `root_certificates`, then wait for the channel to reach `READY`. [web:2]

### What it verifies

- DNS / routing / TCP reachability as seen by gRPC. [web:59]
- TLS handshake success to the remote peer. [web:59][web:2]
- Trust decision using the supplied PEM through the TLS stack. [web:2]
- gRPC channel readiness. [web:2]

### What it does not verify

- That telemetry export succeeds end-to-end.
- That the OTLP service implementation is semantically healthy.
- That authorization headers or payload acceptance are correct.

### When to use

Use this as the baseline probe because it is the closest fit to “real OTLP/gRPC connectivity without actual telemetry transfer.”

---

## Approach B — Readiness probe with connectivity-state diagnostics

### Description

Use the same secure channel as in Approach A, but also subscribe to channel connectivity transitions and record timestamped state changes. [web:2][web:59]

### What it adds

- Visibility into state progression such as `IDLE -> CONNECTING -> READY` on success. [web:2]
- Visibility into repeated failure cycles such as `CONNECTING -> TRANSIENT_FAILURE`. [web:59][web:2]
- Better operator-facing diagnostics and richer logs for troubleshooting. [web:2]

### Why this is likely the best overall approach

This approach gives the same pass/fail behavior as Approach A while providing materially better diagnostics for support and user feedback. [web:2][web:59]

---

## Approach C — Minimal application-level verification

### Description

After channel readiness succeeds, optionally perform a tiny application-level action using the real OTLP stack to verify more than transport.

### Caveat

This is **not** a pure connectivity-only probe and should be treated as a separate, stronger verification mode.

### Possible uses

- Optional advanced mode for environments that want stronger confidence than transport-only checks.
- A later phase after transport readiness succeeds.

### Why it is not the primary design

The requirement specifically avoids actual telemetry transfer, so this should be considered optional rather than default.

---

## 6. Health RPC discussion

A standard gRPC health-check RPC is a valid concept in general gRPC systems, but it should **not** be assumed to exist on the OpenTelemetry Collector OTLP/gRPC endpoint.  
Earlier review of Collector health functionality showed that the Collector’s documented `health_check` extension is HTTP-oriented rather than a guaranteed gRPC health service on the OTLP port. [page:2][page:3]

### Decision

- Do not rely on gRPC health-check RPC as the default OTLP endpoint probe.
- Do not rely on Collector HTTP health URL for this feature, because the explicit requirement is to validate real gRPC/TLS connectivity to the OTLP endpoint itself.
- Prefer the secure-channel readiness probe instead. [web:2]

---

## 7. PEM handling strategy

## Goal

Validate that the user-supplied PEM text is structurally acceptable and suitable for use as TLS trust material, then use it in the actual live gRPC/TLS connection.

## Library choice

Use `cryptography` for offline certificate parsing and metadata inspection because it provides the X.509 parsing APIs needed for PEM loading, validity checks, and extension inspection. [web:79]

## What to validate offline

### Basic parse checks

- The text is valid PEM.
- At least one certificate is present.
- Multiple adjacent certificates are handled correctly if the user pastes a chain or bundle. [web:79]

### Time validity

Check that each relevant certificate is within its validity window using the certificate validity fields exposed by the X.509 API. [web:79]

### If the PEM is intended as a CA trust anchor

Check that the certificate appears suitable for CA use, especially:

- `BasicConstraints` indicates `CA=TRUE`. [web:87]
- `KeyUsage`, when present, is compatible with certificate-signing usage such as `keyCertSign`. [web:87]

### Useful metadata to capture for diagnostics

- Subject.
- Issuer.
- Fingerprint.
- Serial number.
- Validity window.
- Subject Alternative Name presence, if relevant to operator troubleshooting. [web:79]

## What not to implement manually

Do **not** attempt to reimplement full PKIX trust validation in application code by manually checking signatures or issuer relationships alone, because the X.509 reference explicitly warns that direct signature verification performs only limited checks and does not amount to complete validation. [web:79]

## Runtime trust decision

The final trust decision must be made by the actual TLS connection established by `grpcio`, using the user PEM as `root_certificates`. [web:2]

---

## 8. Hostname / endpoint identity verification

A valid trust chain alone is not enough; the peer identity must also match the intended server name.  
Python’s TLS facilities include hostname-matching behavior intended to fail when the certificate name does not match the expected host. [web:100][web:93]

### Design guidance

- Let the TLS stack perform peer identity validation during the live gRPC/TLS connection.
- Avoid implementing hostname matching manually unless there is a very specific advanced requirement.
- Treat “certificate trusted but hostname mismatch” as a distinct diagnostic outcome when possible. [web:100][web:93]

---

## 9. Why `grpcio` is still the right runtime probe in Snowflake

Even though the application will later use the Python OTLP exporter to send telemetry, `grpcio` remains the better tool for the connection precheck because it exposes the exact low-level signal required: secure channel creation plus readiness detection. [web:2]

The OTLP exporter is focused on export operations and exporter behavior, while the probe needs to answer a narrower question: “did the gRPC/TLS channel become ready using the supplied endpoint and trust material?” [web:24][web:2]

### Design consequence

The implementation should:

- Derive probe settings from the same source of truth as the exporter configuration.
- Keep the connectivity probe and telemetry export as separate concerns.
- Ensure both use matching endpoint and TLS parameters to avoid false positives.

---

## 10. Error classification expectations

## What can be classified well

### Successful connection

If the channel reaches `READY`, then the network path, TLS handshake, and gRPC channel establishment succeeded. [web:59][web:2]

### Fast rejection

A fast failure such as “connection refused” generally suggests the host is reachable but nothing is listening on that port or an intermediary is actively rejecting the connection. [web:72]

### TLS-specific failure

If the secure connection fails after a TCP path exists, that indicates a TLS problem such as trust failure, certificate mismatch, or protocol negotiation issue. [web:59][web:2]

## What cannot always be distinguished conclusively

A silent firewall drop, blackholed route, unreachable path, or similar timeout-style failures often cannot be distinguished from one another by gRPC state transitions alone, because gRPC connectivity states intentionally abstract across name resolution, TCP connection attempts, and TLS handshaking. [web:59][web:72]

Likewise, “transparent firewall silently dropping packets” and “remote path unavailable” may both present as repeated `CONNECTING` / `TRANSIENT_FAILURE` followed by deadline expiry. [web:59][web:72]

### Recommended classification buckets

Return operator-friendly buckets such as:

- `READY`
- `PORT_REJECTED_OR_NO_LISTENER`
- `TLS_VALIDATION_FAILED`
- `CONNECTIVITY_TIMEOUT_OR_SILENT_DROP`
- `UNKNOWN_CONNECTIVITY_FAILURE`

Each bucket should include raw gRPC details and recorded state transitions where available. [web:2][web:59]

---

## 11. Snowflake Native App architecture

## Components

### Streamlit app

Responsibilities:

- Collect OTLP endpoint details from the user.
- Collect PEM text from the user.
- Optionally collect timeout and advanced TLS options.
- Trigger the stored procedure.
- Render returned diagnostics.

### Python stored procedure

Responsibilities:

- Receive endpoint and PEM input.
- Parse and validate the PEM offline using `cryptography`. [web:79]
- Perform the live gRPC/TLS readiness probe using `grpcio`. [web:2]
- Record connectivity state transitions for diagnostics. [web:2]
- Return structured results.

### Snowflake network configuration

Responsibilities:

- External access integration must permit outbound access to the OTLP endpoint. [web:143][web:149]
- Network rules must match the target host and port. [web:143][web:149]

## Important placement rule

Because Streamlit in Snowflake does not support `.so` files, the gRPC-native part of the design must execute in the stored procedure runtime rather than the Streamlit runtime. [web:137]

---

## 12. Expected inputs

The implementation agent should assume support for at least:

- OTLP endpoint host / port or full authority string.
- Whether TLS is enabled.
- User-supplied PEM text used as trust material.
- Timeout.
- Optional diagnostic verbosity level.

Possible future inputs:

- Client certificate and private key for mTLS.
- Custom authority / server-name override if needed for advanced deployments.
- Additional exporter-aligned channel options.

---

## 13. Expected outputs

The stored procedure should return structured diagnostics rather than only a boolean.

### Recommended output fields

- Overall status.
- Classification bucket.
- Human-readable message.
- Final connectivity state.
- Ordered state transitions with timestamps. [web:2][web:59]
- Whether PEM parse succeeded.
- Certificate metadata summary.
- Timeout used.
- Raw error category and raw error text if available.
- Whether the result is transport-only or stronger-than-transport validation.

### Why structured output matters

This allows the Streamlit UI to present a clear diagnosis to the user and allows downstream automation to make decisions without parsing free text.

---

## 14. Security and UX considerations

- Treat user-supplied PEM text as sensitive input and avoid unnecessary persistence.
- Do not log full PEM bodies.
- Log safe certificate metadata instead, such as subject, issuer, fingerprint, and expiration date. [web:79]
- Keep the probe transport-only by default to avoid surprising users with unintended telemetry generation.
- Make any stronger verification mode explicit and opt-in.

---

## 15. Non-goals

The default probe is **not** intended to prove:

- Telemetry is accepted end-to-end.
- Authorization headers are correct.
- Collector pipelines are fully configured.
- OTLP traces / metrics / logs services are all semantically operational.

Those are separate verification problems from “real TLS gRPC connectivity exists.”

---

## 16. Recommended decision path for the coding agent

1. Implement the feature in a Python stored procedure, not in Streamlit. [web:137]
2. Use `cryptography` for PEM/X.509 parsing and offline sanity checks. [web:79]
3. Use `grpcio` secure channel readiness as the default live probe. [web:2]
4. Add connectivity-state subscription for richer diagnostics. [web:2][web:59]
5. Return structured diagnostics with classification buckets rather than a single success/fail flag.
6. Ensure the procedure uses the same endpoint and TLS-related configuration source that the actual OTLP exporter will use. [web:24][web:2]
7. Require external access integration and matching network rules for the OTLP target. [web:143][web:149]

---

## 17. Final recommendation

The strongest design for this Snowflake Native App is:

- Streamlit collects OTLP endpoint details and PEM text.
- A Python stored procedure validates the PEM offline using `cryptography`.
- The same procedure performs a real TLS gRPC channel probe to the OTLP endpoint using `grpcio`.
- The procedure records channel state transitions and returns structured diagnostics.
- The actual OTLP exporter remains separate and uses the same resolved connection configuration when real telemetry export begins. [web:79][web:2][web:24][web:137][web:143][web:149]

This design best satisfies the requirement of validating **real OTLP/gRPC TLS connectivity without telemetry transfer**, while remaining compatible with Snowflake Native App constraints and giving useful diagnostics when failures occur. [web:2][web:59][web:137]
