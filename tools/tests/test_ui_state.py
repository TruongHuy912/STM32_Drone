from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from monitor_app.models import MotorTestRecord, SafetySnapshot  # noqa: E402
from monitor_app.theme import COLORS  # noqa: E402
from monitor_app.ui_state import (  # noqa: E402
    channel_presentation,
    emergency_stop_available,
    esc_pulse_presentation,
    fault_presentation,
    gate_summary,
    navigation_state,
    run_disable_reasons,
    safety_gate_values,
    stale_presentation,
    status_presentation,
)


def passing_safety() -> SafetySnapshot:
    return SafetySnapshot(
        serial_connected=True, ibus_link_valid=True, ibus_fresh=True,
        throttle_low=True, ch5_enabled=True, ch6_enabled=True,
        esc_safe=True, esc_started=True, esc_fresh=True,
        mtest_fresh=True, mtest_ready=True, propellers_removed=True,
    )


class UIStateTests(unittest.TestCase):
    def test_status_color_mapping(self) -> None:
        self.assertEqual(status_presentation("SAFE").tone, "success")
        self.assertEqual(status_presentation("FAULT").tone, "danger")
        self.assertEqual(status_presentation("RUNNING").tone, "warning")

    def test_channel_state_mapping(self) -> None:
        self.assertEqual(channel_presentation(1500, True).text, "NORMAL")
        self.assertEqual(channel_presentation(1100, True, throttle=True).tone, "warning")
        self.assertEqual(channel_presentation(None, False).text, "NO DATA")

    def test_esc_pulse_state(self) -> None:
        self.assertEqual(esc_pulse_presentation(1000, True).text, "IDLE")
        self.assertEqual(esc_pulse_presentation(1050, True).text, "TEST")
        self.assertEqual(esc_pulse_presentation(1200, True).text, "INVALID")
        self.assertEqual(esc_pulse_presentation(1000, False).text, "STALE")

    def test_stale_state(self) -> None:
        self.assertEqual(stale_presentation(0.1, 0.25).tone, "success")
        self.assertEqual(stale_presentation(0.3, 0.25).tone, "warning")
        self.assertEqual(stale_presentation(1.0, 0.25).tone, "danger")

    def test_run_disable_reason(self) -> None:
        safety = SafetySnapshot(**{**passing_safety().__dict__, "ch5_enabled": False})
        reasons = run_disable_reasons(safety, True)
        self.assertEqual(len(reasons), 1)
        self.assertIn("CH5", reasons[0])

    def test_gate_summary(self) -> None:
        values = safety_gate_values(passing_safety(), True)
        self.assertEqual(gate_summary(values).tone, "success")
        values["esc_safe"] = False
        self.assertEqual(gate_summary(values).tone, "danger")

    def test_fault_presentation(self) -> None:
        record = MotorTestRecord(1, 3, 0, 0, 1000, 0, 0, 10, 1, 0, 1, 0)
        result = fault_presentation(record, "INTERNAL_ERROR")
        self.assertEqual(result.tone, "danger")
        self.assertIn("INTERNAL_ERROR", result.text)

    def test_emergency_stop_availability(self) -> None:
        self.assertTrue(emergency_stop_available(True))
        self.assertFalse(emergency_stop_available(False))
        self.assertFalse(emergency_stop_available(True, replay_mode=True))

    def test_theme_constants(self) -> None:
        required = {"APP_BG", "SIDEBAR_BG", "SURFACE", "ACCENT", "SUCCESS", "WARNING", "DANGER"}
        self.assertTrue(required.issubset(COLORS))
        self.assertTrue(all(COLORS[name].startswith("#") for name in required))

    def test_page_navigation_state(self) -> None:
        self.assertEqual(navigation_state("Motor Test"), "Motor Test")
        self.assertEqual(navigation_state("Unknown"), "Dashboard")


if __name__ == "__main__":
    unittest.main()
