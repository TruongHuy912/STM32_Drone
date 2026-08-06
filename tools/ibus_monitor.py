#!/usr/bin/env python3
"""Tkinter monitor for machine-readable FlySky iBUS lines from USART1."""

from __future__ import annotations

import argparse
import csv
import math
import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional, TextIO

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None


IBUS_PREFIX = "@IBUS,"
IBUS_FIELD_COUNT = 16
DISPLAY_MIN = 800
DISPLAY_MAX = 2200
NORMAL_MIN = 1000
NORMAL_MAX = 2000
CENTER_VALUE = 1500
QUEUE_POLL_MS = 30
GUI_AGE_UPDATE_MS = 100
SERIAL_READ_LIMIT = 512

CHANNEL_NAMES = (
    "CH1 Roll",
    "CH2 Pitch",
    "CH3 Throttle",
    "CH4 Yaw",
    "CH5 AUX1",
    "CH6 AUX2",
    "CH7 AUX3",
    "CH8 AUX4",
)

CSV_HEADER = (
    "timestamp_pc",
    "timestamp_us",
    "stream_alive",
    "age_ms",
    "ch1",
    "ch2",
    "ch3",
    "ch4",
    "ch5",
    "ch6",
    "ch7",
    "ch8",
    "valid_frames",
    "checksum_errors",
    "uart_errors",
    "ring_overflows",
)


@dataclass(frozen=True)
class IBusRecord:
    timestamp_us: int
    stream_alive: int
    age_ms: int
    channels: tuple[int, int, int, int, int, int, int, int]
    valid_frames: int
    checksum_errors: int
    uart_errors: int
    ring_overflows: int


def parse_ibus_line(line: str) -> Optional[IBusRecord]:
    """Return None for unrelated logs and raise ValueError for malformed @IBUS."""
    line = line.rstrip("\r\n")
    if not line.startswith(IBUS_PREFIX):
        return None

    fields = line.split(",")
    if len(fields) != IBUS_FIELD_COUNT or fields[0] != "@IBUS":
        raise ValueError("wrong field count")

    numeric_fields = fields[1:]
    if any(
        not field or not field.isascii() or not field.isdecimal()
        for field in numeric_fields
    ):
        raise ValueError("non-decimal or whitespace-containing field")

    values = [int(field, 10) for field in numeric_fields]
    timestamp_us, stream_alive, age_ms = values[0:3]
    channels = tuple(values[3:11])
    valid_frames, checksum_errors, uart_errors, ring_overflows = values[11:15]

    if timestamp_us > 0xFFFFFFFF or age_ms > 0xFFFFFFFF:
        raise ValueError("timestamp or age outside uint32 range")
    if stream_alive not in (0, 1):
        raise ValueError("stream_alive must be 0 or 1")
    if any(channel > 0xFFFF for channel in channels):
        raise ValueError("channel outside uint16 range")
    if any(value > 0xFFFFFFFF for value in values[11:15]):
        raise ValueError("counter outside uint32 range")

    return IBusRecord(
        timestamp_us=timestamp_us,
        stream_alive=stream_alive,
        age_ms=age_ms,
        channels=channels,  # type: ignore[arg-type]
        valid_frames=valid_frames,
        checksum_errors=checksum_errors,
        uart_errors=uart_errors,
        ring_overflows=ring_overflows,
    )


class SerialReader(threading.Thread):
    """Own the serial port and send parsed events to the Tkinter thread."""

    def __init__(
        self,
        connection_id: int,
        port_name: str,
        baud: int,
        events: queue.Queue,
    ) -> None:
        super().__init__(name="ibus-serial-reader", daemon=True)
        self.connection_id = connection_id
        self.port_name = port_name
        self.baud = baud
        self.events = events
        self.stop_event = threading.Event()
        self.serial_lock = threading.Lock()
        self.serial_port = None

    def emit(self, kind: str, payload: object = None) -> None:
        self.events.put((self.connection_id, kind, payload))

    def stop(self) -> None:
        self.stop_event.set()
        with self.serial_lock:
            port = self.serial_port
        if port is not None:
            try:
                port.close()
            except Exception:
                pass

    def run(self) -> None:
        if serial is None:
            self.emit("error", "pyserial is not installed")
            self.emit("disconnected", True)
            return

        port = None
        had_error = False
        try:
            port = serial.Serial(
                port=self.port_name,
                baudrate=self.baud,
                timeout=0.2,
                write_timeout=0.2,
            )
            with self.serial_lock:
                self.serial_port = port
            self.emit("connected", f"{self.port_name} @ {self.baud}")

            while not self.stop_event.is_set():
                raw_line = port.read_until(b"\n", SERIAL_READ_LIMIT)
                if not raw_line:
                    continue

                line = raw_line.decode("ascii", errors="replace").rstrip("\r\n")
                if not line.startswith(IBUS_PREFIX):
                    continue

                try:
                    record = parse_ibus_line(line)
                except ValueError:
                    self.emit("malformed", line)
                    continue

                if record is not None:
                    self.emit("record", record)
        except Exception as exc:
            if not self.stop_event.is_set():
                had_error = True
                self.emit("error", str(exc))
        finally:
            with self.serial_lock:
                self.serial_port = None
            if port is not None:
                try:
                    port.close()
                except Exception:
                    pass
            self.emit("disconnected", had_error)


class ChannelBar:
    def __init__(self, parent: ttk.Frame, row: int, name: str) -> None:
        self.name = name
        self.value = 0
        self.alive = False

        ttk.Label(parent, text=name, width=14).grid(
            row=row, column=0, padx=(4, 8), pady=3, sticky="w"
        )
        self.canvas = tk.Canvas(
            parent,
            height=24,
            width=560,
            highlightthickness=1,
            highlightbackground="#9aa0a6",
        )
        self.canvas.grid(row=row, column=1, padx=4, pady=3, sticky="ew")
        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.value_label = tk.Label(
            parent, text="0", width=7, anchor="e", font=("Segoe UI", 10, "bold")
        )
        self.value_label.grid(row=row, column=2, padx=(8, 4), pady=3)

    def set(self, value: int, alive: bool) -> None:
        self.value = value
        self.alive = alive
        self.redraw()

    def redraw(self) -> None:
        width = max(self.canvas.winfo_width(), 20)
        height = max(self.canvas.winfo_height(), 20)
        margin = 3
        usable = max(width - (2 * margin), 1)

        def x_for(value: int) -> float:
            return margin + ((value - DISPLAY_MIN) * usable / (DISPLAY_MAX - DISPLAY_MIN))

        display_value = min(max(self.value, DISPLAY_MIN), DISPLAY_MAX)
        self.canvas.delete("all")

        if self.alive:
            background = "#edf1f4"
            normal = "#d9f2df"
            fill = "#3182ce"
            center = "#202124"
            value_color = "#b00020" if not (
                DISPLAY_MIN <= self.value <= DISPLAY_MAX
            ) else "#202124"
        else:
            background = "#e0e0e0"
            normal = "#cccccc"
            fill = "#9e9e9e"
            center = "#777777"
            value_color = "#777777"

        self.canvas.create_rectangle(
            margin, margin, width - margin, height - margin,
            fill=background, outline=""
        )
        self.canvas.create_rectangle(
            x_for(NORMAL_MIN), margin, x_for(NORMAL_MAX), height - margin,
            fill=normal, outline=""
        )
        self.canvas.create_rectangle(
            x_for(DISPLAY_MIN), margin, x_for(display_value), height - margin,
            fill=fill, outline=""
        )
        self.canvas.create_line(
            x_for(CENTER_VALUE), margin, x_for(CENTER_VALUE), height - margin,
            fill=center, width=2
        )
        self.value_label.configure(text=str(self.value), foreground=value_color)


class IBusMonitorApp:
    def __init__(
        self,
        root: tk.Tk,
        initial_port: Optional[str],
        baud: int,
        demo: bool,
    ) -> None:
        self.root = root
        self.root.title("FlySky iBUS Monitor — STM32H743")
        self.root.minsize(820, 650)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.events: queue.Queue = queue.Queue()
        self.reader: Optional[SerialReader] = None
        self.connection_id = 0
        self.demo_mode = demo
        self.demo_after_id: Optional[str] = None
        self.demo_start = time.monotonic()
        self.demo_last_valid = self.demo_start
        self.demo_valid_frames = 0
        self.demo_channels = [1500] * 8

        self.malformed_line_count = 0
        self.last_gui_data_monotonic: Optional[float] = None
        self.csv_file: Optional[TextIO] = None
        self.csv_writer: Optional[csv.writer] = None

        self.port_var = tk.StringVar(value=initial_port or "")
        self.baud_var = tk.StringVar(value=str(baud))
        self.serial_status_var = tk.StringVar(value="Disconnected")
        self.link_status_var = tk.StringVar(value="LINK LOST")
        self.age_var = tk.StringVar(value="Frame age: -- ms")
        self.timestamp_var = tk.StringVar(value="timestamp_us: --")
        self.valid_var = tk.StringVar(value="0")
        self.checksum_var = tk.StringVar(value="0")
        self.uart_var = tk.StringVar(value="0")
        self.overflow_var = tk.StringVar(value="0")
        self.malformed_var = tk.StringVar(value="0")
        self.gui_age_var = tk.StringVar(value="No GUI data received")
        self.csv_status_var = tk.StringVar(value="CSV logging stopped")

        self._build_interface()
        self.refresh_ports()
        self.root.after(QUEUE_POLL_MS, self._process_events)
        self.root.after(GUI_AGE_UPDATE_MS, self._update_gui_age)

        if self.demo_mode:
            self._start_demo()
        elif initial_port:
            self.root.after(150, self.connect)

    def _build_interface(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        connection = ttk.LabelFrame(self.root, text="Serial connection")
        connection.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        connection.columnconfigure(1, weight=1)

        ttk.Label(connection, text="COM port").grid(row=0, column=0, padx=5, pady=6)
        self.port_combo = ttk.Combobox(
            connection, textvariable=self.port_var, width=16, state="normal"
        )
        self.port_combo.grid(row=0, column=1, padx=5, pady=6, sticky="w")
        self.refresh_button = ttk.Button(connection, text="Refresh", command=self.refresh_ports)
        self.refresh_button.grid(row=0, column=2, padx=5, pady=6)

        ttk.Label(connection, text="Baud").grid(row=0, column=3, padx=5, pady=6)
        self.baud_combo = ttk.Combobox(
            connection,
            textvariable=self.baud_var,
            values=("115200",),
            width=10,
            state="normal",
        )
        self.baud_combo.grid(row=0, column=4, padx=5, pady=6)
        self.connect_button = ttk.Button(connection, text="Connect", command=self.connect)
        self.connect_button.grid(row=0, column=5, padx=5, pady=6)
        self.disconnect_button = ttk.Button(
            connection, text="Disconnect", command=self.disconnect, state="disabled"
        )
        self.disconnect_button.grid(row=0, column=6, padx=5, pady=6)
        ttk.Label(connection, textvariable=self.serial_status_var).grid(
            row=1, column=0, columnspan=7, padx=5, pady=(0, 6), sticky="w"
        )

        link = ttk.LabelFrame(self.root, text="iBUS link")
        link.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.link_label = tk.Label(
            link,
            textvariable=self.link_status_var,
            background="#b3261e",
            foreground="white",
            font=("Segoe UI", 16, "bold"),
            padx=14,
            pady=5,
        )
        self.link_label.grid(row=0, column=0, padx=8, pady=8)
        ttk.Label(link, textvariable=self.age_var).grid(row=0, column=1, padx=15)
        ttk.Label(link, textvariable=self.timestamp_var).grid(row=0, column=2, padx=15)

        channels_frame = ttk.LabelFrame(self.root, text="RC channels")
        channels_frame.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")
        channels_frame.columnconfigure(1, weight=1)
        ttk.Label(
            channels_frame,
            text="Display 800–2200  |  normal 1000–2000  |  center marker 1500",
        ).grid(row=0, column=0, columnspan=3, padx=5, pady=(5, 2), sticky="w")
        self.channel_bars = [
            ChannelBar(channels_frame, index + 1, name)
            for index, name in enumerate(CHANNEL_NAMES)
        ]

        diagnostics = ttk.LabelFrame(self.root, text="Diagnostics")
        diagnostics.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        diagnostic_items = (
            ("Valid frames", self.valid_var),
            ("Checksum errors", self.checksum_var),
            ("UART errors", self.uart_var),
            ("Ring overflows", self.overflow_var),
            ("Malformed @IBUS lines", self.malformed_var),
        )
        for index, (label, variable) in enumerate(diagnostic_items):
            ttk.Label(diagnostics, text=f"{label}:").grid(
                row=0, column=index * 2, padx=(6, 2), pady=6, sticky="e"
            )
            ttk.Label(diagnostics, textvariable=variable).grid(
                row=0, column=(index * 2) + 1, padx=(2, 10), pady=6, sticky="w"
            )
        ttk.Label(diagnostics, textvariable=self.gui_age_var).grid(
            row=1, column=0, columnspan=10, padx=6, pady=(0, 6), sticky="w"
        )

        logging_frame = ttk.LabelFrame(self.root, text="Optional CSV logging")
        logging_frame.grid(row=4, column=0, padx=10, pady=(5, 10), sticky="ew")
        self.start_log_button = ttk.Button(
            logging_frame, text="Start CSV Log", command=self.start_csv_log
        )
        self.start_log_button.grid(row=0, column=0, padx=6, pady=6)
        self.stop_log_button = ttk.Button(
            logging_frame, text="Stop CSV Log", command=self.stop_csv_log,
            state="disabled"
        )
        self.stop_log_button.grid(row=0, column=1, padx=6, pady=6)
        ttk.Label(logging_frame, textvariable=self.csv_status_var).grid(
            row=0, column=2, padx=10, pady=6, sticky="w"
        )

    def refresh_ports(self) -> None:
        current = self.port_var.get().strip()
        ports = []
        if list_ports is not None:
            try:
                ports = sorted(port.device for port in list_ports.comports())
            except Exception as exc:
                self.serial_status_var.set(f"Port refresh failed: {exc}")
        if current and current not in ports:
            ports.insert(0, current)
        self.port_combo.configure(values=ports)
        if not current and ports:
            self.port_var.set(ports[0])

    def connect(self) -> None:
        if self.demo_mode:
            return
        if serial is None:
            messagebox.showerror(
                "pyserial missing",
                "Install pyserial with: py -m pip install pyserial",
            )
            return

        port_name = self.port_var.get().strip()
        if not port_name:
            messagebox.showwarning("COM port", "Select or enter a COM port.")
            return
        try:
            baud = int(self.baud_var.get(), 10)
            if baud <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Baud", "Baud must be a positive integer.")
            return

        self.disconnect()
        self.connection_id += 1
        self.reader = SerialReader(
            self.connection_id, port_name, baud, self.events
        )
        self.serial_status_var.set(f"Connecting to {port_name}...")
        self.connect_button.configure(state="disabled")
        self.disconnect_button.configure(state="normal")
        self.reader.start()

    def disconnect(self) -> None:
        reader = self.reader
        self.reader = None
        self.connection_id += 1
        if reader is not None:
            reader.stop()
        if not self.demo_mode:
            self.serial_status_var.set("Disconnected")
            self.connect_button.configure(state="normal")
            self.disconnect_button.configure(state="disabled")

    def _process_events(self) -> None:
        try:
            while True:
                connection_id, kind, payload = self.events.get_nowait()
                if connection_id != self.connection_id:
                    continue
                if kind == "connected":
                    self.serial_status_var.set(f"Connected: {payload}")
                    self.connect_button.configure(state="disabled")
                    self.disconnect_button.configure(state="normal")
                elif kind == "record" and isinstance(payload, IBusRecord):
                    self._handle_record(payload)
                elif kind == "malformed":
                    self.malformed_line_count += 1
                    self.malformed_var.set(str(self.malformed_line_count))
                elif kind == "error":
                    self.serial_status_var.set(f"Serial error: {payload}")
                elif kind == "disconnected":
                    self.reader = None
                    if not payload:
                        self.serial_status_var.set("Disconnected")
                    self.connect_button.configure(state="normal")
                    self.disconnect_button.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(QUEUE_POLL_MS, self._process_events)

    def _handle_record(self, record: IBusRecord) -> None:
        alive = record.stream_alive == 1
        self.last_gui_data_monotonic = time.monotonic()
        self.link_status_var.set("LINK OK" if alive else "LINK LOST")
        self.link_label.configure(background="#188038" if alive else "#b3261e")
        self.age_var.set(f"Frame age: {record.age_ms} ms")
        self.timestamp_var.set(f"timestamp_us: {record.timestamp_us}")

        for bar, value in zip(self.channel_bars, record.channels):
            bar.set(value, alive)

        self.valid_var.set(str(record.valid_frames))
        self.checksum_var.set(str(record.checksum_errors))
        self.uart_var.set(str(record.uart_errors))
        self.overflow_var.set(str(record.ring_overflows))
        self._write_csv_record(record)

    def _update_gui_age(self) -> None:
        if self.last_gui_data_monotonic is None:
            self.gui_age_var.set("No GUI data received")
        else:
            age = time.monotonic() - self.last_gui_data_monotonic
            self.gui_age_var.set(f"Last GUI data: {age:.1f} s ago")
        self.root.after(GUI_AGE_UPDATE_MS, self._update_gui_age)

    def start_csv_log(self) -> None:
        if self.csv_file is not None:
            return
        try:
            project_root = Path(__file__).resolve().parent.parent
            logs_dir = project_root / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            filename = datetime.now().strftime("ibus_%Y%m%d_%H%M%S.csv")
            path = logs_dir / filename
            self.csv_file = path.open("w", newline="", encoding="utf-8")
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(CSV_HEADER)
            self.csv_file.flush()
            self.csv_status_var.set(f"Logging: {path}")
            self.start_log_button.configure(state="disabled")
            self.stop_log_button.configure(state="normal")
        except OSError as exc:
            self.csv_file = None
            self.csv_writer = None
            messagebox.showerror("CSV logging", str(exc))

    def stop_csv_log(self) -> None:
        if self.csv_file is not None:
            try:
                self.csv_file.close()
            except OSError:
                pass
        self.csv_file = None
        self.csv_writer = None
        self.csv_status_var.set("CSV logging stopped")
        self.start_log_button.configure(state="normal")
        self.stop_log_button.configure(state="disabled")

    def _write_csv_record(self, record: IBusRecord) -> None:
        if self.csv_writer is None or self.csv_file is None:
            return
        try:
            self.csv_writer.writerow(
                (
                    datetime.now().astimezone().isoformat(timespec="milliseconds"),
                    record.timestamp_us,
                    record.stream_alive,
                    record.age_ms,
                    *record.channels,
                    record.valid_frames,
                    record.checksum_errors,
                    record.uart_errors,
                    record.ring_overflows,
                )
            )
            self.csv_file.flush()
        except OSError as exc:
            self.stop_csv_log()
            self.csv_status_var.set(f"CSV error: {exc}")

    def _start_demo(self) -> None:
        self.serial_status_var.set("DEMO mode — no COM port opened")
        self.port_combo.configure(state="disabled")
        self.baud_combo.configure(state="disabled")
        self.refresh_button.configure(state="disabled")
        self.connect_button.configure(state="disabled")
        self.disconnect_button.configure(state="disabled")
        self._demo_tick()

    def _demo_tick(self) -> None:
        elapsed = time.monotonic() - self.demo_start
        alive = (elapsed % 8.0) < 6.0

        if alive:
            self.demo_channels = [
                int(1500 + 480 * math.sin(elapsed * 1.0)),
                int(1500 + 420 * math.sin(elapsed * 0.8 + 1.2)),
                int(1000 + 1000 * ((elapsed % 5.0) / 5.0)),
                int(1500 + 450 * math.sin(elapsed * 0.65 + 2.0)),
                1000 if int(elapsed) % 4 < 2 else 2000,
                1000 if int(elapsed) % 6 < 3 else 2000,
                1500,
                1500,
            ]
            self.demo_valid_frames += 1
            self.demo_last_valid = time.monotonic()
            age_ms = int((self.demo_valid_frames % 4) + 2)
        else:
            age_ms = int((time.monotonic() - self.demo_last_valid) * 1000)

        record = IBusRecord(
            timestamp_us=int(elapsed * 1_000_000) & 0xFFFFFFFF,
            stream_alive=1 if alive else 0,
            age_ms=age_ms,
            channels=tuple(self.demo_channels),  # type: ignore[arg-type]
            valid_frames=self.demo_valid_frames,
            checksum_errors=int(elapsed // 10),
            uart_errors=int(elapsed // 20),
            ring_overflows=int(elapsed // 30),
        )
        self._handle_record(record)
        self.demo_after_id = self.root.after(50, self._demo_tick)

    def close(self) -> None:
        if self.demo_after_id is not None:
            try:
                self.root.after_cancel(self.demo_after_id)
            except tk.TclError:
                pass
        reader = self.reader
        self.reader = None
        if reader is not None:
            reader.stop()
            reader.join(timeout=0.5)
        self.stop_csv_log()
        self.root.destroy()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FlySky iBUS USART monitor")
    parser.add_argument("--port", help="COM port, for example COM6")
    parser.add_argument("--baud", type=int, default=115200, help="serial baud rate")
    parser.add_argument(
        "--demo", action="store_true", help="run animated GUI without opening a COM port"
    )
    return parser


def main() -> int:
    args = build_argument_parser().parse_args()
    root = tk.Tk()
    IBusMonitorApp(root, args.port, args.baud, args.demo)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
