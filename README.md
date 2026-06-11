# status-hub-intelli-integration-provider

Status Hub provider plugin for Shulex Intelli integration-project automation.

This repository is intentionally separate from `status-hub`. Status Hub installs
the plugin from GitHub, starts the provider command, and reads the generated
status JSON. The provider stores job run records locally so scheduled jobs,
Codex skills, or manual scripts can report progress without being built into the
Hub app.

## Features

The provider exposes four Intelli integration work streams:

- Sprint demand preparation: collect integration-related demand candidates,
  manual demand notes, point estimates, priorities, and sprint document links.
- Daily feedback defect triage: group daily feedback defects by module and
  assign owners for investigation.
- Sprint demand progress tracking: compare sprint demand docs with requirement
  table state and prepare human-confirmed backfill actions.
- Production log analysis: track production integration-error analysis outputs
  separately from sprint demand preparation.

Production SLS routing for log-analysis jobs should use:

```text
project: shulex-prod-applications-0714
```

## Status Hub Plugin

The plugin manifest is `statushub-plugin.json`. Status Hub starts:

```text
bin/intelli-integration-provider
```

The command writes the status file passed through `STATUS_HUB_STATUS_FILE`.

## Local Data

By default, job runs are read from:

```text
~/Library/Application Support/IntelliIntegrationAutomation/runs/*.json
```

Override the location with:

```bash
export INTELLI_AUTOMATION_HOME="/path/to/data"
```

## Run Record Format

Scheduled tasks and Codex skills should write one JSON file per run:

```json
{
  "runId": "20260611-093000-daily-feedback-defect-triage",
  "jobType": "daily-feedback-defect-triage",
  "status": "needs_confirmation",
  "trigger": "scheduled",
  "startedAt": "2026-06-11T09:30:00+08:00",
  "finishedAt": "2026-06-11T09:36:42+08:00",
  "sprint": "Sprint 202606 15 - 19",
  "summary": "分析缺陷反馈 18 条，生成 5 个模块处理项",
  "artifacts": [
    {
      "title": "每日缺陷反馈分析",
      "url": "https://alidocs.dingtalk.com/i/nodes/..."
    }
  ],
  "logPath": "/Users/norman/Library/Application Support/IntelliIntegrationAutomation/logs/example.log",
  "note": "人工确认前不写回 AI 表格。"
}
```

Supported run statuses:

- `pending`
- `running`
- `success`
- `failed`
- `needs_confirmation`
- `canceled`
- `unknown`

## Recording Runs

For local testing or manual integration:

```bash
bin/intelli-integration-job record \
  --job-type daily-feedback-defect-triage \
  --status needs_confirmation \
  --summary "生成每日反馈缺陷分析，等待 Owner 确认" \
  --artifact-title "每日反馈缺陷分析" \
  --artifact-url "https://alidocs.dingtalk.com/i/nodes/..."
```

Run the provider once:

```bash
STATUS_HUB_STATUS_FILE=/tmp/intelli-status.json bin/intelli-integration-provider --once
cat /tmp/intelli-status.json
```

Run as a daemon:

```bash
STATUS_HUB_STATUS_FILE=/tmp/intelli-status.json bin/intelli-integration-provider
```

