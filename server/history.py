"""Historisation des valeurs dans une base SQLite.

Deux flux sont persistés :
- les télémétries T.ONE (PUBLISH "in" de la box) : chaque champ numérique
  du payload est stocké comme un échantillon (ts, key, value) ;
- les événements de connexion (box et cloud) : booléen 1/0.

La rétention est paramétrable (jours). La table est purgée périodiquement.
Le stockage est thread-safe (verrou autour de chaque transaction).
"""
import json
import os
import sqlite3
import threading
import time


class HistoryDB:
    def __init__(self, path, retention_days=90):
        self._path = os.path.abspath(path)
        self._days = max(1, int(retention_days))
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    # --- schéma ---
    def _init_schema(self):
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS samples (
                    ts REAL NOT NULL,
                    kind TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_samples_key_ts
                    ON samples (key, ts);
                CREATE INDEX IF NOT EXISTS idx_samples_ts
                    ON samples (ts);
                """
            )
            self._conn.commit()

    @property
    def retention_days(self):
        return self._days

    # --- écriture ---
    def record_telemetry(self, payload):
        """Stocke les champs numériques d'un payload télémétrie (str ou dict)."""
        if isinstance(payload, bytes):
            try:
                payload = payload.decode("utf-8", errors="replace")
            except Exception:
                return 0
        if isinstance(payload, str):
            pos = payload.find("{")
            if pos < 0:
                return 0
            payload = payload[pos:]
            try:
                data = json.loads(payload)
            except Exception:
                return 0
        else:
            data = payload
        if not isinstance(data, dict):
            return 0
        now = time.time()
        rows = []
        for k, v in data.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                rows.append((now, "telemetry", k, float(v)))
        if not rows:
            return 0
        with self._lock:
            self._conn.executemany(
                "INSERT INTO samples (ts, kind, key, value) VALUES (?, ?, ?, ?)", rows
            )
            self._conn.commit()
        return len(rows)

    def record_status(self, key, value):
        """Stocke un événement de connexion : key dans ("box", "cloud")."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO samples (ts, kind, key, value) VALUES (?, 'status', ?, ?)",
                (time.time(), key, 1 if value else 0),
            )
            self._conn.commit()

    # --- lecture ---
    def keys(self):
        """Liste des clés disponibles avec métadonnées (nb échantillons, dernier ts)."""
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT key, kind, COUNT(*) AS n, MAX(ts) AS last_ts
                FROM samples
                GROUP BY key, kind
                ORDER BY key
                """
            )
            out = []
            for key, kind, n, last_ts in cur.fetchall():
                out.append({
                    "key": key,
                    "kind": kind,
                    "samples": n,
                    "last_ts": last_ts,
                })
            return out

    def series(self, key, start=None, end=None, bucket=None):
        """Série horodatée d'une clé, éventuellement agrégée par buckets de `bucket` s.

        Si bucket est fourni : renvoie min/max/avg par bucket. Sinon chaque
        échantillon brut (ts, value).
        """
        start = start if start is not None else 0.0
        end = end if end is not None else time.time() + 1
        params = [key, start, end]
        if bucket and bucket > 0:
            sql = (
                "SELECT CAST(ts / ? AS INTEGER) * ? AS t, "
                "       MIN(value) AS mn, MAX(value) AS mx, AVG(value) AS avg, COUNT(*) AS n "
                "FROM samples WHERE key = ? AND ts >= ? AND ts <= ? "
                "GROUP BY t ORDER BY t"
            )
            with self._lock:
                rows = self._conn.execute(
                    sql, [bucket, bucket, key, start, end]
                ).fetchall()
            return [
                {"ts": t + bucket / 2, "min": mn, "max": mx, "avg": avg, "n": n}
                for t, mn, mx, avg, n in rows
            ]
        sql = (
            "SELECT ts, value FROM samples WHERE key = ? AND ts >= ? AND ts <= ? "
            "ORDER BY ts"
        )
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [{"ts": ts, "value": value} for ts, value in rows]

    def table(self, start=None, end=None, limit=500, offset=0):
        """Échantillons bruts (toutes clés) pour la vue tableau, du plus récent au plus ancien."""
        start = start if start is not None else 0.0
        end = end if end is not None else time.time() + 1
        limit = max(1, min(limit, 5000))
        offset = max(0, offset)
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM samples WHERE ts >= ? AND ts <= ?",
                (start, end),
            )
            total = cur.fetchone()[0]
            rows = self._conn.execute(
                "SELECT ts, kind, key, value FROM samples "
                "WHERE ts >= ? AND ts <= ? ORDER BY ts DESC LIMIT ? OFFSET ?",
                (start, end, limit, offset),
            ).fetchall()
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "samples": [
                {"ts": ts, "kind": kind, "key": key, "value": value}
                for ts, kind, key, value in rows
            ],
        }

    # --- rétention ---
    def purge(self, days=None):
        """Supprime les échantillons plus vieux que `days` (défaut : rétention)."""
        days = days if days is not None else self._days
        cutoff = time.time() - days * 86400
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM samples WHERE ts < ?", (cutoff,)
            )
            self._conn.commit()
        return cur.rowcount

    def count(self):
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]

    def close(self):
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass