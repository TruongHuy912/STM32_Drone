"""Small reusable tooltip safe against destroyed widgets."""

from __future__ import annotations

import tkinter as tk

from ..theme import COLORS, FONTS


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 450) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after: str | None = None
        self._window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")

    def _schedule(self, _event: object = None) -> None:
        self.hide()
        try:
            self._after = self.widget.after(self.delay_ms, self.show)
        except tk.TclError:
            self._after = None

    def show(self) -> None:
        self._after = None
        try:
            if not self.widget.winfo_exists():
                return
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
            window = tk.Toplevel(self.widget)
            window.wm_overrideredirect(True)
            window.wm_geometry(f"+{x}+{y}")
            tk.Label(window, text=self.text, justify="left", wraplength=320,
                     background=COLORS["SURFACE_ALT"], foreground=COLORS["TEXT_PRIMARY"],
                     relief="solid", borderwidth=1, padx=9, pady=6,
                     font=FONTS["SMALL"]).pack()
            self._window = window
        except tk.TclError:
            self._window = None
    def hide(self, _event: object = None) -> None:
        if self._after is not None:
            try:
                self.widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        if self._window is not None:
            try:
                self._window.destroy()
            except tk.TclError:
                pass
            self._window = None
