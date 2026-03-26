"""Unit tests for PEM certificate validation (Story 2.2).

Uses the project's existing test fixtures:
  - grpc_test/tls-setup/ca.crt       — valid self-signed CA, CN=OTLP Test CA, expires 2027-03-18
  - grpc_test/tls-setup/wrong_ca.crt — expired cert, CN=WrongCA, expired 2026-03-19
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cert_validate import (
    _MAX_PEM_SIZE,
    _extract_first_pem_block,
    _normalize_pem,
    _pem_fingerprint,
    validate_pem,
)


FIXTURES = Path(__file__).resolve().parent.parent / "grpc_test" / "tls-setup"
VALID_PEM = (FIXTURES / "ca.crt").read_text()
EXPIRED_PEM = (FIXTURES / "wrong_ca.crt").read_text()

_mock_session = MagicMock()


def _parse(json_str: str) -> dict:
    return json.loads(json_str)


# ── Normalization & fingerprint ──────────────────────────────────


class TestNormalization:
    def test_crlf_normalized(self) -> None:
        raw = "-----BEGIN CERTIFICATE-----\r\nAAA\r\n-----END CERTIFICATE-----"
        assert b"\r\n" not in _normalize_pem(raw)

    def test_fingerprint_stable(self) -> None:
        fp1 = _pem_fingerprint(VALID_PEM.encode())
        fp2 = _pem_fingerprint(VALID_PEM.encode())
        assert fp1 == fp2
        assert len(fp1) == 64  # SHA-256 hex

    def test_fingerprint_differs_between_certs(self) -> None:
        assert _pem_fingerprint(VALID_PEM.encode()) != _pem_fingerprint(EXPIRED_PEM.encode())


# ── PEM block extraction ─────────────────────────────────────────


class TestPEMExtraction:
    def test_extracts_first_block(self) -> None:
        block = _extract_first_pem_block(VALID_PEM.encode())
        assert block.startswith(b"-----BEGIN CERTIFICATE-----")
        assert block.endswith(b"-----END CERTIFICATE-----")

    def test_raises_on_missing_header(self) -> None:
        with pytest.raises(ValueError, match="BEGIN CERTIFICATE"):
            _extract_first_pem_block(b"just some random bytes")

    def test_raises_on_missing_footer(self) -> None:
        with pytest.raises(ValueError, match="END CERTIFICATE"):
            _extract_first_pem_block(b"-----BEGIN CERTIFICATE-----\nDATA")


# ── validate_pem: success cases ──────────────────────────────────


class TestValidPEM:
    def test_valid_cert_returns_ok(self) -> None:
        result = _parse(validate_pem(_mock_session, VALID_PEM))
        assert result["ok"] is True
        assert "expires" in result["message"].lower()
        assert result["expires_on"] == "2027-03-18"
        assert result["subject"] is not None
        assert "OTLP Test CA" in result["subject"]
        assert result["pem_fingerprint"] is not None
        assert result["error_code"] is None

    def test_valid_cert_with_crlf(self) -> None:
        crlf_pem = VALID_PEM.replace("\n", "\r\n")
        result = _parse(validate_pem(_mock_session, crlf_pem))
        assert result["ok"] is True

    def test_valid_cert_with_whitespace(self) -> None:
        padded = "\n\n  " + VALID_PEM + "  \n\n"
        result = _parse(validate_pem(_mock_session, padded))
        assert result["ok"] is True


# ── validate_pem: failure cases ──────────────────────────────────


class TestInvalidPEM:
    def test_empty_string(self) -> None:
        result = _parse(validate_pem(_mock_session, ""))
        assert result["ok"] is False
        assert result["error_code"] == "EMPTY"

    def test_whitespace_only(self) -> None:
        result = _parse(validate_pem(_mock_session, "   \n\t  "))
        assert result["ok"] is False
        assert result["error_code"] == "EMPTY"

    def test_no_pem_markers(self) -> None:
        result = _parse(validate_pem(_mock_session, "not a certificate"))
        assert result["ok"] is False
        assert result["error_code"] == "NO_HEADER"

    def test_too_large(self) -> None:
        huge = "A" * (_MAX_PEM_SIZE + 1)
        result = _parse(validate_pem(_mock_session, huge))
        assert result["ok"] is False
        assert result["error_code"] == "TOO_LARGE"

    def test_garbage_between_markers(self) -> None:
        bad = "-----BEGIN CERTIFICATE-----\nNOTBASE64!!!\n-----END CERTIFICATE-----"
        result = _parse(validate_pem(_mock_session, bad))
        assert result["ok"] is False
        assert result["error_code"] == "PARSE_ERROR"

    def test_expired_cert(self) -> None:
        result = _parse(validate_pem(_mock_session, EXPIRED_PEM))
        assert result["ok"] is False
        assert result["error_code"] == "EXPIRED"
        assert "expired" in result["message"].lower()
        assert result["expires_on"] == "2026-03-19"

    def test_missing_footer(self) -> None:
        truncated = VALID_PEM.split("-----END CERTIFICATE-----")[0]
        result = _parse(validate_pem(_mock_session, truncated))
        assert result["ok"] is False


# ── validate_pem: multi-PEM ─────────────────────────────────────


class TestMultiPEM:
    def test_multi_block_validates_first(self) -> None:
        multi = VALID_PEM + "\n" + VALID_PEM
        result = _parse(validate_pem(_mock_session, multi))
        assert result["ok"] is True
        assert "first certificate" in result["message"].lower()

    def test_valid_then_expired_still_ok(self) -> None:
        multi = VALID_PEM + "\n" + EXPIRED_PEM
        result = _parse(validate_pem(_mock_session, multi))
        assert result["ok"] is True
