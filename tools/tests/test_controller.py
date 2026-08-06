from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from monitor_app.controller import CommandDispatcher, OutgoingQueue  # noqa: E402
from monitor_app.models import SafetySnapshot  # noqa: E402
from monitor_app.models import CommandAckRecord  # noqa: E402


def passing_safety() -> SafetySnapshot:
    return SafetySnapshot(
        serial_connected=True,
        ibus_link_valid=True,
        ibus_fresh=True,
        throttle_low=True,
        ch5_enabled=True,
        ch6_enabled=True,
        esc_safe=True,
        esc_started=True,
        esc_fresh=True,
        mtest_fresh=True,
        mtest_ready=True,
        propellers_removed=True,
    )


class ControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.outgoing = OutgoingQueue()
        self.dispatcher = CommandDispatcher(self.outgoing)
        self.dispatcher.set_connected(True)

    def test_run_enabled_only_when_every_gate_passes(self) -> None:
        self.assertTrue(self.dispatcher.can_run(passing_safety()))
        failed = SafetySnapshot(**{**passing_safety().__dict__, "ch6_enabled": False})
        self.assertFalse(self.dispatcher.can_run(failed))

    def test_does_not_queue_two_run_commands(self) -> None:
        self.assertTrue(self.dispatcher.queue_run(1, 1020, 500))
        self.assertFalse(self.dispatcher.queue_run(2, 1050, 500))
        self.assertEqual(self.outgoing.count_kind("RUN"), 1)

    def test_accepted_run_stays_locked_until_new_non_running_telemetry(self) -> None:
        self.assertTrue(self.dispatcher.queue_run(1, 1020, 500))
        self.outgoing.get()
        self.dispatcher.handle_ack(
            CommandAckRecord(1, "RUN", 1, "NONE", 1, 1020, 500)
        )
        self.assertFalse(self.dispatcher.can_run(passing_safety()))
        self.assertFalse(self.dispatcher.queue_run(2, 1020, 500))
        self.dispatcher.handle_mtest_state(2)
        self.assertFalse(self.dispatcher.can_run(passing_safety()))
        self.dispatcher.handle_mtest_state(1)
        self.assertTrue(self.dispatcher.can_run(passing_safety()))

    def test_emergency_clears_pending_run_and_goes_first(self) -> None:
        self.assertTrue(self.dispatcher.queue_run(1, 1020, 500))
        self.assertTrue(self.dispatcher.queue_emergency_stop())
        self.assertEqual(self.outgoing.count_kind("RUN"), 0)
        request = self.outgoing.get()
        self.assertIsNotNone(request)
        self.assertEqual(request.payload, b"!")
        self.assertFalse(self.dispatcher.run_pending)

    def test_stop_clears_pending_run(self) -> None:
        self.dispatcher.queue_run(1, 1020, 500)
        self.dispatcher.queue_stop()
        self.assertEqual(self.outgoing.count_kind("RUN"), 0)
        self.assertEqual(self.outgoing.get().payload, b"MTEST STOP\r\n")

    def test_disconnected_never_runs(self) -> None:
        self.dispatcher.set_connected(False)
        self.assertFalse(self.dispatcher.can_run(passing_safety()))
        self.assertFalse(self.dispatcher.queue_run(1, 1020, 500))


if __name__ == "__main__":
    unittest.main()
