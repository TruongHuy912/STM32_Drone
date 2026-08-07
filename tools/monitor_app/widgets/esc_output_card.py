"""Read-only ESC output card."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..theme import COLORS, FONTS
from ..ui_state import esc_pulse_presentation
from .status_badge import StatusBadge


class ESCOutputCard(ttk.Frame):
    def __init__(self, parent: tk.Misc, motor: str, pin: str, timer: str) -> None:
        super().__init__(parent, style="Card.TFrame", padding=14)
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text=motor, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self, text=f"{pin} · {timer}", style="SurfaceSecondary.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.badge = StatusBadge(self, "STALE", "neutral")
        self.badge.grid(row=0, column=1, rowspan=2, sticky="e")
        self.pulse_var = tk.StringVar(value="-- us")
        ttk.Label(self, textvariable=self.pulse_var, style="CardValue.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(15, 8))
        self.canvas = tk.Canvas(self, height=34, background=COLORS["SURFACE"], highlightthickness=0)
        self.canvas.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.canvas.bind("<Configure>", lambda _event: self._draw())
        self.pulse: int | None = None
        self.fresh = False

    def set(self, pulse_us: int | None, fresh: bool) -> None:
        self.pulse = pulse_us
        self.fresh = fresh
        state = esc_pulse_presentation(pulse_us, fresh)
        self.badge.set(state.text, state.tone)
        self.pulse_var.set("-- us" if pulse_us is None else f"{pulse_us} us")
        self._draw()

    def _x(self, value: int) -> float:
        width = max(240, self.canvas.winfo_width())
        return 12 + (max(900, min(2100, value)) - 900) * (width - 24) / 1200

    def _draw(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        width = max(240, canvas.winfo_width())
        canvas.create_rectangle(12, 11, width - 12, 23, fill=COLORS["SURFACE_ALT"], outline=COLORS["BORDER"])
        canvas.create_rectangle(self._x(1020), 11, self._x(1100), 23, fill="#5B4515", outline="")
        canvas.create_line(self._x(1000), 6, self._x(1000), 28, fill=COLORS["SAFE_IDLE"], width=2)
        if self.pulse is not None:
            state = esc_pulse_presentation(self.pulse, self.fresh)
            color = {"success": COLORS["SUCCESS"], "warning": COLORS["WARNING"], "danger": COLORS["DANGER"], "neutral": COLORS["DISABLED"]}[state.tone]
            x = self._x(self.pulse)
            canvas.create_line(x, 5, x, 29, fill=color, width=4)
        canvas.create_text(12, 32, anchor="sw", text="900", fill=COLORS["TEXT_SECONDARY"], font=("Segoe UI", 7))
        canvas.create_text(width - 12, 32, anchor="se", text="2100 us", fill=COLORS["TEXT_SECONDARY"], font=("Segoe UI", 7))
