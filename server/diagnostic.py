"""Diagnostic (check-up systeme) — extrait de api.py."""
import os
import resource
import socket
import subprocess
import time
from datetime import datetime, timezone

_log = None  # lazy


def _ensure_log():
    global _log
    if _log is None:
        import logging
        _log = logging.getLogger("aldes-diagnostic")


def run_diagnostic(state, engine):
    """Execute tous les checks de diagnostic et retourne le dict complet."""
    _ensure_log()
    _PROCESS_START = time.time()  # module-level cache
    checks = []

    # 1. DNS resolution DoH
    try:
        from ..tls import _doh_query
        ip = _doh_query(state.real_host, timeout=5)
        checks.append({
            "id": "dns_doh",
            "label": "DNS DoH (Cloudflare)",
            "detail": f"{state.real_host} → {ip}" if ip else "Pas de réponse A record",
            "ok": ip is not None,
            "ip": ip,
        })
    except Exception as exc:
        checks.append({"id": "dns_doh", "label": "DNS DoH (Cloudflare)", "detail": str(exc), "ok": False})

    # 2. DNS systeme
    try:
        ip_sys = socket.gethostbyname(state.real_host)
        is_local = ip_sys in ("127.0.0.1", "::1", state._azure_ip)
        checks.append({
            "id": "dns_system",
            "label": "DNS systeme (dnsmasq)",
            "detail": f"{state.real_host} → {ip_sys}" + (" — resolu vers le bridge !" if is_local else ""),
            "ok": not is_local,
            "ip": ip_sys,
            "warn": is_local,
        })
    except Exception as exc:
        checks.append({"id": "dns_system", "label": "DNS systeme (dnsmasq)", "detail": str(exc), "ok": False})

    # 3. IP Azure stockee
    azure_ip = state._azure_ip
    checks.append({
        "id": "azure_ip",
        "label": "IP Azure résolue",
        "detail": azure_ip or "Non résolue",
        "ok": azure_ip is not None,
        "ip": azure_ip,
    })

    # 4. Connectivite TCP vers Azure (port 8883)
    if azure_ip:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((azure_ip, 8883))
            sock.close()
            checks.append({
                "id": "tcp_azure",
                "label": f"TCP Azure ({azure_ip}:8883)",
                "detail": "Atteignable" if result == 0 else f"Refuse (errno {result})",
                "ok": result == 0,
            })
        except Exception as exc:
            checks.append({"id": "tcp_azure", "label": f"TCP Azure ({azure_ip}:8883)", "detail": str(exc), "ok": False})
    else:
        checks.append({"id": "tcp_azure", "label": "TCP Azure", "detail": "IP non resolue — test impossible", "ok": False})

    # 5. Listener MQTT
    try:
        port = engine.mqtt_port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        checks.append({
            "id": "mqtt_listener",
            "label": f"Listener MQTT (:{port})",
            "detail": "En écoute" if result == 0 else "Pas en écoute",
            "ok": result == 0,
        })
    except Exception as exc:
        checks.append({"id": "mqtt_listener", "label": "Listener MQTT", "detail": str(exc), "ok": False})

    # 6. iptables PREROUTING
    try:
        out = subprocess.check_output(
            ["iptables", "-t", "nat", "-L", "PREROUTING", "-n", "--line-numbers"],
            stderr=subprocess.STDOUT, timeout=3,
        ).decode(errors="replace")
        has_8883 = "8883" in out
        rules = [l for l in out.splitlines() if "8883" in l]
        checks.append({
            "id": "iptables",
            "label": "iptables PREROUTING",
            "detail": f"{len(rules)} règle(s) REDIRECT 8883" if has_8883 else "Aucune règle 8883",
            "ok": has_8883,
            "rules": rules,
        })
    except FileNotFoundError:
        checks.append({"id": "iptables", "label": "iptables", "detail": "iptables non disponible", "ok": False, "warn": True})
    except Exception as exc:
        checks.append({"id": "iptables", "label": "iptables", "detail": str(exc), "ok": False})

    # 7. Connexion box
    with state._lock:
        box_connected = state._connected
        box_ip = state._client_id
        cloud_connected = state._cloud_since is not None
    checks.append({
        "id": "box_connected",
        "label": "Box Aldes",
        "detail": f"Connectée (client: {box_ip})" if box_connected else "Non connectée",
        "ok": box_connected,
    })

    # 8. Connexion Azure cloud
    checks.append({
        "id": "cloud_connected",
        "label": "Azure IoT Hub (cloud)",
        "detail": "Connecté" if cloud_connected else "Non connecté",
        "ok": cloud_connected,
    })

    # 9. Mode courant
    checks.append({
        "id": "mode",
        "label": "Mode actif",
        "detail": state.mode,
        "ok": state.mode in ("proxy", "bridge"),
    })

    # 10. Version
    checks.append({
        "id": "version",
        "label": "Version",
        "detail": f"Backend {state.server_version} · UI {state.ui_version}",
        "ok": True,
    })

    # 11. Broker MQTT HA (auto-detection)
    ha_mqtt = getattr(state, "_ha_mqtt_resolved", None)
    if ha_mqtt:
        source_label = {"supervisor": "Supervisor API", "cli": "CLI", "fallback": "Fallback"}.get(ha_mqtt["source"], ha_mqtt["source"])
        checks.append({
            "id": "ha_mqtt_broker",
            "label": "Broker MQTT HA",
            "detail": f"{source_label} → {ha_mqtt['host']}:{ha_mqtt['port']}",
            "ok": True,
            "host": ha_mqtt["host"],
            "port": ha_mqtt["port"],
            "source": ha_mqtt["source"],
        })
    else:
        checks.append({
            "id": "ha_mqtt_broker",
            "label": "Broker MQTT HA",
            "detail": "Desactive (--ha-mqtt non utilise)",
            "ok": False,
            "warn": True,
        })

    # 12. Certificat TLS self-signe
    try:
        from ..tls import _generate
        from cryptography import x509 as _x509
        cert_path, key_path = _generate(state.real_host)
        try:
            with open(cert_path, "rb") as _cf:
                cert_pem = _cf.read()
            cert = _x509.load_pem_x509_certificate(cert_pem)
            not_after = cert.not_valid_after_utc
            now_aware = datetime.now(timezone.utc)
            days_left = (not_after - now_aware).days
            detail = f"Expire le {not_after.strftime('%Y-%m-%d')} ({days_left}j)"
            ok = days_left > 30
            warn = 0 < days_left <= 30
            checks.append({
                "id": "tls_cert",
                "label": "Certificat TLS",
                "detail": detail,
                "ok": ok,
                "warn": warn,
            })
        finally:
            os.unlink(cert_path)
            os.unlink(key_path)
    except Exception as exc:
        checks.append({"id": "tls_cert", "label": "Certificat TLS", "detail": str(exc), "ok": False})

    # 13. Latence reseau vers Azure (RTT TCP)
    if azure_ip:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            t0 = time.monotonic()
            result_tcp = sock.connect_ex((azure_ip, 8883))
            rtt_ms = (time.monotonic() - t0) * 1000
            sock.close()
            if result_tcp == 0:
                detail = f"{rtt_ms:.0f} ms" + (" (lent)" if rtt_ms > 1000 else "")
                checks.append({
                    "id": "azure_latency",
                    "label": "Latence Azure",
                    "detail": detail,
                    "ok": rtt_ms < 1000,
                    "warn": rtt_ms > 500,
                })
            else:
                checks.append({"id": "azure_latency", "label": "Latence Azure", "detail": f"Refuse (errno {result_tcp})", "ok": False})
        except Exception as exc:
            checks.append({"id": "azure_latency", "label": "Latence Azure", "detail": str(exc), "ok": False})
    else:
        checks.append({"id": "azure_latency", "label": "Latence Azure", "detail": "IP non resolue", "ok": False})

    # 14. Sante du processus backend
    try:
        uptime_s = time.time() - _PROCESS_START
        if uptime_s < 60:
            uptime_str = f"{uptime_s:.0f}s"
        elif uptime_s < 3600:
            uptime_str = f"{uptime_s / 60:.0f}min"
        else:
            uptime_str = f"{uptime_s / 3600:.1f}h"
        mem_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        mem_mb = mem_kb / 1024
        checks.append({
            "id": "process_health",
            "label": "Processus backend",
            "detail": f"Uptime {uptime_str} · {mem_mb:.0f} Mo RSS",
            "ok": True,
        })
    except Exception as exc:
        checks.append({"id": "process_health", "label": "Processus backend", "detail": str(exc), "ok": False})

    # 15. Consignes en attente
    try:
        with state._lock:
            consignes = {k: dict(v) for k, v in state._consignes.items()}
        pending = {z: c for z, c in consignes.items() if not c.get("confirmed")}
        if not pending:
            checks.append({
                "id": "pending_consignes",
                "label": "Consignes en attente",
                "detail": "Aucune consigne en attente",
                "ok": True,
            })
        else:
            now_ts = time.time()
            oldest_age = 0
            for z, c in pending.items():
                try:
                    ts_str = c.get("ts", "")
                    if ts_str:
                        from datetime import datetime as _dt
                        ts_dt = _dt.fromisoformat(ts_str)
                        age = now_ts - ts_dt.timestamp()
                        oldest_age = max(oldest_age, age)
                except Exception:
                    pass
            if oldest_age < 60:
                age_str = f"{oldest_age:.0f}s"
            elif oldest_age < 3600:
                age_str = f"{oldest_age / 60:.0f}min"
            else:
                age_str = f"{oldest_age / 3600:.1f}h"
            zones = ", ".join(sorted(pending.keys()))
            ok = oldest_age < 300
            warn = not ok and oldest_age < 1800
            detail = f"{len(pending)} zone(s) [{zones}] · {age_str}"
            if not ok:
                detail += " — probablement perdue"
            checks.append({
                "id": "pending_consignes",
                "label": "Consignes en attente",
                "detail": detail,
                "ok": ok,
                "warn": warn,
            })
    except Exception as exc:
        checks.append({"id": "pending_consignes", "label": "Consignes en attente", "detail": str(exc), "ok": False})

    ok_count = sum(1 for c in checks if c.get("ok"))
    total = len(checks)
    return {
        "ok": ok_count == total,
        "passed": ok_count,
        "total": total,
        "checks": checks,
    }
