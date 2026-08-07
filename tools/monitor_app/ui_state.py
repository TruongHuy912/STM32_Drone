"""Pure presentation-state mapping used by pages and unit tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from .constants import GATE_LABELS, PAGE_INFO
from .models import MotorTestRecord, SafetySnapshot


@dataclass(frozen=True)
class Presentation:
    text: str
    tone: str


def status_presentation(value: str) -> Presentation:
    normalized = value.upper()
    if normalized in {"PASS", "SAFE", "READY", "CONNECTED", "ONLINE", "OK", "IDLE"}:
        return Presentation(normalized, "success")
    if normalized in {"RUNNING", "TEST", "STALE", "CONNECTING", "DISCONNECTING"}:
        return Presentation(normalized, "warning")
    if normalized in {"FAIL", "FAULT", "ERROR", "LOST", "INVALID", "REJECTED", "OFFLINE"}:
        return Presentation(normalized, "danger")
    return Presentation(normalized, "neutral")


def channel_presentation(value: Optional[int], linked: bool, *, throttle: bool = False) -> Presentation:
    if value is None or not linked:
        return Presentation("NO DATA", "neutral")
    if not 800 <= value <= 2200:
        return Presentation("OUT OF RANGE", "danger")
    if throttle and value > 1050:
        return Presentation("THROTTLE HIGH", "warning")
    if 1000 <= value <= 2000:
        return Presentation("NORMAL", "success")
    return Presentation("EXTENDED", "warning")


def esc_pulse_presentation(pulse_us: Optional[int], fresh: bool) -> Presentation:
    if pulse_us is None or not fresh:
        return Presentation("STALE", "neutral")
    if pulse_us == 1000:
        return Presentation("IDLE", "success")
    if 1020 <= pulse_us <= 1100:
        return Presentation("TEST", "warning")
    return Presentation("INVALID", "danger")


def stale_presentation(age_s: Optional[float], limit_s: float) -> Presentation:
    if age_s is None:
        return Presentation("NO DATA", "neutral")
    if age_s <= limit_s:
        return Presentation("FRESH", "success")
    if age_s <= limit_s * 2.0:
        return Presentation("STALE", "warning")
    return Presentation("STALE", "danger")


def safety_gate_values(safety: SafetySnapshot, protocol_online: bool) -> dict[str, bool]:
    return {
        "serial_connected": safety.serial_connected,
        "protocol_online": protocol_online,
        "ibus_link_valid": safety.ibus_link_valid,
        "ibus_fresh": safety.ibus_fresh,
        "throttle_low": safety.throttle_low,
        "ch5_enabled": safety.ch5_enabled,
        "ch6_enabled": safety.ch6_enabled,
        "esc_safe": safety.esc_safe,
        "esc_started": safety.esc_started,
        "esc_fresh": safety.esc_fresh,
        "mtest_fresh": safety.mtest_fresh,
        "mtest_ready": safety.mtest_ready,
        "propellers_removed": safety.propellers_removed,
    }


def run_disable_reasons(
    safety: SafetySnapshot,
    protocol_online: bool,
    *,
    run_pending: bool = False,
    run_accepted: bool = False,
) -> tuple[str, ...]:
    if run_pending:
        return ("Waiting for firmware command acknowledgment.",)
    if run_accepted:
        return ("A motor test is still active or awaiting READY telemetry.",)
    values = safety_gate_values(safety, protocol_online)
    return tuple(GATE_LABELS[key][1] for key, passed in values.items() if not passed)


def gate_summary(values: Mapping[str, bool]) -> Presentation:
    failed = sum(not passed for passed in values.values())
    if failed == 0:
        return Presentation("READY FOR BENCH TEST", "success")
    return Presentation(f"NOT READY · {failed} CHECK{'S' if failed != 1 else ''} FAILED", "danger")


def fault_presentation(record: Optional[MotorTestRecord], abort_name: str = "NONE") -> Presentation:
    if record is None:
        return Presentation("NO MOTOR-TEST TELEMETRY", "neutral")
    if record.state == 3:
        return Presentation(f"FAULT · {abort_name}", "danger")
    if record.state == 2:
        return Presentation("RUNNING", "warning")
    if record.state == 1 and record.active_us == 1000:
        return Presentation("READY", "success")
    if record.state == 0:
        return Presentation("DISABLED", "neutral")
    return Presentation("OUTPUT NOT SAFE", "danger")


def emergency_stop_available(serial_connected: bool, replay_mode: bool = False) -> bool:
    return serial_connected and not replay_mode


def navigation_state(requested: str) -> str:
    return requested if requested in PAGE_INFO else "Dashboard"


def format_age(age_s: Optional[float]) -> str:
    if age_s is None:
        return "--"
    if age_s < 1.0:
        return f"{age_s * 1000.0:.0f} ms"
    return f"{age_s:.1f} s"
