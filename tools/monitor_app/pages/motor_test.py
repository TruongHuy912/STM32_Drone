"""Safety-gated single-motor test page."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Mapping

from ..constants import GATE_LABELS, MOTORS
from ..models import CommandAckRecord, MotorTestRecord
from ..protocol import (
    DURATION_MAX_MS,
    DURATION_MIN_MS,
    MTEST_ABORT_NAMES,
    MTEST_STATE_NAMES,
    PULSE_MAX_US,
    PULSE_MIN_US,
)
from ..theme import COLORS, FONTS
from ..ui_state import fault_presentation
from ..widgets import SafetyItem, StatusBadge, Tooltip


class MotorTestPage(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        run: Callable[[], None],
        stop: Callable[[], None],
        emergency: Callable[[], None],
        confirmation_changed: Callable[[], None],
    ) -> None:
        super().__init__(parent, style="App.TFrame", padding=14)
        self.columnconfigure(0, weight=11, minsize=275)
        self.columnconfigure(1, weight=10, minsize=275)
        self.columnconfigure(2, weight=10, minsize=275)
        self.rowconfigure(0, weight=1)
        self._run_callback = run
        self._stop_callback = stop
        self._emergency_callback = emergency
        self._selected_motor = 1
        self._connected = False
        self._running = False
        self._control_state: tuple[bool, bool, bool, str] | None = None

        self._build_safety_column()
        self._build_setup_column(confirmation_changed)
        self._build_live_column()
        self._build_guide()

    def _build_safety_column(self) -> None:
        card = ttk.Frame(self, style="Card.TFrame", padding=12)
        card.grid(row=0, column=0, padx=(0, 6), sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(2, weight=1)
        ttk.Label(card, text="A · SAFETY GATE", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card, text="Every item must pass here and independently in firmware.", style="SurfaceSecondary.TLabel", wraplength=300).grid(row=1, column=0, sticky="w", pady=(3, 9))
        canvas = tk.Canvas(card, width=270, background=COLORS["SURFACE"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(card, command=canvas.yview)
        canvas.grid(row=2, column=0, sticky="nsew")
        scrollbar.grid(row=2, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)
        inner = ttk.Frame(canvas, style="Surface.TFrame")
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        self.safety_items: dict[str, SafetyItem] = {}
        for row, (key, (title, help_text)) in enumerate(GATE_LABELS.items()):
            item = SafetyItem(inner, title, help_text)
            item.grid(row=row, column=0, sticky="ew", pady=(0, 5))
            self.safety_items[key] = item
        inner.columnconfigure(0, weight=1)

    def _build_setup_column(self, confirmation_changed: Callable[[], None]) -> None:
        card = ttk.Frame(self, style="Card.TFrame", padding=12)
        card.grid(row=0, column=1, padx=6, sticky="nsew")
        card.columnconfigure((0, 1), weight=1)
        ttk.Label(card, text="B · TEST SETUP", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(card, text="One motor only. Start with the lowest preset.", style="SurfaceSecondary.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 10))
        self.motor_buttons: dict[int, tk.Button] = {}
        for index, (number, name, pin, _timer) in enumerate(MOTORS):
            button = tk.Button(
                card, text=f"{name}\n{pin}", command=lambda value=number: self.select_motor(value),
                background=COLORS["SURFACE_ALT"], foreground=COLORS["TEXT_PRIMARY"],
                activebackground=COLORS["ACCENT_DARK"], activeforeground=COLORS["WHITE"],
                font=FONTS["NORMAL_BOLD"], borderwidth=1, relief="solid", padx=8, pady=8,
                highlightthickness=0,
            )
            button.grid(row=2 + index // 2, column=index % 2, padx=(0 if index % 2 == 0 else 4, 4 if index % 2 == 0 else 0), pady=4, sticky="ew")
            self.motor_buttons[number] = button
        self.select_motor(1)

        self.pulse_var = tk.IntVar(value=PULSE_MIN_US)
        self.duration_var = tk.IntVar(value=500)
        ttk.Label(card, text="Pulse", style="Surface.TLabel").grid(row=4, column=0, sticky="w", pady=(12, 2))
        self.pulse_spin = ttk.Spinbox(card, from_=PULSE_MIN_US, to=PULSE_MAX_US, increment=10, textvariable=self.pulse_var, width=9)
        self.pulse_spin.grid(row=4, column=1, sticky="e", pady=(12, 2))
        self.pulse_scale = tk.Scale(
            card, from_=PULSE_MIN_US, to=PULSE_MAX_US, resolution=10, orient="horizontal",
            variable=self.pulse_var, showvalue=False, background=COLORS["SURFACE"],
            foreground=COLORS["TEXT_PRIMARY"], troughcolor=COLORS["SURFACE_ALT"],
            activebackground=COLORS["ACCENT"], highlightthickness=0,
        )
        self.pulse_scale.grid(row=5, column=0, columnspan=2, sticky="ew")
        ttk.Label(card, text=f"Allowed {PULSE_MIN_US}–{PULSE_MAX_US} us · step 10 us", style="SurfaceSecondary.TLabel").grid(row=6, column=0, columnspan=2, sticky="w")
        ttk.Label(card, text="Duration", style="Surface.TLabel").grid(row=7, column=0, sticky="w", pady=(10, 2))
        self.duration_spin = ttk.Spinbox(card, from_=DURATION_MIN_MS, to=DURATION_MAX_MS, increment=100, textvariable=self.duration_var, width=9)
        self.duration_spin.grid(row=7, column=1, sticky="e", pady=(10, 2))
        self.duration_scale = tk.Scale(
            card, from_=DURATION_MIN_MS, to=DURATION_MAX_MS, resolution=100, orient="horizontal",
            variable=self.duration_var, showvalue=False, background=COLORS["SURFACE"],
            foreground=COLORS["TEXT_PRIMARY"], troughcolor=COLORS["SURFACE_ALT"],
            activebackground=COLORS["ACCENT"], highlightthickness=0,
        )
        self.duration_scale.grid(row=8, column=0, columnspan=2, sticky="ew")
        ttk.Label(card, text=f"Allowed {DURATION_MIN_MS}–{DURATION_MAX_MS} ms · step 100 ms", style="SurfaceSecondary.TLabel").grid(row=9, column=0, columnspan=2, sticky="w")
        preset = ttk.Frame(card, style="Surface.TFrame")
        preset.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        preset.columnconfigure((0, 1), weight=1)
        ttk.Button(preset, text="SAFE START\n1020 us / 100 ms", style="Secondary.TButton", command=lambda: self.set_preset(1020, 100)).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(preset, text="SHORT TEST\n1050 us / 500 ms", style="Secondary.TButton", command=lambda: self.set_preset(1050, 500)).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.propellers_var = tk.BooleanVar(value=False)
        self.propellers_check = ttk.Checkbutton(
            card, text="I confirm that all propellers are removed.",
            variable=self.propellers_var, command=confirmation_changed,
        )
        self.propellers_check.grid(row=11, column=0, columnspan=2, sticky="w", pady=(14, 8))
        Tooltip(self.propellers_check, "This confirmation is never saved and resets after disconnect, serial error, app restart or detected firmware reset.")
        self.run_button = ttk.Button(card, text="RUN SELECTED MOTOR", style="Primary.TButton", command=self._run_callback, state="disabled")
        self.run_button.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(5, 5))
        self.disable_reason_var = tk.StringVar(value="Waiting for safety telemetry.")
        ttk.Label(card, textvariable=self.disable_reason_var, style="SurfaceSecondary.TLabel", wraplength=300, justify="left").grid(row=13, column=0, columnspan=2, sticky="ew")

    def _build_live_column(self) -> None:
        card = ttk.Frame(self, style="Card.TFrame", padding=12)
        card.grid(row=0, column=2, padx=(6, 0), sticky="nsew")
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text="C · LIVE TEST", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.state_badge = StatusBadge(card, "NO DATA", "neutral")
        self.state_badge.grid(row=0, column=1, sticky="e")
        self.live_vars = {
            key: tk.StringVar(value="--")
            for key in ("motor", "commanded", "active", "remaining", "abort", "counters")
        }
        for row, (key, title) in enumerate((("motor", "Selected motor"), ("commanded", "Commanded pulse"), ("active", "Active pulse"), ("remaining", "Remaining")), start=1):
            ttk.Label(card, text=title, style="SurfaceSecondary.TLabel").grid(row=row, column=0, sticky="w", pady=4)
            ttk.Label(card, textvariable=self.live_vars[key], style="Surface.TLabel", font=("Segoe UI", 10, "bold")).grid(row=row, column=1, sticky="e", pady=4)
        self.progress = ttk.Progressbar(card, mode="determinate", maximum=2000, style="Test.Horizontal.TProgressbar")
        self.progress.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 8))
        self.ack_badge = StatusBadge(card, "NO ACK", "neutral")
        self.ack_badge.grid(row=6, column=0, sticky="w", pady=(8, 3))
        self.ack_var = tk.StringVar(value="Last command: --")
        ttk.Label(card, textvariable=self.ack_var, style="SurfaceSecondary.TLabel", wraplength=300, justify="left").grid(row=7, column=0, columnspan=2, sticky="w")
        ttk.Label(card, text="Last abort", style="SurfaceSecondary.TLabel").grid(row=8, column=0, sticky="w", pady=(12, 3))
        ttk.Label(card, textvariable=self.live_vars["abort"], style="Surface.TLabel").grid(row=8, column=1, sticky="e", pady=(12, 3))
        ttk.Label(card, textvariable=self.live_vars["counters"], style="SurfaceSecondary.TLabel", wraplength=310, justify="left").grid(row=9, column=0, columnspan=2, sticky="w")
        self.fault_frame = tk.Frame(card, background=COLORS["DANGER"], padx=12, pady=10)
        self.fault_var = tk.StringVar(value="")
        tk.Label(self.fault_frame, text="FIRMWARE FAULT", background=COLORS["DANGER"], foreground=COLORS["WHITE"], font=FONTS["NORMAL_BOLD"]).pack(anchor="w")
        tk.Label(self.fault_frame, textvariable=self.fault_var, background=COLORS["DANGER"], foreground=COLORS["WHITE"], wraplength=290, justify="left").pack(anchor="w", pady=(3, 0))
        self.fault_frame.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.fault_frame.grid_remove()
        self.request_var = tk.StringVar(value="")
        ttk.Label(card, textvariable=self.request_var, style="SurfaceSecondary.TLabel", foreground=COLORS["WARNING"], wraplength=310).grid(row=11, column=0, columnspan=2, sticky="w", pady=(10, 4))
        actions = ttk.Frame(card, style="Surface.TFrame")
        actions.grid(row=12, column=0, columnspan=2, sticky="sew", pady=(8, 0))
        actions.columnconfigure(0, weight=1)
        self.stop_button = ttk.Button(actions, text="STOP", style="Secondary.TButton", command=self._stop_callback, state="disabled")
        self.stop_button.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        self.emergency_button = ttk.Button(actions, text="EMERGENCY STOP  !", style="Danger.TButton", command=self._emergency_callback, state="disabled")
        self.emergency_button.grid(row=1, column=0, sticky="ew")
        Tooltip(self.emergency_button, "Immediately queues the raw emergency byte '!'. Firmware confirms the resulting state through telemetry.")

    def _build_guide(self) -> None:
        self.guide_open = tk.BooleanVar(value=False)
        guide = ttk.Frame(self, style="Card.TFrame", padding=(12, 7))
        guide.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(guide, text="Bench Test Guide", variable=self.guide_open, command=self._toggle_guide).pack(anchor="w")
        self.guide_body = ttk.Label(
            guide,
            text="1. Remove all propellers.   2. Verify LINK OK.   3. Throttle below 1050.   4. Enable CH5 and CH6.\n"
                 "5. Verify ESC SAFE / 0x0F.   6. Select one motor.   7. Start at 1020 us / 100 ms.\n"
                 "8. Confirm output returns to 1000 us.   9. Repeat one motor at a time.",
            style="SurfaceSecondary.TLabel", justify="left",
        )
        self.guide_body.pack(anchor="w", pady=(7, 0))
        self.guide_body.pack_forget()

    def _toggle_guide(self) -> None:
        if self.guide_open.get():
            self.guide_body.pack(anchor="w", pady=(7, 0))
        else:
            self.guide_body.pack_forget()

    def select_motor(self, motor: int) -> None:
        self._selected_motor = motor
        for number, button in self.motor_buttons.items():
            active = number == motor
            button.configure(
                background=COLORS["ACCENT_DARK"] if active else COLORS["SURFACE_ALT"],
                relief="sunken" if active else "solid",
            )

    def selected_motor(self) -> int:
        return self._selected_motor

    def set_preset(self, pulse_us: int, duration_ms: int) -> None:
        self.pulse_var.set(pulse_us)
        self.duration_var.set(duration_ms)

    def clear_confirmation(self) -> None:
        self.propellers_var.set(False)

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        self.propellers_check.configure(state="normal" if connected else "disabled")
        self.stop_button.configure(state="normal" if connected else "disabled")
        self.emergency_button.configure(state="normal" if connected else "disabled")
        if not connected:
            self.run_button.configure(state="disabled")

    def set_safety(
        self,
        values: Mapping[str, bool],
        details: Mapping[str, tuple[str, str]] | None = None,
    ) -> None:
        details = details or {}
        for key, item in self.safety_items.items():
            current, required = details.get(key, ("", ""))
            item.set(bool(values.get(key, False)), current, required)

    def set_control_state(self, connected: bool, running: bool, can_run: bool, disable_reason: str = "") -> None:
        rendered = (connected, running, can_run, disable_reason)
        if rendered == self._control_state:
            return
        self._control_state = rendered
        self._running = running
        controls_state = "disabled" if running or not connected else "normal"
        for button in self.motor_buttons.values():
            button.configure(state=controls_state)
        self.pulse_spin.configure(state=controls_state)
        self.duration_spin.configure(state=controls_state)
        self.pulse_scale.configure(state=controls_state)
        self.duration_scale.configure(state=controls_state)
        self.propellers_check.configure(state=controls_state)
        self.run_button.configure(state="normal" if can_run else "disabled")
        self.stop_button.configure(state="normal" if connected else "disabled")
        self.emergency_button.configure(state="normal" if connected else "disabled")
        self.disable_reason_var.set("All GUI gates pass. Firmware will validate again." if can_run else disable_reason or "RUN is disabled.")

    def update_record(self, record: MotorTestRecord, progress_max: int) -> None:
        state_name = MTEST_STATE_NAMES[record.state]
        abort_name = MTEST_ABORT_NAMES[record.last_abort]
        presentation = fault_presentation(record, abort_name)
        self.state_badge.set(presentation.text, presentation.tone)
        self.live_vars["motor"].set("--" if record.motor == 0 else f"Motor {record.motor}")
        self.live_vars["commanded"].set(f"{record.commanded_us} us")
        self.live_vars["active"].set(f"{record.active_us} us")
        self.live_vars["remaining"].set(f"{record.remaining_ms} ms")
        self.live_vars["abort"].set(abort_name)
        self.live_vars["counters"].set(
            f"Runs {record.run_count} · Completed {record.completed_count} · "
            f"Aborted {record.abort_count} · Rejected {record.rejected_count} · Gates 0x{record.gate_mask:02X}"
        )
        self.progress.configure(maximum=max(1, progress_max))
        self.progress["value"] = min(progress_max, record.remaining_ms)
        if record.state == 2 and 1 <= record.motor <= 4:
            self.select_motor(record.motor)
        if record.state == 3:
            self.fault_var.set(f"{abort_name}. No bypass is provided. Reset the board if the firmware fault is latched.")
            self.fault_frame.grid()
        else:
            self.fault_frame.grid_remove()
        if record.state != 2 and self.request_var.get().startswith("STOP REQUESTED"):
            self.request_var.set("STOP CONFIRMED BY TELEMETRY")

    def update_ack(self, ack: CommandAckRecord) -> None:
        accepted = ack.accepted == 1
        self.ack_badge.set("ACCEPTED" if accepted else "REJECTED", "success" if accepted else "danger")
        self.ack_var.set(f"{ack.command} · {ack.reason} · t_us={ack.timestamp_us}")

    def confirm_run(self, motor: int, pulse_us: int, duration_ms: int) -> bool:
        dialog = tk.Toplevel(self)
        dialog.title("Single Motor Bench Test")
        dialog.configure(background=COLORS["APP_BG"])
        dialog.resizable(False, False)
        dialog.transient(self.winfo_toplevel())
        result = {"confirmed": False}
        body = ttk.Frame(dialog, style="Card.TFrame", padding=24)
        body.pack(fill="both", expand=True, padx=2, pady=2)
        ttk.Label(body, text="WARNING — SINGLE MOTOR BENCH TEST", style="CardValue.TLabel", foreground=COLORS["DANGER"]).pack(anchor="w")
        _number, name, pin, _timer = MOTORS[motor - 1]
        ttk.Label(body, text=f"Motor: {name} — {pin}\nPulse: {pulse_us} us\nDuration: {duration_ms} ms", style="Surface.TLabel", font=("Segoe UI", 11), justify="left").pack(anchor="w", pady=(18, 14))
        warning = tk.Label(body, text="PROPELLERS MUST BE REMOVED", background=COLORS["DANGER"], foreground=COLORS["WHITE"], font=("Segoe UI", 12, "bold"), padx=14, pady=10)
        warning.pack(fill="x")
        buttons = ttk.Frame(body, style="Surface.TFrame")
        buttons.pack(fill="x", pady=(20, 0))
        buttons.columnconfigure((0, 1), weight=1)

        def confirm() -> None:
            result["confirmed"] = True
            dialog.destroy()

        cancel = ttk.Button(buttons, text="CANCEL", style="Secondary.TButton", command=dialog.destroy)
        cancel.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(buttons, text="CONFIRM AND RUN", style="Danger.TButton", command=confirm).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        # Enter is intentionally not bound to the destructive action.
        dialog.update_idletasks()
        parent = self.winfo_toplevel()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - dialog.winfo_reqwidth()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - dialog.winfo_reqheight()) // 2)
        dialog.geometry(f"+{x}+{y}")
        cancel.focus_set()
        dialog.grab_set()
        self.wait_window(dialog)
        return result["confirmed"]
