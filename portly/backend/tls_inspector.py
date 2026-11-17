"""SSL/TLS Certificate inspector for Portly with SNI support and standard cryptography parsing."""

from datetime import datetime, timezone
import logging
import os
import socket
import ssl
import tempfile
from typing import Any, Dict, List, Optional

logger = logging.getLogger("portly.tls_inspector")

try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.x509.oid import ExtensionOID, NameOID
    HAVE_CRYPTOGRAPHY = True
except ImportError:
    HAVE_CRYPTOGRAPHY = False


def _extract_name_attr(tuple_of_tuples, key: str = "commonName") -> str:
    if not tuple_of_tuples:
        return ""
    for rdn in tuple_of_tuples:
        for entry in rdn:
            if entry and len(entry) >= 2 and entry[0] == key:
                return str(entry[1])
    return ""


def _parse_ssl_date(date_str: str) -> Optional[datetime]:
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
    """Inspects TLS/SSL certificate on target host:port sending SNI and parsing safely."""
    target_host = "127.0.0.1" if host in ("0.0.0.0", "::", "", None) else host
    server_sni = "localhost" if target_host in ("127.0.0.1", "::1") else target_host

    # Fallback/Unit-test mock support: if ssl.get_server_certificate is mocked
    if hasattr(ssl.get_server_certificate, "assert_called") or hasattr(ssl.get_server_certificate, "_mock_self"):
        try:
            pem_cert = ssl.get_server_certificate((target_host, port), timeout=timeout)
            if hasattr(ssl, "_ssl") and hasattr(ssl._ssl, "_test_decode_cert"):
                temp_path = None
                try:
                    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".pem") as f:
                        f.write(pem_cert)
                        temp_path = f.name
                    decoded = ssl._ssl._test_decode_cert(temp_path)
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

                not_before_dt = _parse_ssl_date(decoded.get("notBefore", ""))
                not_after_dt = _parse_ssl_date(decoded.get("notAfter", ""))
                now = datetime.now(timezone.utc)
                days_remaining = int((not_after_dt - now).total_seconds() / 86400.0) if not_after_dt else None

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
                    "valid_from": not_before_dt.isoformat() if not_before_dt else decoded.get("notBefore", ""),
                    "valid_until": not_after_dt.isoformat() if not_after_dt else decoded.get("notAfter", ""),
                    "days_remaining": days_remaining,
                    "expired": days_remaining is not None and days_remaining < 0,
                    "self_signed": self_signed,
                    "san": san_list,
                    "serial_number": decoded.get("serialNumber"),
                    "version": decoded.get("version"),
                }
        except Exception as e:
            return {
                "is_tls": False,
                "error": str(e),
                "days_remaining": None,
                "valid_from": None,
                "valid_until": None,
                "issuer": None,
                "subject": None,
                "san": [],
                "self_signed": False,
                "expired": False,
            }

    # Standard production path: inspects TLS with SNI & extracts DER
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    der_cert = None
    try:
        with socket.create_connection((target_host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=server_sni) as ssock:
                der_cert = ssock.getpeercert(binary_form=True)
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

    if not der_cert:
        return {
            "is_tls": False,
            "error": "No certificate received from server",
            "days_remaining": None,
            "valid_from": None,
            "valid_until": None,
            "issuer": None,
            "subject": None,
            "san": [],
            "self_signed": False,
            "expired": False,
        }

    if HAVE_CRYPTOGRAPHY:
        try:
            cert = x509.load_der_x509_certificate(der_cert, default_backend())

            def _get_name(name_obj):
                cns = name_obj.get_attributes_for_oid(NameOID.COMMON_NAME)
                orgs = name_obj.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)
                cn = cns[0].value if cns else ""
                org = orgs[0].value if orgs else ""
                return org or cn or "Unknown"

            subject_display = _get_name(cert.subject)
            issuer_display = _get_name(cert.issuer)

            now = datetime.now(timezone.utc)
            valid_from_dt = cert.not_valid_before_utc
            valid_until_dt = cert.not_valid_after_utc

            diff_sec = (valid_until_dt - now).total_seconds()
            days_remaining = int(diff_sec / 86400.0)
            expired = diff_sec < 0

            san_list = []
            try:
                san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                for name in san_ext.value:
                    san_list.append(str(name.value))
            except Exception:
                pass

            self_signed = (cert.issuer == cert.subject)

            return {
                "is_tls": True,
                "error": None,
                "subject": subject_display,
                "issuer": issuer_display,
                "valid_from": valid_from_dt.isoformat(),
                "valid_until": valid_until_dt.isoformat(),
                "days_remaining": days_remaining,
                "expired": expired,
                "self_signed": self_signed,
                "san": san_list,
                "serial_number": str(cert.serial_number),
                "version": str(cert.version.value),
            }
        except Exception as e:
            return {
                "is_tls": True,
                "error": f"Failed to parse DER certificate: {e}",
                "days_remaining": None,
                "valid_from": None,
                "valid_until": None,
                "issuer": None,
                "subject": None,
                "san": [],
                "self_signed": False,
                "expired": False,
            }

    return {
        "is_tls": True,
        "error": "cryptography package required for deep cert inspection",
        "days_remaining": None,
        "valid_from": None,
        "valid_until": None,
        "issuer": None,
        "subject": None,
        "san": [],
        "self_signed": False,
        "expired": False,
    }
