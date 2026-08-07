"""Bounded diagnostics console and counter dashboard."""

from __future__ import annotations

import collections
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable, Mapping

from ..constants import CONSOLE_FILTERS, SEVERITY_FILTERS
from ..protocol import classify_console_line
from ..theme import COLORS, FONTS
from ..widgets import Tooltip


def console_severity(line: str) -> str:
    upper = line.upper()
    if any(word in upper for word in ("ERROR", "FAULT", "FAIL", "REJECTED", "LOST")):
        return "ERROR"
    if any(word in upper for word in ("WARNING", "WARN", "STALE", "ABORT")):
        return "WARNING"
    return "INFO"


class DiagnosticsPage(ttk.Frame):
    MAX_STORED_LINES = 2000
    MAX_WIDGET_LINES = 1000

    def __init__(
        self,
        parent: tk.Misc,
        start_csv: Callable[[], None],
        stop_csv: Callable[[], None],
    ) -> None:
        super().__init__(parent, style="App.TFrame", padding=14)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.lines: collections.deque[tuple[str, str, str]] = collections.deque(maxlen=self.MAX_STORED_LINES)
        self.pending: collections.deque[tuple[str, str, str]] = collections.deque(
            maxlen=self.MAX_STORED_LINES
        )
        self.paused = False
        self._build_counters()
        self._build_console()
        self._build_csv(start_csv, stop_csv)

    def _build_counters(self) -> None:
        frame = ttk.Frame(self, style="App.TFrame")
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        keys = (
            ("rx_bytes", "RX BYTES"), ("rx_lines", "RX LINES"), ("rx_rate", "RX B/S"),
            ("valid", "VALID FRAMES"), ("checksum", "CHECKSUM"), ("header", "HEADER"),
            ("uart", "UART"), ("overflow", "OVERFLOW"), ("m_ibus", "BAD IBUS"),
            ("m_esc", "BAD ESC"), ("m_mtest", "BAD MTEST"), ("m_mack", "BAD MACK"),
            ("tx", "TX COMMANDS"),
        )
        self.counter_vars = {key: tk.StringVar(value="0") for key, _label in keys}
        for index, (key, label) in enumerate(keys):
            row, column = divmod(index, 7)
            card = ttk.Frame(frame, style="Card.TFrame", padding=(9, 6))
            card.grid(row=row, column=column, padx=(0 if column == 0 else 2, 2), pady=2, sticky="ew")
            frame.columnconfigure(column, weight=1)
            ttk.Label(card, text=label, style="SurfaceSecondary.TLabel", font=("Segoe UI", 7)).pack(anchor="w")
            ttk.Label(card, textvariable=self.counter_vars[key], style="Surface.TLabel", font=("Segoe UI", 10, "bold")).pack(anchor="w")
            if key.startswith("m_"):
                Tooltip(card, "Malformed machine-readable lines are counted and discarded without stopping the parser.")

    def _build_console(self) -> None:
        card = ttk.Frame(self, style="Card.TFrame", padding=10)
        card.grid(row=1, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(card, style="Surface.TFrame")
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        toolbar.columnconfigure(0, weight=1)
        filter_row = ttk.Frame(toolbar, style="Surface.TFrame")
        filter_row.grid(row=0, column=0, sticky="ew")
        action_row = ttk.Frame(toolbar, style="Surface.TFrame")
        action_row.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.filter_var = tk.StringVar(value="ALL")
        self.severity_var = tk.StringVar(value="ALL")
        self.search_var = tk.StringVar(value="")
        ttk.Label(filter_row, text="Packet", style="SurfaceSecondary.TLabel").pack(side="left")
        packet = ttk.Combobox(filter_row, textvariable=self.filter_var, values=CONSOLE_FILTERS, state="readonly", width=10)
        packet.pack(side="left", padx=(5, 10))
        packet.bind("<<ComboboxSelected>>", lambda _event: self.redraw())
        ttk.Label(filter_row, text="Severity", style="SurfaceSecondary.TLabel").pack(side="left")
        severity = ttk.Combobox(filter_row, textvariable=self.severity_var, values=SEVERITY_FILTERS, state="readonly", width=9)
        severity.pack(side="left", padx=(5, 10))
        severity.bind("<<ComboboxSelected>>", lambda _event: self.redraw())
        ttk.Label(filter_row, text="Search", style="SurfaceSecondary.TLabel").pack(side="left")
        search = ttk.Entry(filter_row, textvariable=self.search_var, width=20)
        search.pack(side="left", padx=(5, 10))
        search.bind("<KeyRelease>", lambda _event: self.redraw())
        self.pause_button = ttk.Button(action_row, text="Pause", style="Tool.TButton", command=self.toggle_pause)
        self.pause_button.pack(side="left", padx=2)
        ttk.Button(action_row, text="Clear", style="Tool.TButton", command=self.clear).pack(side="left", padx=2)
        ttk.Button(action_row, text="Copy", style="Tool.TButton", command=self.copy_visible).pack(side="left", padx=2)
        ttk.Button(action_row, text="Save", style="Tool.TButton", command=self.save_visible).pack(side="left", padx=2)
        self.autoscroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(action_row, text="Auto-scroll", variable=self.autoscroll_var).pack(side="left", padx=10)
        self.text = tk.Text(
            card, wrap="none", font=FONTS["CONSOLE"], background=COLORS["BLACK"],
            foreground=COLORS["TEXT_PRIMARY"], insertbackground=COLORS["TEXT_PRIMARY"],
            selectbackground=COLORS["ACCENT_DARK"], borderwidth=0, padx=8, pady=8,
        )
        self.text.grid(row=1, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(card, command=self.text.yview)
        yscroll.grid(row=1, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(card, orient="horizontal", command=self.text.xview)
        xscroll.grid(row=2, column=0, sticky="ew")
        self.text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set, state="disabled")
        tags = {
            "IBUS": COLORS["CHANNEL_FILL"], "ESC": COLORS["ACCENT"],
            "MTEST": COLORS["WARNING"], "MACK_OK": COLORS["SUCCESS"],
            "ERROR": COLORS["DANGER"], "SENSORS": COLORS["TEXT_SECONDARY"],
            "DEFAULT": COLORS["TEXT_PRIMARY"],
        }
        for tag, color in tags.items():
            self.text.tag_configure(tag, foreground=color)

    def _build_csv(self, start_csv: Callable[[], None], stop_csv: Callable[[], None]) -> None:
        frame = ttk.Frame(self, style="Card.TFrame", padding=(10, 7))
        frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(frame, text="CSV", style="Section.TLabel").pack(side="left", padx=(0, 10))
        self.csv_types = {kind: tk.BooleanVar(value=True) for kind in ("IBUS", "ESC", "MTEST", "MACK")}
        for kind, variable in self.csv_types.items():
            ttk.Checkbutton(frame, text=kind, variable=variable).pack(side="left", padx=3)
        self.csv_start = ttk.Button(frame, text="Start CSV", style="Secondary.TButton", command=start_csv)
        self.csv_start.pack(side="left", padx=(12, 4))
        self.csv_stop = ttk.Button(frame, text="Stop CSV", style="Secondary.TButton", command=stop_csv, state="disabled")
        self.csv_stop.pack(side="left", padx=4)
        self.csv_status = tk.StringVar(value="CSV logging stopped")
        ttk.Label(frame, textvariable=self.csv_status, style="SurfaceSecondary.TLabel").pack(side="left", padx=10)

    def append_line(self, line: str) -> None:
        category = classify_console_line(line)
        severity = console_severity(line)
        item = (category, severity, line)
        self.lines.append(item)
        self.pending.append(item)

    def flush_lines(self) -> None:
        if self.paused:
            self.pending.clear()
            return
        if not self.pending:
            return
        batch: list[tuple[str, str, str]] = []
        while self.pending:
            batch.append(self.pending.popleft())
        visible = [item for item in batch if self._matches(item)]
        if not visible:
            return
        self.text.configure(state="normal")
        for category, severity, line in visible:
            self.text.insert("end", line + "\n", self._tag(category, severity, line))
        self._trim_widget()
        if self.autoscroll_var.get():
            self.text.see("end")
        self.text.configure(state="disabled")

    def _matches(self, item: tuple[str, str, str]) -> bool:
        category, severity, line = item
        packet_ok = self.filter_var.get() == "ALL" or self.filter_var.get() == category
        severity_ok = self.severity_var.get() == "ALL" or self.severity_var.get() == severity
        search = self.search_var.get().strip().casefold()
        return packet_ok and severity_ok and (not search or search in line.casefold())

    @staticmethod
    def _tag(category: str, severity: str, line: str) -> str:
        if severity == "ERROR":
            return "ERROR"
        if category == "MACK":
            return "MACK_OK" if ",1," in line else "ERROR"
        return category if category in {"IBUS", "ESC", "MTEST", "SENSORS"} else "DEFAULT"

    def _trim_widget(self) -> None:
        line_count = int(self.text.index("end-1c").split(".")[0])
        if line_count > self.MAX_WIDGET_LINES:
            self.text.delete("1.0", f"{line_count - self.MAX_WIDGET_LINES + 1}.0")

    def redraw(self) -> None:
        self.pending.clear()
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for item in self.lines:
            if self._matches(item):
                category, severity, line = item
                self.text.insert("end", line + "\n", self._tag(category, severity, line))
        self._trim_widget()
        if self.autoscroll_var.get():
            self.text.see("end")
        self.text.configure(state="disabled")

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.pause_button.configure(text="Resume" if self.paused else "Pause")
        if not self.paused:
            self.redraw()

    def clear(self) -> None:
        self.lines.clear()
        self.pending.clear()
        self.redraw()

    def copy_visible(self) -> None:
        text = self.text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)

    def save_visible(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="Save visible console", defaultextension=".log",
            filetypes=(("Log file", "*.log"), ("Text file", "*.txt"), ("All files", "*.*")),
        )
        if path:
            Path(path).write_text(self.text.get("1.0", "end-1c"), encoding="utf-8")

    def set_counters(self, values: Mapping[str, int | float | str]) -> None:
        for key, variable in self.counter_vars.items():
            value = values.get(key, 0)
            variable.set(f"{value:,}" if isinstance(value, int) else str(value))
