#!/usr/bin/env python3
"""
PEM validation for TLS trust material — Section 7 of grpc_connectivity_testing_nites.md.

Validates user-supplied PEM text for use as TLS root_certificates in gRPC/TLS connections.
Uses cryptography for offline parsing; does NOT perform PKIX trust validation.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.x509.oid import ExtensionOID


@dataclass(slots=True)
class CertMetadata:
    """Metadata for a single certificate."""

    subject: str
    issuer: str
    serial_number: int
    fingerprint_sha256: str
    not_valid_before: str
    not_valid_after: str
    is_ca: bool
    key_usage: str | None
    san_present: bool
    san_dns_names: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ValidationResult:
    """Result of PEM validation."""

    valid: bool
    message: str
    cert_count: int
    certs: list[CertMetadata] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _format_name(name: x509.Name) -> str:
    """Format X509 name for display."""
    return name.rfc4514_string()


def _extract_cert_metadata(cert: x509.Certificate) -> CertMetadata:
    """Extract metadata from a certificate."""
    fingerprint = cert.fingerprint(SHA256())
    fp_hex = fingerprint.hex()

    is_ca = False
    try:
        bc = cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
        is_ca = bc.value.ca
    except x509.ExtensionNotFound:
        pass

    key_usage: str | None = None
    try:
        ku = cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE)
        usages = []
        if ku.value.key_cert_sign:
            usages.append("keyCertSign")
        if ku.value.crl_sign:
            usages.append("crlSign")
        if ku.value.digital_signature:
            usages.append("digitalSignature")
        if ku.value.key_encipherment:
            usages.append("keyEncipherment")
        if usages:
            key_usage = ", ".join(usages)
    except x509.ExtensionNotFound:
        pass

    san_dns_names: list[str] = []
    try:
        san = cert.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        san_dns_names = list(san.value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        pass

    return CertMetadata(
        subject=_format_name(cert.subject),
        issuer=_format_name(cert.issuer),
        serial_number=cert.serial_number,
        fingerprint_sha256=fp_hex,
        not_valid_before=cert.not_valid_before_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        not_valid_after=cert.not_valid_after_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        is_ca=is_ca,
        key_usage=key_usage,
        san_present=len(san_dns_names) > 0,
        san_dns_names=san_dns_names,
    )


def validate_pem(
    pem_data: str | bytes,
    *,
    expect_ca: bool = True,
    check_time_validity: bool = True,
) -> ValidationResult:
    """
    Validate PEM-encoded certificate(s) per Section 7 PEM handling strategy.

    Args:
        pem_data: PEM text or bytes (file content or pasted string).
        expect_ca: If True, first cert should have BasicConstraints CA=TRUE.
        check_time_validity: If True, verify certs are within validity window.

    Returns:
        ValidationResult with valid flag, metadata, and any errors/warnings.
    """
    errors: list[str] = []
    warnings: list[str] = []

    pem_bytes = pem_data.encode("utf-8") if isinstance(pem_data, str) else pem_data

    # Basic parse checks
    try:
        certs = x509.load_pem_x509_certificates(pem_bytes)
    except Exception as e:
        return ValidationResult(
            valid=False,
            message="Invalid PEM: failed to parse",
            cert_count=0,
            errors=[str(e)],
        )

    if not certs:
        return ValidationResult(
            valid=False,
            message="No certificate(s) found in PEM",
            cert_count=0,
            errors=["PEM must contain at least one certificate"],
        )

    now = datetime.now(UTC)
    cert_metadatas: list[CertMetadata] = []

    for i, cert in enumerate(certs):
        meta = _extract_cert_metadata(cert)
        cert_metadatas.append(meta)

        # Time validity
        if check_time_validity:
            if cert.not_valid_before_utc > now:
                errors.append(
                    f"Cert {i + 1}: not yet valid (valid from {meta.not_valid_before})"
                )
            if cert.not_valid_after_utc < now:
                errors.append(f"Cert {i + 1}: expired (expired {meta.not_valid_after})")

        # CA trust anchor checks (for first cert when expect_ca)
        if expect_ca and i == 0:
            if not meta.is_ca:
                errors.append(
                    "First certificate is not a CA (BasicConstraints CA=TRUE required for trust anchor)"
                )
            if meta.key_usage and "keyCertSign" not in meta.key_usage:
                warnings.append(
                    "First certificate KeyUsage does not include keyCertSign "
                    "(may still be acceptable for some CAs)"
                )

    valid = len(errors) == 0
    message = "PEM valid" if valid else "; ".join(errors[:3])

    return ValidationResult(
        valid=valid,
        message=message,
        cert_count=len(certs),
        certs=cert_metadatas,
        errors=errors,
        warnings=warnings,
    )


def validate_pem_file(
    path: Path,
    *,
    expect_ca: bool = True,
    check_time_validity: bool = True,
) -> ValidationResult:
    """Load PEM from file and validate."""
    try:
        pem_bytes = path.read_bytes()
    except OSError as e:
        return ValidationResult(
            valid=False,
            message=f"Cannot read file: {e}",
            cert_count=0,
            errors=[str(e)],
        )
    return validate_pem(
        pem_bytes,
        expect_ca=expect_ca,
        check_time_validity=check_time_validity,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate PEM certificate(s) for TLS trust material (Section 7)",
    )
    parser.add_argument(
        "pem",
        type=Path,
        help="Path to PEM file (or - for stdin)",
    )
    parser.add_argument(
        "--no-ca-check",
        action="store_true",
        help="Do not require first cert to be a CA (e.g. for server cert)",
    )
    parser.add_argument(
        "--no-time-check",
        action="store_true",
        help="Skip validity window check",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print full certificate metadata",
    )
    args = parser.parse_args()

    expect_ca = not args.no_ca_check
    check_time_validity = not args.no_time_check

    if args.pem == Path("-"):
        pem_data = sys.stdin.buffer.read()
        result = validate_pem(
            pem_data,
            expect_ca=expect_ca,
            check_time_validity=check_time_validity,
        )
    else:
        if not args.pem.exists():
            print(f"Error: file not found: {args.pem}", file=sys.stderr)
            return 1
        result = validate_pem_file(
            args.pem,
            expect_ca=expect_ca,
            check_time_validity=check_time_validity,
        )

    if args.verbose:
        print("--- PEM validation result ---")
        print(f"Valid: {result.valid}")
        print(f"Message: {result.message}")
        print(f"Certificate count: {result.cert_count}")
        if result.errors:
            print("Errors:")
            for e in result.errors:
                print(f"  - {e}")
        if result.warnings:
            print("Warnings:")
            for w in result.warnings:
                print(f"  - {w}")
        for i, c in enumerate(result.certs):
            print(f"\nCertificate {i + 1}:")
            print(f"  Subject: {c.subject}")
            print(f"  Issuer: {c.issuer}")
            print(f"  Serial: {c.serial_number}")
            print(f"  Fingerprint (SHA-256): {c.fingerprint_sha256}")
            print(f"  Valid: {c.not_valid_before} — {c.not_valid_after}")
            print(f"  Is CA: {c.is_ca}")
            if c.key_usage:
                print(f"  KeyUsage: {c.key_usage}")
            if c.san_present:
                print(f"  SAN (DNS): {c.san_dns_names}")
    else:
        status = "OK" if result.valid else "FAILED"
        print(f"{status}: {result.message}")
        if result.errors:
            for e in result.errors:
                print(f"  Error: {e}")

    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
