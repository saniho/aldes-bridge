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


def _doh_query(host, timeout=5):
    """Resout un hostname via DNS over HTTPS (DoH) — contourne toute redirection DNS locale."""
    import json
    import urllib.request
    import urllib.error

    # Cloudflare DoH JSON API (pas de port 53, pas d'interception)
    url = "https://cloudflare-dns.com/dns-query?name=%s&type=A" % host
    req = urllib.request.Request(url, headers={
        "Accept": "application/dns-json",
        "User-Agent": "aldes-bridge/1.0",
    })
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
    data = json.loads(resp.read())
    for ans in data.get("Answer", []):
        if ans.get("type") == 1:  # A record
            return ans["data"]
    return None


def _dns_query_udp(host, server="1.1.1.1", timeout=5):
    """Envoie une requete DNS UDP directe a un serveur."""
    import random
    import struct

    tid = random.randint(0, 0xFFFF)
    header = struct.pack("!HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    question = b""
    for label in host.encode().split(b"."):
        question += bytes([len(label)]) + label
    question += b"\x00"
    question += struct.pack("!HH", 1, 1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(header + question, (server, 53))
        data, _ = sock.recvfrom(512)
    finally:
        sock.close()

    i = 12
    while i < len(data) and data[i] != 0:
        i += data[i] + 1
    i += 1
    i += 4
    while i < len(data) - 12:
        i += 2
        rtype = struct.unpack("!H", data[i:i+2])[0]
        i += 8
        rdlen = struct.unpack("!H", data[i:i+2])[0]
        i += 2
        if rtype == 1 and rdlen == 4:
            return "%d.%d.%d.%d" % tuple(data[i:i+4])
        i += rdlen
    return None


def resolve(host, port):
    """Resout l'IP du vrai hote en contournant le dnsmasq local.

    Priorite : DoH (HTTPS) > UDP direct > system DNS.
    Le DoH contourne toute redirection DNS car il utilise le port 443,
    pas le port 53.
    """
    if host in ("localhost", "127.0.0.1", "::1"):
        return host
    # 1. DoH — contourne completement dnsmasq
    try:
        ip = _doh_query(host)
        if ip:
            return ip
    except Exception:
        pass
    # 2. UDP direct — peut etre intercepte par iptables
    try:
        ip = _dns_query_udp(host, "1.1.1.1")
        if ip:
            return ip
    except Exception:
        pass
    try:
        ip = _dns_query_udp(host, "8.8.8.8")
        if ip:
            return ip
    except Exception:
        pass
    # 3. Dernier recours: system DNS (dnsmasq)
    return socket.gethostbyname(host)
