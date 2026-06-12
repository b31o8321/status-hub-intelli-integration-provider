# status-hub-intelli-integration-provider

Status Hub provider plugin for Shulex Intelli integration-project automation.

This repository is intentionally separate from `status-hub`. Status Hub installs
the plugin from GitHub, starts the provider command, and reads the generated
status JSON. The provider stores job run records locally so scheduled jobs,
Codex skills, or manual scripts can report progress without being built into the
Hub app.

## Features

The provider exposes three Intelli integration work streams:

- Sprint demand preparation: collect integration-related demand candidates,
  manual demand notes, point estimates, priorities, sprint document links, and
  demand-pool status items that may need human-confirmed sync. The generated
  demand document must include source reference links for every candidate row so
  reviewers can jump back to the original table, record, log query, or code path.
- Daily feedback defect triage: group only integration-project related daily
  feedback defects by integration module and assign owners for investigation.
  This daily job also checks in-progress integration requirements planned for
  the current week and reminds owners to update progress or report blockers.
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
| Daily feedback defect triage | Weekdays 10:30 | Run the Codex skill, create/update the daily feedback and progress document, then send a summary DingTalk reminder when notification is enabled |
| Sprint demand preparation | Friday 10:00 | Run the Codex skill and create/update the next-sprint demand document |
| Production log analysis | Disabled by default | Manual trigger only |

The scheduler uses the `schedules` array in
`config/intelli-integration-workflow.json`. It supports standard 5-field cron
expressions: `minute hour day month weekday`.

Scheduled runs and manual Status Hub triggers use the same provider runner. When
a job config provides `command`, the runner executes that command and records the
returned result. The built-in commands call the local Codex CLI.

Schedules can be enabled or disabled without editing the plugin repository:

```bash
bin/intelli-integration-job set-schedule \
  --job-type daily-feedback-defect-triage \
  --enabled false
```

Status Hub renders provider item actions, so each job can be manually triggered
from the provider detail page and its schedule can be turned on or off there.

## Codex Execution Protocol

The provider executes jobs through:

```text
bin/intelli-run-codex-job
```

The script calls local `codex exec` in the `shulex-intelli` workspace and asks
Codex to run the configured skill. Requirements:

- The local `codex` CLI must be installed and signed in.
- DingTalk MCP access must be available to Codex when a job needs to create or
  update DingTalk documents.
- `CODEX_BIN` can override the Codex binary path.
- `INTELLI_CODEX_WORKDIR` can override the workspace passed to `codex exec`.

Codex must return a fixed JSON object as its final message. The provider parses
that JSON, writes the run record, exposes document links to Status Hub, and sends
DingTalk robot notifications according to local notification settings.

For `prepare-sprint-iteration`, the DingTalk demand document created by Codex
must include a `参考源链接` column in the P0/P1/P2 demand tables and related
modules. When a DingTalk AI Table row has no separate row URL, use the source
table/view link plus the recordId or requirement number.

Expected final-message JSON:

```json
{
  "status": "success",
  "summary": "缺陷反馈 12 条，聚类 4 个；本周进行中集成需求 3 个，提醒 2 位 Owner。",
  "sprint": "Sprint 202606 15 - 19",
  "artifacts": [
    {
      "title": "每日反馈与进度提醒 2026-06-11",
      "url": "https://alidocs.dingtalk.com/i/nodes/..."
    }
  ],
  "notificationMarkdown": "### Intelli 每日反馈与进度提醒\n...",
  "notifyAtUserIds": ["17786332925024466"],
  "note": "人工确认前不写回 AI 表格。"
}
```

## DingTalk Robot Notifications

The provider can send a DingTalk robot markdown message when a run finishes.
By default only these job types are selected for notifications:

- `daily-feedback-defect-triage`

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
    "secret": "SEC...",
    "userDisplayNames": {
      "17417778857341994": "许嘉凯"
    }
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

The default message includes status, trigger source, short summary, up to three
artifact links, and a log path when available. Run records may also provide
`notificationMarkdown` and `notifyAtUserIds`; in that case the provider sends
the custom markdown summary and mentions the listed DingTalk users.

`notificationMarkdown` should display human-readable names, while
`notifyAtUserIds` triggers the actual DingTalk mentions. The optional
`userDisplayNames` mapping is a fallback that rewrites visible `@userId` text to
names before sending.

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
  "runId": "20260611-103000-daily-feedback-defect-triage",
  "jobType": "daily-feedback-defect-triage",
  "status": "success",
  "trigger": "scheduled",
  "startedAt": "2026-06-11T10:30:00+08:00",
  "finishedAt": "2026-06-11T10:36:42+08:00",
  "sprint": "Sprint 202606 15 - 19",
  "summary": "分析缺陷反馈 18 条，生成 5 个模块处理项",
  "artifacts": [
    {
      "title": "每日缺陷反馈分析",
      "url": "https://alidocs.dingtalk.com/i/nodes/..."
    }
  ],
  "logPath": "/Users/norman/Library/Application Support/IntelliIntegrationAutomation/logs/example.log",
  "notificationMarkdown": "### Intelli 每日反馈与进度提醒\n...",
  "notifyAtUserIds": ["17786332925024466"],
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

Use `needs_confirmation` only when the run genuinely needs a human decision
before it can be considered complete. A job that successfully creates/updates
documents and prepares optional notification content should return `success`.

## Recording Runs

For local testing or manual integration:

```bash
bin/intelli-integration-job record \
  --job-type daily-feedback-defect-triage \
  --status success \
  --summary "缺陷反馈 12 条，聚类 4 个；本周进行中集成需求 3 个，提醒 2 位 Owner。" \
  --artifact-title "每日反馈与进度提醒 2026-06-11" \
  --artifact-url "https://alidocs.dingtalk.com/i/nodes/..." \
  --notification-markdown "### Intelli 每日反馈与进度提醒 2026-06-11\n..." \
  --notify-at-user-ids "17786332925024466,17417778857341994" \
  --send-notification
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
`~/Library/Application Support/IntelliIntegrationAutomation/logs`, parses the
fixed JSON result, and stores the log path in the run record. Without a command,
the runner creates a `needs_confirmation` record.

Run the provider once:

```bash
STATUS_HUB_STATUS_FILE=/tmp/intelli-status.json bin/intelli-integration-provider --once
cat /tmp/intelli-status.json
```

Run as a daemon:

```bash
STATUS_HUB_STATUS_FILE=/tmp/intelli-status.json bin/intelli-integration-provider
```
