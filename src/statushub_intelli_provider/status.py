from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import os
import tempfile
from typing import Any

from .config import load_config
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
    timestamp = str(run.get("finishedAt") or run.get("startedAt") or run.get("createdAt") or "")
    return f"{timestamp}-{run.get('runId') or ''}"


def build_snapshot(runs_dir: Path | None = None) -> dict[str, Any]:
    runs = load_runs(runs_dir)
    latest = latest_runs_by_type(runs)
    schedule_by_type = load_schedule_details()
    job_config_by_type = configured_jobs()
    items = []

    for definition in JOB_DEFINITIONS:
        job_config = job_config_by_type.get(definition.job_type, {})
        run = latest.get(definition.job_type)
        schedule = schedule_by_type.get(definition.job_type, {})
        detail = display_schedule_detail(schedule)
        enabled = schedule.get("enabled") != "false"
        if run:
            status = RUN_STATUS_TO_HUB.get(str(run.get("status", "unknown")), "unknown")
            summary = str(run.get("summary") or definition.default_summary)
            note = str(run.get("note") or "").strip()
            subtitle = f"{summary} · {note}" if note else summary
            artifact_url = first_artifact_url(run)
            detail.update(run_detail(run))
        else:
            status = "success" if enabled else "idle"
            subtitle = definition.default_summary
            artifact_url = None

        schedule_action = {
            "id": "disable-schedule" if enabled else "enable-schedule",
            "title": "关闭定时" if enabled else "开启定时",
            "command": "bin/intelli-integration-job",
            "arguments": [
                "set-schedule",
                "--job-type",
                definition.job_type,
                "--enabled",
                "false" if enabled else "true",
            ],
            "workingDirectory": ".",
        }
        actions = [schedule_action]
        if job_config.get("command"):
            actions.insert(
                0,
                {
                    "id": "run",
                    "title": "触发",
                    "command": "bin/intelli-integration-job",
                    "arguments": [
                        "run",
                        "--job-type",
                        definition.job_type,
                        "--trigger",
                        "hub",
                    ],
                    "workingDirectory": ".",
                },
            )

        items.append(
            {
                "id": definition.job_type,
                "title": definition.title,
                "subtitle": subtitle,
                "status": status,
                "url": artifact_url,
                "value": value_for(status),
                "detail": detail,
                "actions": actions,
                "links": recent_artifact_links(definition.job_type, runs),
            }
        )

    overall = overall_status([item["status"] for item in items], any(item["status"] != "idle" for item in items))
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


def recent_artifact_links(job_type: str, runs: list[dict[str, Any]], limit: int = 3) -> list[dict[str, str]]:
    links = []
    related = [run for run in runs if str(run.get("jobType")) == job_type]
    for run in sorted(related, key=sort_key, reverse=True):
        artifacts = run.get("artifacts")
        if not isinstance(artifacts, list):
            continue
        for index, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict) or not artifact.get("url"):
                continue
            title = str(artifact.get("title") or "产出文档")
            finished = short_datetime(str(run.get("finishedAt") or run.get("startedAt") or ""))
            links.append(
                {
                    "id": f"{run.get('runId', job_type)}-{index}",
                    "title": f"{title} · {finished}" if finished else title,
                    "url": str(artifact["url"]),
                }
            )
            if len(links) >= limit:
                return links
    return links


def run_detail(run: dict[str, Any]) -> dict[str, str]:
    detail = {}
    started = short_datetime(str(run.get("startedAt") or ""))
    trigger = str(run.get("trigger") or "")
    if started:
        trigger_text = "手动" if trigger in {"manual", "hub"} else "定时" if trigger == "scheduled" else trigger
        detail["lastRunText"] = f"{started} {trigger_text}".strip()
    finished = short_datetime(str(run.get("finishedAt") or ""))
    if finished:
        detail["finishedText"] = finished
    if run.get("logPath"):
        detail["logPath"] = str(run["logPath"])
    return detail


def display_schedule_detail(schedule: dict[str, str]) -> dict[str, str]:
    detail = {}
    if schedule.get("enabled") == "false":
        detail["nextRunText"] = "已关闭"
    elif schedule.get("nextRunAt"):
        detail["nextRunText"] = short_datetime(schedule["nextRunAt"])
    return detail


def short_datetime(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.strftime("%m-%d %H:%M")


def load_schedule_details() -> dict[str, dict[str, str]]:
    try:
        from .scheduler import schedule_details
    except ImportError:
        return {}
    return schedule_details()


def configured_jobs() -> dict[str, dict[str, Any]]:
    config = load_config()
    result: dict[str, dict[str, Any]] = {}
    for job in config.get("jobs", []):
        if isinstance(job, dict) and job.get("jobType"):
            result[str(job["jobType"])] = job
    return result


def value_for(status: str) -> str:
    return {
        "idle": "空闲",
        "running": "运行中",
        "attention": "待确认",
        "failed": "失败",
        "success": "正常",
        "unknown": "未知",
    }.get(status, status)


def overall_status(statuses: list[str], has_enabled_or_runs: bool) -> str:
    if not has_enabled_or_runs:
        return "idle"
    return max(statuses, key=lambda value: HUB_SEVERITY.get(value, 2))


def summary_text(items: list[dict[str, Any]], runs: list[dict[str, Any]]) -> str:
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
    if not parts and counts["success"] == 0:
        parts.append("所有定时任务已关闭")
    if not parts:
        parts.append(f"{counts['success']} 个已启用")
    return "，".join(parts)


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    write_json(path, snapshot)


def write_json(path: Path, payload: dict[str, Any]) -> None:
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
