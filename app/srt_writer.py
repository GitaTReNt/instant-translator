import os, time

def fmt_ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000.0))
    h = ms // (3600*1000); ms %= (3600*1000)
    m = ms // (60*1000);   ms %= (60*1000)
    s = ms // 1000;        ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

class TxtWriter:
    def __init__(self, path):
        self.path = path
        self._f = None

    def open(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._f = open(self.path, "w", encoding="utf-8")
        self._f.write(f"# GuiLiveSubs session {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        self._f.flush()

    def write_line(self, src: str, tgt: str):
        if not self._f:
            return
        if src:
            self._f.write(src.strip() + "\n")
        if tgt:
            self._f.write(tgt.strip() + "\n")
        self._f.flush()

    def close(self):
        if self._f:
            self._f.close()
            self._f = None

class SrtWriter:
    def __init__(self, path, session_start_monotonic: float = 0.0):
        self.path = path
        self._f = None
        self.index = 0
        self.t0 = session_start_monotonic

    def open(self):
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._f = open(self.path, "w", encoding="utf-8")

    def write_caption(self, start_monotonic: float, end_monotonic: float, src: str, tgt: str):
        if not self._f:
            return
        self.index += 1
        start_rel = max(0.0, start_monotonic - self.t0)
        end_rel = max(start_rel, end_monotonic - self.t0)
        self._f.write(f"{self.index}\n")
        self._f.write(f"{fmt_ts(start_rel)} --> {fmt_ts(end_rel)}\n")
        lines = []
        if src:
            lines.append(src.strip())
        if tgt:
            lines.append(tgt.strip())
        self._f.write("\n".join(lines) + "\n\n")
        self._f.flush()

    def close(self):
        if self._f:
            self._f.close()
            self._f = None
