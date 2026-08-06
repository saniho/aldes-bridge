"""Certificat TLS self-signed et contextes SSL permissifs (reprise de mqtt_proxy.py)."""
"""Certificat TLS self-signed et contextes SSL permissifs (reprise de mqtt_proxy.py)."""
import socket
import ssl
import tempfile
from datetime import datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def _generate(common_name):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(common_name)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_fd, cert_path = tempfile.mkstemp(prefix="aldes_crt_", suffix=".pem")
    key_fd, key_path = tempfile.mkstemp(prefix="aldes_key_", suffix=".pem")
    with open(cert_fd, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_fd, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
    return cert_path, key_path


def _permissive(ctx):
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.minimum_version = ssl.TLSVersion.TLSv1
    except Exception:
        pass
    try:
        ctx.set_ciphers("ALL:@SECLEVEL=0")
    except ssl.SSLError:
        pass
    return ctx


def server_context(common_name="aldesiotsuite.azure-devices.net"):
    """Contexte TLS serveur qui imite le domaine Azure pour la box."""
    cert_path, key_path = _generate(common_name)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    return _permissive(ctx)


def client_context():
    """Contexte TLS client permissif pour joindre le vrai Azure."""
    ctx = ssl.create_default_context()
    return _permissive(ctx)


def resolve(host, port):
    """Resout l'IP du vrai hote en contournant le dnsmasq local (via DNS public 1.1.1.1)."""
    if host in ("localhost", "127.0.0.1", "::1"):
        return host
    try:
        import subprocess
        r = subprocess.run(
            ["nslookup", host, "1.1.1.1"],
            capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.split("\n"):
            if "Address:" in line and "#" not in line and "Address:" in line:
                ip = line.split("Address:")[-1].strip()
                if ip and not ip.endswith("#53") and ":" not in ip:
                    return ip
    except Exception:
        pass
    return socket.gethostbyname(host)
