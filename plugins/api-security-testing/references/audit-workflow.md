# Audit Workflow

> **Command conventions used throughout this file**
> - `<binary>` — the full path resolved during binary discovery (e.g. `~/.42crunch/bin/42c-ast`). Never call `42c-ast` by name alone unless it is confirmed to be on PATH.
> - **Never write a literal credential value into a command.** Load credentials from the conf file into the environment first, then let the command inherit them — the raw value must never appear in a command string, tool output, or chat message.
> - **Platform mode**: before every command, load credentials — macOS/Linux: `set -a; . "$HOME/.42crunch/conf/env"; set +a`; Windows: `Get-Content "$env:APPDATA\42Crunch\conf\env" | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }`. The command then inherits `API_KEY`/`PLATFORM_HOST` — no explicit prefix needed.
> - **Token mode**: load `TRIAL_TOKEN` the same way, then add `--freemium-host stateless.42crunch.com:443` and `--token "$TRIAL_TOKEN"` (macOS/Linux) or `--token $env:TRIAL_TOKEN` (Windows) to every command — never the literal token.
> - **Score tracking**: record `initial_score`, `initial_sec_score`, and `initial_data_score` immediately after the first parse (Step 2). These are used to build the before/after comparison in the final summary.

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

```powershell
# Windows
$OUTPUT_DIR = "$env:TEMP\42c-audit"
New-Item -ItemType Directory -Force -Path $OUTPUT_DIR | Out-Null
```

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

- **`statusCode: 0`** → continue to Step 2.
- **`statusCode: 3` and `statusMessage: limits_reached`** (Token mode
  only) → the token plan has hit its usage limit. Follow `./token-limit.md` now.
  Do not proceed to Step 2 — `todo.json`/`report.json` were not written.
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

Extract only the needed fields — do not read the raw file into context.

> **Platform note**: macOS/Linux use the Python snippets below. Windows users
> should use the PowerShell equivalents that follow.

**macOS / Linux (Python)**

```bash
python3 << 'EOF'
import json, os, sys

with open("$OUTPUT_DIR/todo.json") as f:
    d = json.load(f)

state = d["openapiState"]

# fileInvalid/structureInvalid reports carry no score or security/data
# sections at all — handle them before touching anything else.
if state == "fileInvalid":
    errors = [k for k, v in d["errors"].items() if v]
    print(f"openapi_state: fileInvalid")
    print(f"file_errors: {', '.join(errors) if errors else '(unspecified)'}")
    sys.exit(0)
if state == "structureInvalid":
    print(f"openapi_state: structureInvalid")
    print(f"structural_issue_count: {d['issueCounter']}")
    sys.exit(0)

score      = d["score"]
sec_score  = d["security"]["score"]
data_score = d["data"]["score"]
print(f"score: {score}  security: {sec_score}  data: {data_score}")

# Collect issues as TOON. "semanticErrors"/"warnings" use totalIssues,
# "security"/"data" use issueCounter — that field is the true total;
# len(issues) is only what's shown (capped at maxEntriesPerIssue).
issues = []
for section in ["semanticErrors", "warnings", "security", "data"]:
    section_data = d.get(section)
    if not section_data:
        continue
    for issue_id, issue_data in section_data["issues"].items():
        crit      = issue_data.get("criticality", 0)
        desc      = issue_data["description"]
        shown     = len(issue_data.get("issues", []))
        total     = issue_data.get("issueCounter", issue_data.get("totalIssues", shown))
        truncated = issue_data.get("tooManyError", False)
        issues.append((issue_id, section, crit, desc, shown, total, truncated))

if issues:
    print(f"\nissues[{len(issues)}]{{id,section,criticality,description,shown,total,truncated}}:")
    for issue_id, section, crit, desc, shown, total, truncated in issues:
        print(f"  {issue_id},{section},{crit},{desc},{shown},{total},{truncated}")

# sqg.json (platform mode only — file is absent in token mode)
if os.path.exists("$OUTPUT_DIR/sqg.json"):
    with open("$OUTPUT_DIR/sqg.json") as f:
        sqg = json.load(f)
    print(f"sqg_acceptance: {sqg['acceptance']}")
    print(f"sqg_name: {sqg['sqgsDetail'][0]['name']}")
    blocking = [r for pd in sqg.get("processingDetails", []) for r in pd.get("blockingRules", [])]
    if blocking:
        print(f"blocking_rules: {', '.join(blocking)}")
EOF
```

**Windows (PowerShell)**

```powershell
$d = Get-Content "$OUTPUT_DIR\todo.json" | ConvertFrom-Json
$state = $d.openapiState

# fileInvalid/structureInvalid reports carry no score or security/data
# sections at all — handle them before touching anything else.
if ($state -eq "fileInvalid") {
    $fileErrors = ($d.errors.PSObject.Properties | Where-Object { $_.Value } | ForEach-Object { $_.Name })
    Write-Host "openapi_state: fileInvalid"
    Write-Host "file_errors: $(if ($fileErrors) { $fileErrors -join ', ' } else { '(unspecified)' })"
    exit
}
if ($state -eq "structureInvalid") {
    Write-Host "openapi_state: structureInvalid"
    Write-Host "structural_issue_count: $($d.issueCounter)"
    exit
}

$score     = $d.score
$secScore  = $d.security.score
$dataScore = $d.data.score
Write-Host "score: $score  security: $secScore  data: $dataScore"

# "semanticErrors"/"warnings" use totalIssues, "security"/"data" use
# issueCounter — that field is the true total; .issues.Count is only what's
# shown (capped at maxEntriesPerIssue).
$issues = @()
foreach ($section in @("semanticErrors", "warnings", "security", "data")) {
    $sectionData = $d.$section
    if (-not $sectionData) { continue }
    $sectionIssues = $sectionData.issues
    foreach ($issueId in ($sectionIssues | Get-Member -MemberType NoteProperty).Name) {
        $issueData = $sectionIssues.$issueId
        $crit      = if ($null -ne $issueData.criticality) { $issueData.criticality } else { 0 }
        $desc      = $issueData.description
        $shown     = if ($issueData.issues) { $issueData.issues.Count } else { 0 }
        $total     = if ($null -ne $issueData.issueCounter) { $issueData.issueCounter } elseif ($null -ne $issueData.totalIssues) { $issueData.totalIssues } else { $shown }
        $truncated = [bool]$issueData.tooManyError
        $issues += [PSCustomObject]@{ id=$issueId; section=$section; criticality=$crit; description=$desc; shown=$shown; total=$total; truncated=$truncated }
    }
}

if ($issues.Count -gt 0) {
    Write-Host "`nissues[$($issues.Count)]{id,section,criticality,description,shown,total,truncated}:"
    foreach ($i in $issues) {
        Write-Host "  $($i.id),$($i.section),$($i.criticality),$($i.description),$($i.shown),$($i.total),$($i.truncated)"
    }
}

# sqg.json (platform mode only — file is absent in token mode)
if (Test-Path "$OUTPUT_DIR\sqg.json") {
    $sqg = Get-Content "$OUTPUT_DIR\sqg.json" | ConvertFrom-Json
    Write-Host "sqg_acceptance: $($sqg.acceptance)"
    Write-Host "sqg_name: $($sqg.sqgsDetail[0].name)"
    $blocking = $sqg.processingDetails | ForEach-Object { $_.blockingRules } | Where-Object { $_ }
    if ($blocking) {
        Write-Host "blocking_rules: $($blocking -join ', ')"
    }
}
```

Use the extracted output above for all display and fix logic. Never include
raw `todo.json` or `sqg.json` content in your response.

```python
# Reference: field paths used in display and fix logic
# todo.json
index = d["index"]                      # list of OAS paths (resolve pointer ints against this)
score = d["score"]
sec_score  = d["security"]["score"]
data_score = d["data"]["score"]

# Save initial scores for before/after comparison (used in final summary)
initial_score      = score
initial_sec_score  = sec_score
initial_data_score = data_score

# Determine which issue IDs are SQG-blocking (semanticErrors/warnings are
# never SQG-blocking — they carry no per-type criticality and sit outside
# the security/data score)
blocking_ids = set()
if sqg:
    # Platform mode: use sqg.json
    if sqg["acceptance"] != "yes":
        blocking_ids = set(sqg["sqgsDetail"][0]["directives"].get("issueRules", []))
else:
    # Token mode: use user-defined blocking_severity_threshold from the
    # session threshold prompt (CRITICAL=4, HIGH=3, MEDIUM=2, LOW=1)
    for section in ["security", "data"]:
        for issue_id, issue_data in d[section]["issues"].items():
            if issue_data["criticality"] >= blocking_severity_threshold:
                blocking_ids.add(issue_id)

# Iterate issues across both scored sections
for section in ["security", "data"]:
    for issue_id, issue_data in d[section]["issues"].items():
        title       = issue_data["description"]           # always populated — use as the title
        pointers    = [index[loc["pointer"]] for loc in issue_data["issues"]]
        # specificDescription is frequently absent or "" — never rely on it alone
        details     = [loc.get("specificDescription") or title for loc in issue_data["issues"]]
        crit        = issue_data["criticality"]   # 4=CRITICAL 3=HIGH 2=MEDIUM 1=LOW 0=INFO
        is_blocking = issue_id in blocking_ids
        total       = issue_data["issueCounter"]           # true total, not len(pointers)
        truncated   = issue_data["tooManyError"]           # True => total > len(pointers) shown

# Iterate spec-conformance issues (never SQG-blocking, no per-type criticality)
for section in ["semanticErrors", "warnings"]:
    section_data = d.get(section)
    if not section_data:
        continue
    for issue_id, issue_data in section_data["issues"].items():
        title     = issue_data["description"]
        total     = issue_data["totalIssues"]
        truncated = issue_data["tooManyError"]

# sqg.json
sqg_passed     = sqg["acceptance"] == "yes"
sqg_name       = sqg["sqgsDetail"][0]["name"]
blocking_rules = [r for d in sqg.get("processingDetails", [])
                  for r in d.get("blockingRules", [])]
```

### Rendered format

Group issues into four tiers. Resolve each `pointer` integer to its human-readable
OAS path using `index[pointer]`. Severity label: 4=CRITICAL, 3=HIGH, 2=MEDIUM, 1=LOW, 0=INFO.
Use each issue type's `description` as the title; append a location's
`specificDescription` only when it is present and non-empty. When `truncated`
is true for an issue type, append `(showing <shown> of <total> locations)` to
its heading — never imply the listed locations are the complete set.

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

1. Map the issue `pointer` integer to its human-readable OAS path using
   `index[pointer]` from `todo.json`.
2. Read the structural context in the OAS file at that path: the operation,
   request/response schema, security requirements, or parameter definition.
3. Apply the minimum correct fix required to resolve the blocking rule. Do not
   make speculative or cosmetic changes — only fix what is explicitly blocking
   SQG acceptance.

If an issue was `truncated` (more locations exist than were shown), fixing the
listed pointers does not clear the rule — the remaining, unseen occurrences
still block SQG. Treat this as expected and plan to repeat fix-and-re-audit
until `issueCounter` for that rule reaches `0`, rather than treating the first
pass as failed.

After all fixes are applied, re-run the audit (**Step 1**) to confirm the SQG
now passes:
- **Platform mode**: confirm `sqg["acceptance"]` is `"yes"` in the new `sqg.json`.
- **Token mode**: confirm the new score meets `target_score` and no issues
  with criticality ≥ `blocking_severity_threshold` remain in `todo.json`.
- If a previously blocking issue still has occurrences after a fix cycle
  (`issueCounter > 0` for that rule ID), repeat Steps 3–4 for the remaining
  locations before declaring it resolved.

After confirming the SQG passes, compute the before/after score deltas and
pass them to the final summary:

```python
delta_score      = round(final_score      - initial_score,      1)
delta_sec_score  = round(final_sec_score  - initial_sec_score,  1)
delta_data_score = round(final_data_score - initial_data_score, 1)

def fmt_delta(d):
    return f"+{d}" if d > 0 else (f"-{abs(d)}" if d < 0 else "±0")
```

Format the `Score change:` line as:

```
Score change:   <initial_score> → <final_score>  (<fmt_delta(delta_score)>)  |  Data: <initial_data_score> → <final_data_score>  (<fmt_delta(delta_data_score)>)
```

Include a Security segment only when `delta_sec_score != 0`:

```
  |  Security: <initial_sec_score> → <final_sec_score>  (<fmt_delta(delta_sec_score)>)
```

Omit the `Score change:` line entirely when no fixes were applied (user
declined at the consent gate, or there were no SQG-blocking issues).

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
