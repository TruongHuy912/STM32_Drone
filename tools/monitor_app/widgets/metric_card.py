"""Compact dashboard metric card."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..theme import FONTS
from .status_badge import StatusBadge


class MetricCard(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        value: str = "--",
        detail: str = "Waiting for telemetry",
    ) -> None:
        super().__init__(parent, style="Card.TFrame", padding=14)
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text=title.upper(), style="SurfaceSecondary.TLabel", font=FONTS["SMALL"]).grid(row=0, column=0, sticky="w")
        self.badge = StatusBadge(self, "NO DATA", "neutral")
        self.badge.grid(row=0, column=1, sticky="e")
        self.value_var = tk.StringVar(value=value)
        ttk.Label(self, textvariable=self.value_var, style="CardValue.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(13, 5))
        self.detail_var = tk.StringVar(value=detail)
        ttk.Label(self, textvariable=self.detail_var, style="SurfaceSecondary.TLabel", wraplength=235, justify="left").grid(row=2, column=0, columnspan=2, sticky="ew")
        self._rendered: tuple[str, str, str, str] | None = None

    def set(self, value: str, detail: str, status: str, tone: str) -> None:
        rendered = (value, detail, status, tone)
        if rendered == self._rendered:
            return
        self._rendered = rendered
        self.value_var.set(value)
        self.detail_var.set(detail)
        self.badge.set(status, tone)
