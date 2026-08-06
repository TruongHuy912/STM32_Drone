"""Single owner thread for all serial RX and TX operations."""

from __future__ import annotations

import queue
import threading
import time
from typing import Optional

try:
    import serial
except ImportError:  # pragma: no cover - exercised on systems without pyserial
    serial = None

from .controller import OutgoingQueue
from .models import TxRequest
from .protocol import format_stop_command, parse_machine_line


def friendly_serial_error(exc: BaseException) -> str:
    text = str(exc)
    lowered = text.lower()
    if isinstance(exc, PermissionError) or "access is denied" in lowered or "permission" in lowered:
        return "COM port is busy. Close PuTTY or any other serial application."
    return f"Serial connection error: {text}"


class SerialWorker(threading.Thread):
    def __init__(
        self,
        connection_id: int,
        port_name: str,
        baud: int,
        events: queue.Queue,
        outgoing: OutgoingQueue,
    ) -> None:
        super().__init__(name="bench-serial-worker", daemon=True)
        self.connection_id = connection_id
        self.port_name = port_name
        self.baud = baud
        self.events = events
        self.outgoing = outgoing
        self._shutdown = threading.Event()
        self._send_stop_on_shutdown = False
        self._port_lock = threading.Lock()
        self._port = None
        self.rx_line_count = 0
        self.tx_command_count = 0

    def emit(self, kind: str, payload: object = None) -> None:
        self.events.put((self.connection_id, kind, payload))

    def request_disconnect(self, *, send_stop: bool = True) -> None:
        self.outgoing.remove_kind("RUN")
        self._send_stop_on_shutdown = self._send_stop_on_shutdown or send_stop
        self._shutdown.set()

    def _write(self, port: object, request: TxRequest) -> None:
        port.write(request.payload)  # type: ignore[attr-defined]
        self.tx_command_count += 1
        self.emit("tx", (request, self.tx_command_count))

    def _best_effort_stop(self, port: object) -> None:
        try:
            port.write(format_stop_command())  # type: ignore[attr-defined]
            self.tx_command_count += 1
            self.emit(
                "tx",
                (TxRequest("STOP", format_stop_command(), "MTEST STOP"), self.tx_command_count),
            )
        except Exception:
            pass

    def run(self) -> None:
        if serial is None:
            self.emit("serial_error", "pyserial is not installed")
            self.emit("disconnected", None)
            return

        port = None
        try:
            port = serial.Serial(
                port=self.port_name,
                baudrate=self.baud,
                timeout=0.04,
                write_timeout=0.1,
            )
            with self._port_lock:
                self._port = port
            self.emit("connected", f"{self.port_name} @ {self.baud}")

            while not self._shutdown.is_set():
                for _ in range(4):
                    request = self.outgoing.get(timeout=0.0)
                    if request is None:
                        break
                    self._write(port, request)

                raw_line = port.read_until(b"\n", 768)
                if not raw_line:
                    continue
                line = raw_line.decode("ascii", errors="replace").rstrip("\r\n")
                self.rx_line_count += 1
                self.emit("line", (line, self.rx_line_count, time.monotonic()))
                try:
                    parsed = parse_machine_line(line)
                except ValueError as exc:
                    prefix = line.split(",", 1)[0].lstrip("@") or "UNKNOWN"
                    self.emit("malformed", (prefix, str(exc)))
                else:
                    if parsed is not None:
                        self.emit("record", (parsed, time.monotonic()))

            if self._send_stop_on_shutdown and port.is_open:
                self._best_effort_stop(port)
                time.sleep(0.03)
        except Exception as exc:
            if port is not None:
                self._best_effort_stop(port)
            self.emit("serial_error", friendly_serial_error(exc))
        finally:
            with self._port_lock:
                self._port = None
            if port is not None:
                try:
                    port.close()
                except Exception:
                    pass
            self.emit("disconnected", None)
