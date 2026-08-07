"""Text status badge that never relies on color alone."""

from __future__ import annotations

import tkinter as tk

from ..theme import COLORS, FONTS, TONE_COLORS


class StatusBadge(tk.Label):
    def __init__(self, parent: tk.Misc, text: str = "NO DATA", tone: str = "neutral") -> None:
        super().__init__(
            parent,
            text=text,
            font=FONTS["SMALL"][:2] + ("bold",),
            padx=10,
            pady=4,
            borderwidth=0,
        )
        self.tone = "neutral"
        self._rendered: tuple[str, str, str] | None = None
        self.set(text, tone)

    def set(
        self,
        text: str,
        tone: str | bool | None = None,
        *,
        ok: bool | None = None,
        color: str | None = None,
    ) -> None:
        if isinstance(tone, bool):
            tone = "success" if tone else "danger"
        if ok is not None:
            tone = "success" if ok else "danger"
        tone = tone or self.tone
        if color is not None:
            background, foreground = color, COLORS["WHITE"]
        else:
            background, foreground = TONE_COLORS.get(tone, TONE_COLORS["neutral"])
        rendered = (text, background, foreground)
        if rendered == self._rendered:
            return
        self._rendered = rendered
        self.tone = tone
        self.configure(text=text, background=background, foreground=foreground)
