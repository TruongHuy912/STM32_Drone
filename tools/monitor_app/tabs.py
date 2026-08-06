"""Tkinter tab views. Views expose state setters and delegate actions to app callbacks."""

from __future__ import annotations

import collections
import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable

from .protocol import (
    DURATION_MAX_MS,
    DURATION_MIN_MS,
    MOTOR_MAX,
    MOTOR_MIN,
    PULSE_MAX_US,
    PULSE_MIN_US,
    MTEST_ABORT_NAMES,
    MTEST_STATE_NAMES,
    classify_console_line,
)

GREEN = "#188038"
RED = "#b3261e"
AMBER = "#b06000"
GRAY = "#5f6368"
BLUE = "#1a73e8"

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
MOTOR_NAMES = ("MOTOR1 PD12", "MOTOR2 PD13", "MOTOR3 PD14", "MOTOR4 PD15")


class StatusPill(tk.Label):
    def __init__(self, parent: tk.Misc, text: str = "NO DATA") -> None:
        super().__init__(
            parent,
            text=text,
            background=GRAY,
            foreground="white",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=3,
        )

    def set(self, text: str, ok: bool | None = None, *, color: str | None = None) -> None:
        if color is None:
            color = GRAY if ok is None else (GREEN if ok else RED)
        self.configure(text=text, background=color)


class ValueBar:
    def __init__(
        self,
        parent: tk.Misc,
        row: int,
        name: str,
        minimum: int,
        maximum: int,
        markers: Iterable[int],
    ) -> None:
        self.minimum = minimum
        self.maximum = maximum
        self.markers = tuple(markers)
        ttk.Label(parent, text=name, width=18).grid(
            row=row, column=0, padx=(8, 4), pady=3, sticky="w"
        )
        self.canvas = tk.Canvas(parent, height=25, highlightthickness=1)
        self.canvas.grid(row=row, column=1, padx=4, pady=3, sticky="ew")
        self.value = ttk.Label(parent, text="--", width=10, anchor="e")
        self.value.grid(row=row, column=2, padx=(4, 8), pady=3, sticky="e")
        self.current_value = minimum
        self.current_ok = False
        self.canvas.bind("<Configure>", lambda _event: self._draw())

    def set(self, value: int, ok: bool = True, suffix: str = "") -> None:
        self.current_value = value
        self.current_ok = ok
        self.value.configure(text=f"{value}{suffix}", foreground=GREEN if ok else RED)
        self._draw()

    def _draw(self) -> None:
        width = max(10, self.canvas.winfo_width())
        height = max(10, self.canvas.winfo_height())
        margin = 3

        def x_for(value: int) -> float:
            clipped = min(self.maximum, max(self.minimum, value))
            return margin + (width - 2 * margin) * (
                (clipped - self.minimum) / (self.maximum - self.minimum)
            )

        self.canvas.delete("all")
        self.canvas.create_rectangle(
            margin, margin, width - margin, height - margin, fill="#e8eaed", outline=""
        )
        self.canvas.create_rectangle(
            margin,
            margin,
            x_for(self.current_value),
            height - margin,
            fill=BLUE if self.current_ok else RED,
            outline="",
        )
        for marker in self.markers:
            x = x_for(marker)
            self.canvas.create_line(x, margin, x, height - margin, fill="#202124")


class ConnectionTab(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        connect: Callable[[], None],
        disconnect: Callable[[], None],
        refresh: Callable[[], None],
        log_command: Callable[[str], None],
    ) -> None:
        super().__init__(parent, padding=14)
        self.columnconfigure(0, weight=1)
        connection = ttk.LabelFrame(self, text="Serial Connection", padding=12)
        connection.grid(row=0, column=0, sticky="ew")
        connection.columnconfigure(1, weight=1)
        self.port_var = tk.StringVar()
        self.baud_var = tk.StringVar(value="115200")
        ttk.Label(connection, text="COM port").grid(row=0, column=0, padx=4, pady=6)
        self.port_combo = ttk.Combobox(connection, textvariable=self.port_var, width=18)
        self.port_combo.grid(row=0, column=1, padx=4, pady=6, sticky="w")
        ttk.Button(connection, text="Refresh", command=refresh).grid(
            row=0, column=2, padx=4, pady=6
        )
        ttk.Label(connection, text="Baud").grid(row=0, column=3, padx=(16, 4), pady=6)
        ttk.Combobox(
            connection, textvariable=self.baud_var, values=("115200",), width=10
        ).grid(row=0, column=4, padx=4, pady=6)
        self.connect_button = ttk.Button(connection, text="Connect", command=connect)
        self.connect_button.grid(row=0, column=5, padx=4, pady=6)
        self.disconnect_button = ttk.Button(
            connection, text="Disconnect", command=disconnect, state="disabled"
        )
        self.disconnect_button.grid(row=0, column=6, padx=4, pady=6)
        self.status = StatusPill(connection, "DISCONNECTED")
        self.status.grid(row=1, column=0, columnspan=2, padx=4, pady=8, sticky="w")
        self.status_detail = ttk.Label(connection, text="No board connected")
        self.status_detail.grid(row=1, column=2, columnspan=5, padx=6, pady=8, sticky="w")

        board = ttk.LabelFrame(self, text="Board & Protocol", padding=12)
        board.grid(row=1, column=0, pady=12, sticky="ew")
        self.board_var = tk.StringVar(value="STM32H743 — waiting for telemetry")
        ttk.Label(board, textvariable=self.board_var, font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w"
        )
        self.ages = {
            name: tk.StringVar(value=f"Last @{name}: --")
            for name in ("IBUS", "ESC", "MTEST")
        }
        for index, name in enumerate(("IBUS", "ESC", "MTEST")):
            ttk.Label(board, textvariable=self.ages[name]).grid(
                row=1, column=index, padx=(0, 24), pady=8, sticky="w"
            )
        self.last_rx_var = tk.StringVar(value="Last received: --")
        ttk.Label(board, textvariable=self.last_rx_var).grid(row=2, column=0, sticky="w")
        self.rx_count_var = tk.StringVar(value="RX lines: 0")
        self.tx_count_var = tk.StringVar(value="TX commands: 0")
        ttk.Label(board, textvariable=self.rx_count_var).grid(row=2, column=1, sticky="w")
        ttk.Label(board, textvariable=self.tx_count_var).grid(row=2, column=2, sticky="w")

        logging = ttk.LabelFrame(self, text="Firmware Log Mode", padding=12)
        logging.grid(row=2, column=0, sticky="ew")
        ttk.Label(
            logging,
            text="QUIET keeps machine telemetry, command replies, aborts and critical errors.",
        ).grid(row=0, column=0, columnspan=3, pady=(0, 8), sticky="w")
        self.log_buttons = []
        for column, mode in enumerate(("QUIET", "FULL", "STATUS")):
            button = ttk.Button(
                logging, text=f"LOG {mode}", command=lambda value=mode: log_command(value)
            )
            button.grid(row=1, column=column, padx=(0, 8), sticky="w")
            self.log_buttons.append(button)
        self.set_connected(False)

    def set_connected(self, connected: bool) -> None:
        self.status.set("CONNECTED" if connected else "DISCONNECTED", connected)
        self.connect_button.configure(state="disabled" if connected else "normal")
        self.disconnect_button.configure(state="normal" if connected else "disabled")
        for button in self.log_buttons:
            button.configure(state="normal" if connected else "disabled")


class ReceiverTab(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=12)
        self.columnconfigure(0, weight=1)
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew")
        self.link = StatusPill(header, "LINK LOST")
        self.link.grid(row=0, column=0, padx=(0, 12))
        self.frame_age = tk.StringVar(value="Frame age: -- ms")
        ttk.Label(header, textvariable=self.frame_age).grid(row=0, column=1, padx=8)
        self.counters = tk.StringVar(
            value="valid=0  checksum=0  uart=0  overflow=0"
        )
        ttk.Label(header, textvariable=self.counters).grid(row=0, column=2, padx=8)

        gates = ttk.LabelFrame(self, text="Receiver Safety", padding=8)
        gates.grid(row=1, column=0, pady=10, sticky="ew")
        self.safety_pills: dict[str, StatusPill] = {}
        for column, name in enumerate(("THROTTLE LOW", "CH5 ENABLED", "CH6 ENABLED")):
            pill = StatusPill(gates, f"{name}: FAIL")
            pill.grid(row=0, column=column, padx=8)
            self.safety_pills[name] = pill

        channels = ttk.LabelFrame(
            self, text="Channels — scale 800–2200, markers 1000 / 1500 / 2000", padding=6
        )
        channels.grid(row=2, column=0, sticky="nsew")
        channels.columnconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)
        self.channel_bars = [
            ValueBar(channels, index, name, 800, 2200, (1000, 1500, 2000))
            for index, name in enumerate(CHANNEL_NAMES)
        ]

    def update_record(self, record: object) -> None:
        alive = record.stream_alive == 1
        self.link.set("LINK OK" if alive else "LINK LOST", alive)
        self.frame_age.set(f"Frame age: {record.age_ms} ms")
        self.counters.set(
            f"valid={record.valid_frames}  checksum={record.checksum_errors}  "
            f"uart={record.uart_errors}  overflow={record.ring_overflows}"
        )
        for bar, value in zip(self.channel_bars, record.channels):
            bar.set(value, alive and 800 <= value <= 2200)
        checks = {
            "THROTTLE LOW": record.channels[2] <= 1050,
            "CH5 ENABLED": record.channels[4] >= 1900,
            "CH6 ENABLED": record.channels[5] >= 1900,
        }
        for name, passed in checks.items():
            self.safety_pills[name].set(f"{name}: {'PASS' if passed else 'FAIL'}", passed)


class ESCOutputsTab(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=12)
        self.columnconfigure(0, weight=1)
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew")
        self.state = StatusPill(header)
        self.state.grid(row=0, column=0, padx=(0, 12))
        self.mask_var = tk.StringVar(value="started_mask: --")
        self.frequency_var = tk.StringVar(value="frequency: -- Hz")
        self.age_var = tk.StringVar(value="Last @ESC: --")
        ttk.Label(header, textvariable=self.mask_var).grid(row=0, column=1, padx=8)
        ttk.Label(header, textvariable=self.frequency_var).grid(row=0, column=2, padx=8)
        ttk.Label(header, textvariable=self.age_var).grid(row=0, column=3, padx=8)
        outputs = ttk.LabelFrame(self, text="TIM4 PWM Outputs — scale 900–2100 us", padding=10)
        outputs.grid(row=1, column=0, pady=12, sticky="nsew")
        outputs.columnconfigure(1, weight=1)
        self.output_bars = [
            ValueBar(outputs, index, name, 900, 2100, (1000, 1020, 1100))
            for index, name in enumerate(MOTOR_NAMES)
        ]
        self.diag_var = tk.StringVar(value="rejected=0  start_errors=0")
        ttk.Label(self, textvariable=self.diag_var).grid(row=2, column=0, sticky="w")

    def update_record(self, record: object, fresh: bool = True) -> None:
        safe = record.state == 1
        started = record.started_mask == 0x0F
        overall = safe and started and fresh
        self.state.set("SAFE" if safe else f"ERROR ({record.state})", overall)
        self.mask_var.set(f"started_mask: 0x{record.started_mask:02X}")
        self.frequency_var.set(f"frequency: {record.frequency_hz} Hz")
        for bar, pulse in zip(self.output_bars, record.motor_us):
            allowed = pulse == 1000 or 1020 <= pulse <= 1100
            bar.set(pulse, overall and allowed, " us")
        self.diag_var.set(
            f"rejected={record.rejected}  start_errors={record.start_errors}"
        )

    def set_stale(self, stale: bool) -> None:
        if stale:
            self.state.set("TELEMETRY STALE", False)


class MotorTestTab(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        run: Callable[[], None],
        stop: Callable[[], None],
        emergency: Callable[[], None],
        confirmation_changed: Callable[[], None],
    ) -> None:
        super().__init__(parent, padding=10)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        safety = ttk.LabelFrame(self, text="Safety Checklist", padding=8)
        safety.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.safety_labels: dict[str, StatusPill] = {}
        safety_names = (
            "Serial connected",
            "iBUS link valid",
            "iBUS frame <= 50 ms",
            "Throttle <= 1050",
            "CH5 >= 1900",
            "CH6 >= 1900",
            "ESC state SAFE",
            "started_mask == 0x0F",
            "@ESC telemetry fresh",
            "@MTEST telemetry fresh",
            "Motor test READY",
        )
        for index, name in enumerate(safety_names):
            pill = StatusPill(safety, f"{name}: FAIL")
            pill.grid(row=index // 4, column=index % 4, padx=5, pady=3, sticky="w")
            self.safety_labels[name] = pill
        self.propellers_var = tk.BooleanVar(value=False)
        self.propellers_check = ttk.Checkbutton(
            safety,
            text="I confirm that all propellers are removed.",
            variable=self.propellers_var,
            command=confirmation_changed,
        )
        self.propellers_check.grid(row=3, column=0, columnspan=4, padx=5, pady=(8, 2), sticky="w")

        controls = ttk.LabelFrame(self, text="Manual Single-Motor Command", padding=10)
        controls.grid(row=1, column=0, padx=(0, 6), pady=10, sticky="nsew")
        self.motor_var = tk.IntVar(value=1)
        self.pulse_var = tk.IntVar(value=PULSE_MIN_US)
        self.duration_var = tk.IntVar(value=500)
        ttk.Label(controls, text="Motor").grid(row=0, column=0, sticky="w")
        self.motor_combo = ttk.Combobox(
            controls,
            state="readonly",
            values=tuple(f"Motor {i} — PD{11 + i}" for i in range(MOTOR_MIN, MOTOR_MAX + 1)),
            width=22,
        )
        self.motor_combo.current(0)
        self.motor_combo.grid(row=0, column=1, padx=6, pady=4)
        ttk.Label(controls, text="Pulse").grid(row=1, column=0, sticky="w")
        self.pulse_spin = ttk.Spinbox(
            controls,
            from_=PULSE_MIN_US,
            to=PULSE_MAX_US,
            increment=10,
            textvariable=self.pulse_var,
            width=10,
        )
        self.pulse_spin.grid(row=1, column=1, padx=6, pady=4, sticky="w")
        ttk.Label(controls, text="us").grid(row=1, column=2, sticky="w")
        ttk.Label(controls, text="Duration").grid(row=2, column=0, sticky="w")
        self.duration_spin = ttk.Spinbox(
            controls,
            from_=DURATION_MIN_MS,
            to=DURATION_MAX_MS,
            increment=100,
            textvariable=self.duration_var,
            width=10,
        )
        self.duration_spin.grid(row=2, column=1, padx=6, pady=4, sticky="w")
        ttk.Label(controls, text="ms").grid(row=2, column=2, sticky="w")
        self.run_button = ttk.Button(controls, text="RUN SELECTED MOTOR", command=run)
        self.run_button.grid(row=3, column=0, columnspan=3, pady=(10, 4), sticky="ew")
        self.stop_button = ttk.Button(controls, text="STOP", command=stop)
        self.stop_button.grid(row=4, column=0, columnspan=3, pady=4, sticky="ew")
        self.emergency_button = tk.Button(
            controls,
            text="EMERGENCY STOP  !",
            command=emergency,
            background=RED,
            foreground="white",
            activebackground="#8c1d18",
            activeforeground="white",
            font=("Segoe UI", 12, "bold"),
            pady=7,
        )
        self.emergency_button.grid(row=5, column=0, columnspan=3, pady=(8, 2), sticky="ew")

        status = ttk.LabelFrame(self, text="Firmware Motor-Test State", padding=10)
        status.grid(row=1, column=1, padx=(6, 0), pady=10, sticky="nsew")
        self.state = StatusPill(status)
        self.state.grid(row=0, column=0, padx=(0, 10), sticky="w")
        self.status_var = tk.StringVar(value="Waiting for @MTEST telemetry")
        ttk.Label(status, textvariable=self.status_var, justify="left").grid(
            row=1, column=0, columnspan=2, pady=8, sticky="w"
        )
        self.progress = ttk.Progressbar(status, mode="determinate", maximum=2000)
        self.progress.grid(row=2, column=0, columnspan=2, sticky="ew")
        status.columnconfigure(0, weight=1)
        self.ack = StatusPill(status, "NO COMMAND ACK")
        self.ack.grid(row=3, column=0, pady=(12, 4), sticky="w")
        self.ack_var = tk.StringVar(value="Last command: --")
        ttk.Label(status, textvariable=self.ack_var).grid(row=4, column=0, sticky="w")
        self.request_var = tk.StringVar(value="")
        ttk.Label(status, textvariable=self.request_var, foreground=AMBER).grid(
            row=5, column=0, pady=4, sticky="w"
        )
        self.set_connected(False)

    def selected_motor(self) -> int:
        return self.motor_combo.current() + 1

    def clear_confirmation(self) -> None:
        self.propellers_var.set(False)

    def set_safety(self, values: dict[str, bool]) -> None:
        for name, passed in values.items():
            self.safety_labels[name].set(
                f"{name}: {'PASS' if passed else 'FAIL'}", passed
            )

    def set_connected(self, connected: bool) -> None:
        state = "normal" if connected else "disabled"
        self.stop_button.configure(state=state)
        self.emergency_button.configure(state=state)
        if not connected:
            self.run_button.configure(state="disabled")
            self.propellers_check.configure(state="disabled")
        else:
            self.propellers_check.configure(state="normal")

    def set_control_state(self, connected: bool, running: bool, can_run: bool) -> None:
        edit_state = "disabled" if running or not connected else "readonly"
        self.motor_combo.configure(state=edit_state)
        spin_state = "disabled" if running or not connected else "normal"
        self.pulse_spin.configure(state=spin_state)
        self.duration_spin.configure(state=spin_state)
        self.run_button.configure(state="normal" if can_run else "disabled")
        self.stop_button.configure(state="normal" if connected else "disabled")
        self.emergency_button.configure(state="normal" if connected else "disabled")

    def update_record(self, record: object, progress_max: int) -> None:
        state_name = MTEST_STATE_NAMES[record.state]
        color = {
            "DISABLED": GRAY,
            "READY": GREEN,
            "RUNNING": AMBER,
            "FAULT": RED,
        }[state_name]
        idle_output_safe = record.state not in (0, 1) or record.active_us == 1000
        if not idle_output_safe:
            state_name = f"{state_name} / OUTPUT NOT SAFE"
            color = RED
        self.state.set(state_name, color=color)
        self.status_var.set(
            f"motor={record.motor}  commanded={record.commanded_us} us  "
            f"active={record.active_us} us\n"
            f"remaining={record.remaining_ms} ms  gates=0x{record.gate_mask:02X}  "
            f"abort={MTEST_ABORT_NAMES[record.last_abort]}\n"
            f"runs={record.run_count}  completed={record.completed_count}  "
            f"aborted={record.abort_count}  rejected={record.rejected_count}"
        )
        self.progress.configure(maximum=max(1, progress_max))
        self.progress["value"] = min(progress_max, record.remaining_ms)
        if record.state != 2 and self.request_var.get() == "STOP REQUESTED":
            self.request_var.set("STOP CONFIRMED BY TELEMETRY")

    def update_ack(self, ack: object) -> None:
        accepted = ack.accepted == 1
        self.ack.set("ACCEPTED" if accepted else "REJECTED", accepted)
        self.ack_var.set(
            f"Last command: {ack.command}  reason={ack.reason}  "
            f"t_us={ack.timestamp_us}"
        )


class DiagnosticsTab(ttk.Frame):
    MAX_STORED_LINES = 2000
    MAX_WIDGET_LINES = 1000

    def __init__(
        self,
        parent: tk.Misc,
        start_csv: Callable[[], None],
        stop_csv: Callable[[], None],
    ) -> None:
        super().__init__(parent, padding=8)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew")
        self.filter_var = tk.StringVar(value="ALL")
        ttk.Label(toolbar, text="Filter").pack(side="left")
        filter_box = ttk.Combobox(
            toolbar,
            textvariable=self.filter_var,
            state="readonly",
            width=12,
            values=("ALL", "IBUS", "ESC", "MTEST", "MACK", "SENSORS", "ERRORS"),
        )
        filter_box.pack(side="left", padx=5)
        filter_box.bind("<<ComboboxSelected>>", lambda _event: self.redraw())
        self.paused = False
        self.pause_button = ttk.Button(toolbar, text="Pause", command=self.toggle_pause)
        self.pause_button.pack(side="left", padx=4)
        ttk.Button(toolbar, text="Clear", command=self.clear).pack(side="left", padx=4)
        self.autoscroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(toolbar, text="Auto-scroll", variable=self.autoscroll_var).pack(
            side="left", padx=8
        )
        self.text = tk.Text(self, wrap="none", height=20, font=("Consolas", 9))
        self.text.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(self, command=self.text.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set, state="disabled")
        self.lines: collections.deque[tuple[str, str]] = collections.deque(
            maxlen=self.MAX_STORED_LINES
        )

        counters = ttk.LabelFrame(self, text="Diagnostics", padding=6)
        counters.grid(row=2, column=0, columnspan=2, pady=6, sticky="ew")
        self.counter_var = tk.StringVar(value="Waiting for telemetry")
        ttk.Label(counters, textvariable=self.counter_var).grid(row=0, column=0, sticky="w")

        csv_frame = ttk.LabelFrame(self, text="Optional CSV Logging", padding=6)
        csv_frame.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.csv_types = {
            kind: tk.BooleanVar(value=True) for kind in ("IBUS", "ESC", "MTEST", "MACK")
        }
        for column, (kind, variable) in enumerate(self.csv_types.items()):
            ttk.Checkbutton(csv_frame, text=kind, variable=variable).grid(
                row=0, column=column, padx=5
            )
        self.csv_start = ttk.Button(csv_frame, text="Start CSV", command=start_csv)
        self.csv_start.grid(row=0, column=4, padx=8)
        self.csv_stop = ttk.Button(
            csv_frame, text="Stop CSV", command=stop_csv, state="disabled"
        )
        self.csv_stop.grid(row=0, column=5, padx=4)
        self.csv_status = tk.StringVar(value="CSV logging stopped")
        ttk.Label(csv_frame, textvariable=self.csv_status).grid(
            row=0, column=6, padx=8, sticky="w"
        )

    def append_line(self, line: str) -> None:
        category = classify_console_line(line)
        self.lines.append((category, line))
        selected = self.filter_var.get()
        if not self.paused and (selected == "ALL" or selected == category):
            self._insert(line)

    def _insert(self, line: str) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n")
        line_count = int(self.text.index("end-1c").split(".")[0])
        if line_count > self.MAX_WIDGET_LINES:
            self.text.delete("1.0", f"{line_count - self.MAX_WIDGET_LINES + 1}.0")
        if self.autoscroll_var.get():
            self.text.see("end")
        self.text.configure(state="disabled")

    def redraw(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        selected = self.filter_var.get()
        for category, line in self.lines:
            if selected == "ALL" or selected == category:
                self.text.insert("end", line + "\n")
        if self.autoscroll_var.get():
            self.text.see("end")
        self.text.configure(state="disabled")

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.pause_button.configure(text="Resume" if self.paused else "Pause")
        if not self.paused:
            self.redraw()

    def clear(self) -> None:
        self.lines.clear()
        self.redraw()
