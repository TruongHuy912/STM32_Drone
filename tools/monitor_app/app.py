"""Application coordinator for the five-tab drone bench configurator."""

from __future__ import annotations

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

from .controller import CommandDispatcher, OutgoingQueue
from .models import CommandAckRecord, ESCRecord, IBusRecord, MotorTestRecord, ParsedLine, SafetySnapshot
from .protocol import (
    MTEST_ABORT_NAMES,
    classify_console_line,
    firmware_reset_detected,
    parse_ibus_header_errors,
    telemetry_is_fresh,
    validate_run_values,
)
from .serial_worker import SerialWorker
from .tabs import ConnectionTab, DiagnosticsTab, ESCOutputsTab, MotorTestTab, ReceiverTab

QUEUE_POLL_MS = 25
AGE_UPDATE_MS = 100
IBUS_RECEIPT_FRESH_S = 0.25
ESC_FRESH_S = 0.35
MTEST_FRESH_S = 0.35


class BenchConfiguratorApp:
    def __init__(
        self,
        root: tk.Tk,
        initial_port: Optional[str] = None,
        baud: int = 115200,
        demo: bool = False,
    ) -> None:
        self.root = root
        self.root.title("STM32H743 Drone Bench Configurator")
        self.root.geometry("1100x700")
        self.root.minsize(900, 620)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.events: queue.Queue = queue.Queue()
        self.outgoing = OutgoingQueue()
        self.dispatcher = CommandDispatcher(self.outgoing)
        self.worker: Optional[SerialWorker] = None
        self.connection_id = 0
        self.connected = False
        self.demo = demo
        self.closing = False
        self.reconnect_count = 0
        self.successful_connections = 0
        self.rx_line_count = 0
        self.tx_command_count = 0
        self.last_serial_error: Optional[str] = None
        self.last_rx_monotonic: Optional[float] = None
        self.latest_ibus: Optional[IBusRecord] = None
        self.latest_esc: Optional[ESCRecord] = None
        self.latest_mtest: Optional[MotorTestRecord] = None
        self.latest_ack: Optional[CommandAckRecord] = None
        self.received_at: dict[str, Optional[float]] = {
            "IBUS": None,
            "ESC": None,
            "MTEST": None,
            "MACK": None,
        }
        self.last_firmware_timestamp: dict[str, Optional[int]] = {
            key: None for key in self.received_at
        }
        self.malformed = {key: 0 for key in ("IBUS", "ESC", "MTEST", "MACK")}
        self.header_errors = 0
        self.auto_stop_latched = False
        self.csv_file: Optional[TextIO] = None
        self.csv_writer: Optional[csv.writer] = None
        self.demo_start = time.monotonic()
        self.demo_manual_until: Optional[float] = None
        self.demo_manual_motor = 1
        self.demo_manual_pulse = 1020
        self.demo_manual_duration = 500
        self.demo_last_emit = 0.0

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=6, pady=6)
        self.connection_tab = ConnectionTab(
            notebook, self.connect, self.disconnect, self.refresh_ports, self.send_log_command
        )
        self.receiver_tab = ReceiverTab(notebook)
        self.esc_tab = ESCOutputsTab(notebook)
        self.motor_tab = MotorTestTab(
            notebook,
            self.run_selected_motor,
            self.request_stop,
            self.request_emergency_stop,
            self.refresh_safety,
        )
        self.diagnostics_tab = DiagnosticsTab(notebook, self.start_csv, self.stop_csv)
        for tab, title in (
            (self.connection_tab, "Connection"),
            (self.receiver_tab, "Receiver"),
            (self.esc_tab, "ESC Outputs"),
            (self.motor_tab, "Motor Test"),
            (self.diagnostics_tab, "Diagnostics & Logs"),
        ):
            notebook.add(tab, text=title)

        self.connection_tab.port_var.set(initial_port or "")
        self.connection_tab.baud_var.set(str(baud))
        self.refresh_ports()
        self.root.after(QUEUE_POLL_MS, self.process_events)
        self.root.after(AGE_UPDATE_MS, self.update_ages)
        if demo:
            self.start_demo()

    def refresh_ports(self) -> None:
        current = self.connection_tab.port_var.get().strip()
        ports: list[str] = []
        if list_ports is not None:
            try:
                ports = sorted(port.device for port in list_ports.comports())
            except Exception:
                ports = []
        if current and current not in ports:
            ports.insert(0, current)
        self.connection_tab.port_combo.configure(values=ports)
        if not current and ports:
            self.connection_tab.port_var.set(ports[0])

    def connect(self) -> None:
        if self.demo or self.worker is not None:
            return
        port_name = self.connection_tab.port_var.get().strip()
        if not port_name:
            messagebox.showwarning("COM port", "Select or enter a COM port.")
            return
        try:
            baud = int(self.connection_tab.baud_var.get(), 10)
            if baud <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Baud", "Baud must be a positive integer.")
            return
        self.outgoing.clear()
        self.last_serial_error = None
        self.connection_id += 1
        self.worker = SerialWorker(
            self.connection_id, port_name, baud, self.events, self.outgoing
        )
        self.connection_tab.status.set("CONNECTING", color="#b06000")
        self.connection_tab.status_detail.configure(text=f"Opening {port_name}...")
        self.connection_tab.connect_button.configure(state="disabled")
        self.worker.start()

    def disconnect(self) -> None:
        if self.demo:
            return
        worker = self.worker
        self.last_serial_error = None
        self._disable_motor_controls("DISCONNECTING — best-effort STOP requested")
        if worker is not None:
            worker.request_disconnect(send_stop=True)
        self.connected = False
        self.dispatcher.set_connected(False)
        self.connection_tab.set_connected(False)
        if worker is not None:
            self.connection_tab.connect_button.configure(state="disabled")
            self.connection_tab.status.set("DISCONNECTING", color="#b06000")

    def _disable_motor_controls(self, message: str) -> None:
        self.motor_tab.clear_confirmation()
        self.motor_tab.set_connected(False)
        self.motor_tab.request_var.set(message)
        self.auto_stop_latched = True

    def send_log_command(self, mode: str) -> None:
        if self.demo:
            self._demo_ack(f"LOG_{mode}", True, "NONE")
            return
        self.dispatcher.queue_log(mode)

    def run_selected_motor(self) -> None:
        motor = self.motor_tab.selected_motor()
        try:
            pulse = int(self.motor_tab.pulse_var.get())
            duration = int(self.motor_tab.duration_var.get())
            validate_run_values(motor, pulse, duration)
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("Invalid motor command", str(exc))
            return
        safety = self.current_safety()
        if not self.dispatcher.can_run(safety):
            messagebox.showwarning("Safety gate", "RUN is disabled until every safety item passes.")
            return
        confirmation = (
            f"Motor {motor}\nPulse {pulse} us\nDuration {duration} ms\n\n"
            "PROPELLERS MUST BE REMOVED"
        )
        if not messagebox.askokcancel("Confirm single-motor test", confirmation, icon="warning"):
            return
        if self.demo:
            self.demo_manual_motor = motor
            self.demo_manual_pulse = pulse
            self.demo_manual_duration = duration
            self.demo_manual_until = time.monotonic() + duration / 1000.0
            self.dispatcher.run_pending = True
            self._demo_ack("RUN", True, "NONE", motor, pulse, duration)
            self.dispatcher.run_pending = False
        elif not self.dispatcher.queue_run(motor, pulse, duration):
            return
        self.motor_tab.request_var.set("RUN REQUESTED — awaiting firmware ACK")
        self.refresh_safety()

    def request_stop(self, *, automatic: bool = False) -> None:
        if automatic and self.auto_stop_latched:
            return
        if automatic:
            self.auto_stop_latched = True
        if self.demo:
            self.demo_manual_until = None
            self._demo_ack("STOP", True, "USER_STOP")
        else:
            self.dispatcher.queue_stop(front=True)
        self.motor_tab.request_var.set("STOP REQUESTED")
        self.refresh_safety()

    def request_emergency_stop(self) -> None:
        if self.demo:
            self.demo_manual_until = None
            self._demo_ack("ESTOP", True, "EMERGENCY_STOP")
        else:
            self.dispatcher.queue_emergency_stop()
        self.auto_stop_latched = True
        self.motor_tab.request_var.set("STOP REQUESTED — EMERGENCY ! sent")
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
                    self.dispatcher.set_connected(True)
                    self.successful_connections += 1
                    self.reconnect_count = max(0, self.successful_connections - 1)
                    self.connection_tab.set_connected(True)
                    self.connection_tab.status_detail.configure(text=str(payload))
                    self.connection_tab.board_var.set("STM32H743 — H3B-2 protocol connected")
                    self.motor_tab.set_connected(True)
                elif kind == "line":
                    line, count, received = payload
                    self.rx_line_count = count
                    self.last_rx_monotonic = received
                    self.diagnostics_tab.append_line(line)
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
                    self.diagnostics_tab.append_line(f"> {request.display}")
                elif kind == "serial_error":
                    self.last_serial_error = str(payload)
                    self.connection_tab.status.set("SERIAL ERROR", False)
                    self.connection_tab.status_detail.configure(text=self.last_serial_error)
                    self._disable_motor_controls("SERIAL ERROR — best-effort STOP attempted")
                    self.connected = False
                    self.dispatcher.set_connected(False)
                elif kind == "disconnected":
                    self.worker = None
                    self.connected = False
                    self.dispatcher.set_connected(False)
                    self.connection_tab.set_connected(False)
                    if self.last_serial_error is not None:
                        self.connection_tab.status.set("SERIAL ERROR", False)
                        self.connection_tab.status_detail.configure(
                            text=self.last_serial_error
                        )
                    else:
                        self.connection_tab.status_detail.configure(text="Serial port closed")
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
            self.motor_tab.clear_confirmation()
            self.dispatcher.run_pending = False
            self.motor_tab.request_var.set("FIRMWARE RESET DETECTED — confirmation cleared")
        self.last_firmware_timestamp[parsed.kind] = timestamp
        self.received_at[parsed.kind] = received
        if parsed.kind == "IBUS":
            self.latest_ibus = record
            self.receiver_tab.update_record(record)
        elif parsed.kind == "ESC":
            self.latest_esc = record
            self.esc_tab.update_record(record, True)
        elif parsed.kind == "MTEST":
            self.latest_mtest = record
            self.dispatcher.handle_mtest_state(record.state)
            self.motor_tab.update_record(record, self.dispatcher.last_run_duration_ms)
            if record.state != 2:
                self.auto_stop_latched = False
        elif parsed.kind == "MACK":
            self.latest_ack = record
            self.dispatcher.handle_ack(record)
            self.motor_tab.update_ack(record)
        self.refresh_safety()

    def current_safety(self, now: Optional[float] = None) -> SafetySnapshot:
        now = time.monotonic() if now is None else now
        ibus = self.latest_ibus
        esc = self.latest_esc
        mtest = self.latest_mtest
        ibus_receipt_fresh = telemetry_is_fresh(
            self.received_at["IBUS"], now, IBUS_RECEIPT_FRESH_S
        )
        return SafetySnapshot(
            serial_connected=self.connected,
            ibus_link_valid=bool(ibus and ibus_receipt_fresh and ibus.stream_alive == 1),
            ibus_fresh=bool(ibus and ibus_receipt_fresh and ibus.age_ms <= 50),
            throttle_low=bool(ibus and ibus.channels[2] <= 1050),
            ch5_enabled=bool(ibus and ibus.channels[4] >= 1900),
            ch6_enabled=bool(ibus and ibus.channels[5] >= 1900),
            esc_safe=bool(esc and esc.state == 1),
            esc_started=bool(esc and esc.started_mask == 0x0F),
            esc_fresh=telemetry_is_fresh(self.received_at["ESC"], now, ESC_FRESH_S),
            mtest_fresh=telemetry_is_fresh(
                self.received_at["MTEST"], now, MTEST_FRESH_S
            ),
            mtest_ready=bool(
                mtest and mtest.state == 1 and mtest.active_us == 1000
            ),
            propellers_removed=self.motor_tab.propellers_var.get(),
        )

    def refresh_safety(self) -> None:
        safety = self.current_safety()
        values = {
            "Serial connected": safety.serial_connected,
            "iBUS link valid": safety.ibus_link_valid,
            "iBUS frame <= 50 ms": safety.ibus_fresh,
            "Throttle <= 1050": safety.throttle_low,
            "CH5 >= 1900": safety.ch5_enabled,
            "CH6 >= 1900": safety.ch6_enabled,
            "ESC state SAFE": safety.esc_safe,
            "started_mask == 0x0F": safety.esc_started,
            "@ESC telemetry fresh": safety.esc_fresh,
            "@MTEST telemetry fresh": safety.mtest_fresh,
            "Motor test READY": safety.mtest_ready,
        }
        self.motor_tab.set_safety(values)
        running = bool(self.latest_mtest and self.latest_mtest.state == 2)
        self.motor_tab.set_control_state(
            self.connected, running, self.dispatcher.can_run(safety)
        )
        if running:
            unsafe_while_running = not all(
                (
                    safety.ibus_link_valid,
                    safety.ibus_fresh,
                    safety.throttle_low,
                    safety.ch5_enabled,
                    safety.ch6_enabled,
                )
            )
            if unsafe_while_running and not self.auto_stop_latched:
                self.request_stop(automatic=True)

    def update_ages(self) -> None:
        now = time.monotonic()
        for kind in ("IBUS", "ESC", "MTEST"):
            received = self.received_at[kind]
            text = "--" if received is None else f"{now - received:.1f} s ago"
            self.connection_tab.ages[kind].set(f"Last @{kind}: {text}")
        if self.last_rx_monotonic is None:
            self.connection_tab.last_rx_var.set("Last received: --")
        else:
            self.connection_tab.last_rx_var.set(
                f"Last received: {now - self.last_rx_monotonic:.1f} s ago"
            )
        self.connection_tab.rx_count_var.set(f"RX lines: {self.rx_line_count}")
        self.connection_tab.tx_count_var.set(f"TX commands: {self.tx_command_count}")
        esc_fresh = telemetry_is_fresh(self.received_at["ESC"], now, ESC_FRESH_S)
        self.esc_tab.age_var.set(
            "Last @ESC: --"
            if self.received_at["ESC"] is None
            else f"Last @ESC: {now - self.received_at['ESC']:.1f} s ago"
        )
        self.esc_tab.set_stale(not esc_fresh)
        self._update_diagnostics()
        self.refresh_safety()
        if self.demo:
            self.demo_tick(now)
        if not self.closing:
            self.root.after(AGE_UPDATE_MS, self.update_ages)

    def _update_diagnostics(self) -> None:
        ibus = self.latest_ibus
        self.diagnostics_tab.counter_var.set(
            f"valid={getattr(ibus, 'valid_frames', 0)}  "
            f"crc={getattr(ibus, 'checksum_errors', 0)}  header={self.header_errors}  "
            f"uart={getattr(ibus, 'uart_errors', 0)}  "
            f"overflow={getattr(ibus, 'ring_overflows', 0)}  "
            f"malformed IBUS/ESC/MTEST/MACK="
            f"{self.malformed['IBUS']}/{self.malformed['ESC']}/"
            f"{self.malformed['MTEST']}/{self.malformed['MACK']}  "
            f"reconnects={self.reconnect_count}  TX={self.tx_command_count}"
        )

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
            self.diagnostics_tab.csv_status.set(f"Logging: {path.name}")
            self.diagnostics_tab.csv_start.configure(state="disabled")
            self.diagnostics_tab.csv_stop.configure(state="normal")
        except OSError as exc:
            messagebox.showerror("CSV logging", str(exc))

    def stop_csv(self) -> None:
        if self.csv_file is not None:
            try:
                self.csv_file.close()
            except OSError:
                pass
        self.csv_file = None
        self.csv_writer = None
        self.diagnostics_tab.csv_status.set("CSV logging stopped")
        self.diagnostics_tab.csv_start.configure(state="normal")
        self.diagnostics_tab.csv_stop.configure(state="disabled")

    def _write_csv(self, line: str) -> None:
        if self.csv_writer is None:
            return
        kind = classify_console_line(line)
        selected = self.diagnostics_tab.csv_types
        if kind not in selected or not selected[kind].get():
            return
        try:
            self.csv_writer.writerow(
                (datetime.now().astimezone().isoformat(timespec="milliseconds"), kind, line)
            )
        except OSError as exc:
            self.stop_csv()
            self.diagnostics_tab.csv_status.set(f"CSV error: {exc}")

    def start_demo(self) -> None:
        self.connected = True
        self.dispatcher.set_connected(True)
        self.connection_tab.set_connected(True)
        self.connection_tab.connect_button.configure(state="disabled")
        self.connection_tab.disconnect_button.configure(state="disabled")
        self.connection_tab.status.set("DEMO", color="#1a73e8")
        self.connection_tab.status_detail.configure(text="No COM port opened; no serial writes")
        self.connection_tab.board_var.set("STM32H743 H3B-2 simulated telemetry")
        self.motor_tab.set_connected(True)

    def demo_tick(self, now: float) -> None:
        if now - self.demo_last_emit < 0.1:
            return
        self.demo_last_emit = now
        elapsed = now - self.demo_start
        phase = elapsed % 14.0
        link_alive = phase < 10.0
        stale = 11.0 <= phase < 13.0
        channels = (
            int(1500 + 350 * math.sin(elapsed)),
            int(1500 + 300 * math.sin(elapsed * 0.7)),
            1000,
            1500,
            2000,
            2000,
            1500,
            1500,
        )
        timestamp = int(elapsed * 1_000_000) & 0xFFFFFFFF
        ibus = IBusRecord(timestamp, int(link_alive), 3 if link_alive else 150, channels, int(elapsed * 140), 0, 0, 0)
        self._demo_record("IBUS", ibus, now)
        if not stale:
            manual_running = self.demo_manual_until is not None and now < self.demo_manual_until
            auto_running = 3.0 <= phase < 5.0
            running = manual_running or auto_running
            if manual_running:
                motor, pulse = self.demo_manual_motor, self.demo_manual_pulse
                remaining = max(0, int((self.demo_manual_until - now) * 1000))
            elif auto_running:
                motor, pulse, remaining = 1, 1050, int((5.0 - phase) * 1000)
            else:
                motor, pulse, remaining = 0, 0, 0
            motor_us = [1000, 1000, 1000, 1000]
            if running:
                motor_us[motor - 1] = pulse
            esc = ESCRecord(timestamp, 1, 0x0F, 50, tuple(motor_us), 0, 0)  # type: ignore[arg-type]
            if running or phase < 5.0:
                last_abort = 0
            elif phase < 6.0:
                last_abort = 3  # TIME_EXPIRED
            elif phase < 7.0:
                last_abort = 2  # EMERGENCY_STOP
            else:
                last_abort = 3
            mtest = MotorTestRecord(
                timestamp, 2 if running else 1, motor, pulse, pulse if running else 1000,
                remaining, 0xFF, last_abort, int(elapsed // 14) + 1, int(elapsed // 14), 0, 0,
            )
            self._demo_record("ESC", esc, now)
            self._demo_record("MTEST", mtest, now)
        if 7.0 <= phase < 7.2:
            self._demo_ack("RUN", False, "CH5_NOT_ENABLED", 1, 1050, 500)
        self.rx_line_count += 3
        self.last_rx_monotonic = now

    def _demo_record(self, kind: str, record: object, received: float) -> None:
        raw = f"@{kind},demo"
        self.diagnostics_tab.append_line(raw)
        self._handle_record(ParsedLine(kind, record, raw), received)

    def _demo_ack(
        self,
        command: str,
        accepted: bool,
        reason: str,
        motor: int = 0,
        pulse: int = 1000,
        duration: int = 0,
    ) -> None:
        timestamp = int((time.monotonic() - self.demo_start) * 1_000_000) & 0xFFFFFFFF
        ack = CommandAckRecord(timestamp, command, int(accepted), reason, motor, pulse, duration)
        self.tx_command_count += 1
        self.diagnostics_tab.append_line(
            f"@MACK,{timestamp},{command},{int(accepted)},{reason},{motor},{pulse},{duration}"
        )
        self._handle_record(ParsedLine("MACK", ack, "@MACK,demo"), time.monotonic())

    def close(self) -> None:
        if self.closing:
            return
        self.closing = True
        self.motor_tab.clear_confirmation()
        worker = self.worker
        if worker is not None:
            worker.request_disconnect(send_stop=True)
            worker.join(timeout=0.2)
        self.stop_csv()
        self.root.destroy()
