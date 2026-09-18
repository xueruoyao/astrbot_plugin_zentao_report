# ZenTao Report: WeCom Agent Integration and Delivery Plan

## 1. Current Implementation Inventory

Plugin directory:

```text
AstrBot/data/plugins/astrbot_plugin_zentao_report
```

Implemented now:

- ZenTao API v1 read client.
- API Token support, with account/password Token exchange fallback.
- Product and project scope discovery.
- Product and project defect pagination with `status=all`.
- Project scope identity preservation: a project remains its project ID even when ZenTao bug objects expose an underlying product ID.
- Basic aggregate report data: unresolved, active, resolved/closed, S1/S2 risk, scope counts, and high-risk list.
- Jinja2 `1080 x 1920` phone-ratio report HTML.
- AstrBot HTML renderer path and Pillow fallback path.
- `/zentao_report preview` and `/zentao_report status` prototype commands.
- Unit tests for scope parsing and report aggregation.

Not implemented now:

- WeCom Agent configuration or connection.
- WeCom text delivery.
- WeCom image delivery.
- Push Webhook configuration.
- Scheduled daily or weekly jobs.
- `/bug_report` command group from `DESIGN.md`.
- Hot-project, module-ranking, submitter, trend, weekly, AI-summary, and review-list calculations.
- Persisted runtime configuration, delivery history, retries, or administrative authorization.

The current plugin is preview-only and must remain push-disabled until the delivery tests below pass.

## 2. Platform Compatibility Check

The local AstrBot source contains an older WeCom adapter configuration:

```text
corpid
secret
token
encoding_aes_key
```

Its source implementation sends text/image replies to the source user session. It does not establish the newer proactive WeCom smart-robot push Webhook capability described in AstrBot `v4.15.0+` documentation.

Before implementing proactive group delivery:

1. Confirm the deployed AstrBot version is `>= 4.15.0`.
2. Upgrade the server only through the normal AstrBot upgrade procedure, not by copying this local legacy source tree over the running service.
3. Confirm the deployment exposes the documented WeCom smart-robot Agent configuration and optional message-push Webhook field.
4. Confirm that text and image message components sent by the active AstrBot platform adapter use the configured push Webhook for proactive group delivery.

The plugin must depend on AstrBot's documented send abstraction. It must not directly reverse engineer, imitate, or persist an enterprise WeCom OAuth user session.

## 3. Credential and Configuration Model

### WeCom Agent Configuration

Create a dedicated WeCom Agent / smart robot for report delivery. Keep its identity separate from personal accounts and from ZenTao credentials.

AstrBot platform configuration owns:

```text
WeCom Corp ID
WeCom Agent / robot Secret
Callback Token
Encoding AES Key
Optional proactive message-push Webhook URL
```

Plugin configuration owns only report behavior:

```text
zentao_base_url
zentao_account or zentao_token
scope_project_ids
scope_product_ids
report_title
timezone
daily_schedule
weekly_schedule
enabled_sections
push_enabled
target_session_or_group
```

Rules:

- Never copy WeCom Agent secret or push Webhook URL into plugin source, report template, test fixture, report image, or log output.
- `push_enabled` defaults to `false`.
- A configured Webhook alone must never start scheduled delivery.
- Status output shows only `configured` / `not configured`, never URL fragments or token fragments.
- Use a dedicated ZenTao read-only report account or a scoped API Token.

## 4. Server-to-Agent Connection Procedure

### Step 1: Prepare the Server Network Boundary

The report runner needs both WeCom access and ZenTao access.

ZenTao readiness checks from the report server:

```bash
getent ahostsv4 zentao.example.com

curl --noproxy '*' -sS -I \
  --connect-timeout 10 --max-time 20 \
  'https://zentao.example.com/bug-view-1432.html'

curl --noproxy '*' -sS -D - -o /dev/null \
  --connect-timeout 10 --max-time 20 \
  'https://zentao.example.com/api.php/v1/bugs/1432'
```

Expected boundary results:

```text
Page: 302 Found
API without ZenTao Token: 401 Authorization Required
```

Those results prove DNS, IP allowlisting, TLS, and API routing. They do not prove ZenTao account authorization.

### Step 2: Create and Configure the WeCom Agent

1. Create the Agent / smart robot in the WeCom admin console.
2. Configure the callback endpoint required by the active AstrBot WeCom adapter.
3. Configure callback Token and Encoding AES Key in AstrBot platform configuration.
4. Create a push robot in the destination internal group through group settings -> message push.
5. Store the generated push Webhook URL in the AstrBot platform's documented push-WebHook configuration, not in the plugin code.
6. Restart or reload the AstrBot WeCom platform adapter using AstrBot's supported lifecycle.

### Step 3: Check Agent Health

The future command:

```text
/bug_report health
```

must validate and report these fields without revealing secrets:

```text
WeCom adapter loaded
WeCom Agent credential configured
Proactive push Webhook configured
ZenTao hostname resolves
ZenTao page boundary is 302
ZenTao API boundary is 401 before API auth
ZenTao read credentials configured
HTML renderer available or Pillow fallback available
Daily schedule enabled/disabled
Push enabled/disabled
```

## 5. Delivery Test Sequence

Push must be implemented and tested in this exact order. No scheduled job is enabled during these tests.

### Test A: Agent Receives an Inbound Message

1. Send a plain message to the WeCom Agent from an authorized internal account.
2. Confirm AstrBot logs one inbound WeCom event.
3. Run a harmless command such as `/bug_report status`.
4. Confirm the Agent returns a text reply to the initiating account.

Pass condition:

```text
Inbound WeCom -> AstrBot -> text reply works.
```

### Test B: Proactive Group Text Message

Implementation target: a temporary administrator-only command, removed or restricted after validation.

```text
/bug_report test text
```

Expected payload content:

```text
[TEST ONLY] ZenTao report delivery channel is reachable.
```

Pass condition:

```text
The target WeCom internal group receives exactly one text message.
```

Failure classification:

- No group message and no platform error: target session/group mapping is incorrect.
- Agent replies in private chat but group has no proactive message: push Webhook is missing or unsupported by the installed AstrBot version.
- `400` / credential error: Agent Secret or platform configuration is invalid.
- Image-only failure after text success: media upload/send capability mismatch.

### Test C: Proactive Group Image Message

Implementation target:

```text
/bug_report test image
```

Use a static generated PNG containing only:

```text
ZenTao Report
Image delivery test
No production data
```

Pass condition:

```text
The target group receives one rendered PNG, not a file path, broken URL, or empty card.
```

The test must verify the active AstrBot WeCom transport handles media upload / image conversion. The plugin passes an image component/path to AstrBot; the plugin does not manually expose WeCom tokens.

### Test D: ZenTao Preview, No Delivery

```text
/bug_report preview
```

Pass condition:

- Image contains real ZenTao report data.
- No group message is sent.
- No Webhook call occurs.
- Image contains no password, Token, Webhook, raw API response, or unredacted action payload.

### Test E: One Explicit End-to-End Send

Only after A-D pass and an administrator turns on `push_enabled`:

```text
/bug_report send --confirm
```

Pass condition:

- One text summary and one report image arrive in the target group.
- Delivery record stores time, report hash, recipient identifier, transport response state, and no secret.
- A second send is not triggered accidentally by command retry or renderer retry.

### Test F: Scheduled Dry Run

Configure a one-time test schedule five minutes in the future with delivery still disabled:

```text
/bug_report schedule once YYYY-MM-DD HH:MM --dry-run
```

Pass condition:

- Scheduler runs once.
- Report is generated and delivery is explicitly skipped.
- Log records `dry_run` rather than `sent`.

### Test G: Scheduled Production Send

Enable daily schedule only after all previous tests pass:

```text
/bug_report schedule daily 18:30
/bug_report push enable --confirm
```

Pass condition:

- Exactly one text and one image report arrive at the configured time.
- The report cutoff time matches generation time.
- Failure sends no partial duplicate image; it records a retryable failure state.

## 6. Implementation Roadmap

### Phase 1: Refactor Existing Preview Core

1. Move report data collection, aggregation, and rendering to isolated modules.
2. Preserve current preview-only behavior.
3. Add a configuration persistence layer through AstrBot-supported plugin configuration/state storage.
4. Rename the public interface to the designed `/bug_report` command group while keeping `/zentao_report` as a temporary alias.
5. Add `/bug_report health` and `/bug_report status` before any sending capability.

### Phase 2: Complete Daily Data Model

Implement the image sections in this order:

1. Headline metrics.
2. Hot projects.
3. Hot project module defect ranking.
4. Today-created and today-resolved delta.
5. Same-day submitter ranking.
6. High-risk attention list.
7. Pending review queue.
8. Optional AI factual summary.

The report must calculate a single cutoff timestamp once at the beginning. Every API read and every section uses that same cutoff.

### Phase 3: Interactive Drilldown

Implement:

```text
/bug_report review PROJECT
/bug_report review PROJECT MODULE
```

The compact result includes title, direct ZenTao link, assignee, status, resolved timestamp, and review reason. It uses a 20-item page limit and explicit remaining count.

### Phase 4: Schedules and Image Sections

Implement configuration commands:

```text
/bug_report schedule show
/bug_report schedule daily HH:MM
/bug_report schedule weekly DAY HH:MM
/bug_report sections
/bug_report sections set SECTION on|off
```

Schedules generate reports but still do not send until Phase 5 turns on the transport switch.

### Phase 5: WeCom Transport

1. Add `push_enabled=false` by default.
2. Implement administrator-only `/bug_report test text`.
3. Implement administrator-only `/bug_report test image`.
4. Implement manual `/bug_report send --confirm`.
5. Implement scheduled delivery after tests A-G.
6. Add delivery history, redacted errors, idempotency key, and retry policy.

### Phase 6: Trend and Weekly Report

Implement a small persisted report snapshot store. It contains only aggregates and report metadata, not full raw bug responses.

Then add:

```text
/bug_report weekly_preview
```

Weekly content:

- 7-day and 14-day created/resolved/closed/reopened/net-backlog trend.
- Hot-project movement.
- Weekly submitter distribution.
- Reopened and pending-review summary.
- Next-week S1/S2 and aging risk list.

## 7. Test Matrix for Functional Requirements

| Requirement | Test Method | Expected Result |
| --- | --- | --- |
| Hot projects | Fixture and live read-only preview | Ranking follows unresolved/risk score. |
| Totals | Fixture assertion | Total = closed + all non-closed statuses. |
| Module ranking | Project fixture with multiple modules | Ranking counts unresolved defects per module. |
| Daily submitters | Fixed date fixture | Only cutoff-day opened records count. |
| Pending review | Resolved/reopened/comment-after-resolution fixture | Each rule produces the expected reason. |
| AI summary | Mock provider and provider failure | Factual summary or deterministic fallback. |
| 7/14 day trend | Stored aggregate snapshots | Dates, deltas, and missing days are correct. |
| Text push | WeCom test group | Exactly one test text message. |
| Image push | WeCom test group | Exactly one valid PNG. |
| Scheduler | One-time dry-run then controlled send | No delivery in dry-run; one delivery in enabled run. |
| Secret safety | Log and config-output scan | No Token, password, Secret, or Webhook output. |

## 8. Rollout Gates

Do not move to the next gate until the current one passes:

```text
Gate 0: server DNS/IP allowlist/API boundary healthy
Gate 1: WeCom Agent inbound reply healthy
Gate 2: proactive group text healthy
Gate 3: proactive group image healthy
Gate 4: real ZenTao image preview correct and no push
Gate 5: one confirmed manual send
Gate 6: one-time scheduled dry-run
Gate 7: daily push enabled
Gate 8: weekly and trend features enabled
```
