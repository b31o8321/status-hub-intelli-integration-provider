from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import subprocess
from typing import Any

from .config import load_config
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
    )
    log_path.write_text(completed.stdout or "", encoding="utf-8")
    if completed.returncode == 0:
        return {
            "status": str(job_config.get("successStatus") or "needs_confirmation"),
            "summary": f"{JOB_BY_TYPE[job_type].title} 执行完成",
            "logPath": str(log_path),
            "note": "命令已完成，按配置等待人工确认或标记完成。",
        }
    return {
        "status": "failed",
        "summary": f"{JOB_BY_TYPE[job_type].title} 执行失败",
        "logPath": str(log_path),
        "note": f"命令退出码：{completed.returncode}",
    }


def configured_job(config: dict[str, Any], job_type: str) -> dict[str, Any]:
    for job in config.get("jobs", []):
        if isinstance(job, dict) and job.get("jobType") == job_type:
            return job
    return {}
