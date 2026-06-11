from __future__ import annotations

from pathlib import Path
import json
import os
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "intelli-integration-workflow.json"


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or DEFAULT_CONFIG_PATH
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    config = data if isinstance(data, dict) else {}
    override_path = os.environ.get("STATUS_HUB_CONFIG_FILE")
    if override_path:
        try:
            override = json.loads(Path(override_path).expanduser().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            override = {}
        if isinstance(override, dict):
            config = deep_merge(config, override)
    return config


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(base, ensure_ascii=False))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
