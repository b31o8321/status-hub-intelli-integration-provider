from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import os
import subprocess
from typing import Any

from .config import ROOT_DIR, load_config
from .jobs import JOB_DEFINITIONS
from .notification import notify_run
from .status import automation_home, now_iso
from .status import write_json


JOB_BY_TYPE = {job.job_type: job for job in JOB_DEFINITIONS}


def locks_directory() -> Path:
    return automation_home() / "locks"


def logs_directory() -> Path:
    return automation_home() / "logs"


def runs_directory() -> Path:
    return automation_home() / "runs"


def run_job(job_type: str, trigger: str = "manual", note: str | None = None) -> Path:
    if job_type not in JOB_BY_TYPE:
        raise ValueError(f"unsupported job type: {job_type}")

    lock_path = locks_directory() / f"{job_type}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return lock_path

    try:
        os.write(fd, str(os.getpid()).encode("utf-8"))
    finally:
        os.close(fd)

    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:-3]}-{job_type}"
    run_path = runs_directory() / f"{run_id}.json"
    definition = JOB_BY_TYPE[job_type]
    started_at = now_iso()
    record: dict[str, Any] = {
        "runId": run_id,
        "jobType": job_type,
        "status": "running",
        "trigger": trigger,
        "startedAt": started_at,
        "summary": f"正在执行：{definition.title}",
    }
    if note:
        record["note"] = note
    write_json(run_path, record)

    try:
        final = execute_job(job_type, trigger)
        record.update(final)
    except Exception as exc:
        record.update(
            {
                "status": "failed",
                "summary": f"{definition.title} 执行失败",
                "note": str(exc),
            }
        )
    finally:
        record["finishedAt"] = now_iso()
        write_json(run_path, record)
        try:
            notify_run(record)
        except Exception:
            pass
        try:
            lock_path.unlink()
        except OSError:
            pass

    return run_path


def execute_job(job_type: str, trigger: str) -> dict[str, Any]:
    config = load_config()
    job_config = configured_job(config, job_type)
    command = job_config.get("command")
    if command:
        return execute_command_job(job_type, trigger, command, job_config)

    definition = JOB_BY_TYPE[job_type]
    skill = str(job_config.get("skill") or "对应 Codex skill")
    return {
        "status": "needs_confirmation",
        "summary": f"{definition.title} 已触发，等待使用 {skill} 生成或确认产出",
        "note": "当前 provider 已完成调度和运行记录；实际业务执行仍由人工/Codex 确认后完成，避免后台静默写回。",
    }


def execute_command_job(
    job_type: str,
    trigger: str,
    command: str | list[str],
    job_config: dict[str, Any],
) -> dict[str, Any]:
    started = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = logs_directory() / f"{started}-{job_type}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timeout_seconds = int(job_config.get("timeoutSeconds") or 3600)
    env = os.environ.copy()
    env.update(
        {
            "INTELLI_JOB_TYPE": job_type,
            "INTELLI_JOB_TRIGGER": trigger,
            "INTELLI_AUTOMATION_HOME": str(automation_home()),
        }
    )
    shell = isinstance(command, str)
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout_seconds,
        check=False,
        shell=shell,
        env=env,
        cwd=str(ROOT_DIR),
    )
    log_path.write_text(completed.stdout or "", encoding="utf-8")
    parsed = parse_command_result(completed.stdout or "")
    if completed.returncode == 0:
        result = {
            "status": str(job_config.get("successStatus") or "needs_confirmation"),
            "summary": f"{JOB_BY_TYPE[job_type].title} 执行完成",
            "logPath": str(log_path),
        }
        result.update(filtered_result(parsed))
        result["status"] = normalize_status(str(result.get("status") or "success"))
        return result
    failure = {
        "status": "failed",
        "summary": f"{JOB_BY_TYPE[job_type].title} 执行失败",
        "logPath": str(log_path),
        "note": f"命令退出码：{completed.returncode}",
    }
    failure.update(filtered_result(parsed))
    failure["status"] = "failed"
    if not failure.get("note"):
        failure["note"] = f"命令退出码：{completed.returncode}"
    return failure


def parse_command_result(output: str) -> dict[str, Any]:
    marked = extract_marked_json(output)
    if marked:
        return marked
    stripped = strip_code_fence(output.strip())
    direct = load_json_object(stripped)
    if direct:
        return direct
    return last_json_object(output)


def extract_marked_json(output: str) -> dict[str, Any]:
    begin = "STATUS_HUB_RESULT_JSON_BEGIN"
    end = "STATUS_HUB_RESULT_JSON_END"
    if begin not in output or end not in output:
        return {}
    payload = output.split(begin, 1)[1].split(end, 1)[0].strip()
    return load_json_object(strip_code_fence(payload))


def strip_code_fence(value: str) -> str:
    if value.startswith("```"):
        lines = value.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
    return value


def load_json_object(value: str) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def last_json_object(output: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    latest: dict[str, Any] = {}
    for index, char in enumerate(output):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            latest = parsed
    return latest


def filtered_result(result: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "status",
        "summary",
        "sprint",
        "artifacts",
        "notificationMarkdown",
        "notifyAtUserIds",
        "note",
    }
    filtered = {key: value for key, value in result.items() if key in allowed and value}
    if "artifacts" in filtered and not valid_artifacts(filtered["artifacts"]):
        filtered.pop("artifacts", None)
    if "notifyAtUserIds" in filtered and isinstance(filtered["notifyAtUserIds"], str):
        filtered["notifyAtUserIds"] = [
            item.strip()
            for item in filtered["notifyAtUserIds"].split(",")
            if item.strip()
        ]
    if "notifyAtUserIds" in filtered and not isinstance(filtered["notifyAtUserIds"], list):
        filtered.pop("notifyAtUserIds", None)
    return filtered


def valid_artifacts(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if not isinstance(item, dict) or not item.get("url"):
            return False
    return True


def normalize_status(status: str) -> str:
    if status in {"pending", "running", "success", "failed", "needs_confirmation", "canceled", "unknown"}:
        return status
    return "success"


def configured_job(config: dict[str, Any], job_type: str) -> dict[str, Any]:
    for job in config.get("jobs", []):
        if isinstance(job, dict) and job.get("jobType") == job_type:
            return job
    return {}
