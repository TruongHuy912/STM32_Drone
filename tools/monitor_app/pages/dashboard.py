"""Read-only system overview dashboard."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..constants import GATE_LABELS
from ..models import ESCRecord, IBusRecord, MotorTestRecord, SafetySnapshot
from ..theme import COLORS
from ..ui_state import gate_summary, safety_gate_values
from ..widgets import MetricCard, SafetyItem, StatusBadge


class DashboardPage(ttk.Frame):
    def __init__(self, parent: tk.Misc, navigate: Callable[[str], None], demo: bool = False, demo_action: Callable[[str], None] | None = None) -> None:
        super().__init__(parent, style="App.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        canvas = tk.Canvas(self, background=COLORS["APP_BG"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, command=canvas.yview)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)
        content = ttk.Frame(canvas, style="App.TFrame", padding=18)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        content.columnconfigure((0, 1, 2), weight=1)
        self.cards = {
            name: MetricCard(content, name)
            for name in ("Serial", "Board Protocol", "Receiver", "ESC PWM", "Motor Test", "Sensors")
        }
        for index, card in enumerate(self.cards.values()):
            card.grid(row=index // 3, column=index % 3, padx=(0 if index % 3 == 0 else 6, 0 if index % 3 == 2 else 6), pady=6, sticky="nsew")
        readiness = ttk.Frame(content, style="Card.TFrame", padding=15)
        readiness.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
        readiness.columnconfigure((0, 1), weight=1)
        self.ready_badge = StatusBadge(readiness, "NOT READY", "danger")
        self.ready_badge.grid(row=0, column=0, sticky="w")
        ttk.Button(readiness, text="OPEN MOTOR TEST", style="Secondary.TButton", command=lambda: navigate("Motor Test")).grid(row=0, column=1, sticky="e")
        ttk.Label(readiness, text="Ready for Bench Test", style="CardValue.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 8))
        self.check_var = tk.StringVar(value="Waiting for telemetry")
        ttk.Label(readiness, textvariable=self.check_var, style="SurfaceSecondary.TLabel", wraplength=760, justify="left").grid(row=2, column=0, columnspan=2, sticky="ew")
        if demo and demo_action is not None:
            demo_frame = ttk.Frame(content, style="Card.TFrame", padding=12)
            demo_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))
            ttk.Label(demo_frame, text="DEMO CONTROLS", style="Section.TLabel").grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 12))
            for index, scenario in enumerate(("READY", "AUX OFF", "RUNNING", "EXPIRED", "EMERGENCY", "REJECTED", "FAULT", "STALE", "DISCONNECTED", "AUTO")):
                row, column = divmod(index, 5)
                ttk.Button(demo_frame, text=scenario, style="Tool.TButton", command=lambda value=scenario: demo_action(value)).grid(row=row, column=column + 1, padx=3, pady=2, sticky="ew")
                demo_frame.columnconfigure(column + 1, weight=1)

    def update_view(
        self, *, connected: bool, port: str, baud: int, rx_rate: float,
        protocol_online: bool, packet_age: str, ibus: IBusRecord | None,
        esc: ESCRecord | None, mtest: MotorTestRecord | None,
        safety: SafetySnapshot, bmi_alive: bool, bmp_alive: bool,
    ) -> None:
        self.cards["Serial"].set(
            "CONNECTED" if connected else "DISCONNECTED",
            f"{port or '--'} @ {baud} · {rx_rate:.0f} B/s",
            "CONNECTED" if connected else "DISCONNECTED",
            "success" if connected else "danger",
        )
        self.cards["Board Protocol"].set(
            "H3B-2", f"Latest packet: {packet_age}",
            "ONLINE" if protocol_online else "OFFLINE",
            "success" if protocol_online else "danger",
        )
        channels = ibus.channels if ibus else (0,) * 8
        link = bool(ibus and ibus.stream_alive == 1 and safety.ibus_fresh)
        self.cards["Receiver"].set(
            "LINK OK" if link else "LINK LOST",
            f"CH3 {channels[2] or '--'} · CH5 {channels[4] or '--'} · CH6 {channels[5] or '--'}",
            "OK" if link else "LOST", "success" if link else "danger",
        )
        esc_safe = bool(esc and safety.esc_safe and safety.esc_started and safety.esc_fresh)
        self.cards["ESC PWM"].set(
            "SAFE" if esc_safe else "ERROR",
            f"mask {f'0x{esc.started_mask:02X}' if esc else '--'} · {f'{esc.frequency_hz} Hz' if esc else '--'}",
            "SAFE" if esc_safe else "ERROR", "success" if esc_safe else "danger",
        )
        states = ("DISABLED", "READY", "RUNNING", "FAULT")
        state = states[mtest.state] if mtest else "NO DATA"
        tone = "success" if state == "READY" else "warning" if state == "RUNNING" else "danger" if state == "FAULT" else "neutral"
        self.cards["Motor Test"].set(
            state, f"Motor {mtest.motor if mtest else '--'} · abort {mtest.last_abort if mtest else '--'}",
            state, tone,
        )
        both = bmi_alive and bmp_alive
        self.cards["Sensors"].set(
            "2 / 2" if both else f"{int(bmi_alive) + int(bmp_alive)} / 2",
            f"BMI270 {'alive' if bmi_alive else 'no recent log'} · BMP388 {'alive' if bmp_alive else 'no recent log'}",
            "ONLINE" if both else "NO DATA", "success" if both else "neutral",
        )
        values = safety_gate_values(safety, protocol_online)
        summary = gate_summary(values)
        self.ready_badge.set(summary.text, summary.tone)
        failures = [GATE_LABELS[key][0] for key, passed in values.items() if not passed]
        self.check_var.set(
            "All GUI preflight checks pass. Firmware will independently validate every safety gate."
            if not failures else "Needs attention: " + " · ".join(failures)
        )
