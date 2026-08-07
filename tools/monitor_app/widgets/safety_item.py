"""Accessible safety-gate row with status and remediation text."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..theme import COLORS
from .status_badge import StatusBadge


class SafetyItem(ttk.Frame):
    def __init__(self, parent: tk.Misc, title: str, help_text: str) -> None:
        super().__init__(parent, style="CardAlt.TFrame", padding=(10, 7))
        self.columnconfigure(1, weight=1)
        self.icon = tk.Label(self, text="×", background=COLORS["SURFACE_ALT"], foreground=COLORS["DANGER"], font=("Segoe UI", 12, "bold"))
        self.icon.grid(row=0, column=0, rowspan=2, padx=(0, 8))
        ttk.Label(self, text=title, style="Alt.TLabel", font=("Segoe UI", 9, "bold")).grid(row=0, column=1, sticky="w")
        self.detail_var = tk.StringVar(value=help_text)
        ttk.Label(self, textvariable=self.detail_var, style="Alt.TLabel", foreground=COLORS["TEXT_SECONDARY"], wraplength=180).grid(row=1, column=1, sticky="w")
        self.badge = StatusBadge(self, "FAIL", "danger")
        self.badge.grid(row=0, column=2, rowspan=2, padx=(8, 0))
        self.help_text = help_text
        self._rendered: tuple[bool, str, str] | None = None

    def set(self, passed: bool, current: str = "", required: str = "") -> None:
        rendered = (passed, current, required)
        if rendered == self._rendered:
            return
        self._rendered = rendered
        self.icon.configure(text="✓" if passed else "×", foreground=COLORS["SUCCESS"] if passed else COLORS["DANGER"])
        self.badge.set("PASS" if passed else "FAIL", "success" if passed else "danger")
        parts = [part for part in (current, required if passed else self.help_text) if part]
        self.detail_var.set(" · ".join(parts))
