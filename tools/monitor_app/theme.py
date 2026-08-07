"""Centralized dark ttk theme and palette."""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from tkinter import ttk

COLORS = {
    "APP_BG": "#0B1220",
    "SIDEBAR_BG": "#111827",
    "SURFACE": "#172033",
    "SURFACE_ALT": "#1E293B",
    "BORDER": "#334155",
    "TEXT_PRIMARY": "#F8FAFC",
    "TEXT_SECONDARY": "#94A3B8",
    "ACCENT": "#38BDF8",
    "ACCENT_DARK": "#0284C7",
    "SUCCESS": "#22C55E",
    "WARNING": "#F59E0B",
    "DANGER": "#EF4444",
    "DISABLED": "#475569",
    "CHANNEL_FILL": "#3B82F6",
    "SAFE_IDLE": "#22C55E",
    "TEST_ACTIVE": "#F59E0B",
    "WHITE": "#FFFFFF",
    "BLACK": "#020617",
}

FONTS = {
    "APP_TITLE": ("Segoe UI", 19, "bold"),
    "PAGE_TITLE": ("Segoe UI", 17, "bold"),
    "CARD_VALUE": ("Segoe UI", 20, "bold"),
    "SECTION": ("Segoe UI", 11, "bold"),
    "NORMAL": ("Segoe UI", 10),
    "NORMAL_BOLD": ("Segoe UI", 10, "bold"),
    "SMALL": ("Segoe UI", 9),
    "CONSOLE": ("Consolas", 9),
}

TONE_COLORS = {
    "success": (COLORS["SUCCESS"], COLORS["BLACK"]),
    "warning": (COLORS["WARNING"], COLORS["BLACK"]),
    "danger": (COLORS["DANGER"], COLORS["WHITE"]),
    "info": (COLORS["ACCENT"], COLORS["BLACK"]),
    "neutral": (COLORS["DISABLED"], COLORS["TEXT_PRIMARY"]),
}


def enable_windows_dpi_awareness() -> None:
    """Disable Windows DPI virtualization before Tk creates its first window."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def apply_theme(root: tk.Tk) -> ttk.Style:
    """Apply the dependency-free dark theme to the application."""
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(background=COLORS["APP_BG"])

    style.configure(".", background=COLORS["APP_BG"], foreground=COLORS["TEXT_PRIMARY"],
                    fieldbackground=COLORS["SURFACE_ALT"], bordercolor=COLORS["BORDER"],
                    lightcolor=COLORS["BORDER"], darkcolor=COLORS["BORDER"],
                    font=FONTS["NORMAL"])
    style.configure("App.TFrame", background=COLORS["APP_BG"])
    style.configure("Surface.TFrame", background=COLORS["SURFACE"])
    style.configure("Alt.TFrame", background=COLORS["SURFACE_ALT"])
    style.configure("Sidebar.TFrame", background=COLORS["SIDEBAR_BG"])
    style.configure("Card.TFrame", background=COLORS["SURFACE"], relief="solid", borderwidth=1)
    style.configure("CardAlt.TFrame", background=COLORS["SURFACE_ALT"], relief="solid", borderwidth=1)
    style.configure("TLabel", background=COLORS["APP_BG"], foreground=COLORS["TEXT_PRIMARY"])
    style.configure("Surface.TLabel", background=COLORS["SURFACE"], foreground=COLORS["TEXT_PRIMARY"])
    style.configure("Alt.TLabel", background=COLORS["SURFACE_ALT"], foreground=COLORS["TEXT_PRIMARY"])
    style.configure("Secondary.TLabel", background=COLORS["APP_BG"], foreground=COLORS["TEXT_SECONDARY"])
    style.configure("SurfaceSecondary.TLabel", background=COLORS["SURFACE"], foreground=COLORS["TEXT_SECONDARY"])
    style.configure("PageTitle.TLabel", background=COLORS["APP_BG"], foreground=COLORS["TEXT_PRIMARY"], font=FONTS["PAGE_TITLE"])
    style.configure("Section.TLabel", background=COLORS["SURFACE"], foreground=COLORS["TEXT_PRIMARY"], font=FONTS["SECTION"])
    style.configure("CardValue.TLabel", background=COLORS["SURFACE"], foreground=COLORS["TEXT_PRIMARY"], font=FONTS["CARD_VALUE"])
    style.configure("Primary.TButton", background=COLORS["ACCENT_DARK"], foreground=COLORS["WHITE"], padding=(14, 9), font=FONTS["NORMAL_BOLD"], borderwidth=0)
    style.map("Primary.TButton", background=[("active", COLORS["ACCENT"]), ("disabled", COLORS["DISABLED"])], foreground=[("disabled", COLORS["TEXT_SECONDARY"])])
    style.configure("Secondary.TButton", background=COLORS["SURFACE_ALT"], foreground=COLORS["TEXT_PRIMARY"], padding=(12, 8), font=FONTS["NORMAL_BOLD"])
    style.map("Secondary.TButton", background=[("active", COLORS["BORDER"]), ("disabled", COLORS["DISABLED"])])
    style.configure("Danger.TButton", background=COLORS["DANGER"], foreground=COLORS["WHITE"], padding=(15, 10), font=FONTS["NORMAL_BOLD"], borderwidth=0)
    style.map("Danger.TButton", background=[("active", "#DC2626"), ("disabled", COLORS["DISABLED"])])
    style.configure("Tool.TButton", background=COLORS["SURFACE_ALT"], foreground=COLORS["TEXT_PRIMARY"], padding=(9, 5))
    style.configure("TCheckbutton", background=COLORS["SURFACE"], foreground=COLORS["TEXT_PRIMARY"])
    style.map("TCheckbutton", background=[("active", COLORS["SURFACE"])])
    style.configure("TCombobox", padding=6, arrowsize=14)
    style.map("TCombobox", fieldbackground=[("readonly", COLORS["SURFACE_ALT"])], selectbackground=[("readonly", COLORS["SURFACE_ALT"])], selectforeground=[("readonly", COLORS["TEXT_PRIMARY"])])
    style.configure("TSpinbox", padding=5, fieldbackground=COLORS["SURFACE_ALT"])
    style.configure("Horizontal.TProgressbar", troughcolor=COLORS["SURFACE_ALT"], background=COLORS["ACCENT"], bordercolor=COLORS["BORDER"])
    style.configure("Test.Horizontal.TProgressbar", troughcolor=COLORS["SURFACE_ALT"], background=COLORS["TEST_ACTIVE"], bordercolor=COLORS["BORDER"])
    style.configure("Vertical.TScrollbar", background=COLORS["SURFACE_ALT"], troughcolor=COLORS["APP_BG"], arrowcolor=COLORS["TEXT_SECONDARY"])
    style.configure("Horizontal.TScale", background=COLORS["SURFACE"], troughcolor=COLORS["SURFACE_ALT"])
    root.option_add("*TCombobox*Listbox.background", COLORS["SURFACE_ALT"])
    root.option_add("*TCombobox*Listbox.foreground", COLORS["TEXT_PRIMARY"])
    root.option_add("*TCombobox*Listbox.selectBackground", COLORS["ACCENT_DARK"])
    root.option_add("*TCombobox*Listbox.selectForeground", COLORS["WHITE"])
    return style
