"""Generate a self-signed TLS cert for LAN HTTPS (uvicorn).

Usage:
  pip install cryptography
  python -m scripts.gen_dev_ssl
  python -m scripts.gen_dev_ssl --ip 172.30.0.1 --dns localhost
"""

from __future__ import annotations

import argparse
import ipaddress
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
CERTS_DIR = BACKEND_ROOT / "certs"


def _local_ipv4s() -> list[str]:
    ips: set[str] = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips)


def main() -> None:
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    except ImportError as exc:
        raise SystemExit(
            "Install cryptography first: pip install cryptography"
        ) from exc

    parser = argparse.ArgumentParser(description="Write certs/dev-cert.pem and certs/dev-key.pem")
    parser.add_argument(
        "--ip",
        action="append",
        default=[],
        help="IP to put in the certificate SAN (repeatable). Defaults to non-loopback local IPv4s.",
    )
    parser.add_argument(
        "--dns",
        action="append",
        default=["localhost"],
        help="DNS name SAN (repeatable). Default: localhost",
    )
    parser.add_argument("--days", type=int, default=825)
    args = parser.parse_args()

    ips = list(args.ip) or _local_ipv4s()
    if "127.0.0.1" not in ips:
        ips.append("127.0.0.1")

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    san: list[x509.GeneralName] = []
    for name in args.dns:
        san.append(x509.DNSName(name))
    for raw in ips:
        san.append(x509.IPAddress(ipaddress.ip_address(raw)))

    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ips[0])])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=args.days))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    CERTS_DIR.mkdir(parents=True, exist_ok=True)
    cert_path = CERTS_DIR / "dev-cert.pem"
    key_path = CERTS_DIR / "dev-key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    print(f"Wrote {cert_path}")
    print(f"Wrote {key_path}")
    print("SANs:", ", ".join(args.dns + ips))
    print("Set in .env:")
    print("  SSL_CERTFILE=./certs/dev-cert.pem")
    print("  SSL_KEYFILE=./certs/dev-key.pem")
    print("  PUBLIC_API_URL=https://<lan-ip>:4100")
    print("Then start with: python run.py")
    print("Browsers and phones will warn until you trust this self-signed cert.")


if __name__ == "__main__":
    main()
