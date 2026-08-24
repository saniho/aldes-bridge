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


def _dns_query(host, server="1.1.1.1", timeout=5):
    """Envoie une requete DNS UDP directe a un serveur, contournant le resolver local."""
    import random
    import struct

    tid = random.randint(0, 0xFFFF)
    # Header: ID, flags=0x0100 (standard query, recursion desired), 1 question
    header = struct.pack("!HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    # Question: type A (1), class IN (1)
    question = b""
    for label in host.encode().split(b"."):
        question += bytes([len(label)]) + label
    question += b"\x00"  # end of name
    question += struct.pack("!HH", 1, 1)  # type A, class IN

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(header + question, (server, 53))
        data, _ = sock.recvfrom(512)
    finally:
        sock.close()

    # Parse response: skip header (12 bytes) + question
    qname_len = 0
    i = 12
    while i < len(data) and data[i] != 0:
        i += data[i] + 1
    i += 1  # skip null byte
    i += 4  # skip type + class
    # Parse answer RRs
    while i < len(data) - 12:
        i += 2  # skip name (pointer or label)
        rtype = struct.unpack("!H", data[i:i+2])[0]
        i += 8  # type, class, ttl
        rdlen = struct.unpack("!H", data[i:i+2])[0]
        i += 2
        if rtype == 1 and rdlen == 4:  # type A
            return "%d.%d.%d.%d" % tuple(data[i:i+4])
        i += rdlen
    return None


def resolve(host, port):
    """Resout l'IP du vrai hote en contournant le dnsmasq local (via DNS public 1.1.1.1)."""
    if host in ("localhost", "127.0.0.1", "::1"):
        return host
    try:
        ip = _dns_query(host, "1.1.1.1")
        if ip:
            return ip
    except Exception:
        pass
    # Fallback: essayer 8.8.8.8
    try:
        ip = _dns_query(host, "8.8.8.8")
        if ip:
            return ip
    except Exception:
        pass
    return socket.gethostbyname(host)
