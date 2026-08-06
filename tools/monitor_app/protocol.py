"""Strict machine telemetry parsing and safe command formatting."""

from __future__ import annotations

import re
from typing import Optional

from .models import CommandAckRecord, ESCRecord, IBusRecord, MotorTestRecord, ParsedLine

IBUS_PREFIX = "@IBUS,"
ESC_PREFIX = "@ESC,"
MTEST_PREFIX = "@MTEST,"
MACK_PREFIX = "@MACK,"

IBUS_FIELD_COUNT = 16
ESC_FIELD_COUNT = 11
MTEST_FIELD_COUNT = 13
MACK_FIELD_COUNT = 8

MTEST_STATE_NAMES = ("DISABLED", "READY", "RUNNING", "FAULT")
MTEST_ABORT_NAMES = (
    "NONE",
    "USER_STOP",
    "EMERGENCY_STOP",
    "TIME_EXPIRED",
    "THROTTLE_NOT_LOW",
    "CH5_NOT_ENABLED",
    "CH6_NOT_ENABLED",
    "IBUS_TIMEOUT",
    "IBUS_INVALID",
    "ESC_NOT_SAFE",
    "INVALID_COMMAND",
    "INTERNAL_ERROR",
)

MOTOR_MIN = 1
MOTOR_MAX = 4
PULSE_MIN_US = 1020
PULSE_MAX_US = 1100
DURATION_MIN_MS = 100
DURATION_MAX_MS = 2000
SAFE_PULSE_US = 1000

_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _decimal_values(fields: list[str]) -> list[int]:
    if any(
        not field or not field.isascii() or not field.isdecimal()
        for field in fields
    ):
        raise ValueError("non-decimal or whitespace-containing field")
    return [int(field, 10) for field in fields]


def parse_ibus_line(line: str) -> Optional[IBusRecord]:
    line = line.rstrip("\r\n")
    if not line.startswith(IBUS_PREFIX):
        return None
    fields = line.split(",")
    if len(fields) != IBUS_FIELD_COUNT or fields[0] != "@IBUS":
        raise ValueError("wrong @IBUS field count")
    values = _decimal_values(fields[1:])
    timestamp_us, stream_alive, age_ms = values[0:3]
    channels = tuple(values[3:11])
    valid_frames, checksum_errors, uart_errors, ring_overflows = values[11:15]
    if timestamp_us > 0xFFFFFFFF or age_ms > 0xFFFFFFFF:
        raise ValueError("@IBUS timestamp or age outside uint32")
    if stream_alive not in (0, 1):
        raise ValueError("@IBUS stream must be 0 or 1")
    if any(value > 0xFFFF for value in channels):
        raise ValueError("@IBUS channel outside uint16")
    if any(value > 0xFFFFFFFF for value in values[11:15]):
        raise ValueError("@IBUS counter outside uint32")
    return IBusRecord(
        timestamp_us,
        stream_alive,
        age_ms,
        channels,  # type: ignore[arg-type]
        valid_frames,
        checksum_errors,
        uart_errors,
        ring_overflows,
    )


def parse_esc_line(line: str) -> Optional[ESCRecord]:
    line = line.rstrip("\r\n")
    if not line.startswith(ESC_PREFIX):
        return None
    fields = line.split(",")
    if len(fields) != ESC_FIELD_COUNT or fields[0] != "@ESC":
        raise ValueError("wrong @ESC field count")
    values = _decimal_values(fields[1:])
    timestamp_us, state, started_mask, frequency_hz = values[0:4]
    motor_us = tuple(values[4:8])
    rejected, start_errors = values[8:10]
    if timestamp_us > 0xFFFFFFFF:
        raise ValueError("@ESC timestamp outside uint32")
    if state > 0xFF or started_mask > 0xFF:
        raise ValueError("@ESC state or mask outside uint8")
    if frequency_hz == 0 or frequency_hz > 0xFFFFFFFF:
        raise ValueError("@ESC frequency outside uint32")
    if any(value > 0xFFFF for value in motor_us):
        raise ValueError("@ESC pulse outside uint16")
    if rejected > 0xFFFFFFFF or start_errors > 0xFFFFFFFF:
        raise ValueError("@ESC counter outside uint32")
    return ESCRecord(
        timestamp_us,
        state,
        started_mask,
        frequency_hz,
        motor_us,  # type: ignore[arg-type]
        rejected,
        start_errors,
    )


def parse_mtest_line(line: str) -> Optional[MotorTestRecord]:
    line = line.rstrip("\r\n")
    if not line.startswith(MTEST_PREFIX):
        return None
    fields = line.split(",")
    if len(fields) != MTEST_FIELD_COUNT or fields[0] != "@MTEST":
        raise ValueError("wrong @MTEST field count")
    values = _decimal_values(fields[1:])
    if values[0] > 0xFFFFFFFF:
        raise ValueError("@MTEST timestamp outside uint32")
    if values[1] >= len(MTEST_STATE_NAMES) or values[2] > MOTOR_MAX:
        raise ValueError("@MTEST state or motor invalid")
    if any(value > 0xFFFF for value in values[3:6]):
        raise ValueError("@MTEST pulse or remaining outside uint16")
    if values[6] > 0xFFFFFFFF or values[7] >= len(MTEST_ABORT_NAMES):
        raise ValueError("@MTEST gate or abort invalid")
    if any(value > 0xFFFFFFFF for value in values[8:12]):
        raise ValueError("@MTEST counter outside uint32")
    return MotorTestRecord(*values)


def parse_mack_line(line: str) -> Optional[CommandAckRecord]:
    line = line.rstrip("\r\n")
    if not line.startswith(MACK_PREFIX):
        return None
    fields = line.split(",")
    if len(fields) != MACK_FIELD_COUNT or fields[0] != "@MACK":
        raise ValueError("wrong @MACK field count")
    timestamp, accepted, motor, pulse, duration = _decimal_values(
        [fields[1], fields[3], fields[5], fields[6], fields[7]]
    )
    command, reason = fields[2], fields[4]
    if not _TOKEN_RE.fullmatch(command) or not _TOKEN_RE.fullmatch(reason):
        raise ValueError("@MACK command or reason token invalid")
    if timestamp > 0xFFFFFFFF or accepted not in (0, 1):
        raise ValueError("@MACK timestamp or accepted invalid")
    if motor > MOTOR_MAX or pulse > 0xFFFF or duration > 0xFFFF:
        raise ValueError("@MACK command parameters invalid")
    return CommandAckRecord(timestamp, command, accepted, reason, motor, pulse, duration)


def parse_machine_line(line: str) -> Optional[ParsedLine]:
    for kind, parser in (
        ("IBUS", parse_ibus_line),
        ("ESC", parse_esc_line),
        ("MTEST", parse_mtest_line),
        ("MACK", parse_mack_line),
    ):
        record = parser(line)
        if record is not None:
            return ParsedLine(kind, record, line.rstrip("\r\n"))
    return None


def validate_run_values(motor: int, pulse_us: int, duration_ms: int) -> None:
    if type(motor) is not int or not MOTOR_MIN <= motor <= MOTOR_MAX:
        raise ValueError("motor must be from 1 to 4")
    if type(pulse_us) is not int or not PULSE_MIN_US <= pulse_us <= PULSE_MAX_US:
        raise ValueError("pulse must be from 1020 to 1100 us")
    if type(duration_ms) is not int or not DURATION_MIN_MS <= duration_ms <= DURATION_MAX_MS:
        raise ValueError("duration must be from 100 to 2000 ms")


def format_run_command(motor: int, pulse_us: int, duration_ms: int) -> bytes:
    validate_run_values(motor, pulse_us, duration_ms)
    return f"MTEST RUN {motor} {pulse_us} {duration_ms}\r\n".encode("ascii")


def format_stop_command() -> bytes:
    return b"MTEST STOP\r\n"


def format_emergency_stop() -> bytes:
    return b"!"


def format_log_command(mode: str) -> bytes:
    normalized = mode.strip().upper()
    if normalized not in {"QUIET", "FULL", "STATUS"}:
        raise ValueError("unknown log mode")
    return f"LOG {normalized}\r\n".encode("ascii")


def telemetry_is_fresh(last_received: Optional[float], now: float, limit_s: float) -> bool:
    return last_received is not None and 0.0 <= now - last_received <= limit_s


def firmware_reset_detected(previous_us: Optional[int], current_us: int) -> bool:
    if previous_us is None or current_us >= previous_us:
        return False
    timer_wrapped = previous_us >= 0xF0000000 and current_us <= 0x0FFFFFFF
    return not timer_wrapped


def classify_console_line(line: str) -> str:
    if line.startswith(IBUS_PREFIX):
        return "IBUS"
    if line.startswith(ESC_PREFIX):
        return "ESC"
    if line.startswith(MTEST_PREFIX):
        return "MTEST"
    if line.startswith(MACK_PREFIX):
        return "MACK"
    upper = line.upper()
    if upper.startswith(("BMI270", "BMP388")):
        return "SENSORS"
    if any(word in upper for word in ("ERROR", "FAIL", "FAULT", "LOST", "REJECT")):
        return "ERRORS"
    return "OTHER"


def parse_ibus_header_errors(line: str) -> Optional[int]:
    if not line.startswith("IBUS DIAG:"):
        return None
    match = re.search(r"\bheader_err=(\d+)", line)
    return int(match.group(1)) if match else None
