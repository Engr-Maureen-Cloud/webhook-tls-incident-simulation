
"""
Create demo certificates for the webhook receiver.

Outputs in ./certs:
  ca.pem               demo certificate authority
  server.key            server private key
  server_valid.pem      valid certificate (healthy state)
  server_expired.pem    expired certificate (incident simulation)

Usage: python make_certs.py --host localhost
"""

import argparse
import datetime as dt
import ipaddress
import os

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ap = argparse.ArgumentParser()
ap.add_argument("--host", default="localhost")
host = ap.parse_args().host

os.makedirs("certs", exist_ok=True)
now = dt.datetime.now(dt.timezone.utc)


def name(cn):
    return x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Meridian Demo"),
        x509.NameAttribute(NameOID.COMMON_NAME, cn),
    ])


def write(path, data):
    with open(path, "wb") as f:
        f.write(data)


# =========================================================
# 1. Create the Certificate Authority (CA)
# =========================================================

ca_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
)

ca_cert = (
    x509.CertificateBuilder()
    .subject_name(name("Meridian Demo CA"))
    .issuer_name(name("Meridian Demo CA"))
    .public_key(ca_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - dt.timedelta(days=800))
    .not_valid_after(now + dt.timedelta(days=3650))
    .add_extension(
        x509.BasicConstraints(ca=True, path_length=None),
        critical=True,
    )
    .add_extension(
        x509.KeyUsage(
            digital_signature=False,
            content_commitment=False,
            key_encipherment=False,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=True,
            crl_sign=True,
            encipher_only=None,
            decipher_only=None,
        ),
        critical=True,
    )
    .add_extension(
        x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
        critical=False,
    )
    .sign(ca_key, hashes.SHA256())
)

# =========================================================
# 2. Create the server private key
# =========================================================

server_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
)

# =========================================================
# 3. Identify the server hostname or IP address
# =========================================================

try:
    san = x509.IPAddress(ipaddress.ip_address(host))
except ValueError:
    san = x509.DNSName(host)

sans = [san]

if host == "localhost":
    sans.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
    sans.append(x509.DNSName("localhost"))

# =========================================================
# 4. Create server certificates
# =========================================================

def server_cert(start, end):
    return (
        x509.CertificateBuilder()
        .subject_name(name(host))
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(end)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                x509.oid.ExtendedKeyUsageOID.SERVER_AUTH
            ]),
            critical=False,
        )
        .add_extension(
            x509.SubjectAlternativeName(sans),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                ca_key.public_key()
            ),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(
                server_key.public_key()
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

# =========================================================
# 5. Generate one valid and one expired certificate
# =========================================================

valid = server_cert(
    now - dt.timedelta(days=80),
    now + dt.timedelta(days=285),
)

expired = server_cert(
    now - dt.timedelta(days=100),
    now - dt.timedelta(days=10),
)

# =========================================================
# 6. Save the certificates and private key
# =========================================================

pem = serialization.Encoding.PEM

write("certs/ca.pem", ca_cert.public_bytes(pem))

write(
    "certs/server.key",
    server_key.private_bytes(
        pem,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ),
)

write("certs/server_valid.pem", valid.public_bytes(pem))
write("certs/server_expired.pem", expired.public_bytes(pem))

print(f"Created certs for {host}")
print("  valid until", valid.not_valid_after_utc.date())
print("  expired on  ", expired.not_valid_after_utc.date())
