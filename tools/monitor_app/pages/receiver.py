"""Flight-configurator-style iBUS receiver page."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..constants import CHANNELS
from ..models import IBusRecord
from ..theme import COLORS
from ..widgets import ChannelBar, MetricCard, SafetyItem, StatusBadge


class ReceiverPage(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="App.TFrame", padding=18)
        self.columnconfigure(0, weight=1)
        header = ttk.Frame(self, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        self.link_badge = StatusBadge(header, "LINK LOST", "danger")
        self.link_badge.pack(side="left")
        self.metric_vars = {key: tk.StringVar(value="--") for key in ("age", "valid", "crc", "uart", "overflow")}
        for key, label in (("age", "FRAME AGE"), ("valid", "VALID"), ("crc", "CHECKSUM"), ("uart", "UART"), ("overflow", "OVERFLOW")):
            frame = ttk.Frame(header, style="Card.TFrame", padding=(10, 5))
            frame.pack(side="left", padx=(10, 0))
            ttk.Label(frame, text=label, style="SurfaceSecondary.TLabel").pack(side="left")
            ttk.Label(frame, textvariable=self.metric_vars[key], style="Surface.TLabel").pack(side="left", padx=(7, 0))

        safety = ttk.Frame(self, style="App.TFrame")
        safety.grid(row=1, column=0, sticky="ew", pady=(14, 12))
        safety.columnconfigure((0, 1, 2), weight=1)
        self.safety_items = {
            "throttle": SafetyItem(safety, "Throttle Low", "Move throttle below 1050 us."),
            "ch5": SafetyItem(safety, "CH5 Safety 1", "Enable CH5 to at least 1900 us."),
            "ch6": SafetyItem(safety, "CH6 Safety 2", "Enable CH6 to at least 1900 us."),
        }
        for column, item in enumerate(self.safety_items.values()):
            item.grid(row=0, column=column, padx=(0 if column == 0 else 6, 0 if column == 2 else 6), sticky="ew")

        self.empty = ttk.Frame(self, style="Card.TFrame", padding=20)
        ttk.Label(self.empty, text="No iBUS telemetry", style="CardValue.TLabel").pack(anchor="w")
        ttk.Label(self.empty, text="Check the COM connection, USB-TTL wiring, receiver power and firmware output. Channel values remain unavailable until a valid @IBUS packet arrives.", style="SurfaceSecondary.TLabel", wraplength=780, justify="left").pack(anchor="w", pady=(8, 0))
        self.empty.grid(row=2, column=0, sticky="ew")

        channels = ttk.Frame(self, style="App.TFrame")
        channels.grid(row=3, column=0, sticky="nsew", pady=(0, 0))
        channels.columnconfigure((0, 1), weight=1)
        self.channel_bars: list[ChannelBar] = []
        for index, (channel, role) in enumerate(CHANNELS):
            bar = ChannelBar(channels, channel, role, throttle=index == 2)
            bar.grid(row=index // 2, column=index % 2, padx=(0 if index % 2 == 0 else 6, 6 if index % 2 == 0 else 0), pady=4, sticky="ew")
            self.channel_bars.append(bar)
        self.channels_frame = channels
        self.rowconfigure(3, weight=1)

    def update_view(self, record: IBusRecord | None, receipt_fresh: bool) -> None:
        linked = bool(record and receipt_fresh and record.stream_alive == 1)
        self.link_badge.set("LINK OK" if linked else "LINK LOST", "success" if linked else "danger")
        if record is None:
            self.empty.grid()
            self.channels_frame.grid_remove()
            for item in self.safety_items.values():
                item.set(False, "No data")
            return
        self.empty.grid_remove()
        self.channels_frame.grid()
        self.metric_vars["age"].set(f"{record.age_ms} ms")
        self.metric_vars["valid"].set(f"{record.valid_frames:,}")
        self.metric_vars["crc"].set(f"{record.checksum_errors:,}")
        self.metric_vars["uart"].set(f"{record.uart_errors:,}")
        self.metric_vars["overflow"].set(f"{record.ring_overflows:,}")
        for bar, value in zip(self.channel_bars, record.channels):
            bar.set(value, linked)
        throttle, ch5, ch6 = record.channels[2], record.channels[4], record.channels[5]
        self.safety_items["throttle"].set(linked and throttle <= 1050, f"{throttle} us", "Required: ≤ 1050 us")
        self.safety_items["ch5"].set(linked and ch5 >= 1900, f"{ch5} us", "Required: ≥ 1900 us")
        self.safety_items["ch6"].set(linked and ch6 >= 1900, f"{ch6} us", "Required: ≥ 1900 us")
