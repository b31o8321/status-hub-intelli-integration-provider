from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import os
import tempfile
from typing import Any

from .jobs import JOB_DEFINITIONS


RUN_STATUS_TO_HUB = {
    "pending": "idle",
    "running": "running",
    "success": "success",
    "failed": "failed",
    "needs_confirmation": "attention",
    "canceled": "unknown",
    "unknown": "unknown",
}

HUB_SEVERITY = {
    "idle": 0,
    "success": 1,
    "unknown": 2,
    "running": 3,
    "attention": 4,
    "failed": 5,
}


def automation_home() -> Path:
    override = os.environ.get("INTELLI_AUTOMATION_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "IntelliIntegrationAutomation"


def runs_directory() -> Path:
    return automation_home() / "runs"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_runs(runs_dir: Path | None = None) -> list[dict[str, Any]]:
    directory = runs_dir or runs_directory()
    if not directory.exists():
        return []

    runs: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("jobType"):
            data["_path"] = str(path)
            runs.append(data)
    return runs


def latest_runs_by_type(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for run in runs:
        job_type = str(run.get("jobType", ""))
        current = latest.get(job_type)
        if current is None or sort_key(run) > sort_key(current):
            latest[job_type] = run
    return latest


def sort_key(run: dict[str, Any]) -> str:
    return str(
        run.get("finishedAt")
        or run.get("startedAt")
        or run.get("createdAt")
        or run.get("runId")
        or ""
    )


def build_snapshot(runs_dir: Path | None = None) -> dict[str, Any]:
    runs = load_runs(runs_dir)
    latest = latest_runs_by_type(runs)
    items = []

    for definition in JOB_DEFINITIONS:
        run = latest.get(definition.job_type)
        if run:
            status = RUN_STATUS_TO_HUB.get(str(run.get("status", "unknown")), "unknown")
            summary = str(run.get("summary") or definition.default_summary)
            note = str(run.get("note") or "").strip()
            subtitle = f"{summary} · {note}" if note else summary
            artifact_url = first_artifact_url(run)
        else:
            status = "idle"
            subtitle = definition.default_summary
            artifact_url = None

        items.append(
            {
                "id": definition.job_type,
                "title": definition.title,
                "subtitle": subtitle,
                "status": status,
                "url": artifact_url,
            }
        )

    overall = overall_status([item["status"] for item in items], bool(runs))
    return {
        "status": overall,
        "summary": summary_text(items, runs),
        "updatedAt": now_iso(),
        "items": items,
    }


def first_artifact_url(run: dict[str, Any]) -> str | None:
    artifacts = run.get("artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if isinstance(artifact, dict) and artifact.get("url"):
                return str(artifact["url"])
    return None


def overall_status(statuses: list[str], has_runs: bool) -> str:
    if not has_runs:
        return "idle"
    return max(statuses, key=lambda value: HUB_SEVERITY.get(value, 2))


def summary_text(items: list[dict[str, Any]], runs: list[dict[str, Any]]) -> str:
    if not runs:
        return "暂无运行中的集成自动化任务"

    counts = {"running": 0, "attention": 0, "failed": 0, "success": 0}
    for item in items:
        status = item.get("status")
        if status in counts:
            counts[str(status)] += 1

    parts = []
    if counts["failed"]:
        parts.append(f"{counts['failed']} 个失败")
    if counts["attention"]:
        parts.append(f"{counts['attention']} 个待确认")
    if counts["running"]:
        parts.append(f"{counts['running']} 个运行中")
    if not parts:
        parts.append(f"{counts['success']} 个最近完成")
    return "，".join(parts)


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
        prefix=f".{path.name}.",
    ) as handle:
        handle.write(payload)
        handle.write("\n")
        tmp_path = Path(handle.name)
    tmp_path.replace(path)

