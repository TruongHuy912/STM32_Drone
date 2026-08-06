"""Thread-safe outgoing queue and GUI-side command/safety policy."""

from __future__ import annotations

import collections
import threading
import time
from typing import Optional

from .models import CommandAckRecord, SafetySnapshot, TxRequest
from .protocol import (
    format_emergency_stop,
    format_log_command,
    format_run_command,
    format_stop_command,
)


class OutgoingQueue:
    def __init__(self) -> None:
        self._items: collections.deque[TxRequest] = collections.deque()
        self._condition = threading.Condition()

    def put(self, request: TxRequest, *, front: bool = False) -> None:
        with self._condition:
            if front:
                self._items.appendleft(request)
            else:
                self._items.append(request)
            self._condition.notify()

    def get(self, timeout: float = 0.0) -> Optional[TxRequest]:
        deadline = time.monotonic() + max(0.0, timeout)
        with self._condition:
            while not self._items:
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    return None
                self._condition.wait(remaining)
            return self._items.popleft()

    def remove_kind(self, kind: str) -> int:
        with self._condition:
            original = len(self._items)
            self._items = collections.deque(
                request for request in self._items if request.kind != kind
            )
            return original - len(self._items)

    def clear(self) -> None:
        with self._condition:
            self._items.clear()

    def count_kind(self, kind: str) -> int:
        with self._condition:
            return sum(request.kind == kind for request in self._items)


class CommandDispatcher:
    def __init__(self, outgoing: OutgoingQueue) -> None:
        self.outgoing = outgoing
        self.connected = False
        self.run_pending = False
        self.run_accepted = False
        self.last_run_duration_ms = 500

    def set_connected(self, connected: bool) -> None:
        self.connected = connected
        if not connected:
            self.run_pending = False
            self.run_accepted = False
            self.outgoing.clear()

    def can_run(self, safety: SafetySnapshot) -> bool:
        return (
            self.connected
            and not self.run_pending
            and not self.run_accepted
            and safety.all_pass()
        )

    def queue_run(self, motor: int, pulse_us: int, duration_ms: int) -> bool:
        if (
            not self.connected
            or self.run_pending
            or self.run_accepted
            or self.outgoing.count_kind("RUN")
        ):
            return False
        payload = format_run_command(motor, pulse_us, duration_ms)
        self.outgoing.put(TxRequest("RUN", payload, payload.decode("ascii").strip()))
        self.run_pending = True
        self.last_run_duration_ms = duration_ms
        return True

    def queue_stop(self, *, front: bool = True) -> bool:
        if not self.connected:
            return False
        self.outgoing.remove_kind("RUN")
        self.run_pending = False
        self.run_accepted = False
        self.outgoing.put(
            TxRequest("STOP", format_stop_command(), "MTEST STOP"), front=front
        )
        return True

    def queue_emergency_stop(self) -> bool:
        if not self.connected:
            return False
        self.outgoing.remove_kind("RUN")
        self.run_pending = False
        self.run_accepted = False
        self.outgoing.put(
            TxRequest("ESTOP", format_emergency_stop(), "!"), front=True
        )
        return True

    def queue_log(self, mode: str) -> bool:
        if not self.connected:
            return False
        payload = format_log_command(mode)
        self.outgoing.put(TxRequest("LOG", payload, payload.decode("ascii").strip()))
        return True

    def handle_ack(self, ack: CommandAckRecord) -> None:
        if ack.command == "RUN":
            self.run_pending = False
            self.run_accepted = ack.accepted == 1

    def handle_mtest_state(self, state: int) -> None:
        if self.run_accepted and state != 2:
            self.run_accepted = False
