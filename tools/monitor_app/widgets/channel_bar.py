"""Canvas receiver channel visualization."""

from __future__ import annotations

import tkinter as tk

from ..theme import COLORS, FONTS
from ..ui_state import channel_presentation


class ChannelBar(tk.Canvas):
    MIN_VALUE = 800
    MAX_VALUE = 2200

    def __init__(self, parent: tk.Misc, channel: str, role: str, *, throttle: bool = False) -> None:
        super().__init__(
            parent,
            height=66,
            background=COLORS["SURFACE"],
            highlightthickness=1,
            highlightbackground=COLORS["BORDER"],
        )
        self.channel = channel
        self.role = role
        self.throttle = throttle
        self.target: int | None = None
        self.displayed = 1500.0
        self.linked = False
        self.bind("<Configure>", lambda _event: self._draw())

    def set(self, value: int | None, linked: bool) -> None:
        self.target = value
        self.linked = linked
        if value is not None:
            self.displayed += (value - self.displayed) * 0.45
            if abs(value - self.displayed) < 1.0:
                self.displayed = float(value)
        self._draw()

    def _x(self, value: float) -> float:
        left, right = 116.0, max(130.0, float(self.winfo_width() - 76))
        clipped = max(self.MIN_VALUE, min(self.MAX_VALUE, value))
        return left + (clipped - self.MIN_VALUE) * (right - left) / (self.MAX_VALUE - self.MIN_VALUE)

    def _draw(self) -> None:
        width = max(340, self.winfo_width())
        self.delete("all")
        self.create_text(12, 17, anchor="w", text=self.channel, fill=COLORS["TEXT_PRIMARY"], font=FONTS["NORMAL_BOLD"])
        self.create_text(12, 43, anchor="w", text=self.role, fill=COLORS["TEXT_SECONDARY"], font=FONTS["SMALL"])
        y0, y1 = 23, 43
        self.create_rectangle(self._x(800), y0, self._x(2200), y1, fill=COLORS["SURFACE_ALT"], outline=COLORS["BORDER"])
        self.create_rectangle(self._x(1000), y0, self._x(2000), y1, fill="#1D3557", outline="")
        for marker in (1000, 1500, 2000):
            x = self._x(marker)
            self.create_line(x, y0 - 5, x, y1 + 5, fill=COLORS["TEXT_SECONDARY"])
            self.create_text(x, 55, text=str(marker), fill=COLORS["TEXT_SECONDARY"], font=("Segoe UI", 7))
        presentation = channel_presentation(self.target, self.linked, throttle=self.throttle)
        tone_color = {
            "success": COLORS["CHANNEL_FILL"],
            "warning": COLORS["WARNING"],
            "danger": COLORS["DANGER"],
            "neutral": COLORS["DISABLED"],
        }[presentation.tone]
        if self.target is not None and self.linked:
            current_x = self._x(self.displayed)
            self.create_line(current_x, y0 - 8, current_x, y1 + 8, fill=tone_color, width=4)
            self.create_oval(current_x - 5, y0 + 5, current_x + 5, y0 + 15, fill=tone_color, outline="")
        value_text = "--" if self.target is None else f"{self.target} us"
        self.create_text(width - 12, 24, anchor="e", text=value_text, fill=COLORS["TEXT_PRIMARY"], font=FONTS["NORMAL_BOLD"])
        self.create_text(width - 12, 44, anchor="e", text=presentation.text, fill=tone_color, font=FONTS["SMALL"])
