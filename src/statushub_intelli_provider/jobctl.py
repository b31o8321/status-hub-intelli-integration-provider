from __future__ import annotations

from datetime import datetime
from pathlib import Path
import argparse
import json
import tempfile

from .jobs import JOB_TYPES
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

    list_jobs = subparsers.add_parser("list-jobs", help="list supported job types")
    list_jobs.set_defaults(func=list_supported_jobs)

    args = parser.parse_args(argv)
    if args.command == "record":
        return record_run(args)
    if hasattr(args, "func"):
        return args.func(args)
    return 1


def record_run(args: argparse.Namespace) -> int:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    run_id = args.run_id or f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{args.job_type}"
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

    output = runs_directory() / f"{run_id}.json"
    write_json(output, record)
    print(output)
    return 0


def list_supported_jobs(_args: argparse.Namespace) -> int:
    for job_type in sorted(JOB_TYPES):
        print(job_type)
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

