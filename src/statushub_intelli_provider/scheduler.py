from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import json
from typing import Any

from .config import load_config
from .jobs import JOB_TYPES
from .runner import run_job
from .status import automation_home, write_json


@dataclass(frozen=True)
class Schedule:
    job_type: str
    cron: str
    enabled: bool
    label: str


def scheduler_state_path() -> Path:
    return automation_home() / "scheduler-state.json"


def load_schedules(config: dict[str, Any] | None = None) -> list[Schedule]:
    data = config or load_config()
    schedules = []
    for item in data.get("schedules", []):
        if not isinstance(item, dict):
            continue
        job_type = str(item.get("jobType") or "")
        cron = str(item.get("cron") or "").strip()
        if job_type not in JOB_TYPES or not cron:
            continue
        schedules.append(
            Schedule(
                job_type=job_type,
                cron=cron,
                enabled=bool(item.get("enabled", True)),
                label=str(item.get("label") or job_type),
            )
        )
    return schedules


def tick(now: datetime | None = None) -> list[Path]:
    current = normalize_minute(now or datetime.now().astimezone())
    state = load_state()
    fired_paths: list[Path] = []
    changed = False

    for schedule in load_schedules():
        if not schedule.enabled or not cron_matches(schedule.cron, current):
            continue
        state_key = f"{schedule.job_type}:{schedule.cron}"
        fire_key = current.isoformat(timespec="minutes")
        if state.get("lastFired", {}).get(state_key) == fire_key:
            continue
        fired_paths.append(run_job(schedule.job_type, trigger="scheduled", note=schedule.label))
        state.setdefault("lastFired", {})[state_key] = fire_key
        changed = True

    if changed:
        state["updatedAt"] = current.isoformat(timespec="seconds")
        write_json(scheduler_state_path(), state)
    return fired_paths


def schedule_details(now: datetime | None = None) -> dict[str, dict[str, str]]:
    current = normalize_minute(now or datetime.now().astimezone())
    details: dict[str, dict[str, str]] = {}
    for schedule in load_schedules():
        detail = {
            "cron": schedule.cron,
            "enabled": str(schedule.enabled).lower(),
            "label": schedule.label,
        }
        if schedule.enabled:
            next_run = next_run_after(schedule.cron, current)
            if next_run:
                detail["nextRunAt"] = next_run.isoformat(timespec="minutes")
        details[schedule.job_type] = detail
    return details


def next_run_after(cron: str, start: datetime) -> datetime | None:
    cursor = normalize_minute(start) + timedelta(minutes=1)
    max_minutes = 60 * 24 * 366
    for _ in range(max_minutes):
        if cron_matches(cron, cursor):
            return cursor
        cursor += timedelta(minutes=1)
    return None


def cron_matches(cron: str, value: datetime) -> bool:
    fields = cron.split()
    if len(fields) != 5:
        return False
    minute, hour, day, month, weekday = fields
    return (
        field_matches(minute, value.minute, 0, 59)
        and field_matches(hour, value.hour, 0, 23)
        and field_matches(day, value.day, 1, 31)
        and field_matches(month, value.month, 1, 12)
        and field_matches(weekday, cron_weekday(value), 0, 6)
    )


def field_matches(expression: str, value: int, minimum: int, maximum: int) -> bool:
    if expression == "*":
        return True
    for part in expression.split(","):
        if match_part(part, value, minimum, maximum):
            return True
    return False


def match_part(part: str, value: int, minimum: int, maximum: int) -> bool:
    if "/" in part:
        base, step_text = part.split("/", 1)
        try:
            step = int(step_text)
        except ValueError:
            return False
        if step <= 0:
            return False
        start = minimum if base == "*" else parse_range(base, minimum, maximum)[0]
        return field_matches(base, value, minimum, maximum) and (value - start) % step == 0

    start, end = parse_range(part, minimum, maximum)
    return start <= value <= end


def parse_range(part: str, minimum: int, maximum: int) -> tuple[int, int]:
    if "-" in part:
        left, right = part.split("-", 1)
        start = parse_value(left, minimum, maximum)
        end = parse_value(right, minimum, maximum)
    else:
        start = end = parse_value(part, minimum, maximum)
    return start, end


def parse_value(raw: str, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except ValueError:
        return minimum - 1
    if minimum == 0 and maximum == 6 and value == 7:
        value = 0
    if value < minimum or value > maximum:
        return minimum - 1
    return value


def cron_weekday(value: datetime) -> int:
    return (value.weekday() + 1) % 7


def normalize_minute(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def load_state() -> dict[str, Any]:
    path = scheduler_state_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"lastFired": {}}
    return data if isinstance(data, dict) else {"lastFired": {}}

