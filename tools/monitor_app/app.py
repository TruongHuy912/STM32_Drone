"""Application coordinator for the STM32H743 Drone Bench Configurator."""

from __future__ import annotations

import collections
import csv
import math
import queue
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional, TextIO

try:
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    list_ports = None

from .constants import (
    AGE_REFRESH_MS,
    APP_NAME,
    APP_VERSION,
    ESC_FRESH_S,
    IBUS_RECEIPT_FRESH_S,
    MTEST_FRESH_S,
    PAGE_INFO,
    PROTOCOL_FRESH_S,
    PROTOCOL_VERSION,
    QUEUE_POLL_MS,
    SENSOR_FRESH_S,
    SIDEBAR_WIDTH,
    UI_REFRESH_MS,
    WINDOW_GEOMETRY,
    WINDOW_MIN_HEIGHT,
    WINDOW_MIN_WIDTH,
)
from .controller import CommandDispatcher, OutgoingQueue
from .models import (
    CommandAckRecord,
    ESCRecord,
    IBusRecord,
    MotorTestRecord,
    ParsedLine,
    SafetySnapshot,
)
from .pages import (
    ConnectionPage,
    DashboardPage,
    DiagnosticsPage,
    ESCOutputsPage,
    MotorTestPage,
    ReceiverPage,
)
from .protocol import (
    MTEST_ABORT_NAMES,
    classify_console_line,
    firmware_reset_detected,
    parse_ibus_header_errors,
    telemetry_is_fresh,
    validate_run_values,
)
from .replay_worker import ReplayWorker
from .serial_worker import SerialWorker
from .theme import COLORS, FONTS, apply_theme
from .ui_state import (
    emergency_stop_available,
    format_age,
    navigation_state,
    run_disable_reasons,
    safety_gate_values,
)
from .widgets import SidebarButton, StatusBadge, Tooltip


class BenchConfiguratorApp:
    def __init__(
        self,
        root: tk.Tk,
        initial_port: Optional[str] = None,
        baud: int = 115200,
        demo: bool = False,
        replay_file: Optional[str] = None,
    ) -> None:
        self.root = root
        self.root.title(APP_NAME)
        apply_theme(root)
        self.root.geometry(WINDOW_GEOMETRY)
        self.root.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.events: queue.Queue = queue.Queue()
        self.outgoing = OutgoingQueue()
        self.dispatcher = CommandDispatcher(self.outgoing)
        self.worker: SerialWorker | ReplayWorker | None = None
        self.connection_id = 0
        self.connected = False
        self.demo = demo
        self.replay_file = replay_file
        self.replay_mode = replay_file is not None
        self.closing = False
        self.reconnect_count = 0
        self.successful_connections = 0
        self.rx_line_count = 0
        self.rx_bytes_total = 0
        self.rx_samples: collections.deque[tuple[float, int]] = collections.deque()
        self.tx_command_count = 0
        self.last_serial_error: Optional[str] = None
        self.last_rx_monotonic: Optional[float] = None
        self.latest_ibus: Optional[IBusRecord] = None
        self.latest_esc: Optional[ESCRecord] = None
        self.latest_mtest: Optional[MotorTestRecord] = None
        self.latest_ack: Optional[CommandAckRecord] = None
        self.received_at: dict[str, Optional[float]] = {
            "IBUS": None, "ESC": None, "MTEST": None, "MACK": None,
        }
        self.sensor_received_at: dict[str, Optional[float]] = {"BMI270": None, "BMP388": None}
        self.last_firmware_timestamp: dict[str, Optional[int]] = {key: None for key in self.received_at}
        self.malformed = {key: 0 for key in ("IBUS", "ESC", "MTEST", "MACK")}
        self.header_errors = 0
        self.auto_stop_latched = False
        self.csv_file: Optional[TextIO] = None
        self.csv_writer: Optional[csv.writer] = None
        self.worker_state = "IDLE"
        self.log_mode = "UNKNOWN"
        self.active_page = "Dashboard"
        self.demo_start = time.monotonic()
        self.demo_scenario = "AUTO"
        self.demo_manual_until: Optional[float] = None
        self.demo_manual_motor = 1
        self.demo_manual_pulse = 1020
        self.demo_manual_duration = 500
        self.demo_last_emit = 0.0
        self.demo_previous_scenario = ""

        self._build_shell(initial_port or "", baud)
        self.refresh_ports()
        self.show_page("Dashboard")
        self.root.after(QUEUE_POLL_MS, self.process_events)
        self.root.after(UI_REFRESH_MS, self.refresh_ui)
        if demo:
            self.start_demo()
        elif replay_file:
            self.start_replay(replay_file)

    def _build_shell(self, initial_port: str, baud: int) -> None:
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)
        sidebar = tk.Frame(self.root, background=COLORS["SIDEBAR_BG"], width=SIDEBAR_WIDTH)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(2, weight=1)
        brand = tk.Frame(sidebar, background=COLORS["SIDEBAR_BG"])
        brand.grid(row=0, column=0, sticky="ew", padx=18, pady=(20, 18))
        tk.Label(brand, text="STM32H743", background=COLORS["SIDEBAR_BG"], foreground=COLORS["ACCENT"], font=FONTS["APP_TITLE"]).pack(anchor="w")
        tk.Label(brand, text="DRONE BENCH CONFIGURATOR", background=COLORS["SIDEBAR_BG"], foreground=COLORS["TEXT_SECONDARY"], font=FONTS["SMALL"]).pack(anchor="w", pady=(1, 0))
        nav = tk.Frame(sidebar, background=COLORS["SIDEBAR_BG"])
        nav.grid(row=1, column=0, sticky="new")
        self.nav_buttons: dict[str, SidebarButton] = {}
        for name, (icon, _description) in PAGE_INFO.items():
            button = SidebarButton(nav, icon, name, lambda value=name: self.show_page(value))
            button.pack(fill="x", pady=1)
            self.nav_buttons[name] = button
        footer = tk.Frame(sidebar, background=COLORS["SIDEBAR_BG"])
        footer.grid(row=3, column=0, sticky="sew", padx=18, pady=18)
        self.sidebar_port_var = tk.StringVar(value="COM: --")
        self.sidebar_baud_var = tk.StringVar(value=f"Baud: {baud}")
        for variable in (self.sidebar_port_var, self.sidebar_baud_var):
            tk.Label(footer, textvariable=variable, background=COLORS["SIDEBAR_BG"], foreground=COLORS["TEXT_SECONDARY"], font=FONTS["SMALL"]).pack(anchor="w", pady=1)
        tk.Label(footer, text=f"Protocol: {PROTOCOL_VERSION}", background=COLORS["SIDEBAR_BG"], foreground=COLORS["TEXT_SECONDARY"], font=FONTS["SMALL"]).pack(anchor="w", pady=1)
        tk.Label(footer, text=APP_VERSION, background=COLORS["SIDEBAR_BG"], foreground=COLORS["TEXT_SECONDARY"], font=FONTS["SMALL"]).pack(anchor="w", pady=(1, 0))

        content = ttk.Frame(self.root, style="App.TFrame")
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)
        self._build_header(content)
        self.page_host = ttk.Frame(content, style="App.TFrame")
        self.page_host.grid(row=1, column=0, sticky="nsew")
        self.page_host.columnconfigure(0, weight=1)
        self.page_host.rowconfigure(0, weight=1)

        self.connection_page = ConnectionPage(self.page_host, self.connect, self.disconnect, self.refresh_ports, self.send_log_command)
        self.receiver_page = ReceiverPage(self.page_host)
        self.esc_page = ESCOutputsPage(self.page_host)
        self.motor_page = MotorTestPage(self.page_host, self.run_selected_motor, self.request_stop, self.request_emergency_stop, self.refresh_safety)
        self.diagnostics_page = DiagnosticsPage(self.page_host, self.start_csv, self.stop_csv)
        self.dashboard_page = DashboardPage(self.page_host, self.show_page, self.demo, self.set_demo_scenario)
        self.pages = {
            "Dashboard": self.dashboard_page,
            "Connection": self.connection_page,
            "Receiver": self.receiver_page,
            "ESC Outputs": self.esc_page,
            "Motor Test": self.motor_page,
            "Diagnostics": self.diagnostics_page,
        }
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")
        self.connection_page.port_var.set(initial_port)
        self.connection_page.baud_var.set(str(baud))
        self._build_status_bar(content)

    def _build_header(self, parent: tk.Misc) -> None:
        header = ttk.Frame(parent, style="Card.TFrame", padding=(18, 12))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        titles = ttk.Frame(header, style="Surface.TFrame")
        titles.grid(row=0, column=0, sticky="w")
        self.page_title_var = tk.StringVar(value="Dashboard")
        self.page_description_var = tk.StringVar(value=PAGE_INFO["Dashboard"][1])
        ttk.Label(titles, textvariable=self.page_title_var, style="Surface.TLabel", font=FONTS["PAGE_TITLE"]).pack(anchor="w")
        ttk.Label(titles, textvariable=self.page_description_var, style="SurfaceSecondary.TLabel").pack(anchor="w", pady=(2, 0))
        badges = ttk.Frame(header, style="Surface.TFrame")
        badges.grid(row=1, column=0, columnspan=2, sticky="e", pady=(8, 0))
        self.header_badges = {
            "com": StatusBadge(badges, "COM OFFLINE", "neutral"),
            "protocol": StatusBadge(badges, "PROTOCOL OFFLINE", "danger"),
            "ibus": StatusBadge(badges, "iBUS LOST", "danger"),
            "esc": StatusBadge(badges, "ESC ERROR", "danger"),
        }
        for badge in self.header_badges.values():
            badge.pack(side="left", padx=3)
        self.global_emergency = ttk.Button(header, text="EMERGENCY STOP  !", style="Danger.TButton", command=self.request_emergency_stop, state="disabled")
        self.global_emergency.grid(row=0, column=1, sticky="e", padx=(12, 0))
        Tooltip(self.global_emergency, "Global emergency action. Sends raw byte '!' using the existing command queue. No page change is required.")

    def _build_status_bar(self, parent: tk.Misc) -> None:
        bar = ttk.Frame(parent, style="Card.TFrame", padding=(10, 5))
        bar.grid(row=2, column=0, sticky="ew")
        self.status_vars = {
            key: tk.StringVar(value=value)
            for key, value in (
                ("port", "-- @ 115200"), ("rate", "RX 0 B/s"), ("lines", "Lines 0"),
                ("ibus", "IBUS --"), ("esc", "ESC --"), ("mtest", "MTEST --"),
                ("tx", "TX 0"), ("version", PROTOCOL_VERSION), ("worker", "Worker IDLE"),
            )
        }
        for column, (key, variable) in enumerate(self.status_vars.items()):
            label = ttk.Label(bar, textvariable=variable, style="SurfaceSecondary.TLabel", font=FONTS["SMALL"])
            label.grid(row=0, column=column, padx=(0 if column == 0 else 10, 0), sticky="w")
            if key in {"ibus", "esc", "mtest"}:
                Tooltip(label, "Telemetry age. Stale data is reflected in the header and page status.")
        bar.columnconfigure(8, weight=1)

    def show_page(self, requested: str) -> None:
        page = navigation_state(requested)
        self.active_page = page
        self.pages[page].tkraise()
        self.page_title_var.set(page)
        self.page_description_var.set(PAGE_INFO[page][1])
        for name, button in self.nav_buttons.items():
            button.set_active(name == page)

    def refresh_ports(self) -> None:
        current = self.connection_page.port_var.get().strip()
        ports: list[str] = []
        if list_ports is not None:
            try:
                ports = sorted(port.device for port in list_ports.comports())
            except Exception:
                ports = []
        if current and current not in ports:
            ports.insert(0, current)
        self.connection_page.port_combo.configure(values=ports)
        if not current and ports:
            self.connection_page.port_var.set(ports[0])

    def connect(self) -> None:
        if self.demo or self.replay_mode or self.worker is not None:
            return
        port_name = self.connection_page.port_var.get().strip()
        if not port_name:
            messagebox.showwarning("COM port", "Select or enter a COM port.", parent=self.root)
            return
        try:
            baud = int(self.connection_page.baud_var.get(), 10)
            if baud <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Baud", "Baud must be a positive integer.", parent=self.root)
            return
        self.outgoing.clear()
        self.last_serial_error = None
        self.connection_id += 1
        self.worker = SerialWorker(self.connection_id, port_name, baud, self.events, self.outgoing)
        self.worker_state = "CONNECTING"
        self.connection_page.set_status("CONNECTING", "warning", f"Opening {port_name}...")
        self.connection_page.connect_button.configure(state="disabled")
        self.worker.start()

    def start_replay(self, replay_file: str) -> None:
        self.connection_id += 1
        self.worker = ReplayWorker(self.connection_id, replay_file, self.events)
        self.worker_state = "REPLAY"
        self.connection_page.port_var.set(f"REPLAY:{Path(replay_file).name}")
        self.connection_page.connect_button.configure(state="disabled")
        self.worker.start()

    def disconnect(self) -> None:
        if self.demo:
            self.set_demo_scenario("DISCONNECTED")
            return
        worker = self.worker
        self.last_serial_error = None
        self._disable_motor_controls("DISCONNECTING · best-effort STOP requested")
        if worker is not None:
            worker.request_disconnect(send_stop=not self.replay_mode)
        self.connected = False
        self.dispatcher.set_connected(False)
        self.connection_page.set_connected(False)
        self.worker_state = "DISCONNECTING"
        if worker is not None:
            self.connection_page.connect_button.configure(state="disabled")
            self.connection_page.set_status("DISCONNECTING", "warning", "Closing worker...")

    def _disable_motor_controls(self, message: str) -> None:
        self.motor_page.clear_confirmation()
        self.motor_page.set_connected(False)
        self.motor_page.request_var.set(message)
        self.auto_stop_latched = True

    def send_log_command(self, mode: str) -> None:
        if self.replay_mode:
            return
        if self.demo:
            self.log_mode = mode if mode != "STATUS" else self.log_mode
            self._demo_ack(f"LOG_{mode}", True, "NONE")
            return
        if self.dispatcher.queue_log(mode) and mode != "STATUS":
            self.log_mode = mode

    def run_selected_motor(self) -> None:
        motor = self.motor_page.selected_motor()
        try:
            pulse = int(self.motor_page.pulse_var.get())
            duration = int(self.motor_page.duration_var.get())
            validate_run_values(motor, pulse, duration)
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("Invalid motor command", str(exc), parent=self.root)
            return
        safety = self.current_safety()
        if not self.dispatcher.can_run(safety) or not self.protocol_online():
            messagebox.showwarning("Safety gate", "RUN is disabled until every safety item passes.", parent=self.root)
            return
        if not self.motor_page.confirm_run(motor, pulse, duration):
            return
        if self.demo:
            self.demo_manual_motor = motor
            self.demo_manual_pulse = pulse
            self.demo_manual_duration = duration
            self.demo_manual_until = time.monotonic() + duration / 1000.0
            self.demo_scenario = "RUNNING"
            self.dispatcher.run_pending = True
            self._demo_ack("RUN", True, "NONE", motor, pulse, duration)
            self.dispatcher.run_pending = False
        elif not self.dispatcher.queue_run(motor, pulse, duration):
            return
        self.motor_page.request_var.set("RUN REQUESTED · awaiting firmware ACK")
        self.refresh_safety()

    def request_stop(self, *, automatic: bool = False) -> None:
        if self.replay_mode or not self.connected:
            return
        if automatic and self.auto_stop_latched:
            return
        if automatic:
            self.auto_stop_latched = True
        if self.demo:
            self.demo_manual_until = None
            self.demo_scenario = "READY"
            self._demo_ack("STOP", True, "USER_STOP")
        else:
            self.dispatcher.queue_stop(front=True)
        self.motor_page.request_var.set("STOP REQUESTED")
        self.refresh_safety()

    def request_emergency_stop(self) -> None:
        if self.replay_mode or not self.connected:
            return
        if self.demo:
            self.demo_manual_until = None
            self.demo_scenario = "EMERGENCY"
            self._demo_ack("ESTOP", True, "EMERGENCY_STOP")
        else:
            self.dispatcher.queue_emergency_stop()
        self.auto_stop_latched = True
        self.motor_page.request_var.set("STOP REQUESTED · EMERGENCY ! sent")
        self.refresh_safety()

    def process_events(self) -> None:
        try:
            while True:
                connection_id, kind, payload = self.events.get_nowait()
                if connection_id != self.connection_id:
                    continue
                if kind == "connected":
                    self.last_serial_error = None
                    self.connected = True
                    self.dispatcher.set_connected(not self.replay_mode)
                    self.successful_connections += 1
                    self.reconnect_count = max(0, self.successful_connections - 1)
                    self.connection_page.set_connected(True)
                    self.connection_page.set_status("REPLAY" if self.replay_mode else "CONNECTED", "info" if self.replay_mode else "success", str(payload))
                    self.motor_page.set_connected(not self.replay_mode)
                    self.worker_state = "REPLAY" if self.replay_mode else "RUNNING"
                elif kind == "line":
                    line, count, received = payload
                    self.rx_line_count = count
                    line_bytes = len(line.encode("ascii", errors="replace")) + 1
                    self.rx_bytes_total += line_bytes
                    self.rx_samples.append((received, line_bytes))
                    self.last_rx_monotonic = received
                    self.diagnostics_page.append_line(line)
                    upper = line.upper()
                    for sensor in self.sensor_received_at:
                        if sensor in upper:
                            self.sensor_received_at[sensor] = received
                    header_errors = parse_ibus_header_errors(line)
                    if header_errors is not None:
                        self.header_errors = header_errors
                    self._write_csv(line)
                elif kind == "record":
                    parsed, received = payload
                    self._handle_record(parsed, received)
                elif kind == "malformed":
                    prefix, _reason = payload
                    if prefix in self.malformed:
                        self.malformed[prefix] += 1
                elif kind == "tx":
                    request, count = payload
                    self.tx_command_count = count
                    self.diagnostics_page.append_line(f"> {request.display}")
                elif kind == "serial_error":
                    self.last_serial_error = str(payload)
                    self.connection_page.set_status("SERIAL ERROR", "danger", self.last_serial_error)
                    self._disable_motor_controls("SERIAL ERROR · best-effort STOP attempted")
                    self.connected = False
                    self.dispatcher.set_connected(False)
                    self.worker_state = "ERROR"
                elif kind == "disconnected":
                    self.worker = None
                    self.connected = False
                    self.dispatcher.set_connected(False)
                    self.connection_page.set_connected(False)
                    if self.last_serial_error is not None:
                        self.connection_page.set_status("SERIAL ERROR", "danger", self.last_serial_error)
                        self.worker_state = "ERROR"
                    else:
                        self.connection_page.set_status("DISCONNECTED", "neutral", "Serial/replay worker closed")
                        self.worker_state = "IDLE"
                    self._disable_motor_controls("DISCONNECTED")
        except queue.Empty:
            pass
        if not self.closing:
            self.root.after(QUEUE_POLL_MS, self.process_events)

    def _handle_record(self, parsed: ParsedLine, received: float) -> None:
        record = parsed.record
        timestamp = getattr(record, "timestamp_us")
        previous = self.last_firmware_timestamp[parsed.kind]
        if firmware_reset_detected(previous, timestamp):
            self.motor_page.clear_confirmation()
            self.dispatcher.run_pending = False
            self.motor_page.request_var.set("FIRMWARE RESET DETECTED · confirmation cleared")
        self.last_firmware_timestamp[parsed.kind] = timestamp
        self.received_at[parsed.kind] = received
        if parsed.kind == "IBUS":
            self.latest_ibus = record
        elif parsed.kind == "ESC":
            self.latest_esc = record
        elif parsed.kind == "MTEST":
            self.latest_mtest = record
            self.dispatcher.handle_mtest_state(record.state)
            if record.state != 2:
                self.auto_stop_latched = False
        elif parsed.kind == "MACK":
            self.latest_ack = record
            self.dispatcher.handle_ack(record)
            self.motor_page.update_ack(record)
            if record.command.startswith("LOG_") and record.accepted == 1:
                mode = record.command.removeprefix("LOG_")
                if mode in {"QUIET", "FULL"}:
                    self.log_mode = mode

    def protocol_online(self, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        latest = [received for received in self.received_at.values() if received is not None]
        return self.connected and bool(latest) and now - max(latest) <= PROTOCOL_FRESH_S

    def current_safety(self, now: Optional[float] = None) -> SafetySnapshot:
        now = time.monotonic() if now is None else now
        ibus, esc, mtest = self.latest_ibus, self.latest_esc, self.latest_mtest
        ibus_receipt_fresh = telemetry_is_fresh(self.received_at["IBUS"], now, IBUS_RECEIPT_FRESH_S)
        command_connected = self.connected and not self.replay_mode
        return SafetySnapshot(
            serial_connected=command_connected,
            ibus_link_valid=bool(ibus and ibus_receipt_fresh and ibus.stream_alive == 1),
            ibus_fresh=bool(ibus and ibus_receipt_fresh and ibus.age_ms <= 50),
            throttle_low=bool(ibus and ibus.channels[2] <= 1050),
            ch5_enabled=bool(ibus and ibus.channels[4] >= 1900),
            ch6_enabled=bool(ibus and ibus.channels[5] >= 1900),
            esc_safe=bool(esc and esc.state == 1),
            esc_started=bool(esc and esc.started_mask == 0x0F),
            esc_fresh=telemetry_is_fresh(self.received_at["ESC"], now, ESC_FRESH_S),
            mtest_fresh=telemetry_is_fresh(self.received_at["MTEST"], now, MTEST_FRESH_S),
            mtest_ready=bool(mtest and mtest.state == 1 and mtest.active_us == 1000),
            propellers_removed=self.motor_page.propellers_var.get(),
        )

    def refresh_safety(self, *, update_page: bool = True) -> None:
        now = time.monotonic()
        safety = self.current_safety(now)
        online = self.protocol_online(now)
        values = safety_gate_values(safety, online)
        ibus, esc, mtest = self.latest_ibus, self.latest_esc, self.latest_mtest
        details = {
            "serial_connected": ("Connected" if safety.serial_connected else "Disconnected", "Required: connected"),
            "protocol_online": ("Online" if online else "Offline", "Required: online"),
            "ibus_link_valid": ("LINK OK" if safety.ibus_link_valid else "LINK LOST", "Required: valid stream"),
            "ibus_fresh": (f"{ibus.age_ms} ms" if ibus else "--", "Required: ≤ 50 ms"),
            "throttle_low": (f"{ibus.channels[2]} us" if ibus else "--", "Required: ≤ 1050 us"),
            "ch5_enabled": (f"{ibus.channels[4]} us" if ibus else "--", "Required: ≥ 1900 us"),
            "ch6_enabled": (f"{ibus.channels[5]} us" if ibus else "--", "Required: ≥ 1900 us"),
            "esc_safe": ("SAFE" if safety.esc_safe else "ERROR", "Required: SAFE"),
            "esc_started": (f"0x{esc.started_mask:02X}" if esc else "--", "Required: 0x0F"),
            "esc_fresh": (format_age(self._age("ESC", now)), f"Required: ≤ {ESC_FRESH_S:.2f} s"),
            "mtest_fresh": (format_age(self._age("MTEST", now)), f"Required: ≤ {MTEST_FRESH_S:.2f} s"),
            "mtest_ready": (("READY" if mtest and mtest.state == 1 else "NOT READY"), "Required: READY / 1000 us"),
            "propellers_removed": ("Confirmed" if safety.propellers_removed else "Not confirmed", "Required: physical removal confirmed"),
        }
        running = bool(mtest and mtest.state == 2)
        can_run = self.dispatcher.can_run(safety) and online
        reasons = run_disable_reasons(
            safety, online, run_pending=self.dispatcher.run_pending,
            run_accepted=self.dispatcher.run_accepted,
        )
        if update_page:
            self.motor_page.set_safety(values, details)
            self.motor_page.set_control_state(
                safety.serial_connected, running, can_run,
                reasons[0] if reasons else "",
            )
        available = emergency_stop_available(self.connected, self.replay_mode)
        self.global_emergency.configure(state="normal" if available else "disabled")
        if running:
            unsafe_while_running = not all((
                safety.ibus_link_valid, safety.ibus_fresh, safety.throttle_low,
                safety.ch5_enabled, safety.ch6_enabled,
            ))
            if unsafe_while_running and not self.auto_stop_latched:
                self.request_stop(automatic=True)

    def _age(self, kind: str, now: Optional[float] = None) -> Optional[float]:
        now = time.monotonic() if now is None else now
        received = self.received_at[kind]
        return None if received is None else max(0.0, now - received)

    def _rx_rate(self, now: float) -> float:
        while self.rx_samples and now - self.rx_samples[0][0] > 1.0:
            self.rx_samples.popleft()
        return float(sum(size for _timestamp, size in self.rx_samples))

    def refresh_ui(self) -> None:
        now = time.monotonic()
        rate = self._rx_rate(now)
        online = self.protocol_online(now)
        safety = self.current_safety(now)
        ibus_fresh = telemetry_is_fresh(self.received_at["IBUS"], now, IBUS_RECEIPT_FRESH_S)
        esc_fresh = telemetry_is_fresh(self.received_at["ESC"], now, ESC_FRESH_S)
        if self.active_page == "Receiver":
            self.receiver_page.update_view(self.latest_ibus, ibus_fresh)
        elif self.active_page == "ESC Outputs":
            self.esc_page.update_view(self.latest_esc, esc_fresh, self._age("ESC", now))
        elif self.active_page == "Motor Test" and self.latest_mtest is not None:
            self.motor_page.update_record(
                self.latest_mtest, self.dispatcher.last_run_duration_ms
            )
        self.refresh_safety(update_page=self.active_page == "Motor Test")
        latest_age = None if self.last_rx_monotonic is None else now - self.last_rx_monotonic
        port = self.connection_page.port_var.get().strip()
        try:
            baud = int(self.connection_page.baud_var.get())
        except ValueError:
            baud = 115200
        bmi_alive = telemetry_is_fresh(self.sensor_received_at["BMI270"], now, SENSOR_FRESH_S)
        bmp_alive = telemetry_is_fresh(self.sensor_received_at["BMP388"], now, SENSOR_FRESH_S)
        if self.active_page == "Dashboard":
            self.dashboard_page.update_view(
                connected=self.connected, port=port, baud=baud, rx_rate=rate,
                protocol_online=online, packet_age=format_age(latest_age),
                ibus=self.latest_ibus, esc=self.latest_esc,
                mtest=self.latest_mtest, safety=safety,
                bmi_alive=bmi_alive, bmp_alive=bmp_alive,
            )
        elif self.active_page == "Connection":
            self.connection_page.update_protocol(
                online=online, last_telemetry=format_age(latest_age),
                rx_bytes=self.rx_bytes_total, rx_lines=self.rx_line_count,
                rx_rate=rate, worker_state=self.worker_state,
                exception=self.last_serial_error or "",
            )
            self.connection_page.set_log_mode(self.log_mode)
        self._update_header(safety, online)
        self._update_status_bar(port, baud, rate, now)
        if self.active_page == "Diagnostics":
            self._update_diagnostics(rate)
            self.diagnostics_page.flush_lines()
        if self.demo:
            self.demo_tick(now)
        if not self.closing:
            self.root.after(UI_REFRESH_MS, self.refresh_ui)

    def _update_header(self, safety: SafetySnapshot, online: bool) -> None:
        self.header_badges["com"].set("COM ONLINE" if self.connected else "COM OFFLINE", "success" if self.connected else "neutral")
        self.header_badges["protocol"].set("PROTOCOL ONLINE" if online else "PROTOCOL OFFLINE", "success" if online else "danger")
        self.header_badges["ibus"].set("iBUS LINK OK" if safety.ibus_link_valid and safety.ibus_fresh else "iBUS LOST", "success" if safety.ibus_link_valid and safety.ibus_fresh else "danger")
        esc_ok = safety.esc_safe and safety.esc_started and safety.esc_fresh
        self.header_badges["esc"].set("ESC SAFE" if esc_ok else "ESC ERROR", "success" if esc_ok else "danger")

    def _update_status_bar(self, port: str, baud: int, rate: float, now: float) -> None:
        self.status_vars["port"].set(f"{port or '--'} @ {baud}")
        self.status_vars["rate"].set(f"RX {rate:.0f} B/s")
        self.status_vars["lines"].set(f"Lines {self.rx_line_count:,}")
        self.status_vars["ibus"].set(f"IBUS {format_age(self._age('IBUS', now))}")
        self.status_vars["esc"].set(f"ESC {format_age(self._age('ESC', now))}")
        self.status_vars["mtest"].set(f"MTEST {format_age(self._age('MTEST', now))}")
        self.status_vars["tx"].set(f"TX {self.tx_command_count}")
        self.status_vars["worker"].set(f"Worker {self.worker_state}")
        self.sidebar_port_var.set(f"COM: {port or '--'}")
        self.sidebar_baud_var.set(f"Baud: {baud}")

    def _update_diagnostics(self, rate: float) -> None:
        ibus = self.latest_ibus
        self.diagnostics_page.set_counters({
            "rx_bytes": self.rx_bytes_total,
            "rx_lines": self.rx_line_count,
            "rx_rate": f"{rate:.0f}",
            "valid": getattr(ibus, "valid_frames", 0),
            "checksum": getattr(ibus, "checksum_errors", 0),
            "header": self.header_errors,
            "uart": getattr(ibus, "uart_errors", 0),
            "overflow": getattr(ibus, "ring_overflows", 0),
            "m_ibus": self.malformed["IBUS"],
            "m_esc": self.malformed["ESC"],
            "m_mtest": self.malformed["MTEST"],
            "m_mack": self.malformed["MACK"],
            "tx": self.tx_command_count,
        })

    def start_csv(self) -> None:
        if self.csv_file is not None:
            return
        try:
            logs = Path(__file__).resolve().parents[2] / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            path = logs / datetime.now().strftime("bench_%Y%m%d_%H%M%S.csv")
            self.csv_file = path.open("w", newline="", encoding="utf-8")
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(("timestamp_pc", "type", "raw_line"))
            self.diagnostics_page.csv_status.set(f"Logging: {path.name}")
            self.diagnostics_page.csv_start.configure(state="disabled")
            self.diagnostics_page.csv_stop.configure(state="normal")
        except OSError as exc:
            messagebox.showerror("CSV logging", str(exc), parent=self.root)

    def stop_csv(self) -> None:
        if self.csv_file is not None:
            try:
                self.csv_file.close()
            except OSError:
                pass
        self.csv_file = None
        self.csv_writer = None
        self.diagnostics_page.csv_status.set("CSV logging stopped")
        self.diagnostics_page.csv_start.configure(state="normal")
        self.diagnostics_page.csv_stop.configure(state="disabled")

    def _write_csv(self, line: str) -> None:
        if self.csv_writer is None:
            return
        kind = classify_console_line(line)
        selected = self.diagnostics_page.csv_types
        if kind not in selected or not selected[kind].get():
            return
        try:
            self.csv_writer.writerow((datetime.now().astimezone().isoformat(timespec="milliseconds"), kind, line))
        except OSError as exc:
            self.stop_csv()
            self.diagnostics_page.csv_status.set(f"CSV error: {exc}")

    def start_demo(self) -> None:
        self.connected = True
        self.dispatcher.set_connected(True)
        self.connection_page.set_connected(True)
        self.connection_page.connect_button.configure(state="disabled")
        self.connection_page.disconnect_button.configure(state="normal")
        self.connection_page.set_status("DEMO", "info", "No COM port opened; no serial writes")
        self.connection_page.port_var.set("DEMO")
        self.motor_page.set_connected(True)
        self.worker_state = "DEMO"

    def set_demo_scenario(self, scenario: str) -> None:
        if not self.demo:
            return
        self.demo_scenario = scenario
        self.demo_manual_until = None
        if scenario == "AUTO":
            self.demo_start = time.monotonic()
            self.demo_previous_scenario = ""
        if scenario == "DISCONNECTED":
            self.connected = False
            self.dispatcher.set_connected(False)
            self.motor_page.clear_confirmation()
        else:
            self.connected = True
            self.dispatcher.set_connected(True)

    def demo_tick(self, now: float) -> None:
        if now - self.demo_last_emit < 0.1:
            return
        self.demo_last_emit = now
        elapsed = now - self.demo_start
        scenario = self.demo_scenario
        if scenario == "AUTO":
            phase = elapsed % 15.0
            scenario = (
                "AUX OFF" if phase < 2 else "READY" if phase < 4 else
                "RUNNING" if phase < 6 else "EXPIRED" if phase < 7 else
                "EMERGENCY" if phase < 8 else "REJECTED" if phase < 9 else
                "FAULT" if phase < 11 else "STALE" if phase < 13 else
                "DISCONNECTED"
            )
        if self.demo_manual_until is not None:
            if now < self.demo_manual_until:
                scenario = "RUNNING"
            else:
                self.demo_manual_until = None
                scenario = "EXPIRED"
        if scenario == "DISCONNECTED":
            self.connected = False
            self.dispatcher.set_connected(False)
            self.demo_previous_scenario = scenario
            return
        if not self.connected:
            self.connected = True
            self.dispatcher.set_connected(True)
            self.motor_page.set_connected(True)
        if scenario == "STALE":
            self.demo_previous_scenario = scenario
            return
        scenario_changed = scenario != self.demo_previous_scenario
        self.demo_previous_scenario = scenario
        timestamp = int(elapsed * 1_000_000) & 0xFFFFFFFF
        aux_enabled = scenario != "AUX OFF"
        channels = (
            int(1500 + 300 * math.sin(elapsed)),
            int(1500 + 250 * math.sin(elapsed * 0.7)),
            1000, 1500, 2000 if aux_enabled else 1000,
            2000 if aux_enabled else 1000, 1500, 1500,
        )
        ibus = IBusRecord(timestamp, 1, 3, channels, int(elapsed * 140), 0, 0, 0)
        running = scenario == "RUNNING"
        motor = self.demo_manual_motor if running else 0
        pulse = self.demo_manual_pulse if running else 0
        remaining = max(0, int((self.demo_manual_until - now) * 1000)) if running and self.demo_manual_until else (700 if running else 0)
        motor_us = [1000, 1000, 1000, 1000]
        if running:
            motor = max(1, motor)
            pulse = max(1020, pulse)
            motor_us[motor - 1] = pulse
        esc = ESCRecord(timestamp, 1, 0x0F, 50, tuple(motor_us), 0, 0)  # type: ignore[arg-type]
        state = 3 if scenario == "FAULT" else 2 if running else 1
        abort = 10 if scenario == "FAULT" else 2 if scenario == "EMERGENCY" else 3 if scenario == "EXPIRED" else 0
        mtest = MotorTestRecord(timestamp, state, motor, pulse, pulse if running else 1000, remaining, 0xFF, abort, 2, 1, int(scenario in {"EMERGENCY", "FAULT"}), 0)
        self._demo_record("IBUS", ibus, now)
        self._demo_record("ESC", esc, now)
        self._demo_record("MTEST", mtest, now)
        if scenario == "REJECTED" and scenario_changed:
            self._demo_ack(
                "RUN", False, "CH5_NOT_ENABLED", 1, 1050, 500
            )
        self.sensor_received_at["BMI270"] = now
        self.sensor_received_at["BMP388"] = now
        if int(elapsed * 10) % 20 == 0:
            self.diagnostics_page.append_line("BMI270 sample: demo")
            self.diagnostics_page.append_line("BMP388 sample: demo")

    def _demo_record(self, kind: str, record: object, received: float) -> None:
        raw = self._demo_raw(kind, record)
        self.rx_line_count += 1
        size = len(raw) + 1
        self.rx_bytes_total += size
        self.rx_samples.append((received, size))
        self.last_rx_monotonic = received
        self.diagnostics_page.append_line(raw)
        self._handle_record(ParsedLine(kind, record, raw), received)

    @staticmethod
    def _demo_raw(kind: str, record: object) -> str:
        if kind == "IBUS":
            rec = record
            values = (rec.timestamp_us, rec.stream_alive, rec.age_ms, *rec.channels, rec.valid_frames, rec.checksum_errors, rec.uart_errors, rec.ring_overflows)
        elif kind == "ESC":
            rec = record
            values = (rec.timestamp_us, rec.state, rec.started_mask, rec.frequency_hz, *rec.motor_us, rec.rejected, rec.start_errors)
        elif kind == "MTEST":
            rec = record
            values = (rec.timestamp_us, rec.state, rec.motor, rec.commanded_us, rec.active_us, rec.remaining_ms, rec.gate_mask, rec.last_abort, rec.run_count, rec.completed_count, rec.abort_count, rec.rejected_count)
        else:
            rec = record
            values = (rec.timestamp_us, rec.command, rec.accepted, rec.reason, rec.motor, rec.pulse_us, rec.duration_ms)
        return f"@{kind}," + ",".join(str(value) for value in values)

    def _demo_ack(
        self, command: str, accepted: bool, reason: str, motor: int = 0,
        pulse: int = 1000, duration: int = 0,
    ) -> None:
        now = time.monotonic()
        timestamp = int((now - self.demo_start) * 1_000_000) & 0xFFFFFFFF
        ack = CommandAckRecord(timestamp, command, int(accepted), reason, motor, pulse, duration)
        self._demo_record("MACK", ack, now)

    def close(self) -> None:
        if self.closing:
            return
        self.closing = True
        self.stop_csv()
        worker = self.worker
        if worker is not None:
            worker.request_disconnect(send_stop=not self.replay_mode)
        self.root.after(80, self.root.destroy)
