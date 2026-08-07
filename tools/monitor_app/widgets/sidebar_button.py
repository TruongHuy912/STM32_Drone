"""Sidebar navigation item with active accent rail."""

from __future__ import annotations

import tkinter as tk
from typing import Callable

from ..theme import COLORS, FONTS


class SidebarButton(tk.Frame):
    def __init__(self, parent: tk.Misc, icon: str, text: str, command: Callable[[], None]) -> None:
        super().__init__(parent, background=COLORS["SIDEBAR_BG"], height=48)
        self.pack_propagate(False)
        self.rail = tk.Frame(self, width=4, background=COLORS["SIDEBAR_BG"])
        self.rail.pack(side="left", fill="y")
        self.button = tk.Button(
            self, text=f"{icon}   {text}", command=command, anchor="w",
            background=COLORS["SIDEBAR_BG"], foreground=COLORS["TEXT_SECONDARY"],
            activebackground=COLORS["SURFACE_ALT"], activeforeground=COLORS["TEXT_PRIMARY"],
            borderwidth=0, highlightthickness=0, padx=16, font=FONTS["NORMAL_BOLD"],
        )
        self.button.pack(side="left", fill="both", expand=True)

    def set_active(self, active: bool) -> None:
        background = COLORS["SURFACE_ALT"] if active else COLORS["SIDEBAR_BG"]
        foreground = COLORS["TEXT_PRIMARY"] if active else COLORS["TEXT_SECONDARY"]
        self.configure(background=background)
        self.rail.configure(background=COLORS["ACCENT"] if active else COLORS["SIDEBAR_BG"])
        self.button.configure(background=background, foreground=foreground)
