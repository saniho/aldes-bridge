#!/usr/bin/env python3
"""
Proxy MQTT transparent : espionne la box Aldes sans faire de faux broker.
La box parle au vrai Azure IoT Hub, on logue tout.
"""
import socket, ssl, threading, sys, time
from datetime import datetime

def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

_orig_print = print
def print(*args, **kw):
    _orig_print("[%s]" % ts(), *args, **kw)

REAL_HOST = "aldesiotsuite.azure-devices.net"
REAL_PORT = 8883
BIND_PORT = 8883
CLIENT_ID = None

def real_resolve(host):
    """Resout le vrai IP en contournant dnsmasq local (via DNS public)"""
    try:
        import subprocess
        r = subprocess.run(["nslookup", host, "1.1.1.1"],
            capture_output=True, text=True, timeout=5)
        for line in r.stdout.split('\n'):
            if 'Address:' in line and '#' not in line:
                ip = line.split('Address:')[1].strip()
                return ip, host
    except:
        pass
    # Fallback: utilise le systeme (peut etre notre dnsmasq)
    return socket.gethostbyname(host), host

REAL_IP, _ = real_resolve(REAL_HOST)
print("[*] Azure IoT Hub reel: %s -> %s" % (REAL_HOST, REAL_IP))

now = lambda: datetime.now().strftime("%H:%M:%S.%f")[:12]

def forward(src, dst, direction, log_prefix):
    global CLIENT_ID
    bufsize = 4096
    while True:
        try:
            data = src.recv(bufsize)
            if not data:
                break
            ts = now()
            t = "%s%s" % (log_prefix, direction)
            # Try to detect MQTT packet type
            pt = (data[0] >> 4) & 0xF
            mqtt_types = {1:"CONNECT", 2:"CONNACK", 3:"PUBLISH", 4:"PUBACK",
                          5:"PUBREC", 6:"PUBREL", 7:"PUBCOMP", 8:"SUBSCRIBE",
                          9:"SUBACK", 10:"UNSUBSCRIBE", 11:"UNSUBACK",
                          12:"PINGREQ", 13:"PINGRESP", 14:"DISCONNECT"}
            pname = mqtt_types.get(pt, "PTYPE_%d" % pt)

            log = "%s  [%s] %s (%d bytes)" % (t, pname, ts, len(data))

            # Pour PUBLISH, extraire le topic
            if pt == 3:
                try:
                    rl = data[1]
                    o = 2
                    tlen = (data[o] << 8) | data[o+1]; o += 2
                    topic = data[o:o+tlen].decode(errors='replace'); o += tlen
                    qos = (data[0] & 0x06) >> 1
                    if qos:
                        o += 2
                    payload = data[o:].decode(errors='replace')
                    log += "\n%s    topic=%s qos=%d" % (t, topic, qos)
                    if payload:
                        if payload.startswith('{'):
                            log += "\n%s    payload=%s" % (t, payload[:1000])
                        else:
                            log += "\n%s    payload=%s" % (t, payload[:200])
                except:
                    log += "\n%s    (parse error)" % t

            # Pour SUBSCRIBE, extraire les topics
            if pt == 8:
                try:
                    o = 2
                    pkt_id = (data[o] << 8) | data[o+1]; o += 2
                    log += "\n%s    pkt_id=%d" % (t, pkt_id)
                    while o < len(data):
                        tlen = (data[o] << 8) | data[o+1]; o += 2
                        topic = data[o:o+tlen].decode(errors='replace'); o += tlen
                        qos = data[o]; o += 1
                        log += "\n%s    topic=%s qos=%d" % (t, topic, qos)
                except:
                    log += "\n%s    (parse error)" % t

            # Pour CONNECT, extraire le client_id
            if pt == 1:
                try:
                    # Decode la vraie remaining length (multi-byte)
                    o = 1
                    m = 1
                    rl = 0
                    while True:
                        b = data[o]; o += 1
                        rl += (b & 0x7F) * m
                        if not (b & 0x80): break
                        m *= 128
                    proto_len = (data[o] << 8) | data[o+1]; o += 2 + proto_len  # skip proto name + len
                    level = data[o]; o += 1
                    cflags = data[o]; o += 1
                    keepalive = (data[o] << 8) | data[o+1]; o += 2
                    cid_len = (data[o] << 8) | data[o+1]; o += 2
                    cid = data[o:o+cid_len].decode(); o += cid_len
                    CLIENT_ID = cid
                    log += "\n%s    client_id=%s level=%d keepalive=%d" % (t, cid, level, keepalive)
                    if cflags & 0x80:
                        un = data[o+2:o+2+(data[o]<<8|data[o+1])].decode(errors='replace')
                        log += "\n%s    username=%s" % (t, un[:80])
                    if cflags & 0x40:
                        pwlen = (data[o] << 8) | data[o+1]
                        log += "\n%s    password=%s" % (t, data[o+2:o+2+min(pwlen,60)].decode(errors='replace'))
                except:
                    log += "\n%s    (parse error)" % t

            print(log)

            dst.sendall(data)

            # Save to pcap-like log
            with open("/tmp/mqtt_traffic.log", "a") as f:
                f.write("%s [%s] %s\n" % (ts, direction, pname))
                f.flush()

        except (ConnectionError, OSError) as e:
            ts = now()
            print("%s  [!] Connexion %s: %s" % (log_prefix, direction, e))
            break
        except Exception as e:
            ts = now()
            print("%s  [!!] Erreur %s: %s" % (log_prefix, direction, e))
            break

def handle_box(box_sock, addr):
    global CLIENT_ID
    CLIENT_ID = "?"
    prefix = "[%s]" % CLIENT_ID
    print("\n%s  [+] Connexion box de %s" % (prefix, addr))

    try:
        # Connexion au vrai Azure
        print("%s  [+] Connexion au vrai Azure %s:%d..." % (prefix, REAL_HOST, REAL_PORT))
        real_sock = socket.create_connection((REAL_IP, REAL_PORT), timeout=15)

        # TLS vers Azure (permissif — on observe, on valide pas)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try: ctx.minimum_version = ssl.TLSVersion.TLSv1
        except: pass
        try: ctx.set_ciphers("ALL:@SECLEVEL=0")
        except: pass
        real_tls = ctx.wrap_socket(real_sock, server_hostname=REAL_HOST)
        real_tls.settimeout(None)  # bloquant, pas de timeout
        print("%s  [+] Connecte au vrai Azure !" % prefix)

        # Lancement des deux sens
        t1 = threading.Thread(target=forward, args=(box_sock, real_tls, ">>>", prefix), daemon=True)
        t2 = threading.Thread(target=forward, args=(real_tls, box_sock, "<<<", prefix), daemon=True)
        t1.start(); t2.start()
        t1.join(); t2.join()

    except Exception as e:
        print("%s  [!] Erreur: %s" % (prefix, e))
    finally:
        try: box_sock.close()
        except: pass
        print("%s  [+] Deconnecte\n" % prefix)

# Setup TLS pour la box (permissif comme avant)
print("[*] Generation certificat TLS ...")
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from datetime import timedelta

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, REAL_HOST)])
cert = (
    x509.CertificateBuilder().subject_name(name).issuer_name(name)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.utcnow())
    .not_valid_after(datetime.utcnow() + timedelta(days=3650))
    .add_extension(x509.SubjectAlternativeName([x509.DNSName(REAL_HOST)]), critical=False)
    .sign(key, hashes.SHA256())
)
with open("/tmp/proxy.crt", "wb") as f: f.write(cert.public_bytes(serialization.Encoding.PEM))
with open("/tmp/proxy.key", "wb") as f: f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))

ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain("/tmp/proxy.crt", "/tmp/proxy.key")
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
try: ctx.minimum_version = ssl.TLSVersion.TLSv1
except: pass
try: ctx.set_ciphers("ALL:@SECLEVEL=0")
except: pass

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("0.0.0.0", BIND_PORT)); sock.listen(5)
print("[*] Proxy MQTT transparent sur 0.0.0.0:%d" % BIND_PORT)
print("[*] Redemarre la box Aldes Connect maintenant !")

while True:
    try:
        c, a = sock.accept()
        cs = ctx.wrap_socket(c, server_side=True)
        threading.Thread(target=handle_box, args=(cs, a), daemon=True).start()
    except Exception as e:
        print("[!] Erreur accept: %s" % e)
        try: c.close()
        except: pass
