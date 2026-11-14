"""SSL/TLS Certificate inspector for Portly."""

from datetime import datetime, timezone
import logging
import os
import ssl
import tempfile
from typing import Any, Dict, List, Optional

logger = logging.getLogger("portly.tls_inspector")


def _extract_name_attr(tuple_of_tuples, key: str = "commonName") -> str:
    """Extracts a specific attribute like commonName or organizationName from cert subject/issuer."""
    if not tuple_of_tuples:
        return ""
    for rdn in tuple_of_tuples:
        for entry in rdn:
            if entry and len(entry) >= 2 and entry[0] == key:
                return str(entry[1])
    return ""


def _parse_ssl_date(date_str: str) -> Optional[datetime]:
    """Parses standard SSL date strings into UTC datetime."""
    formats = [
        "%b %d %H:%M:%S %Y %Z",
        "%b  %d %H:%M:%S %Y %Z",
        "%b %d %H:%M:%S %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def inspect_tls_certificate(host: str, port: int, timeout: float = 2.0) -> Dict[str, Any]:
    """Inspects TLS/SSL certificate on target host:port."""
    target_host = "127.0.0.1" if host in ("0.0.0.0", "::", "", None) else host

    try:
        # Fetch PEM certificate
        pem_cert = ssl.get_server_certificate((target_host, port), timeout=timeout)
    except Exception as e:
        return {
            "is_tls": False,
            "error": f"TLS connection failed or port is not HTTPS/TLS: {e}",
            "days_remaining": None,
            "valid_from": None,
            "valid_until": None,
            "issuer": None,
            "subject": None,
            "san": [],
            "self_signed": False,
            "expired": False,
        }

    # Decode certificate using ssl internal parser
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".pem") as f:
            f.write(pem_cert)
            temp_path = f.name

        decoded = ssl._ssl._test_decode_cert(temp_path)
    except Exception as e:
        return {
            "is_tls": True,
            "error": f"Failed to parse certificate: {e}",
            "days_remaining": None,
            "valid_from": None,
            "valid_until": None,
            "issuer": None,
            "subject": None,
            "san": [],
            "self_signed": False,
            "expired": False,
        }
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    subject_cn = _extract_name_attr(decoded.get("subject"), "commonName")
    subject_org = _extract_name_attr(decoded.get("subject"), "organizationName")
    issuer_cn = _extract_name_attr(decoded.get("issuer"), "commonName")
    issuer_org = _extract_name_attr(decoded.get("issuer"), "organizationName")

    issuer_display = issuer_org or issuer_cn or "Unknown Issuer"
    subject_display = subject_cn or subject_org or "Unknown Subject"

    not_before_str = decoded.get("notBefore", "")
    not_after_str = decoded.get("notAfter", "")

    not_before_dt = _parse_ssl_date(not_before_str)
    not_after_dt = _parse_ssl_date(not_after_str)

    now = datetime.now(timezone.utc)
    days_remaining = None
    expired = False

    if not_after_dt:
        diff = (not_after_dt - now).total_seconds() / 86400.0
        days_remaining = int(diff)
        expired = days_remaining < 0

    san_list: List[str] = []
    for item in decoded.get("subjectAltName", ()):
        if item and len(item) >= 2:
            san_list.append(f"{item[0]}:{item[1]}")

    self_signed = (decoded.get("subject") == decoded.get("issuer")) or (
        bool(subject_cn) and subject_cn == issuer_cn
    )

    return {
        "is_tls": True,
        "error": None,
        "subject": subject_display,
        "issuer": issuer_display,
        "valid_from": not_before_dt.isoformat() if not_before_dt else not_before_str,
        "valid_until": not_after_dt.isoformat() if not_after_dt else not_after_str,
        "days_remaining": days_remaining,
        "expired": expired,
        "self_signed": self_signed,
        "san": san_list,
        "serial_number": decoded.get("serialNumber"),
        "version": decoded.get("version"),
    }
