from __future__ import annotations

import sys
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibus_monitor import build_argument_parser  # noqa: E402
from monitor_app.replay_worker import ReplayWorker  # noqa: E402


class ReplayTests(unittest.TestCase):
    def test_csv_row_extracts_raw_machine_line(self) -> None:
        line = ReplayWorker._line_from_row(
            ["2026-08-06T12:00:00+07:00", "ESC", "@ESC,1,1,15,50,1000,1000,1000,1000,0,0"]
        )
        self.assertTrue(line.startswith("@ESC,"))

    def test_raw_log_row_is_preserved(self) -> None:
        self.assertEqual(
            ReplayWorker._line_from_row(["@MTEST", "1", "1"]),
            "@MTEST,1,1",
        )

    def test_replay_cli_option(self) -> None:
        args = build_argument_parser().parse_args(["--replay", "capture.csv"])
        self.assertEqual(args.replay, "capture.csv")
        self.assertFalse(args.demo)

    def test_demo_and_replay_are_mutually_exclusive(self) -> None:
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            build_argument_parser().parse_args(
                ["--demo", "--replay", "capture.csv"]
            )


if __name__ == "__main__":
    unittest.main()
