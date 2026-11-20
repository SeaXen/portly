"""SSL/TLS Certificate inspector for Portly with SNI support and cryptography parsing."""

from datetime import datetime, timezone
import logging
import socket
import ssl
from typing import Any, Dict

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID, NameOID

logger = logging.getLogger("portly.tls_inspector")


def _tls_error(error: str, is_tls: bool = False) -> Dict[str, Any]:
    return {
        "is_tls": is_tls,
        "error": error,
        "days_remaining": None,
        "valid_from": None,
        "valid_until": None,
        "issuer": None,
        "subject": None,
        "san": [],
        "self_signed": False,
        "expired": False,
    }


def inspect_tls_certificate(host: str, port: int, timeout: float = 2.0) -> Dict[str, Any]:
    """Inspects TLS/SSL certificate on target host:port sending SNI and parsing safely."""
    target_host = "127.0.0.1" if host in ("0.0.0.0", "::", "", None) else host
    server_sni = "localhost" if target_host in ("127.0.0.1", "::1") else target_host

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with socket.create_connection((target_host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=server_sni) as ssock:
                der_cert = ssock.getpeercert(binary_form=True)
    except Exception as e:
        return _tls_error(f"TLS connection failed or port is not HTTPS/TLS: {e}")

    if not der_cert:
        return _tls_error("No certificate received from server")

    try:
        cert = x509.load_der_x509_certificate(der_cert, default_backend())

        def _get_name(name_obj):
            cns = name_obj.get_attributes_for_oid(NameOID.COMMON_NAME)
            orgs = name_obj.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)
            cn = cns[0].value if cns else ""
            org = orgs[0].value if orgs else ""
            return org or cn or "Unknown"

        now = datetime.now(timezone.utc)
        valid_from_dt = cert.not_valid_before_utc
        valid_until_dt = cert.not_valid_after_utc
        diff_sec = (valid_until_dt - now).total_seconds()

        san_list = []
        try:
            san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            for name in san_ext.value:
                san_list.append(str(name.value))
        except x509.ExtensionNotFound:
            pass

        return {
            "is_tls": True,
            "error": None,
            "subject": _get_name(cert.subject),
            "issuer": _get_name(cert.issuer),
            "valid_from": valid_from_dt.isoformat(),
            "valid_until": valid_until_dt.isoformat(),
            "days_remaining": int(diff_sec / 86400.0),
            "expired": diff_sec < 0,
            "self_signed": cert.issuer == cert.subject,
            "san": san_list,
            "serial_number": str(cert.serial_number),
            "version": str(cert.version.value),
        }
    except Exception as e:
        logger.warning(f"Failed to parse DER certificate from {target_host}:{port}: {e}")
        return _tls_error(f"Failed to parse DER certificate: {e}", is_tls=True)
