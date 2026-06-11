from __future__ import annotations

from pathlib import Path
import argparse
import os
import signal
import time

from .status import build_snapshot, write_snapshot
from .scheduler import tick


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Status Hub Intelli integration provider")
    parser.add_argument("--once", action="store_true", help="write status once and exit")
    parser.add_argument("--interval", type=float, default=5.0, help="poll interval in seconds")
    parser.add_argument("--disable-scheduler", action="store_true", help="only write status, do not run schedules")
    args = parser.parse_args(argv)

    status_file = os.environ.get("STATUS_HUB_STATUS_FILE")
    if not status_file:
        status_file = str(Path(__file__).resolve().parents[2] / "runtime" / "status.json")
    status_path = Path(status_file).expanduser()

    stopped = False

    def stop(_signum, _frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    while not stopped:
        if not args.once and not args.disable_scheduler:
            tick()
        write_snapshot(status_path, build_snapshot())
        if args.once:
            return 0
        time.sleep(max(args.interval, 1.0))

    return 0
