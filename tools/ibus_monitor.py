#!/usr/bin/env python3
"""Entry point for the STM32H743 Drone Bench Configurator."""

from __future__ import annotations

import argparse
import tkinter as tk

from monitor_app.app import BenchConfiguratorApp
from monitor_app.theme import enable_windows_dpi_awareness


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="STM32H743 Drone Bench Configurator"
    )
    parser.add_argument("--port", help="COM port, for example COM6")
    parser.add_argument("--baud", type=int, default=115200, help="serial baud rate")
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--demo", action="store_true", help="run simulated UI without opening COM"
    )
    source.add_argument(
        "--replay", metavar="LOG_FILE", help="replay a raw or configurator CSV log"
    )
    return parser


def main() -> int:
    args = build_argument_parser().parse_args()
    enable_windows_dpi_awareness()
    root = tk.Tk()
    BenchConfiguratorApp(root, args.port, args.baud, args.demo, args.replay)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
