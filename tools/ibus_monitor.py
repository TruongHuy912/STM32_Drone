#!/usr/bin/env python3
"""Entry point for the STM32H743 Drone Bench Configurator."""

from __future__ import annotations

import argparse
import tkinter as tk

from monitor_app.app import BenchConfiguratorApp


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="STM32H743 Drone Bench Configurator"
    )
    parser.add_argument("--port", help="COM port, for example COM6")
    parser.add_argument("--baud", type=int, default=115200, help="serial baud rate")
    parser.add_argument(
        "--demo", action="store_true", help="run simulated UI without opening COM"
    )
    return parser


def main() -> int:
    args = build_argument_parser().parse_args()
    root = tk.Tk()
    BenchConfiguratorApp(root, args.port, args.baud, args.demo)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
