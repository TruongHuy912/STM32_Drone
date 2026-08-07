"""Read-only ESC PWM output page."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..constants import MOTORS
from ..models import ESCRecord
from ..theme import COLORS
from ..ui_state import format_age
from ..widgets import ESCOutputCard, StatusBadge, Tooltip


class ESCOutputsPage(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="App.TFrame", padding=18)
        self.columnconfigure((0, 1), weight=1)
        header = ttk.Frame(self, style="Card.TFrame", padding=14)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        header.columnconfigure(7, weight=1)
        self.state_badge = StatusBadge(header, "NO DATA", "neutral")
        self.state_badge.grid(row=0, column=0, rowspan=2, padx=(0, 16))
        self.vars = {key: tk.StringVar(value="--") for key in ("mask", "frequency", "age", "rejected", "errors")}
        for column, (key, title) in enumerate((("mask", "STARTED MASK"), ("frequency", "FREQUENCY"), ("age", "TELEMETRY AGE"), ("rejected", "REJECTED"), ("errors", "START ERRORS")), start=1):
            cell = ttk.Frame(header, style="Surface.TFrame")
            cell.grid(row=0, column=column, rowspan=2, padx=12, sticky="w")
            ttk.Label(cell, text=title, style="SurfaceSecondary.TLabel").pack(anchor="w")
            ttk.Label(cell, textvariable=self.vars[key], style="Surface.TLabel", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(3, 0))
        Tooltip(header, "started_mask 0x0F means all four safe PWM outputs started successfully.")
        self.cards: list[ESCOutputCard] = []
        for index, (_number, motor, pin, timer) in enumerate(MOTORS):
            card = ESCOutputCard(self, motor, pin, timer)
            card.grid(row=1 + index // 2, column=index % 2, padx=(0 if index % 2 == 0 else 7, 7 if index % 2 == 0 else 0), pady=7, sticky="nsew")
            self.cards.append(card)
        self.rowconfigure((1, 2), weight=1)
        notice = ttk.Label(self, text="MONITOR ONLY · This page never sends a motor command.", style="Secondary.TLabel")
        notice.grid(row=3, column=0, columnspan=2, pady=(10, 0))

    def update_view(self, record: ESCRecord | None, fresh: bool, age_s: float | None) -> None:
        safe = bool(record and fresh and record.state == 1 and record.started_mask == 0x0F)
        if record is None:
            self.state_badge.set("NO DATA", "neutral")
            for card in self.cards:
                card.set(None, False)
            return
        if not fresh:
            state, tone = "TELEMETRY STALE", "danger"
        elif safe:
            state, tone = "ESC SAFE", "success"
        else:
            state, tone = "ESC ERROR", "danger"
        self.state_badge.set(state, tone)
        self.vars["mask"].set(f"0x{record.started_mask:02X}")
        self.vars["frequency"].set(f"{record.frequency_hz} Hz")
        self.vars["age"].set(format_age(age_s))
        self.vars["rejected"].set(str(record.rejected))
        self.vars["errors"].set(str(record.start_errors))
        for card, pulse in zip(self.cards, record.motor_us):
            card.set(pulse, fresh)
