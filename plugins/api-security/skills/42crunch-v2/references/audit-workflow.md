# Audit Workflow

> **Command conventions used throughout this file**
> - `<binary>` — the full path resolved during binary discovery (e.g. `~/.42crunch/bin/42c-ast`). Never call `42c-ast` by name alone unless it is confirmed to be on PATH.
> - **Platform mode**: prefix every command with `API_KEY="<resolved-value>" PLATFORM_HOST="<value>"` (omit `PLATFORM_HOST` to use the value from your environment or `.env` file).
> - **Freemium mode**: add `--freemium-host stateless.42crunch.com:443` and `--token <FREEMIUM_TOKEN>` to every command.
> - **Score tracking**: record `initial_score`, `initial_sec_score`, and `initial_data_score` immediately after the first parse (Step 2). These are used to build the before/after comparison in the final summary.

---

## Step 1 — Run the Audit

### Platform mode

```bash
API_KEY="<resolved-value>" PLATFORM_HOST="<value>" <binary> audit run \
  --output /tmp/42c-audit/report.json \
  --output-format json \
  --report-sqg \
  --tag <category>:<tagname> \
  <path-to-oas-file>
```

### Freemium mode

```bash
<binary> audit run \
  --freemium-host stateless.42crunch.com:443 \
  --token <FREEMIUM_TOKEN> \
  --output /tmp/42c-audit/report.json \
  --output-format json \
  <path-to-oas-file>
```

Create the output directory before running if it does not exist:

```bash
mkdir -p /tmp/42c-audit
```

### Output files (written to the same directory as `--output`)

| File          | Contents                                                                                           |
|---------------|----------------------------------------------------------------------------------------------------|
| `report.json` | Audit results                                                                                      |
| `todo.json`   | Same as report.json but with `index[]` for OAS path resolution — **prefer this file**              |
| `sqg.json`    | SQG result — only written in platform mode (API_KEY/IDE_TOKEN + PLATFORM_HOST + tag all present). Not written in freemium mode. |

---

## Step 2 — Parse and Display the Audit Report

Parse `todo.json` (fall back to `report.json` if absent) and `sqg.json`. Then
render a **developer-readable, risk-classified report**. Do NOT surface raw
rule IDs — translate each one using the table below.

### Score headline

**Platform mode:**
```
Audit Score: <score> / 100  |  Security: <sec-score>/100  |  Data Validation: <data-score>/100
SQG (<sqg-name>): PASSED / FAILED
```

**Freemium mode** (no `sqg.json` — apply hardcoded SQG rules):
```
Audit Score: <score> / 100  |  Security: <sec-score>/100  |  Data Validation: <data-score>/100
SQG (Freemium): PASSED / FAILED
```

**Score interpretation — always include one line immediately after the score headline:**

- Score ≥ 90: `Your API scores in the top tier — excellent security posture.`
- Score 70–89: `Your API passes the SQG threshold. A few improvements could push it higher.`
- Score 50–69: `Your API is approaching the SQG threshold — the blocking issues below are holding it back.`
- Score < 50: `Your API score is below the SQG threshold. The issues below must be fixed to unblock the scan.`

When the score crosses from below 70 to 70 or above after fixes are applied, add:
> `This improvement moves your API from failing to passing the SQG threshold.`

Freemium SQG rules (applied by the skill, not the platform):
- Score **< 70** → SQG FAILED
- Any issue with criticality **MEDIUM (2), HIGH (3), or CRITICAL (4)** → SQG-blocking (treated as 🔴)
- Issues with criticality LOW (1) or INFO (0) → surfaced only, not blocking

### Parsing reference

```python
# todo.json
index = d["index"]                      # list of OAS paths (resolve pointer ints against this)
score = d["score"]
sec_score  = d["security"]["score"]
data_score = d["data"]["score"]

# Save initial scores for before/after comparison (used in final summary)
initial_score      = score
initial_sec_score  = sec_score
initial_data_score = data_score

# Determine which issue IDs are SQG-blocking
blocking_ids = set()
if sqg:
    # Platform mode: use sqg.json
    if sqg["acceptance"] != "yes":
        blocking_ids = set(sqg["sqgsDetail"][0]["directives"].get("issueRules", []))
else:
    # Freemium mode: issues with criticality >= MEDIUM are blocking
    for section in ["security", "data"]:
        for issue_id, issue_data in d[section]["issues"].items():
            if issue_data["criticality"] >= 2:  # MEDIUM=2, HIGH=3, CRITICAL=4
                blocking_ids.add(issue_id)

# Iterate issues across both sections
for section in ["security", "data"]:
    for issue_id, issue_data in d[section]["issues"].items():
        pointers   = [index[loc["pointer"]] for loc in issue_data["issues"]]
        crit       = issue_data["criticality"]   # 4=CRITICAL 3=HIGH 2=MEDIUM 1=LOW 0=INFO
        is_blocking = issue_id in blocking_ids

# sqg.json
sqg_passed     = sqg["acceptance"] == "yes"
sqg_name       = sqg["sqgsDetail"][0]["name"]
blocking_rules = [r for d in sqg.get("processingDetails", [])
                  for r in d.get("blockingRules", [])]
```

### Rule-ID → developer language translation table

Match each rule ID by suffix. When multiple suffixes match, use the most
specific one.

| Rule ID suffix (end of string) | Plain-English Title | Risk for developers |
|---|---|---|
| `string-pattern` | Missing input format constraint | Without a regex pattern, any string is accepted — enables format-bypass and injection attacks |
| `string-maxlength` | Missing maximum string length | Unbounded strings allow buffer-overflow-style abuse and log flooding |
| `numerical-max` | Missing numeric upper bound | Arbitrarily large numbers can cause integer overflow or resource exhaustion |
| `additionalproperties-true` | Schema allows extra/unknown fields | Mass-assignment risk — undocumented fields submitted by clients may be silently processed |
| `array-maxitems` | Response array has no item cap | API can return unlimited rows, causing data over-exposure and DoS via large payloads |
| `response-403` | 403 Forbidden response not documented | Clients can't reliably detect authorization failures; broken access control goes unnoticed |
| `response-404` | 404 Not Found response not documented | Clients can't distinguish "resource missing" from other errors |
| `response-406` | 406 Not Acceptable response not documented | Content negotiation failures are undocumented; clients may misinterpret errors |
| `response-429` | 429 Too Many Requests response not documented | Rate-limit responses are undocumented; clients cannot implement back-off |
| `response-default-undefined` | No default error response defined | Unhandled errors return undocumented responses; clients fail unpredictably |
| `header-schema-undefined` | Response header has no schema | Header values are unvalidated and undocumented; clients can't rely on them |
| `string-loosepattern` | Regex pattern is too permissive | Overly broad pattern allows values outside the intended format through |
| `sample-undefined` | No example values provided | Scan and test tools cannot auto-generate valid requests; all test coverage is blocked |
| `schema-example-improper` | Example value doesn't match its schema | Misleading documentation — example fails its own schema validation |
| `global-parameter-unused` | Reusable parameter defined but never referenced | Dead schema definition; creates maintenance confusion |
| `accept-empty-security-used` | Empty security override in use | One or more operations may bypass authentication; review intent carefully |

For any rule ID not in the table: derive a title by splitting the rule ID on
`-`, skipping the leading `v3`, and joining the remaining words as a sentence.

### Rendered format

Group issues into three tiers. Resolve each `pointer` integer to its human-readable
OAS path using `index[pointer]`. Severity label: 4=CRITICAL, 3=HIGH, 2=MEDIUM, 1=LOW, 0=INFO.

```
── 🔴 SQG-Blocking Issues — must fix before scan can run ──────────────────

  1. <Plain-English Title>  [<SEVERITY>]
     Where:  <OAS path from index>
     Risk:   <risk sentence from table>
     Fix:    <one-line description of the minimal change needed>

  2. ...

── 🟠 Security Issues (authentication · authorization · transport) ─────────
  (list issues from d["security"]["issues"] that are not SQG-blocking,
   same per-issue format; write "(none)" if empty)

── 🟡 Data Validation Issues (schemas · responses · parameters) ───────────
  (list issues from d["data"]["issues"] that are not SQG-blocking,
   same per-issue format)
```

Number issues sequentially across all three sections so the user can reference
them by number in their consent response.

---

## Step 3 — Consent Gate

After rendering the report, call `AskUserQuestion`:
- **question**: `"I found N SQG-blocking issue(s) (🔴) that must be fixed to pass the SQG, plus M additional finding(s) for your information. For the blocking issues I propose the following changes to <filename>: 1. [issue title] → [one-line fix description] 2. ... What would you like to do?"`
- **options**: `["Yes — apply all fixes now", "Show me the diff first", "No — skip fixes for now"]`

If the user chooses **"Show me the diff first"**, display the proposed change for each
issue one at a time in unified diff format, then call `AskUserQuestion`:
- **question**: `"Apply this change?"` — **options**: `["Yes", "No — skip this one"]`

Only advance to the next fix after the user confirms the current one.

Do **not** offer to fix non-blocking issues at this stage — only the 🔴 items.
Only proceed to Step 4 after the user explicitly confirms.

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

After all fixes are applied, re-run the audit (**Step 1**) to confirm the SQG
now passes:
- **Platform mode**: confirm `sqg["acceptance"]` is `"yes"` in the new `sqg.json`.
- **Freemium mode**: confirm the new score is ≥ 70 and no issues with
  criticality ≥ MEDIUM remain in `todo.json`.

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
