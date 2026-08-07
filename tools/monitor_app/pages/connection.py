"""Connection and protocol page."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..theme import COLORS, FONTS
from ..widgets import MetricCard, StatusBadge, Tooltip


class ConnectionPage(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        connect: Callable[[], None],
        disconnect: Callable[[], None],
        refresh_ports: Callable[[], None],
        send_log: Callable[[str], None],
    ) -> None:
        super().__init__(parent, style="App.TFrame", padding=18)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        serial = ttk.Frame(self, style="Card.TFrame", padding=18)
        serial.grid(row=0, column=0, padx=(0, 9), sticky="nsew")
        serial.columnconfigure(1, weight=1)
        ttk.Label(serial, text="SERIAL PORT", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(serial, text="Select the USB-UART port used by USART1 debug telemetry.", style="SurfaceSecondary.TLabel", wraplength=480).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 18))
        self.port_var = tk.StringVar()
        self.baud_var = tk.StringVar(value="115200")
        ttk.Label(serial, text="COM port", style="Surface.TLabel").grid(row=2, column=0, sticky="w", pady=6)
        self.port_combo = ttk.Combobox(serial, textvariable=self.port_var, width=22)
        self.port_combo.grid(row=2, column=1, sticky="ew", padx=8, pady=6)
        ttk.Button(serial, text="Refresh", style="Secondary.TButton", command=refresh_ports).grid(row=2, column=2, pady=6)
        ttk.Label(serial, text="Baud", style="Surface.TLabel").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Combobox(serial, textvariable=self.baud_var, values=("115200",), state="readonly", width=12).grid(row=3, column=1, sticky="w", padx=8, pady=6)
        button_row = ttk.Frame(serial, style="Surface.TFrame")
        button_row.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(18, 12))
        button_row.columnconfigure((0, 1), weight=1)
        self.connect_button = ttk.Button(button_row, text="CONNECT", style="Primary.TButton", command=connect)
        self.connect_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.disconnect_button = ttk.Button(button_row, text="DISCONNECT", style="Secondary.TButton", command=disconnect, state="disabled")
        self.disconnect_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        self.status = StatusBadge(serial, "DISCONNECTED", "neutral")
        self.status.grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.status_detail_var = tk.StringVar(value="Select a COM port and connect")
        ttk.Label(serial, textvariable=self.status_detail_var, style="SurfaceSecondary.TLabel", wraplength=470).grid(row=5, column=1, columnspan=2, sticky="w", padx=8, pady=(8, 0))

        right = ttk.Frame(self, style="App.TFrame")
        right.grid(row=0, column=1, padx=(9, 0), sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        protocol = ttk.Frame(right, style="Card.TFrame", padding=18)
        protocol.grid(row=0, column=0, sticky="nsew")
        protocol.columnconfigure(1, weight=1)
        ttk.Label(protocol, text="BOARD PROTOCOL", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.protocol_badge = StatusBadge(protocol, "OFFLINE", "danger")
        self.protocol_badge.grid(row=0, column=1, sticky="e")
        self.board_var = tk.StringVar(value="STM32H743 · H3B-2")
        ttk.Label(protocol, textvariable=self.board_var, style="CardValue.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(15, 8))
        self.metric_vars = {
            key: tk.StringVar(value="--")
            for key in ("last", "rx_bytes", "rx_lines", "rx_rate", "worker", "exception")
        }
        labels = (
            ("Last telemetry", "last"), ("RX bytes", "rx_bytes"),
            ("RX lines", "rx_lines"), ("RX rate", "rx_rate"),
            ("Worker", "worker"), ("Last exception", "exception"),
        )
        for row, (label, key) in enumerate(labels, start=2):
            ttk.Label(protocol, text=label, style="SurfaceSecondary.TLabel").grid(row=row, column=0, sticky="w", pady=4)
            ttk.Label(protocol, textvariable=self.metric_vars[key], style="Surface.TLabel").grid(row=row, column=1, sticky="e", pady=4)

        logs = ttk.Frame(right, style="Card.TFrame", padding=18)
        logs.grid(row=1, column=0, sticky="ew", pady=(18, 0))
        logs.columnconfigure(0, weight=1)
        ttk.Label(logs, text="FIRMWARE LOG MODE", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.log_mode = StatusBadge(logs, "UNKNOWN", "neutral")
        self.log_mode.grid(row=0, column=1, sticky="e")
        ttk.Label(logs, text="QUIET suppresses periodic human logs but retains machine telemetry and command responses.", style="SurfaceSecondary.TLabel", wraplength=490).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 12))
        buttons = ttk.Frame(logs, style="Surface.TFrame")
        buttons.grid(row=2, column=0, columnspan=2, sticky="ew")
        for column, mode in enumerate(("QUIET", "FULL", "STATUS")):
            button = ttk.Button(buttons, text=f"LOG {mode}", style="Secondary.TButton", command=lambda value=mode: send_log(value))
            button.grid(row=0, column=column, padx=(0 if column == 0 else 5, 0), sticky="ew")
            buttons.columnconfigure(column, weight=1)
            Tooltip(button, f"Send LOG {mode} to firmware. Motor safety behavior is unchanged.")

    def set_connected(self, connected: bool) -> None:
        self.connect_button.configure(state="disabled" if connected else "normal")
        self.disconnect_button.configure(state="normal" if connected else "disabled")
        if connected:
            self.status.set("CONNECTED", "success")
        else:
            self.status.set("DISCONNECTED", "neutral")

    def set_status(self, text: str, tone: str, detail: str) -> None:
        self.status.set(text, tone)
        self.status_detail_var.set(detail)

    def update_protocol(
        self, *, online: bool, last_telemetry: str, rx_bytes: int,
        rx_lines: int, rx_rate: float, worker_state: str, exception: str,
    ) -> None:
        self.protocol_badge.set("ONLINE" if online else "OFFLINE", "success" if online else "danger")
        values = {
            "last": last_telemetry,
            "rx_bytes": f"{rx_bytes:,}",
            "rx_lines": f"{rx_lines:,}",
            "rx_rate": f"{rx_rate:,.0f} B/s",
            "worker": worker_state,
            "exception": exception or "None",
        }
        for key, value in values.items():
            self.metric_vars[key].set(value)

    def set_log_mode(self, mode: str) -> None:
        self.log_mode.set(mode, "info" if mode != "UNKNOWN" else "neutral")
