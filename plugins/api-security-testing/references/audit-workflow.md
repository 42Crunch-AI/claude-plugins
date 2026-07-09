# Audit Workflow

> **Command conventions used throughout this file**
> - `<binary>` — the full path resolved during binary discovery (e.g. `~/.42crunch/bin/42c-ast`). Never call `42c-ast` by name alone unless it is confirmed to be on PATH.
> - **Never write a literal credential value into a command.** Load credentials from the conf file into the environment first, then let the command inherit them — the raw value must never appear in a command string, tool output, or chat message.
> - **Platform mode**: before every command, load credentials with `set -a; . "$HOME/.42crunch/conf/env"; set +a`. The command then inherits `API_KEY`/`PLATFORM_HOST` — no explicit prefix needed.
> - **Token mode**: load `TRIAL_TOKEN` the same way, then add `--freemium-host stateless.42crunch.com:443` and `--token "$TRIAL_TOKEN"` to every command — never the literal token.
> - **Windows**: all command/extraction blocks in this file are macOS/Linux; use the PowerShell equivalents in `./windows-commands.md` (keyed by step), including its credential-loading convention.
> - **Score tracking**: `extract_audit.py` saves the first run's scores as a baseline and prints the before/after `score_change:` line on re-run — no manual score bookkeeping needed.

---

## Step 1 — Run the Audit

> **Token mode**: omit `--tag` and `--report-sqg` from all commands in this
> step. These flags require platform access and must not be used in token mode.

Resolve a platform-appropriate output directory and create it if it does not exist:

```bash
# macOS / Linux
OUTPUT_DIR=/tmp/42c-audit
mkdir -p "$OUTPUT_DIR"
```

*Windows:* `./windows-commands.md` → **Audit — Step 1**.

### Platform mode

```bash
set -a; . "$HOME/.42crunch/conf/env"; set +a
<binary> audit run \
  --enrich=false \
  --output "$OUTPUT_DIR/report.json" \
  --output-format json \
  --report-sqg \
  [--tag <category>:<tagname>] \   # include only when a tag is assigned
  <path-to-oas-file>
```

### Token mode

```bash
set -a; . "$HOME/.42crunch/conf/env"; set +a
<binary> audit run \
  --enrich=false \
  --freemium-host stateless.42crunch.com:443 \
  --token "$TRIAL_TOKEN" \
  --output "$OUTPUT_DIR/report.json" \
  --output-format json \
  <path-to-oas-file>
```

### Output files (written to the same directory as `--output`)

| File          | Contents                                                                                           |
|---------------|----------------------------------------------------------------------------------------------------|
| `report.json` | Audit results                                                                                      |
| `todo.json`   | Same as report.json but with `index[]` for OAS path resolution — **prefer this file**              |
| `sqg.json`    | SQG result — written in platform mode whenever `--report-sqg` is passed (with or without `--tag`). Not written in token mode. |

### Check the run result before proceeding

The command above also prints a top-level status object to stdout (already
visible — no extra capture needed): `{astVersion, logs, statusCode,
statusMessage}`. Check it before touching any output file:

- **`statusCode: 0` / `success`** → continue to Step 2.
- **`statusCode: 3` / `limits_reached`** (Token mode
  only) → the token plan has hit its usage limit. Follow `./token-limit.md` now.
  Do not proceed to Step 2 — `todo.json`/`report.json` were not written.
- **`statusMessage: unauthorized` / `forbidden`** → the API key or token was
  rejected (invalid, expired, or lacking access to this API/tag). Tell the user
  and suggest re-running `42crunch-setup`; do not retry with the same credentials.
- **`statusMessage: timeout`** → the platform was unreachable/slow — surface as
  a connectivity issue, not a spec error.
- **`statusCode: 2` / `unknown_error`** → malformed input **or an
  unsupported/misspelled flag** (the binary reports both this way). Re-check the
  command's flags first; if they are correct, treat as a malformed OAS and
  surface `statusMessage`.
- **Any other non-zero `statusCode`** → surface `statusMessage` to the user
  as an error and stop. Do not attempt to parse `todo.json`/`report.json`.

A re-run in Step 4 (after fixes are applied) is just this same command again
— apply this same check to that run too.

---

## Step 2 — Parse and Display the Audit Report

Parse `todo.json` (fall back to `report.json` if absent) and `sqg.json`. Then
render a **developer-readable, risk-classified report**. Do NOT surface raw
rule IDs — every issue type in the report carries its own `description` field
(e.g. `d["security"]["issues"][issue_id]["description"]`); use that as the
title. When an individual occurrence has a non-empty `specificDescription`,
append it for extra context (operation, method, property name) — it is often
absent or `""`, so always fall back to `description` alone.

> **Token rule**: never load raw JSON file contents into your response. Use the
> Python extraction below to pull only the fields you need (TOON output —
> https://github.com/toon-format/toon), then display the formatted output.
> Do **not** read `./audit-report-schema.md` unless an extraction snippet
> below fails or a field is unexpectedly missing — it is never needed to
> render findings, and reading it costs ~8k tokens.

### Score headline

**Platform mode** (`sqg.json` always present):
```
Audit Score: <score> / 100  |  Security: <sec-score>/30  |  Data Validation: <data-score>/70
SQG (<sqg-name>): PASSED / FAILED
```

**Token mode** (no `sqg.json`):
```
Audit Score: <score> / 100  |  Security: <sec-score>/30  |  Data Validation: <data-score>/70
```

**Platform mode** — score ≥ 90, add one interpretation line:
> `Your API scores in the top tier — excellent security posture.`
Otherwise omit the interpretation line; SQG PASSED/FAILED in the headline is the authoritative result.

**Platform mode only** — when the score crosses from below 70 to 70 or above after fixes are applied, add:
> `This improvement moves your API from failing to passing the SQG threshold.`

**Token mode only** — before rendering the findings report, prompt the user for session
thresholds (call `AskUserQuestion` with two questions):
- **Question 1**: `"What minimum score are you targeting for this API?"` — options:
  `["90+ — Excellent", "70 — Good baseline", "50 — Acceptable for now", "Custom — I'll enter a number"]`
  If "Custom" is chosen, call a follow-up `AskUserQuestion` for the numeric value.
- **Question 2**: `"What is the lowest severity you want treated as a blocking issue?"` — options:
  `["CRITICAL only", "HIGH and above", "MEDIUM and above", "All findings (including LOW)"]`

Map the severity choice to a numeric threshold: CRITICAL=4, HIGH=3, MEDIUM=2, LOW=1.
Store as `target_score` and `blocking_severity_threshold` for this session only — do not persist.

Then add one score interpretation line:
- Score ≥ 90: `Your API scores in the top tier — excellent security posture.`
- Score ≥ target and < 90: `Your API meets your target score. A few improvements could push it higher.`
- Score within 10 of target (but below): `Your API is approaching your target score — the blocking issues below are holding it back.`
- Score more than 10 below target: `Your API score is below your target. The issues below must be fixed.`

### Parsing reference

Run the bundled extractor — it prints a compact summary (scores, per-issue-type
TOON rows, SQG verdict) without loading the raw JSON into context. It also
records the scores in `$OUTPUT_DIR/.baseline.json` on the first run, so a
later re-run after fixes prints a `score_change:` line automatically.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/extract_audit.py" "$OUTPUT_DIR"
```

*Windows without python3:* `./windows-commands.md` → **Audit — Step 2**.

Output shape (all display and fix logic reads from this — never load raw
`todo.json`/`sqg.json` into your response):

```
score: <n>  security: <n>  data: <n>       # security/data omitted for GraphQL (single score)
openapi_state: fileInvalid|structureInvalid # printed INSTEAD of scores for an invalid spec
issues[N]{id,section,criticality,description,shown,total,truncated}:
  <issue-id>,<security|data|semanticErrors|warnings>,<crit>,<desc>,<shown>,<total>,<bool>
sqg_acceptance: yes|no                       # platform mode only
sqg_name: <name>
blocking_rules: <human-readable blocking reasons>
sqg_blocking_issue_ids: <id, id, ...>        # the issue IDs the SQG blocks on (platform, acceptance≠yes)
```

Field semantics for rendering and fix logic:
- `criticality`: 4=CRITICAL 3=HIGH 2=MEDIUM 1=LOW 0=INFO.
- `total` is the true occurrence count; `shown` is what the report lists
  (capped at `maxEntriesPerIssue`). `truncated=True` means `total > shown` —
  say so in the heading (`(showing <shown> of <total> locations)`) and expect
  more than one fix-and-re-audit cycle to clear that rule.
- **SQG-blocking issue IDs**: platform mode → the `sqg_blocking_issue_ids`
  line. Token mode → no SQG; treat an issue as blocking when its `criticality`
  ≥ the session `blocking_severity_threshold` from the score-headline prompt.
- `semanticErrors`/`warnings` are never SQG-blocking (no per-type criticality,
  outside the score).

**Resolve issue locations to OAS paths** only when you need them (the consent
gate and the Step 4 fix loop), by issue ID — this keeps location noise out of
context until it is actionable:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/extract_audit.py" "$OUTPUT_DIR" --locations <id>[,<id>...]
```

It prints each occurrence as a human-readable OAS path plus its
`specificDescription` (falling back to the issue description when that field is
empty, as it frequently is).

### Rendered format

Group issues into four tiers. Use each issue type's `description` as the title;
append a location's `specificDescription` (from `--locations`) only when it is
present and non-empty. When `truncated` is true, append `(showing <shown> of
<total> locations)` to its heading — never imply the listed locations are the
complete set.

```
── 🔴 SQG-Blocking Issues — must fix before scan can run ──────────────────

  1. <description>  [<SEVERITY>]  (showing <shown> of <total> locations)  ← only if truncated
     Where:  <OAS path from index>
     Risk:   <description>
     Fix:    <one-line description of the minimal change needed>

  2. ...

── 🟠 Security Issues (authentication · authorization · transport) ─────────
  (list issues from d["security"]["issues"] that are not SQG-blocking,
   same per-issue format; write "(none)" if empty)

── 🟡 Data Validation Issues (schemas · responses · parameters) ───────────
  (list issues from d["data"]["issues"] that are not SQG-blocking,
   same per-issue format)

── 🟣 Spec Conformance Issues (OAS format, not part of the audit score) ────
  (list issues from d["semanticErrors"]["issues"], same per-issue format;
   these make the OAS non-conformant with the OpenAPI Specification even
   though they don't affect the audit score or SQG; write "(none)" if absent)
```

Number issues sequentially across all four sections so the user can reference
them by number in their consent response.

After the four tiers, if `d["warnings"]` has any issue types, add one summary
line: `N recommendation(s) available (non-blocking, do not affect score) —
ask to see them if you want the detail.` Do not expand warnings by default;
they are frequently in the hundreds and would drown out actionable findings.

---

## Step 3 — Consent Gate

After rendering the report, call `AskUserQuestion`:
- **question**: `"I found N SQG-blocking issue(s) (🔴) that must be fixed to pass the SQG, plus M additional finding(s) across Security, Data Validation, and Spec Conformance for your information (recommendations are not counted here — see the summary line). For the blocking issues I propose the following changes to <filename>: 1. [issue title] → [one-line fix description] 2. ... What would you like to do?"`
- **options**: `["Yes — apply all fixes now", "Show me the diff first", "No — skip fixes for now"]`

If the user chooses **"Show me the diff first"**, display the proposed change for each
issue one at a time in unified diff format, then call `AskUserQuestion`:
- **question**: `"Apply this change?"` — **options**: `["Yes", "No — skip this one"]`

Only advance to the next fix after the user confirms the current one.

Do **not** offer to fix non-blocking issues at this stage — only the 🔴 items.
Only proceed to Step 4 after the user explicitly confirms.

When a 🔴 issue is truncated (`truncated` is true), say so explicitly in the
consent question, e.g. `"...this affects 1016 locations; I'll fix the 30
shown here, then we'll re-run the audit to catch the rest."` Set expectations
that Step 4 may need more than one fix-and-re-audit cycle before this issue
clears the SQG.

**API-first vs code-first — per-issue handling:**
For findings that represent a **spec/implementation mismatch** (e.g. `additionalproperties-true`
where the server actually returns those fields, HTTP vs HTTPS in `servers`, undocumented security
schemes, or response bodies wider than the schema), do **not** assume the OAS is the source of
truth. Instead, present the choice explicitly before applying the fix:
- Call `AskUserQuestion`:
  - **question**: `"For [issue title] at [OAS path]: the spec and implementation disagree. Which should be the source of truth?"` — options: `["Fix the OAS to match the implementation", "Fix the implementation to match the OAS", "Skip this one"]`
- Apply the fix in whichever direction the user chooses.
- Pure security issues (missing patterns, unbounded arrays, undocumented 403/429 responses, etc.)
  that have no implementation-side equivalent do not need this prompt — just propose the OAS fix.

---

## Step 4 — Context-Aware Fix Analysis

For each SQG-blocking issue the user has approved:

1. Locate the issue's occurrences with
   `extract_audit.py "$OUTPUT_DIR" --locations <id>` (Step 2) to get the
   human-readable OAS paths.
2. Read the structural context in the OAS file at each path: the operation,
   request/response schema, security requirements, or parameter definition.
3. Apply the minimum correct fix required to resolve the blocking rule. Do not
   make speculative or cosmetic changes — only fix what is explicitly blocking
   SQG acceptance.

If an issue was `truncated` (more locations exist than were shown), fixing the
listed locations does not clear the rule — the remaining, unseen occurrences
still block SQG. Treat this as expected and plan to repeat fix-and-re-audit
until `total` for that rule reaches `0`, rather than treating the first pass as
failed.

After all fixes are applied, re-run the audit (**Step 1**) and re-run
`extract_audit.py` to confirm the SQG now passes:
- **Platform mode**: confirm `sqg_acceptance: yes`.
- **Token mode**: confirm the new score meets `target_score` and no issues
  with criticality ≥ `blocking_severity_threshold` remain.
- If a previously blocking issue still has occurrences after a fix cycle
  (`total > 0` for that rule ID), repeat Steps 3–4 for the remaining locations
  before declaring it resolved.

The re-run's `extract_audit.py` output includes a `score_change:` line
(computed against the baseline saved on the first run) — use it verbatim for
the final summary's before/after comparison. Omit the score-change line only
when no fixes were applied (user declined at the consent gate, or there were no
SQG-blocking issues).

---

## Flags Reference

```
--output-format json|yaml     output format (default json)
--output <file>               write report to file instead of stdout
--report-sqg                  include sqg_pass in the report
--tag <category>:<tagname>    apply platform tag
--max-impacted-issues <n>     limit reported impacted issues (default 30)
--max-origin-issues <n>       limit reported origin issues (default 30)
```
