#!/usr/bin/env bash
# Generate self-signed CA and server cert for otelcol.israelcentral.cloudapp.azure.com
# For testing TLS connectivity only — not for production.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

HOST="otelcol.israelcentral.cloudapp.azure.com"
VALIDITY_DAYS=365

echo "Generating CA..."
openssl genrsa -out ca.key 2048
openssl req -new -x509 -days "$VALIDITY_DAYS" -key ca.key -out ca.crt \
  -subj "/CN=OTLP Test CA" -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=keyCertSign,cRLSign"

echo "Generating server key and CSR..."
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr -config server.cnf

echo "Signing server certificate..."
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days "$VALIDITY_DAYS" -extensions v3_req -extfile server.cnf

rm -f server.csr
chmod 600 ca.key server.key
chmod 644 ca.crt server.crt

echo ""
echo "Done. Created:"
echo "  ca.crt     — CA certificate (use as --pem for probe)"
echo "  ca.key     — CA private key (keep secret)"
echo "  server.crt — Server certificate for collector"
echo "  server.key — Server private key for collector"
echo ""
echo "Verify SAN:"
openssl x509 -in server.crt -noout -text | grep -A1 "Subject Alternative Name"
