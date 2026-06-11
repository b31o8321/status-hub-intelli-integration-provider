from __future__ import annotations

from datetime import datetime
from pathlib import Path
import argparse
import json
import tempfile

from .jobs import JOB_TYPES
from .notification import notify_run
from .runner import run_job
from .scheduler import load_schedules, next_run_after, set_schedule_enabled
from .status import runs_directory


SUPPORTED_STATUSES = {
    "pending",
    "running",
    "success",
    "failed",
    "needs_confirmation",
    "canceled",
    "unknown",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record Intelli integration automation runs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    record = subparsers.add_parser("record", help="write one run record")
    record.add_argument("--job-type", required=True, choices=sorted(JOB_TYPES))
    record.add_argument("--status", required=True, choices=sorted(SUPPORTED_STATUSES))
    record.add_argument("--summary", required=True)
    record.add_argument("--trigger", default="manual")
    record.add_argument("--run-id")
    record.add_argument("--started-at")
    record.add_argument("--finished-at")
    record.add_argument("--sprint")
    record.add_argument("--artifact-title")
    record.add_argument("--artifact-url")
    record.add_argument("--log-path")
    record.add_argument("--note")
    record.add_argument("--notification-markdown")
    record.add_argument("--notify-at-user-ids")
    record.add_argument("--send-notification", action="store_true")

    run = subparsers.add_parser("run", help="run one supported job through the provider runner")
    run.add_argument("--job-type", required=True, choices=sorted(JOB_TYPES))
    run.add_argument("--trigger", default="manual")
    run.add_argument("--note")
    run.set_defaults(func=run_supported_job)

    list_jobs = subparsers.add_parser("list-jobs", help="list supported job types")
    list_jobs.set_defaults(func=list_supported_jobs)

    list_schedules = subparsers.add_parser("list-schedules", help="list configured schedules")
    list_schedules.set_defaults(func=list_schedules_config)

    set_schedule = subparsers.add_parser("set-schedule", help="enable or disable one schedule")
    set_schedule.add_argument("--job-type", required=True, choices=sorted(JOB_TYPES))
    set_schedule.add_argument("--enabled", required=True, choices=["true", "false"])
    set_schedule.set_defaults(func=set_schedule_config)

    args = parser.parse_args(argv)
    if args.command == "record":
        return record_run(args)
    if hasattr(args, "func"):
        return args.func(args)
    return 1


def record_run(args: argparse.Namespace) -> int:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    run_id = args.run_id or f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:-3]}-{args.job_type}"
    started_at = args.started_at or now
    finished_at = args.finished_at
    if args.status not in {"pending", "running"} and not finished_at:
        finished_at = now

    record = {
        "runId": run_id,
        "jobType": args.job_type,
        "status": args.status,
        "trigger": args.trigger,
        "startedAt": started_at,
        "summary": args.summary,
    }

    optional = {
        "finishedAt": finished_at,
        "sprint": args.sprint,
        "logPath": args.log_path,
        "note": args.note,
        "notificationMarkdown": args.notification_markdown,
    }
    for key, value in optional.items():
        if value:
            record[key] = value

    if args.artifact_url:
        record["artifacts"] = [
            {
                "title": args.artifact_title or "产出物",
                "url": args.artifact_url,
            }
        ]

    if args.notify_at_user_ids:
        record["notifyAtUserIds"] = [
            value.strip()
            for value in args.notify_at_user_ids.split(",")
            if value.strip()
        ]

    output = runs_directory() / f"{run_id}.json"
    write_json(output, record)
    if args.send_notification:
        notify_run(record)
    print(output)
    return 0


def list_supported_jobs(_args: argparse.Namespace) -> int:
    for job_type in sorted(JOB_TYPES):
        print(job_type)
    return 0


def run_supported_job(args: argparse.Namespace) -> int:
    path = run_job(args.job_type, trigger=args.trigger, note=args.note)
    print(path)
    return 0


def list_schedules_config(_args: argparse.Namespace) -> int:
    now = datetime.now().astimezone()
    for schedule in load_schedules():
        enabled = "enabled" if schedule.enabled else "disabled"
        next_run = next_run_after(schedule.cron, now) if schedule.enabled else None
        suffix = f" next={next_run.isoformat(timespec='minutes')}" if next_run else ""
        print(f"{schedule.job_type} {enabled} cron='{schedule.cron}'{suffix}")
    return 0


def set_schedule_config(args: argparse.Namespace) -> int:
    enabled = args.enabled == "true"
    set_schedule_enabled(args.job_type, enabled)
    print(f"{args.job_type} {'enabled' if enabled else 'disabled'}")
    return 0


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
        prefix=f".{path.name}.",
    ) as handle:
        handle.write(data)
        handle.write("\n")
        tmp_path = Path(handle.name)
    tmp_path.replace(path)
