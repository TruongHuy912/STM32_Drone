"""UI constants for the STM32H743 Drone Bench Configurator."""

from __future__ import annotations

APP_NAME = "STM32H743 Drone Bench Configurator"
APP_VERSION = "H3B-2 UI 2.0"
PROTOCOL_VERSION = "H3B-2"

QUEUE_POLL_MS = 25
UI_REFRESH_MS = 50
AGE_REFRESH_MS = 100

IBUS_RECEIPT_FRESH_S = 0.25
ESC_FRESH_S = 0.35
MTEST_FRESH_S = 0.35
PROTOCOL_FRESH_S = 1.0
SENSOR_FRESH_S = 3.0

WINDOW_GEOMETRY = "1440x900"
WINDOW_MIN_WIDTH = 1180
WINDOW_MIN_HEIGHT = 720
SIDEBAR_WIDTH = 224

PAGE_INFO = {
    "Dashboard": ("◈", "System overview and bench readiness"),
    "Connection": ("⛓", "Serial port, protocol and firmware log controls"),
    "Receiver": ("◉", "FlySky iBUS channels and receiver safety inputs"),
    "ESC Outputs": ("⚡", "Read-only TIM4 PWM output monitoring"),
    "Motor Test": ("⚙", "Safety-gated single-motor bench test"),
    "Diagnostics": ("≡", "Counters, serial console and CSV capture"),
}

CHANNELS = (
    ("CH1", "Roll"),
    ("CH2", "Pitch"),
    ("CH3", "Throttle"),
    ("CH4", "Yaw"),
    ("CH5", "Safety 1"),
    ("CH6", "Safety 2"),
    ("CH7", "AUX3"),
    ("CH8", "AUX4"),
)

MOTORS = (
    (1, "Motor 1", "PD12", "TIM4 CH1"),
    (2, "Motor 2", "PD13", "TIM4 CH2"),
    (3, "Motor 3", "PD14", "TIM4 CH3"),
    (4, "Motor 4", "PD15", "TIM4 CH4"),
)

GATE_LABELS = {
    "serial_connected": ("Serial connected", "Connect the board on the Connection page."),
    "protocol_online": ("Protocol online", "Wait for machine-readable telemetry."),
    "ibus_link_valid": ("iBUS valid", "Check receiver power and iBUS wiring."),
    "ibus_fresh": ("Frame age ≤ 50 ms", "Restore a fresh receiver stream."),
    "throttle_low": ("Throttle ≤ 1050", "Move throttle fully low."),
    "ch5_enabled": ("CH5 ≥ 1900", "Enable transmitter safety switch CH5."),
    "ch6_enabled": ("CH6 ≥ 1900", "Enable transmitter safety switch CH6."),
    "esc_safe": ("ESC state SAFE", "Resolve the ESC PWM firmware state."),
    "esc_started": ("PWM mask 0x0F", "All four safe PWM channels must be started."),
    "esc_fresh": ("@ESC telemetry fresh", "Restore ESC telemetry before testing."),
    "mtest_fresh": ("@MTEST telemetry fresh", "Restore motor-test telemetry."),
    "mtest_ready": ("Firmware READY", "Wait for READY with active output at 1000 us."),
    "propellers_removed": ("Propellers removed", "Confirm every propeller is physically removed."),
}

CONSOLE_FILTERS = ("ALL", "IBUS", "ESC", "MTEST", "MACK", "SENSORS", "ERRORS")
SEVERITY_FILTERS = ("ALL", "INFO", "WARNING", "ERROR")
