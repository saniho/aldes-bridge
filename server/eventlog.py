"""Persistance des evenements sur disque (JSONL append-only).

Le fichier tourne (rotation vers <fichier>.1) quand il depasse max_bytes ;
un seul anneau precedent est conserve, donc le stockage reste borne (~2x).
Lecture paginee depuis la fin (tail), sans reparcourir le fichier entier.
"""
import json
import os
import threading


class EventLog:
    def __init__(self, path, max_bytes=25 * 1024 * 1024):
        self._path = os.path.abspath(path)
        self._max = max_bytes
        self._lock = threading.Lock()
        self._fd = None
        self._count = 0
        self._size = 0
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        self._open(initial=os.path.exists(self._path))

    # --- écriture ---
    def _open(self, initial=False):
        if self._fd is not None:
            try:
                self._fd.close()
            except Exception:
                pass
        self._fd = open(self._path, "a", encoding="utf-8")
        try:
            self._size = os.path.getsize(self._path)
        except OSError:
            self._size = 0
        if initial:
            self._count = self._count_lines()

    def _count_lines(self):
        n = 0
        for f in self._files():
            try:
                with open(f, "rb") as fh:
                    for _ in fh:
                        n += 1
            except OSError:
                pass
        return n

    def _files(self):
        """Fichiers dans l'ordre temporel : actuel puis generations .1 / .2."""
        files = [self._path]
        for suf in (".1", ".2"):
            p = self._path + suf
            if os.path.exists(p):
                files.append(p)
        return files

    def _rotate(self):
        # decale les generations (.1 -> .2, actuel -> .1) puis repart sur un fichier neuf
        p1, p2 = self._path + ".1", self._path + ".2"
        try:
            self._fd.close()
        except Exception:
            pass
        if os.path.exists(p2):
            try:
                os.remove(p2)
            except OSError:
                pass
        if os.path.exists(p1):
            try:
                os.replace(p1, p2)
            except OSError:
                pass
        try:
            os.replace(self._path, p1)
        except OSError:
            pass
        self._fd = open(self._path, "a", encoding="utf-8")
        self._size = 0
        self._count = self._count_lines()

    def append(self, event):
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        data = line.encode("utf-8")
        with self._lock:
            if self._size + len(data) > self._max and self._size > 0:
                self._rotate()
            try:
                self._fd.write(line)
                self._fd.flush()
            except Exception:
                pass
            self._size += len(data)
            self._count += 1

    # --- lecture ---
    def total(self):
        with self._lock:
            return self._count

    def tail(self, limit=200, offset=0):
        """Derniers evenements, du plus recent au plus ancien."""
        with self._lock:
            raw = self._tail_lines(limit + offset)
        events = []
        for line in raw[offset:offset + limit]:
            try:
                events.append(json.loads(line))
            except Exception:
                continue
        return events

    def tail_oldest_first(self, limit=200):
        """Derniers evenements dans l'ordre chronologique (pour restaurer l'historique)."""
        return list(reversed(self.tail(limit, 0)))

    def _tail_lines(self, want):
        """Renvoie jusqu'a `want` lignes complètes, la plus recente en premier."""
        if want <= 0:
            return []
        lines = []
        for f in self._files():
            if len(lines) >= want:
                break
            carry = b""
            pos = 0
            try:
                size = os.path.getsize(f)
            except OSError:
                continue
            with open(f, "rb") as fh:
                pos = size
                while pos > 0 and len(lines) < want:
                    block = min(pos, 65536)
                    pos -= block
                    fh.seek(pos)
                    data = fh.read(block)
                    data = carry + data
                    parts = data.split(b"\n")
                    if pos > 0:
                        carry = parts.pop()
                    else:
                        carry = b""
                        if parts and parts[-1] == b"":
                            parts.pop()
                    for p in reversed(parts):
                        if p:
                            lines.append(p)
                            if len(lines) >= want:
                                break
        return [l.decode("utf-8", "replace") for l in lines]

    # --- nettoyage ---
    def clear(self):
        with self._lock:
            try:
                self._fd.close()
            except Exception:
                pass
            self._fd = None
            for f in self._files():
                try:
                    os.remove(f)
                except OSError:
                    pass
            self._fd = open(self._path, "a", encoding="utf-8")
            self._size = 0
            self._count = 0