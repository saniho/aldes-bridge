"""Moteur : listener TLS unique + dispatch per-connexion selon le mode actif.

Modes:
  - proxy / bridge : la box se connecte ici (TLS 8883), on est MITM ou faux broker.
  - raw            : on se connecte en CLIENT a un broker MQTT externe
                     (server/raw.py) — pas de listener TLS.
"""
import logging
import socket
import threading
import time

from .tls import server_context
from .appstate import set_conn_ctx, clear_conn_ctx

_log = logging.getLogger("aldes-engine")
from .bridge import BridgeHandler
from .proxy import ProxyHandler
from .listen import ListenHandler
from .raw import RawClient


class SessionRegistry:
    """Garde la trace de la session MQTT vivante et de ses identifiants.

    Centralise la logique de prise de relai entre connexions : quand une
    nouvelle connexion arrive, elle devient la session courante et l'ancienne
    est marquee `stale` — son nettoyage final (release) ne doit alors plus
    toucher l'etat partage (course deconnexion/reconnexion de la box).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._current = None
        self._next_id = 1

    def register(self, handler):
        """Enregistre une nouvelle session : prend le relai de la precedente
        (marquee stale). Renvoie un identifiant de session unique."""
        with self._lock:
            session_id = self._next_id
            self._next_id += 1
            old = self._current
            self._current = handler
        if old is not None:
            old.stale = True
        return session_id

    @property
    def current(self):
        with self._lock:
            return self._current

    def release(self, handler):
        """Fin de vie d'une session : True si `handler` etait encore la session
        courante (elle est retiree), False si elle avait deja ete remplacee
        (stale) — son teardown ne doit alors pas ecraser l'etat."""
        with self._lock:
            if self._current is handler:
                self._current = None
                return True
        return False


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
        self._sessions = SessionRegistry()

    def stop(self):
        self._stop_ev.set()
        self._mode_changed.set()
        current = self._sessions.current
        if current:
            current.shutdown()
        with self._lock:
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
        return self._sessions.current

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
                self.state.events.publish({"kind": "status", "ts": "now", "note": "MQTT conn from %s:%d" % (addr[0], addr[1])})
                try:
                    cs = ctx.wrap_socket(c, server_side=True)
                except Exception as exc:
                    self.state.events.publish({"kind": "status", "ts": "now", "note": "TLS handshake FAILED from %s:%d: %s" % (addr[0], addr[1], exc)})
                    try:
                        c.close()
                    except Exception:
                        pass
                    continue
                self.state.events.publish({"kind": "status", "ts": "now", "note": "TLS OK from %s:%d" % (addr[0], addr[1])})
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
        if mode == "bridge":
            handler = BridgeHandler(self.state, cs, addr)
        elif mode == "listen":
            handler = ListenHandler(self.state, cs, addr)
        else:
            handler = ProxyHandler(self.state, cs, addr)
        # Prise de relai : devient la session courante, l'ancienne est stale.
        session = self._sessions.register(handler)
        handler.session = session
        set_conn_ctx(session, addr[0])
        try:
            handler.run()
        finally:
            clear_conn_ctx()
            # Seule la session encore courante pose session_down : une session
            # remplacee (stale) ne doit pas ecraser l'etat de la session vivante
            # (course a la deconnexion/reconnexion de la box).
            if self._sessions.release(handler):
                self.state.session_down()
            try:
                cs.close()
            except Exception:
                pass

    # --- API pour l'UI ---
    def inject(self, topic, payload, qos):
        _log.info("inject: topic=%s payload=%s qos=%d mode=%s", topic, payload[:200] if isinstance(payload, str) else payload, qos, self.state.mode)
        if self.state.mode == "raw":
            with self._lock:
                raw = self._raw
            if raw is None:
                _log.warning("inject: mode raw inactif, commande abandonnee")
                return {"ok": False, "error": "mode raw inactif"}
            return raw.inject(topic, payload, qos)
        handler = self.current_handler
        if handler is None:
            _log.warning("inject: aucune box connectee, commande abandonnee")
            return {"ok": False, "error": "aucune box connectee"}
        if not topic or not topic.strip():
            _log.warning("inject: topic vide, commande abandonnee")
            return {"ok": False, "error": "topic vide"}
        result = handler.inject(topic.strip(), payload, qos)
        _log.info("inject: resultat=%s", result)
        return result

    def disconnect(self):
        if self.state.mode == "raw":
            with self._lock:
                raw = self._raw
            if raw:
                raw.drop()
                return {"ok": True, "session": "dropped"}
            return {"ok": True, "session": "none"}
        handler = self._sessions.current
        if handler:
            handler.shutdown()
            return {"ok": True, "session": "dropped"}
        return {"ok": True, "session": "none"}
