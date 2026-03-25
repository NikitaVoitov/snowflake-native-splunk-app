"""PEM certificate validation stored procedure handler (Story 2.2).

Validates a PEM-encoded X.509 certificate: parses the certificate, checks the
validity window (not_before / not_after against UTC now), and returns a JSON
result.  Raw PEM material is never logged or persisted.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from cryptography import x509
from snowflake.snowpark import Session

_PEM_HEADER = b"-----BEGIN CERTIFICATE-----"
_PEM_FOOTER = b"-----END CERTIFICATE-----"
_MAX_PEM_SIZE = 65_536  # 64 KB -- generous for any real cert chain


def _normalize_pem(raw: str) -> bytes:
    """Normalize line endings and strip surrounding whitespace."""
    return raw.strip().replace("\r\n", "\n").encode("utf-8")


def _pem_fingerprint(pem_bytes: bytes) -> str:
    """SHA-256 fingerprint of the normalized PEM bytes."""
    return hashlib.sha256(pem_bytes).hexdigest()


def _extract_first_pem_block(pem_bytes: bytes) -> bytes:
    """Extract the first PEM certificate block from *pem_bytes*.

    If more than one block is present the first is returned and
    ``extra_blocks`` is set in the caller's result.
    """
    start = pem_bytes.find(_PEM_HEADER)
    if start == -1:
        raise ValueError("No BEGIN CERTIFICATE marker found")
    end = pem_bytes.find(_PEM_FOOTER, start)
    if end == -1:
        raise ValueError("No END CERTIFICATE marker found")
    return pem_bytes[start : end + len(_PEM_FOOTER)]


def validate_pem(_session: Session, cert_pem: str) -> str:
    """Validate a PEM certificate and return a JSON result.

    Returns JSON with keys:
        ok            - bool, True when the certificate is currently valid
        message       - human-readable summary
        expires_on    - ISO-8601 date string (YYYY-MM-DD) or null
        subject       - single-line subject string or null
        pem_fingerprint - SHA-256 hex of the normalized PEM bytes
        error_code    - short error code or null
    """
    if not cert_pem or not cert_pem.strip():
        return json.dumps({
            "ok": False,
            "message": "Empty certificate",
            "expires_on": None,
            "subject": None,
            "pem_fingerprint": None,
            "error_code": "EMPTY",
        })

    if len(cert_pem) > _MAX_PEM_SIZE:
        return json.dumps({
            "ok": False,
            "message": f"Input exceeds maximum size ({_MAX_PEM_SIZE} bytes).",
            "expires_on": None,
            "subject": None,
            "pem_fingerprint": None,
            "error_code": "TOO_LARGE",
        })

    pem_bytes = _normalize_pem(cert_pem)
    fingerprint = _pem_fingerprint(pem_bytes)

    header_count = pem_bytes.count(_PEM_HEADER)
    if header_count == 0:
        return json.dumps({
            "ok": False,
            "message": "Missing BEGIN CERTIFICATE marker — paste the full PEM including markers.",
            "expires_on": None,
            "subject": None,
            "pem_fingerprint": fingerprint,
            "error_code": "NO_HEADER",
        })

    multi_block = header_count > 1

    try:
        first_block = _extract_first_pem_block(pem_bytes)
    except ValueError as exc:
        return json.dumps({
            "ok": False,
            "message": str(exc),
            "expires_on": None,
            "subject": None,
            "pem_fingerprint": fingerprint,
            "error_code": "MALFORMED_PEM",
        })

    try:
        cert = x509.load_pem_x509_certificate(first_block)
    except (ValueError, TypeError, x509.InvalidVersion):
        return json.dumps({
            "ok": False,
            "message": "Failed to parse certificate — verify the PEM content is a valid X.509 certificate.",
            "expires_on": None,
            "subject": None,
            "pem_fingerprint": fingerprint,
            "error_code": "PARSE_ERROR",
        })

    now = datetime.now(UTC)
    not_before = cert.not_valid_before_utc
    not_after = cert.not_valid_after_utc
    expires_on = not_after.strftime("%Y-%m-%d")
    subject = cert.subject.rfc4514_string()

    if now < not_before:
        return json.dumps({
            "ok": False,
            "message": f"Certificate is not yet valid (valid from {not_before.strftime('%Y-%m-%d')}).",
            "expires_on": expires_on,
            "subject": subject,
            "pem_fingerprint": fingerprint,
            "error_code": "NOT_YET_VALID",
        })

    if now > not_after:
        return json.dumps({
            "ok": False,
            "message": f"Certificate expired on {expires_on}.",
            "expires_on": expires_on,
            "subject": subject,
            "pem_fingerprint": fingerprint,
            "error_code": "EXPIRED",
        })

    msg = f"Valid certificate (expires {expires_on})"
    if multi_block:
        msg += " — note: only the first certificate in the chain was validated"

    return json.dumps({
        "ok": True,
        "message": msg,
        "expires_on": expires_on,
        "subject": subject,
        "pem_fingerprint": fingerprint,
        "error_code": None,
    })
