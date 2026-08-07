"""Read-only log replay worker using the shared protocol parser."""

from __future__ import annotations

import csv
import queue
import threading
import time
from pathlib import Path

from .protocol import parse_machine_line


class ReplayWorker(threading.Thread):
    def __init__(self, connection_id: int, path: str, events: queue.Queue) -> None:
        super().__init__(name="bench-replay-worker", daemon=True)
        self.connection_id = connection_id
        self.path = Path(path)
        self.events = events
        self._shutdown = threading.Event()

    def emit(self, kind: str, payload: object = None) -> None:
        self.events.put((self.connection_id, kind, payload))

    def request_disconnect(self, *, send_stop: bool = False) -> None:
        del send_stop
        self._shutdown.set()

    @staticmethod
    def _line_from_row(row: list[str]) -> str:
        if len(row) >= 3 and row[1] in {"IBUS", "ESC", "MTEST", "MACK", "SENSORS", "ERRORS"}:
            return row[2]
        return ",".join(row)

    def run(self) -> None:
        try:
            self.emit("connected", f"Replay: {self.path.name}")
            count = 0
            with self.path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                for row in csv.reader(handle):
                    if self._shutdown.is_set():
                        break
                    if row and row[0] == "timestamp_pc":
                        continue
                    line = self._line_from_row(row).rstrip("\r\n")
                    if not line:
                        continue
                    count += 1
                    received = time.monotonic()
                    self.emit("line", (line, count, received))
                    try:
                        parsed = parse_machine_line(line)
                    except ValueError as exc:
                        prefix = line.split(",", 1)[0].lstrip("@") or "UNKNOWN"
                        self.emit("malformed", (prefix, str(exc)))
                    else:
                        if parsed is not None:
                            self.emit("record", (parsed, received))
                    if self._shutdown.wait(0.02):
                        break
        except OSError as exc:
            self.emit("serial_error", f"Replay error: {exc}")
        finally:
            self.emit("disconnected", None)
