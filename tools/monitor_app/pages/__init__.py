"""Configurator pages."""

from .connection import ConnectionPage
from .dashboard import DashboardPage
from .diagnostics import DiagnosticsPage
from .esc_outputs import ESCOutputsPage
from .motor_test import MotorTestPage
from .receiver import ReceiverPage

__all__ = (
    "ConnectionPage", "DashboardPage", "DiagnosticsPage", "ESCOutputsPage",
    "MotorTestPage", "ReceiverPage",
)
