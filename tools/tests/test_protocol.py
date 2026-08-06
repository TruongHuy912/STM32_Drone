from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from monitor_app.protocol import (  # noqa: E402
    firmware_reset_detected,
    format_emergency_stop,
    format_run_command,
    parse_esc_line,
    parse_ibus_line,
    parse_mack_line,
    parse_machine_line,
    parse_mtest_line,
    telemetry_is_fresh,
)
from monitor_app.serial_worker import friendly_serial_error  # noqa: E402


class ProtocolTests(unittest.TestCase):
    def test_parse_valid_ibus(self) -> None:
        record = parse_ibus_line(
            "@IBUS,100,1,3,1500,1500,1000,1500,2000,2000,1500,1500,42,1,2,3"
        )
        self.assertIsNotNone(record)
        self.assertEqual(record.channels[2], 1000)
        self.assertEqual(record.valid_frames, 42)

    def test_parse_valid_esc(self) -> None:
        record = parse_esc_line("@ESC,100,1,15,50,1000,1000,1050,1000,0,0")
        self.assertIsNotNone(record)
        self.assertEqual(record.motor_us[2], 1050)

    def test_parse_valid_mtest(self) -> None:
        record = parse_mtest_line("@MTEST,100,2,3,1050,1050,400,255,0,1,0,0,0")
        self.assertIsNotNone(record)
        self.assertEqual(record.state, 2)
        self.assertEqual(record.remaining_ms, 400)

    def test_parse_valid_mack(self) -> None:
        record = parse_mack_line("@MACK,100,RUN,1,NONE,3,1050,500")
        self.assertIsNotNone(record)
        self.assertEqual(record.command, "RUN")
        self.assertEqual(record.accepted, 1)

    def test_malformed_machine_line_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_machine_line("@MTEST,1,2,missing")
        with self.assertRaises(ValueError):
            parse_mack_line("@MACK,1,RUN,2,NONE,1,1050,500")

    def test_unrelated_line_is_ignored(self) -> None:
        self.assertIsNone(parse_machine_line("H1 boot OK, micros=123"))

    def test_stale_telemetry_calculation(self) -> None:
        self.assertTrue(telemetry_is_fresh(10.0, 10.2, 0.25))
        self.assertFalse(telemetry_is_fresh(10.0, 10.3, 0.25))
        self.assertFalse(telemetry_is_fresh(None, 10.0, 0.25))

    def test_run_command_format(self) -> None:
        self.assertEqual(
            format_run_command(4, 1080, 1500),
            b"MTEST RUN 4 1080 1500\r\n",
        )

    def test_pulse_limits(self) -> None:
        with self.assertRaises(ValueError):
            format_run_command(1, 1019, 500)
        with self.assertRaises(ValueError):
            format_run_command(1, 1101, 500)

    def test_duration_limits(self) -> None:
        with self.assertRaises(ValueError):
            format_run_command(1, 1020, 99)
        with self.assertRaises(ValueError):
            format_run_command(1, 1020, 2001)

    def test_emergency_stop_is_raw_byte(self) -> None:
        self.assertEqual(format_emergency_stop(), b"!")

    def test_reset_detection_distinguishes_timer_wrap(self) -> None:
        self.assertTrue(firmware_reset_detected(2_000_000, 1000))
        self.assertFalse(firmware_reset_detected(0xFFFFFF00, 100))

    def test_access_denied_has_friendly_message(self) -> None:
        message = friendly_serial_error(PermissionError("Access is denied"))
        self.assertEqual(
            message,
            "COM port is busy. Close PuTTY or any other serial application.",
        )


if __name__ == "__main__":
    unittest.main()
