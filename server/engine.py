"""Moteur : listener TLS unique + dispatch per-connexion selon le mode actif.

Modes:
  - proxy / bridge : la box se connecte ici (TLS 8883), on est MITM ou faux broker.
  - raw            : on se connecte en CLIENT a un broker MQTT externe
                     (server/raw.py) — pas de listener TLS.
"""
import socket
import threading
import time

from .tls import server_context
from .bridge import BridgeHandler
from .proxy import ProxyHandler
from .raw import RawClient


class Engine(threading.Thread):
    def __init__(self, state, mqtt_port=8883, bind="0.0.0.0"):
        super().__init__(daemon=True, name="engine")
        self.state = state
        self.mqtt_port = mqtt_port
        self.bind = bind
        self._stop_ev = threading.Event()
        self._lock = threading.Lock()
        self._current = None  # handler de la session active
        self._raw = None  # RawClient actif (mode raw)
        self._mode_changed = threading.Event()
        self._sock = None

    def stop(self):
        self._stop_ev.set()
        self._mode_changed.set()
        with self._lock:
            if self._current:
                self._current.shutdown()
            if self._raw:
                self._raw.stop()
        sock = self._sock
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    def set_mode(self, mode):
        """Appel par l'API : change l'etat et reveille le moteur."""
        self.state.set_mode(mode)
        self._mode_changed.set()

    @property
    def current_handler(self):
        with self._lock:
            return self._current

    def set_raw(self):
        """Re-configure le client raw en mode raw (appel par l'API)."""
        self._mode_changed.set()

    def _switch_raw(self, cfg):
        with self._lock:
            old, self._raw = self._raw, None
            if old:
                old.stop()
        if old:
            old.join(timeout=2)
        if cfg is not None:
            with self._lock:
                if self.state.mode == "raw":
                    self._raw = RawClient(self.state, cfg)
            if self._raw:
                self._raw.start()

    def run(self):
        while not self._stop_ev.is_set():
            self._mode_changed.clear()
            if self.state.mode == "raw":
                self._run_raw()
            else:
                self._run_listener()

    def _run_raw(self):
        cfg = self.state.raw_config()
        self._switch_raw(cfg)
        while not self._stop_ev.is_set() and not self._mode_changed.is_set():
            time.sleep(0.25)
        self._switch_raw(None)

    def _run_listener(self):
        ctx = server_context(self.state.real_host)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((self.bind, self.mqtt_port))
            sock.listen(8)
        except OSError as exc:
            self.state.set_error("bind %s:%d impossible: %s" % (self.bind, self.mqtt_port, exc))
            return
        sock.settimeout(0.5)
        self._sock = sock
        self.state.set_error(None)
        try:
            while not self._stop_ev.is_set() and not self._mode_changed.is_set():
                try:
                    c, addr = sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self._stop_ev.is_set() or self._mode_changed.is_set():
                        break
                    continue
                try:
                    cs = ctx.wrap_socket(c, server_side=True)
                except Exception:
                    try:
                        c.close()
                    except Exception:
                        pass
                    continue
                threading.Thread(
                    target=self._handle, args=(cs, addr), daemon=True, name="conn"
                ).start()
        finally:
            try:
                sock.close()
            except Exception:
                pass
            self._sock = None

    def _handle(self, cs, addr):
        mode = self.state.mode
        handler = BridgeHandler(self.state, cs, addr) if mode == "bridge" else ProxyHandler(self.state, cs, addr)
        with self._lock:
            self._current = handler
        try:
            handler.run()
        finally:
            with self._lock:
                if self._current is handler:
                    self._current = None
            self.state.session_down()
            try:
                cs.close()
            except Exception:
                pass

    # --- API pour l'UI ---
    def inject(self, topic, payload, qos):
        if self.state.mode == "raw":
            with self._lock:
                raw = self._raw
            if raw is None:
                return {"ok": False, "error": "mode raw inactif"}
            return raw.inject(topic, payload, qos)
        handler = self.current_handler
        if handler is None:
            return {"ok": False, "error": "aucune box connectee"}
        if not topic or not topic.strip():
            return {"ok": False, "error": "topic vide"}
        return handler.inject(topic.strip(), payload, qos)

    def disconnect(self):
        if self.state.mode == "raw":
            with self._lock:
                raw = self._raw
            if raw:
                raw.stop()
                return {"ok": True, "session": "dropped"}
            return {"ok": True, "session": "none"}
        with self._lock:
            handler = self._current
        if handler:
            handler.shutdown()
            return {"ok": True, "session": "dropped"}
        return {"ok": True, "session": "none"}
