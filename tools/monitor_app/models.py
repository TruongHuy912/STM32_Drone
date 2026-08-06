"""Immutable telemetry and command models used by worker, controller, and GUI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IBusRecord:
    timestamp_us: int
    stream_alive: int
    age_ms: int
    channels: tuple[int, int, int, int, int, int, int, int]
    valid_frames: int
    checksum_errors: int
    uart_errors: int
    ring_overflows: int


@dataclass(frozen=True)
class ESCRecord:
    timestamp_us: int
    state: int
    started_mask: int
    frequency_hz: int
    motor_us: tuple[int, int, int, int]
    rejected: int
    start_errors: int


@dataclass(frozen=True)
class MotorTestRecord:
    timestamp_us: int
    state: int
    motor: int
    commanded_us: int
    active_us: int
    remaining_ms: int
    gate_mask: int
    last_abort: int
    run_count: int
    completed_count: int
    abort_count: int
    rejected_count: int


@dataclass(frozen=True)
class CommandAckRecord:
    timestamp_us: int
    command: str
    accepted: int
    reason: str
    motor: int
    pulse_us: int
    duration_ms: int


@dataclass(frozen=True)
class ParsedLine:
    kind: str
    record: object
    raw: str


@dataclass(frozen=True)
class TxRequest:
    kind: str
    payload: bytes
    display: str


@dataclass(frozen=True)
class SafetySnapshot:
    serial_connected: bool = False
    ibus_link_valid: bool = False
    ibus_fresh: bool = False
    throttle_low: bool = False
    ch5_enabled: bool = False
    ch6_enabled: bool = False
    esc_safe: bool = False
    esc_started: bool = False
    esc_fresh: bool = False
    mtest_fresh: bool = False
    mtest_ready: bool = False
    propellers_removed: bool = False

    def all_pass(self) -> bool:
        return all(
            (
                self.serial_connected,
                self.ibus_link_valid,
                self.ibus_fresh,
                self.throttle_low,
                self.ch5_enabled,
                self.ch6_enabled,
                self.esc_safe,
                self.esc_started,
                self.esc_fresh,
                self.mtest_fresh,
                self.mtest_ready,
                self.propellers_removed,
            )
        )
