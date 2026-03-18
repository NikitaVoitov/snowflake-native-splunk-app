# OTLP Collector TLS Setup for Testing

Creates a self-signed CA and server certificate for `otelcol.israelcentral.cloudapp.azure.com` so you can test TLS connectivity from the Python probe.

## Prerequisites

- `openssl` (macOS/Linux)
- SSH access to the collector host (`otelcol`)

## Quick Setup

### 1. Generate certificates (run locally)

```bash
cd grpc_test/tls-setup
./generate-certs.sh
```

This creates:

- `ca.crt` — CA certificate (use as `--pem` for the probe)
- `ca.key` — CA private key (keep secret)
- `server.crt` — Server certificate for the collector
- `server.key` — Server private key for the collector

### 2. Deploy to collector and enable TLS

```bash
# Copy certs to collector
scp server.crt server.key otelcol:/tmp/

# SSH and configure
ssh otelcol
sudo mkdir -p /etc/otel/collector/tls
sudo mv /tmp/server.crt /tmp/server.key /etc/otel/collector/tls/
sudo chown splunk-otel-collector:splunk-otel-collector /etc/otel/collector/tls/*.crt /etc/otel/collector/tls/*.key
```

### 3. Edit collector config

Edit `/etc/otel/collector/agent_config.yaml` and add TLS under the OTLP gRPC receiver:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: "${SPLUNK_LISTEN_INTERFACE}:4317"
        tls:
          cert_file: /etc/otel/collector/tls/server.crt
          key_file: /etc/otel/collector/tls/server.key
      http:
        endpoint: "${SPLUNK_LISTEN_INTERFACE}:4318"
```

### 4. Restart collector

```bash
ssh otelcol "sudo systemctl restart splunk-otel-collector"
```

### 5. Test with the probe

```bash
# From project root
uv run python grpc_test/otlp_grpc_probe.py otelcol.israelcentral.cloudapp.azure.com:4317 \
  --tls --pem grpc_test/tls-setup/ca.crt --approach b -v
```

## Verify TLS is active

```bash
# Should complete TLS handshake (no "wrong version number")
openssl s_client -connect otelcol.israelcentral.cloudapp.azure.com:4317 -CAfile grpc_test/tls-setup/ca.crt -brief
```

## Rollback to plaintext

Remove the `tls` block from the OTLP receiver config and restart:

```bash
ssh otelcol "sudo systemctl restart splunk-otel-collector"
```
