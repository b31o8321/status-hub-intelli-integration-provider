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

Workflow defaults live in:

```text
config/intelli-integration-workflow.json
```

That file records the sprint root folder, DingTalk AI table links, production
SLS project, human-confirmation policy, and the current team role split:

- 张意乾: PO and technical support, not direct implementation owner.
- 许嘉凯: 4-year developer, primary owner for higher-complexity integration
  backend/platform work.
- 戴军: 2-year developer, owner for smaller scoped fixes, defect triage, and
  well-bounded integration tasks.

Demand sizing uses Scrum `point`, not `Size`.

## Scheduling

The provider owns its own scheduler. Status Hub only starts the provider
process and reads its status file.

Default schedules:

| Job | Schedule | Behavior |
| --- | --- | --- |
| Daily feedback defect triage | Weekdays 09:30 | Create a run record for daily defect analysis |
| Sprint demand progress tracking | Weekdays 17:00 | Create a run record for progress tracking |
| Sprint demand preparation | Friday 10:00 | Create a run record for next-sprint demand preparation |
| Production log analysis | Disabled by default | Manual trigger only |

The scheduler uses the `schedules` array in
`config/intelli-integration-workflow.json`. It supports standard 5-field cron
expressions: `minute hour day month weekday`.

The first implementation intentionally records a run and marks it
`needs_confirmation` unless the job config provides a shell `command`. This keeps
human/Codex confirmation in the loop and avoids silent DingTalk writeback.

Schedules can be enabled or disabled without editing the plugin repository:

```bash
bin/intelli-integration-job set-schedule \
  --job-type daily-feedback-defect-triage \
  --enabled false
```

Status Hub renders provider item actions, so each job can be manually triggered
from the provider detail page and its schedule can be turned on or off there.

## DingTalk Robot Notifications

The provider can send a DingTalk robot markdown message when a run finishes.
By default only these job types are selected for notifications:

- `daily-feedback-defect-triage`
- `track-sprint-demand-progress`

The repository does not store robot credentials. Create this local file:

```text
~/Library/Application Support/IntelliIntegrationAutomation/notification.json
```

Example:

```json
{
  "dingtalk": {
    "enabled": true,
    "accessToken": "xxx",
    "secret": "SEC..."
  }
}
```

`accessToken` is the value after `access_token=` in the DingTalk robot webhook.
The provider builds the fixed DingTalk robot URL internally. The old `webhook`
field is still supported for compatibility.

`secret` is optional. Fill it only when the DingTalk robot security setting uses
signing and provides a `SEC...` secret. Leave it empty when the robot uses
keyword or IP allowlist security.

You can also use environment variables:

```bash
export DINGTALK_ROBOT_ACCESS_TOKEN="xxx"
export DINGTALK_ROBOT_SECRET="SEC..."
```

`DINGTALK_ROBOT_WEBHOOK` remains supported for older local setups.

The message includes status, trigger source, short summary, up to three artifact
links, and a log path when available.

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

Jobs that would write back to DingTalk AI tables should use
`needs_confirmation` after analysis. The actual writeback should happen only
after manual confirmation.

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

Run a job through the provider runner:

```bash
bin/intelli-integration-job run \
  --job-type prepare-sprint-iteration \
  --trigger manual \
  --note "手动验证"
```

List schedules:

```bash
bin/intelli-integration-job list-schedules
```

If a job config has a `command`, the runner executes it, writes stdout/stderr to
`~/Library/Application Support/IntelliIntegrationAutomation/logs`, and stores the
log path in the run record. Without a command, the runner creates a
`needs_confirmation` record for manual/Codex execution.

Run the provider once:

```bash
STATUS_HUB_STATUS_FILE=/tmp/intelli-status.json bin/intelli-integration-provider --once
cat /tmp/intelli-status.json
```

Run as a daemon:

```bash
STATUS_HUB_STATUS_FILE=/tmp/intelli-status.json bin/intelli-integration-provider
```
