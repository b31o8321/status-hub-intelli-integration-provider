from __future__ import annotations

from datetime import datetime
from pathlib import Path
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any
from urllib import parse, request

from .config import load_config
from .jobs import JOB_DEFINITIONS
from .status import automation_home


JOB_TITLE = {job.job_type: job.title for job in JOB_DEFINITIONS}


def notify_run(record: dict[str, Any]) -> None:
    settings = dingtalk_settings()
    if not settings.get("enabled") or not settings.get("webhook"):
        return
    job_types = settings.get("jobTypes")
    if isinstance(job_types, list) and job_types and record.get("jobType") not in job_types:
        return
    send_dingtalk_markdown(settings, notification_title(record), notification_markdown(record))


def dingtalk_settings() -> dict[str, Any]:
    config = load_config().get("notifications", {}).get("dingtalk", {})
    settings = config.copy() if isinstance(config, dict) else {}
    local = load_local_notification_config().get("dingtalk", {})
    if isinstance(local, dict):
        settings.update(local)
    if os.environ.get("DINGTALK_ROBOT_WEBHOOK"):
        settings["webhook"] = os.environ["DINGTALK_ROBOT_WEBHOOK"]
        settings["enabled"] = True
    if os.environ.get("DINGTALK_ROBOT_SECRET"):
        settings["secret"] = os.environ["DINGTALK_ROBOT_SECRET"]
    return settings


def load_local_notification_config() -> dict[str, Any]:
    path = automation_home() / "notification.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def send_dingtalk_markdown(settings: dict[str, Any], title: str, markdown: str) -> None:
    url = signed_webhook(str(settings["webhook"]), str(settings.get("secret") or ""))
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": markdown,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=8) as response:
        response.read()


def signed_webhook(webhook: str, secret: str) -> str:
    if not secret:
        return webhook
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
    sign = parse.quote_plus(base64.b64encode(digest))
    separator = "&" if "?" in webhook else "?"
    return f"{webhook}{separator}timestamp={timestamp}&sign={sign}"


def notification_title(record: dict[str, Any]) -> str:
    return f"{JOB_TITLE.get(str(record.get('jobType')), 'Intelli 自动化')}：{status_text(record)}"


def notification_markdown(record: dict[str, Any]) -> str:
    title = JOB_TITLE.get(str(record.get("jobType")), str(record.get("jobType", "Intelli 自动化")))
    lines = [
        f"### {title}",
        f"- 状态：{status_text(record)}",
        f"- 触发：{trigger_text(str(record.get('trigger') or ''))}",
        f"- 时间：{short_datetime(str(record.get('finishedAt') or record.get('startedAt') or ''))}",
        f"- 简介：{record.get('summary') or ''}",
    ]
    note = str(record.get("note") or "").strip()
    if note:
        lines.append(f"- 备注：{note}")
    artifacts = record.get("artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts[:3]:
            if isinstance(artifact, dict) and artifact.get("url"):
                lines.append(f"- 产出：[{artifact.get('title') or '文档'}]({artifact['url']})")
    if record.get("logPath"):
        lines.append(f"- 日志：`{record['logPath']}`")
    return "\n".join(lines)


def status_text(record: dict[str, Any]) -> str:
    return {
        "pending": "待执行",
        "running": "运行中",
        "success": "已完成",
        "failed": "失败",
        "needs_confirmation": "待人工确认",
        "canceled": "已取消",
        "unknown": "未知",
    }.get(str(record.get("status") or "unknown"), str(record.get("status") or "unknown"))


def trigger_text(trigger: str) -> str:
    return {
        "hub": "Hub 手动触发",
        "manual": "命令行手动触发",
        "scheduled": "定时触发",
    }.get(trigger, trigger or "未知")


def short_datetime(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%m-%d %H:%M")
    except ValueError:
        return value

