# ZenTao Daily Report Design

## Goal

Generate one concise end-of-day ZenTao defect report for a WeCom group. The report is a phone-first image that lets a team understand remaining work, current risk, and ownership in under a minute before leaving work.

The first release is intentionally a read-only report generator. It does not mutate ZenTao data. Transport is separated from reporting so the same generated image can be previewed in AstrBot, sent by a group Webhook, or archived later without changing data collection or rendering.

## Current Scope

### Required Report Content

- Report date and data cutoff time.
- Hot projects: rank selected projects by unresolved defect count and risk score.
- Total defects in the selected scope.
- Closed defect count.
- Unclosed defect count.
- Active and resolved counts for interpretation of work in progress.
- Hot project module ranking: unresolved defects grouped by module for each hot project.
- Same-day submissions: submitter name and submission count.
- Highest priority unresolved defects: S1/S2 first, then priority and recent activity.
- AI summary: short operational summary with explicitly structured input and a graceful fallback when AI is unavailable.

### First Image Layout

Canvas: `1080 x 1920` PNG, optimized for a mobile screen and WeCom group timeline.

1. Header: report title, date, scope, generated time.
2. Top metrics: total, closed, unresolved, high risk.
3. Hot projects: ranked compact bars with unresolved and risk counts.
4. Module ranking: top modules for the hottest project, or a compact project-module matrix when space permits.
5. Today: submitter leaderboard and today-created / today-resolved delta.
6. Attention list: at most five defect titles with ID, owner, status, severity, and reason.
7. AI summary: three to five factual bullets. It must cite computed values and never invent a resolution status or assignee.
8. Footer: data source, scope count, generation mode, and report version.

## Bot Control Surface

The report is not only a scheduled push. AstrBot is the interactive control plane for operators who need to inspect data, change report composition, and drill into review work without opening ZenTao first.

### Core Commands

All commands use the `bug_report` command group. Command results are read-only unless explicitly marked as configuration changes.

| Command | Purpose | Output |
| --- | --- | --- |
| `/bug_report health` | Check ZenTao DNS, network boundary, API authentication readiness, renderer availability, schedule state, and push configuration state. | Plain diagnostic with secrets redacted. |
| `/bug_report status` | Show the active report configuration and latest generation / delivery state. | Plain configuration summary and last run metadata. |
| `/bug_report preview` | Generate the current daily report image without delivering it. | Current `1080 x 1920` PNG preview. |
| `/bug_report weekly_preview` | Generate the weekly trend report without delivering it. | Weekly PNG preview. |
| `/bug_report schedule show` | Show the configured timezone, workday rule, daily report time, and weekly report time. | Plain schedule summary. |
| `/bug_report schedule daily HH:MM` | Set the daily report time in the configured timezone. | Confirmation only; no immediate push. |
| `/bug_report schedule weekly DAY HH:MM` | Set the weekly report day and time. | Confirmation only; no immediate push. |
| `/bug_report sections` | Show all report-image section switches. | Plain on/off matrix. |
| `/bug_report sections set SECTION on|off` | Enable or disable one report-image section. | Confirmation and effective section matrix. |
| `/bug_report review PROJECT` | List pending review defects for one project. | Compact list: title, ZenTao link, assignee, status, resolved date. |
| `/bug_report review PROJECT MODULE` | List pending review defects for one module in a project. | Same compact list, filtered by module. |

The command parser should accept project/module ID or an exact configured display name. When a name is ambiguous, it must return candidate IDs rather than guessing.

### Report Image Section Switches

The following switches are independently configurable and default to the first-release requirements:

- `headline_metrics`: total, closed, unresolved, active, resolved, high-risk.
- `hot_projects`: project heat ranking.
- `module_ranking`: module defect concentration for hot projects.
- `daily_submitters`: same-day submitter leaderboard.
- `daily_delta`: today-created, today-resolved, today-closed, backlog delta.
- `attention_list`: highest-risk unresolved defects.
- `review_queue`: pending verification and reopened defects.
- `trend_7d`: seven-day created/resolved/closed/reopened/net-backlog trend.
- `trend_14d`: fourteen-day trend; intended for weekly report by default.
- `ai_summary`: optional AI factual summary.
- `footer`: data source, cutoff time, scope, and report version.

Changing a section affects future previews and scheduled reports. It does not send a message and does not mutate ZenTao.

### Pending Review Definition

A defect is in the pending-review list when one of the following is true:

- Status is `resolved` and it has not been closed.
- An action marks it reopened or activated after a resolution.
- A comment/action exists after the recorded resolution time.

Each item shows only the operational minimum:

```text
#ID Title
ZenTao link
Assignee
Status / resolved time / review reason
```

The list is paged and capped. The default maximum is 20 items per command response; the response includes an explicit truncated count and a link or follow-up command for the remaining items.

## Data Boundary

### ZenTao Read APIs

- `POST /api.php/v1/tokens` only when no API Token is configured.
- `GET /api.php/v1/products`.
- `GET /api.php/v1/projects`.
- `GET /api.php/v1/products/:id/bugs?status=all`.
- `GET /api.php/v1/projects/:id/bugs?status=all`.
- `GET /api.php/v1/bugs/:id` only for a bounded attention list when action history is needed.

All list reads paginate until the server `total` is reached or a short page occurs. The reporter must not describe a partial page as complete data.

### Scope Semantics

- Products and projects are both reportable scopes.
- A project uses its project ID as the internal report scope even if returned bugs carry an underlying product ID.
- Project and product labels must stay visually distinct, for example `项目 · 509`.
- Deleted scopes and deleted defects are excluded.
- Closed means `closed`; unresolved means any other status. `resolved` is shown separately because it awaits validation.

## Delivery Modes

### Preview Mode

AstrBot command creates a temporary PNG and returns it in the invoking session. This is safe for template and data verification.

### Scheduled Webhook Mode

Future scheduled mode runs outside the report core:

1. Generate the same report image.
2. Send a text summary and image through the configured WeCom push Webhook.
3. Record a redacted result: time, report hash, status, and response code.

The current implementation must keep push disabled by default. A Webhook URL is a secret and must never be rendered, logged, returned by a status command, or committed.

### Manual Send Mode

Future command creates a fresh report and sends it only when an explicit administrator command is issued. It must use the same sender as scheduled mode and must not bypass the push safety switch.

## Network Preconditions

- The runner must resolve `zentao.example.com` through persistent public DNS configuration.
- The runner public egress IP must be registered with the company navigation IP allowlist before ZenTao access.
- A page request returning `302` and an unauthenticated API request returning `401` are healthy network-boundary checks.
- The runner uses a dedicated read-only ZenTao account or configured API Token.
- OAuth/IP allowlist automation is infrastructure responsibility, not report-template logic. The report plugin only calls ZenTao after the network boundary is ready.

## Security

- Do not store personal ZenTao credentials in source, templates, screenshots, reports, or logs.
- Prefer a dedicated report account with read-only scope.
- Keep Webhook URLs and API tokens in AstrBot secret configuration or server environment variables.
- Redact secrets from exceptions and status output.
- The report is read-only: no defect edit, assignment, comment, resolve, close, or delete capability.

## Common Follow-Up Functions

These are candidates for later iterations, ordered by typical value.

### High Value

- Daily trend: created, resolved, closed, reopened, and net backlog change over 7/14 days.
- Ownership pressure: unresolved and high-risk counts per assignee, including unassigned defects.
- Aging SLA: defects open for 3, 7, 14, and 30+ days; highlight overdue deadlines.
- Reopen quality: reopen rate by project, module, assignee, and resolved build.
- Verification queue: resolved defects with no verification action after a configurable number of days.
- Duplicate and recurring defects: group by duplicate reference, title similarity, or module/type.
- Seven-day trend: created, resolved, closed, reopened, net backlog, and high-risk backlog.
- Fourteen-day trend: same dimensions with a compact day-by-day comparison for the weekly report.

### Project Management

- Release quality snapshot: defects by version/build, resolved build, and pre-release blocker count.
- Module heatmap: module x severity matrix with week-over-week movement.
- Test workload: submitter distribution, confirmation lag, and resolution cycle time.
- Product/project comparison: backlog size, aging, severity mix, and closure rate.
- Weekly digest: five-day trend with top improvements and regressions.
- Weekly report: 7/14 day trends, weekly submitter distribution, hot project changes, reopened defects, and a compact next-week risk list.

### Notification Controls

- Workday schedule, timezone, and holiday calendar.
- Separate recipients for full report, high-risk alert, and weekly digest.
- Send only when thresholds are crossed, such as new S1, backlog increase, or overdue count increase.
- Manual preview and manual send with report hash for auditability.
- Delivery history with a redacted error reason and retry action.
- Daily and weekly schedules are configuration only until push is explicitly enabled.

### AI Assistance

- AI factual summary based only on structured aggregate data.
- AI change narrative comparing current report to previous successful report.
- AI risk explanation that must quote the exact defects/counts used as evidence.
- AI summary review mode: generate draft only; do not automatically make management claims.

AI output must remain optional. Report generation and webhook delivery cannot depend on an LLM being available.

## Non-Goals

- Replacing ZenTao’s full project management UI.
- Automating defect mutations.
- Scraping authenticated ZenTao HTML pages.
- Coupling the report service to company CI/CD.
- Sending any report while preview-only mode is enabled.

## Acceptance Criteria

- One report image fits a `1080 x 1920` phone canvas without truncating the required content.
- It clearly identifies hot projects, unresolved backlog, closed count, module concentration, daily submitters, and high-risk items.
- Every metric is traceable to ZenTao API data.
- Missing AI, missing font, or failed optional image rendering does not prevent a plain factual report from being created.
- Push requires both an explicit enable flag and a configured secret Webhook URL.
- `/bug_report health`, `/bug_report status`, `/bug_report preview`, schedule configuration, section configuration, and project/module pending-review lookup are available without a Webhook URL.
- Pending-review lookup returns title, direct ZenTao link, assignee, and review reason without exposing credentials or private API payloads.
