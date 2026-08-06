"""Moteur : listener TLS unique + dispatch per-connexion selon le mode actif."""
import socket
import threading

from .tls import server_context
from .bridge import BridgeHandler
from .proxy import ProxyHandler


class Engine(threading.Thread):
    def __init__(self, state, mqtt_port=8883, bind="0.0.0.0"):
        super().__init__(daemon=True, name="engine")
        self.state = state
        self.mqtt_port = mqtt_port
        self.bind = bind
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._current = None  # handler de la session active
        self._sock = None

    def stop(self):
        self._stop.set()
        with self._lock:
            if self._current:
                self._current.shutdown()
        sock = self._sock
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    @property
    def current_handler(self):
        with self._lock:
            return self._current

    def run(self):
        ctx = server_context(self.state.real_host)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((self.bind, self.mqtt_port))
            sock.listen(8)
        except OSError as exc:
            self.state.set_error("bind %s:%d impossible: %s" % (self.bind, self.mqtt_port, exc))
            return
        self._sock = sock
        self.state.set_error(None)
        while not self._stop.is_set():
            try:
                c, addr = sock.accept()
            except OSError:
                if self._stop.is_set():
                    break
                continue
            try:
                cs = ctx.wrap_socket(c, server_side=True)
            except Exception as exc:
                try:
                    c.close()
                except Exception:
                    pass
                continue
            threading.Thread(
                target=self._handle, args=(cs, addr), daemon=True, name="conn"
            ).start()
        try:
            sock.close()
        except Exception:
            pass

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
        handler = self.current_handler
        if handler is None:
            return {"ok": False, "error": "aucune box connectee"}
        if not topic or not topic.strip():
            return {"ok": False, "error": "topic vide"}
        return handler.inject(topic.strip(), payload, qos)

    def disconnect(self):
        with self._lock:
            handler = self._current
        if handler:
            handler.shutdown()
            return {"ok": True, "session": "dropped"}
        return {"ok": True, "session": "none"}