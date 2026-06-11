from __future__ import annotations

from datetime import datetime
from pathlib import Path
import base64
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any
from urllib import parse, request

from .config import load_config
from .jobs import JOB_DEFINITIONS
from .status import automation_home


JOB_TITLE = {job.job_type: job.title for job in JOB_DEFINITIONS}
DINGTALK_ROBOT_SEND_URL = "https://oapi.dingtalk.com/robot/send"


def notify_run(record: dict[str, Any]) -> None:
    settings = dingtalk_settings()
    webhook = dingtalk_webhook(settings)
    if not settings.get("enabled") or not webhook:
        return
    job_types = settings.get("jobTypes")
    if isinstance(job_types, list) and job_types and record.get("jobType") not in job_types:
        return
    send_dingtalk_markdown(
        webhook,
        str(settings.get("secret") or ""),
        notification_title(record),
        notification_markdown(record, settings),
        at_user_ids(record),
    )


def dingtalk_settings() -> dict[str, Any]:
    config = load_config().get("notifications", {}).get("dingtalk", {})
    settings = config.copy() if isinstance(config, dict) else {}
    local = load_local_notification_config().get("dingtalk", {})
    if isinstance(local, dict):
        settings.update(local)
    if os.environ.get("DINGTALK_ROBOT_WEBHOOK"):
        settings["webhook"] = os.environ["DINGTALK_ROBOT_WEBHOOK"]
        settings["enabled"] = True
    if os.environ.get("DINGTALK_ROBOT_ACCESS_TOKEN"):
        settings["accessToken"] = os.environ["DINGTALK_ROBOT_ACCESS_TOKEN"]
        settings["enabled"] = True
    if os.environ.get("DINGTALK_ROBOT_TOKEN"):
        settings["accessToken"] = os.environ["DINGTALK_ROBOT_TOKEN"]
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


def dingtalk_webhook(settings: dict[str, Any]) -> str:
    access_token = str(settings.get("accessToken") or "").strip()
    webhook = str(settings.get("webhook") or "").strip()
    if access_token:
        return build_dingtalk_webhook(access_token)
    if webhook:
        return build_dingtalk_webhook(webhook)
    return ""


def build_dingtalk_webhook(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("access_token="):
        value = value.split("=", 1)[1].strip()
    return f"{DINGTALK_ROBOT_SEND_URL}?access_token={parse.quote(value, safe='')}"


def send_dingtalk_markdown(
    webhook: str,
    secret: str,
    title: str,
    markdown: str,
    at_user_ids: list[str] | None = None,
) -> None:
    url = signed_webhook(webhook, secret)
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": markdown,
        },
    }
    if at_user_ids:
        payload["at"] = {"atUserIds": at_user_ids, "isAtAll": False}
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


def notification_markdown(record: dict[str, Any], settings: dict[str, Any] | None = None) -> str:
    custom = str(record.get("notificationMarkdown") or "").strip()
    if custom:
        markdown = normalize_visible_mentions(custom, display_name_mapping(settings or {}))
        return append_source_links(record, markdown)

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
    return append_source_links(record, "\n".join(lines))


def append_source_links(record: dict[str, Any], markdown: str) -> str:
    links = source_links_for_job(str(record.get("jobType") or ""))
    missing_links = [
        (title, url)
        for title, url in links
        if url and url not in markdown
    ]
    if not missing_links:
        return markdown
    lines = [markdown.rstrip(), "", "#### 快捷入口"]
    for title, url in missing_links:
        lines.append(f"- [{title}]({url})")
    return "\n".join(line for line in lines if line is not None).rstrip()


def source_links_for_job(job_type: str) -> list[tuple[str, str]]:
    source_links = load_config().get("sourceLinks", {})
    if not isinstance(source_links, dict):
        return []
    if job_type == "daily-feedback-defect-triage":
        return [
            ("缺陷反馈源表", str(source_links.get("integrationDemandTable") or "")),
            ("本周进行中需求视图", str(source_links.get("iterationRequirementDevelopmentView") or "")),
        ]
    if job_type == "prepare-sprint-iteration":
        return [
            ("需求池源表", str(source_links.get("integrationDemandTable") or "")),
            ("项目管理需求表", str(source_links.get("iterationRequirementTable") or "")),
        ]
    return []


def display_name_mapping(settings: dict[str, Any]) -> dict[str, str]:
    raw = settings.get("userDisplayNames")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in raw.items():
        user_id = str(key).strip()
        display_name = str(value).strip()
        if user_id and display_name:
            result[user_id] = display_name
    return result


def normalize_visible_mentions(markdown: str, names: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        prefix = match.group(1) or ""
        user_id = match.group(2)
        return f"{prefix}@{names.get(user_id, user_id)}"

    return re.sub(r"(^|[^\w])@(\d{6,})", replace, markdown)


def at_user_ids(record: dict[str, Any]) -> list[str]:
    values = record.get("notifyAtUserIds")
    if isinstance(values, str):
        values = [item.strip() for item in values.split(",")]
    if not isinstance(values, list):
        return []
    result: list[str] = []
    seen = set()
    for value in values:
        user_id = str(value).strip()
        if not user_id or user_id in seen:
            continue
        seen.add(user_id)
        result.append(user_id)
    return result


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
