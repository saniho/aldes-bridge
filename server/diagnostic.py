"""Diagnostic (check-up systeme) — extrait de api.py."""
import os
import resource
import socket
import subprocess
import time
from datetime import datetime, timezone

import logging

_log = logging.getLogger("aldes-diagnostic")

_PROCESS_START = time.time()


def _check_dns_doh(state):
    try:
        from ..tls import _doh_query
        ip = _doh_query(state.real_host, timeout=5)
        return {
            "id": "dns_doh", "label": "DNS DoH (Cloudflare)",
            "detail": f"{state.real_host} → {ip}" if ip else "Pas de réponse A record",
            "ok": ip is not None, "ip": ip,
        }
    except Exception as exc:
        return {"id": "dns_doh", "label": "DNS DoH (Cloudflare)", "detail": str(exc), "ok": False}


def _check_dns_system(state):
    try:
        ip_sys = socket.gethostbyname(state.real_host)
        is_local = ip_sys in ("127.0.0.1", "::1", state._azure_ip)
        return {
            "id": "dns_system", "label": "DNS systeme (dnsmasq)",
            "detail": f"{state.real_host} → {ip_sys}" + (" — resolu vers le bridge !" if is_local else ""),
            "ok": not is_local, "ip": ip_sys, "warn": is_local,
        }
    except Exception as exc:
        return {"id": "dns_system", "label": "DNS systeme (dnsmasq)", "detail": str(exc), "ok": False}


def _check_azure_ip(state):
    azure_ip = state._azure_ip
    return {
        "id": "azure_ip", "label": "IP Azure résolue",
        "detail": azure_ip or "Non résolue",
        "ok": azure_ip is not None, "ip": azure_ip,
    }


def _check_tcp_azure(state):
    azure_ip = state._azure_ip
    if not azure_ip:
        return {"id": "tcp_azure", "label": "TCP Azure", "detail": "IP non resolue — test impossible", "ok": False}
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((azure_ip, 8883))
        sock.close()
        return {
            "id": "tcp_azure", "label": f"TCP Azure ({azure_ip}:8883)",
            "detail": "Atteignable" if result == 0 else f"Refuse (errno {result})",
            "ok": result == 0,
        }
    except Exception as exc:
        return {"id": "tcp_azure", "label": f"TCP Azure ({azure_ip}:8883)", "detail": str(exc), "ok": False}


def _check_mqtt_listener(engine):
    try:
        port = engine.mqtt_port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        return {
            "id": "mqtt_listener", "label": f"Listener MQTT (:{port})",
            "detail": "En écoute" if result == 0 else "Pas en écoute",
            "ok": result == 0,
        }
    except Exception as exc:
        return {"id": "mqtt_listener", "label": "Listener MQTT", "detail": str(exc), "ok": False}


def _check_iptables():
    try:
        out = subprocess.check_output(
            ["iptables", "-t", "nat", "-L", "PREROUTING", "-n", "--line-numbers"],
            stderr=subprocess.STDOUT, timeout=3,
        ).decode(errors="replace")
        has_8883 = "8883" in out
        rules = [l for l in out.splitlines() if "8883" in l]
        return {
            "id": "iptables", "label": "iptables PREROUTING",
            "detail": f"{len(rules)} règle(s) REDIRECT 8883" if has_8883 else "Aucune règle 8883",
            "ok": has_8883, "rules": rules,
        }
    except FileNotFoundError:
        return {"id": "iptables", "label": "iptables", "detail": "iptables non disponible", "ok": False, "warn": True}
    except Exception as exc:
        return {"id": "iptables", "label": "iptables", "detail": str(exc), "ok": False}


def _check_box_connected(state):
    with state._lock:
        box_connected = state._connected
        box_ip = state._client_id
    return {
        "id": "box_connected", "label": "Box Aldes",
        "detail": f"Connectée (client: {box_ip})" if box_connected else "Non connectée",
        "ok": box_connected,
    }


def _check_cloud_connected(state):
    with state._lock:
        cloud_connected = state._cloud_since is not None
    return {
        "id": "cloud_connected", "label": "Azure IoT Hub (cloud)",
        "detail": "Connecté" if cloud_connected else "Non connecté",
        "ok": cloud_connected,
    }


def _check_mode(state):
    return {
        "id": "mode", "label": "Mode actif",
        "detail": state.mode,
        "ok": state.mode in ("proxy", "bridge"),
    }


def _check_version(state):
    return {
        "id": "version", "label": "Version",
        "detail": f"Backend {state.server_version} · UI {state.ui_version}",
        "ok": True,
    }


def _check_ha_mqtt_broker(state):
    ha_mqtt = getattr(state, "_ha_mqtt_resolved", None)
    if ha_mqtt:
        source_label = {"supervisor": "Supervisor API", "cli": "CLI", "fallback": "Fallback"}.get(ha_mqtt["source"], ha_mqtt["source"])
        return {
            "id": "ha_mqtt_broker", "label": "Broker MQTT HA",
            "detail": f"{source_label} → {ha_mqtt['host']}:{ha_mqtt['port']}",
            "ok": True, "host": ha_mqtt["host"], "port": ha_mqtt["port"], "source": ha_mqtt["source"],
        }
    return {
        "id": "ha_mqtt_broker", "label": "Broker MQTT HA",
        "detail": "Desactive (--ha-mqtt non utilise)",
        "ok": False, "warn": True,
    }


def _check_tls_cert(state):
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
            return {"id": "tls_cert", "label": "Certificat TLS", "detail": detail, "ok": ok, "warn": warn}
        finally:
            os.unlink(cert_path)
            os.unlink(key_path)
    except Exception as exc:
        return {"id": "tls_cert", "label": "Certificat TLS", "detail": str(exc), "ok": False}


def _check_azure_latency(state):
    azure_ip = state._azure_ip
    if not azure_ip:
        return {"id": "azure_latency", "label": "Latence Azure", "detail": "IP non resolue", "ok": False}
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        t0 = time.monotonic()
        result_tcp = sock.connect_ex((azure_ip, 8883))
        rtt_ms = (time.monotonic() - t0) * 1000
        sock.close()
        if result_tcp == 0:
            detail = f"{rtt_ms:.0f} ms" + (" (lent)" if rtt_ms > 1000 else "")
            return {"id": "azure_latency", "label": "Latence Azure", "detail": detail, "ok": rtt_ms < 1000, "warn": rtt_ms > 500}
        return {"id": "azure_latency", "label": "Latence Azure", "detail": f"Refuse (errno {result_tcp})", "ok": False}
    except Exception as exc:
        return {"id": "azure_latency", "label": "Latence Azure", "detail": str(exc), "ok": False}


def _check_process_health():
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
        return {
            "id": "process_health", "label": "Processus backend",
            "detail": f"Uptime {uptime_str} · {mem_mb:.0f} Mo RSS",
            "ok": True,
        }
    except Exception as exc:
        return {"id": "process_health", "label": "Processus backend", "detail": str(exc), "ok": False}


def _check_pending_consignes(state):
    try:
        with state._lock:
            consignes = {k: dict(v) for k, v in state._consignes.items()}
        pending = {z: c for z, c in consignes.items() if not c.get("confirmed")}
        if not pending:
            return {
                "id": "pending_consignes", "label": "Consignes en attente",
                "detail": "Aucune consigne en attente", "ok": True,
            }
        now_ts = time.time()
        oldest_age = 0
        for z, c in pending.items():
            try:
                ts_str = c.get("ts", "")
                if ts_str:
                    ts_dt = datetime.fromisoformat(ts_str)
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
        return {"id": "pending_consignes", "label": "Consignes en attente", "detail": detail, "ok": ok, "warn": warn}
    except Exception as exc:
        return {"id": "pending_consignes", "label": "Consignes en attente", "detail": str(exc), "ok": False}


def run_diagnostic(state, engine):
    """Execute tous les checks de diagnostic et retourne le dict complet."""
    checks = [
        _check_dns_doh(state),
        _check_dns_system(state),
        _check_azure_ip(state),
        _check_tcp_azure(state),
        _check_mqtt_listener(engine),
        _check_iptables(),
        _check_box_connected(state),
        _check_cloud_connected(state),
        _check_mode(state),
        _check_version(state),
        _check_ha_mqtt_broker(state),
        _check_tls_cert(state),
        _check_azure_latency(state),
        _check_process_health(),
        _check_pending_consignes(state),
    ]
    ok_count = sum(1 for c in checks if c.get("ok"))
    return {
        "ok": ok_count == len(checks),
        "passed": ok_count,
        "total": len(checks),
        "checks": checks,
    }
