# GraphQL Audit Workflow

Applies when pre-flight resolved `API_TYPE=graphql`. This is the GraphQL
sibling of `./audit-workflow.md` — same phases, consent gates, and modes, with
GraphQL-specific commands, report parsing, and remediation guidance.

> **Command conventions used throughout this file**
> - `<binary>` — the full path resolved during binary discovery (e.g. `~/.42crunch/bin/42c-ast`). Never call `42c-ast` by name alone unless it is confirmed to be on PATH.
> - **Never write a literal credential value into a command.** Load credentials from the conf file into the environment first, then let the command inherit them — the raw value must never appear in a command string, tool output, or chat message.
> - **Platform mode**: before every command, load credentials — macOS/Linux: `set -a; . "$HOME/.42crunch/conf/env"; set +a`; Windows: `Get-Content "$env:APPDATA\42Crunch\conf\env" | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }`. The command then inherits `API_KEY`/`PLATFORM_HOST` — no explicit prefix needed.
> - **Token mode**: load `TRIAL_TOKEN` the same way, then add `--freemium-host stateless.42crunch.com:443` and `--token "$TRIAL_TOKEN"` (macOS/Linux) or `--token $env:TRIAL_TOKEN` (Windows) to every command — never the literal token.
> - **Score tracking**: record `initial_score` immediately after the first parse (Step 2). GraphQL audit reports carry a **single global score** — there is no Security/Data split as in the OAS audit.

---

## Step 1 — Run the Audit

> **Token mode**: omit `--tag` and `--report-sqg` from all commands in this
> step. These flags require platform access and must not be used in token mode.

Resolve a platform-appropriate output directory and create it if it does not exist:

```bash
# macOS / Linux
OUTPUT_DIR=/tmp/42c-graphql-audit
mkdir -p "$OUTPUT_DIR"
```

```powershell
# Windows
$OUTPUT_DIR = "$env:TEMP\42c-graphql-audit"
New-Item -ItemType Directory -Force -Path $OUTPUT_DIR | Out-Null
```

### Platform mode

```bash
set -a; . "$HOME/.42crunch/conf/env"; set +a
<binary> graphql audit \
  --output "${OUTPUT_DIR:-/tmp/42c-graphql-audit}/report.json" \
  --output-format json \
  --report-sqg \
  [--tag <category>:<tagname>] \   # include only when a tag is assigned
  <path-to-graphql-schema>
```

### Token mode

```bash
set -a; . "$HOME/.42crunch/conf/env"; set +a
<binary> graphql audit \
  --freemium-host stateless.42crunch.com:443 \
  --token "$TRIAL_TOKEN" \
  --output "${OUTPUT_DIR:-/tmp/42c-graphql-audit}/report.json" \
  --output-format json \
  <path-to-graphql-schema>
# Token mode: 42c-ast also writes sqg.json, evaluated against the default SQG
# policy only (tag-based SQGs managed on the platform do not apply). This
# workflow uses the session target score instead, so remove it. Windows: Remove-Item "$OUTPUT_DIR\sqg.json" -ErrorAction SilentlyContinue
rm -f "${OUTPUT_DIR:-/tmp/42c-graphql-audit}/sqg.json"
```

### Output files (written to the same directory as `--output`)

| File          | Contents                                                                                              |
|---------------|-------------------------------------------------------------------------------------------------------|
| `report.json` | Full audit results — **always parse this file**                                                       |
| `todo.json`   | Only the single top-priority rule, **not** the full report. Unlike the OAS audit, do NOT prefer it — it is a subset. |
| `sqg.json`    | SQG result — written in platform mode whenever `--report-sqg` is passed (with or without `--tag`). In token mode 42c-ast evaluates only the default SQG policy (no tag-based SQGs); the Token-mode command deletes it because this workflow uses the session target score instead. |

### Check the run result before proceeding

The command above also prints a top-level status object to stdout (already
visible — no extra capture needed): `{astVersion, logs, statusCode,
statusMessage}`. Check it before touching any output file:

- **`statusCode: 0`** → continue to Step 2.
- **`statusCode: 3` and `statusMessage: limits_reached`** (Token mode
  only) → the token plan has hit its usage limit. Follow `./token-limit.md` now.
  Do not proceed to Step 2 — `report.json` was not written.
- **`statusCode: 2` (`unknown_error`) in Token mode, with `cannot count
  operation` in the logs** → the schema could not be parsed (Token mode
  reports this instead of a `valid: false` report). Tell the user the schema
  is invalid — most often a directive used without its `directive @…`
  definition, or a syntax error — and help fix it before re-running.
- **Any other non-zero `statusCode`** → surface `statusMessage` to the user
  as an error and stop. Do not attempt to parse `report.json`.

A re-run in Step 4 (after fixes are applied) is just this same command again
— apply this same check to that run too.

---

## Step 2 — Parse and Display the Audit Report

Parse `report.json` and (platform mode) `sqg.json`. Then render a
**developer-readable, risk-classified report**. Do NOT surface raw rule IDs —
every rule carries a `description` field; use that as the title. Each
occurrence usually carries a `specificDescription` naming the exact directive
the audit expects (e.g. `Output is missing a '@cost' directive or
equivalent`) — append it when present and non-empty.

> **Token rule**: never load raw JSON file contents into your response. Use
> the extraction below to pull only the fields you need, then display the
> formatted output.

### Report structure

GraphQL audit reports differ from OAS audit reports:

- **Single global `score`** (0–100). No Security/Data sub-scores.
- **No `criticality` field.** Each occurrence instead carries a negative
  `score` — its deduction from the global score. Rank rules by total impact.
- `index[]` holds human-readable schema locations
  (e.g. `Query.book(id: ID!)`, `Mutation.addBook(title: String!)`); each
  occurrence's `logicalLocation` is an integer index into it.
- `absoluteLocation` is `[startLine, startCol, endLine, endCol]` in the
  schema file — use it to jump straight to the fix site.
- **Invalid schema**: `valid: false` with a `validationErrors[]` string list
  and no `issues` key at all. Handle before touching anything else.

### Score headline

**Platform mode** (`sqg.json` always present):
```
GraphQL Audit Score: <score> / 100
SQG (<sqg-name>): PASSED / FAILED
```

**Token mode** (no `sqg.json`):
```
GraphQL Audit Score: <score> / 100
```

**Platform mode** — score ≥ 90, add one interpretation line:
> `Your GraphQL schema scores in the top tier — excellent security posture.`
Otherwise omit the interpretation line; SQG PASSED/FAILED in the headline is the authoritative result.

**Token mode only** — before rendering the findings report, prompt the user
for a session threshold (call `AskUserQuestion` with one question):
- **Question**: `"What minimum score are you targeting for this schema?"` — options:
  `["90+ — Excellent", "70 — Good baseline", "50 — Acceptable for now", "Custom — I'll enter a number"]`
  If "Custom" is chosen, call a follow-up `AskUserQuestion` for the numeric value.

Store as `target_score` for this session only — do not persist. GraphQL
findings carry no per-issue severity, so there is no blocking-severity
question — fix candidates are ranked by score impact instead.

Then add one score interpretation line:
- Score ≥ 90: `Your schema scores in the top tier — excellent security posture.`
- Score ≥ target and < 90: `Your schema meets your target score. A few improvements could push it higher.`
- Score within 10 of target (but below): `Your schema is approaching your target score — the highest-impact issues below are holding it back.`
- Score more than 10 below target: `Your schema score is below your target. The issues below must be fixed.`

### Parsing reference

Extract only the needed fields — do not read the raw file into context.

> **Platform note**: macOS/Linux use the Python snippet below. Windows users
> should use the PowerShell equivalent that follows.

**macOS / Linux (Python)**

```bash
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/42c-graphql-audit}" python3 << 'EOF'
import json, os, sys

# The quoted heredoc stops the shell from expanding variables inside the
# script, so the output directory is passed in through the environment.
out = os.environ["OUTPUT_DIR"]
with open(os.path.join(out, "report.json")) as f:
    d = json.load(f)

# Invalid schemas carry validationErrors and no issues section at all —
# handle them before touching anything else.
if not d["valid"]:
    print("schema_state: invalid")
    for e in d.get("validationErrors") or []:
        print(f"validation_error: {e}")
    sys.exit(0)

score = d["score"]
print(f"score: {score}")

index = d["index"]
# A schema with no scored findings has no "issues" key at all (score 100).
issues = d.get("issues") or {}
# counter is the true total; len(occurrences) is only what is shown
# (capped at maxImpactedIssue). impact = total score deduction for the rule.
rules = []
for rule_id, rd in issues.items():
    occ = rd["occurrences"]
    impact = round(sum(abs(o.get("score", 0)) for o in occ), 2)
    rules.append((rule_id, rd["counter"], len(occ), impact,
                  rd["description"], rd["tooManyImpacted"]))
rules.sort(key=lambda r: -r[3])

if rules:
    print(f"\nrules[{len(rules)}]{{id,total,shown,impact,description,truncated}}:")
    for rule_id, total, shown, impact, desc, truncated in rules:
        print(f"  {rule_id},{total},{shown},{impact},{desc},{truncated}")

# Per-rule locations (schema position + expected directive)
for rule_id, rd in issues.items():
    for o in rd["occurrences"]:
        loc  = index[o["logicalLocation"]]
        line = o["absoluteLocation"][0]
        spec = o.get("specificDescription") or ""
        print(f"  {rule_id} @ {loc} (line {line}) {spec}")

# Warnings do not affect the score; surface them as informational.
warnings = d.get("warnings") or {}
if warnings:
    print(f"\nwarnings[{len(warnings)}]{{id,total,description}}:")
    for rule_id, rd in warnings.items():
        locs = ", ".join(index[o["logicalLocation"]] for o in rd.get("occurrences", [])[:3])
        print(f"  {rule_id},{rd.get('counter', 0)},{rd['description']} @ {locs}")

# sqg.json (platform mode only — the Token-mode command deletes its default-policy sqg.json)
if os.path.exists(os.path.join(out, "sqg.json")):
    with open(os.path.join(out, "sqg.json")) as f:
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
if (-not $OUTPUT_DIR) { $OUTPUT_DIR = "$env:TEMP\42c-graphql-audit" }
$d = Get-Content "$OUTPUT_DIR\report.json" | ConvertFrom-Json

# Invalid schemas carry validationErrors and no issues section at all —
# handle them before touching anything else.
if (-not $d.valid) {
    Write-Host "schema_state: invalid"
    foreach ($e in $d.validationErrors) { Write-Host "validation_error: $e" }
    exit
}

Write-Host "score: $($d.score)"

$index = $d.index
# counter is the true total; occurrences.Count is only what is shown
# (capped at maxImpactedIssue). impact = total score deduction for the rule.
$rules = @()
# A schema with no scored findings has no "issues" key at all (score 100).
$ruleIds = if ($d.issues) { ($d.issues | Get-Member -MemberType NoteProperty).Name } else { @() }
foreach ($ruleId in $ruleIds) {
    $rd = $d.issues.$ruleId
    $impact = [math]::Round((($rd.occurrences | ForEach-Object { [math]::Abs($_.score) }) | Measure-Object -Sum).Sum, 2)
    $rules += [PSCustomObject]@{ id=$ruleId; total=$rd.counter; shown=$rd.occurrences.Count; impact=$impact; description=$rd.description; truncated=[bool]$rd.tooManyImpacted }
}
$rules = $rules | Sort-Object -Property impact -Descending

if ($rules.Count -gt 0) {
    Write-Host "`nrules[$($rules.Count)]{id,total,shown,impact,description,truncated}:"
    foreach ($r in $rules) {
        Write-Host "  $($r.id),$($r.total),$($r.shown),$($r.impact),$($r.description),$($r.truncated)"
    }
}

# Per-rule locations (schema position + expected directive)
foreach ($ruleId in $ruleIds) {
    foreach ($o in $d.issues.$ruleId.occurrences) {
        $loc  = $index[$o.logicalLocation]
        $line = $o.absoluteLocation[0]
        $spec = if ($o.specificDescription) { $o.specificDescription } else { "" }
        Write-Host "  $ruleId @ $loc (line $line) $spec"
    }
}

# Warnings do not affect the score; surface them as informational.
if ($d.warnings) {
    $warnIds = ($d.warnings | Get-Member -MemberType NoteProperty).Name
    Write-Host "`nwarnings[$($warnIds.Count)]{id,total,description}:"
    foreach ($w in $warnIds) {
        $wd = $d.warnings.$w
        $locs = (@($wd.occurrences) | Select-Object -First 3 | ForEach-Object { $index[$_.logicalLocation] }) -join ', '
        Write-Host "  $w,$($wd.counter),$($wd.description) @ $locs"
    }
}

# sqg.json (platform mode only — the Token-mode command deletes its default-policy sqg.json)
if (Test-Path "$OUTPUT_DIR\sqg.json") {
    $sqg = Get-Content "$OUTPUT_DIR\sqg.json" | ConvertFrom-Json
    Write-Host "sqg_acceptance: $($sqg.acceptance)"
    Write-Host "sqg_name: $($sqg.sqgsDetail[0].name)"
    $blocking = $sqg.processingDetails | ForEach-Object { $_.blockingRules } | Where-Object { $_ }
    if ($blocking) { Write-Host "blocking_rules: $($blocking -join ', ')" }
}
```

Use the extracted output above for all display and fix logic. Never include
raw `report.json` or `sqg.json` content in your response.

### Determining fix candidates

- **Platform mode**: `sqg["acceptance"] == "yes"` → no blocking work; all
  findings are informational. When acceptance is `"no"`, the `blockingRules`
  strings state why — typically a minimum-score rule (e.g. `minimum audit
  score not reached: the audit sqg expects 50, got 38`). Score-threshold
  blocking has no fixed rule subset: treat **all rules, in descending impact
  order,** as the fix queue and work through it until a re-run passes the SQG.
  If `sqgsDetail[0].directives` contains `issueRules`, those rule IDs are
  additionally blocking regardless of score.
- **Token mode**: the fix queue is all rules in descending impact order; the
  goal is `score >= target_score` from the session threshold prompt.

### Rendered format

Group rules into tiers **by rule-id prefix** (GraphQL findings carry no
severity, so tiers reflect risk family; order rules inside each tier by
descending impact). When `truncated` is true for a rule, append
`(showing <shown> of <total> locations)` to its heading — never imply the
listed locations are the complete set.

```
── 🔴 Resource Limiting (query cost · list sizes — the DoS surface) ─────────
   (rules whose id starts with "graphql-cost-";
    also include "graphql-data-*-list-*" rules here — unbounded lists are a
    resource-exhaustion risk)

  1. <description>  [impact: -<impact> pts]  (showing <shown> of <total> locations)  ← only if truncated
     Where:  <index[logicalLocation]>  (line <absoluteLocation[0]>)
     Risk:   <description>
     Fix:    <one-line description of the minimal change — use the occurrence's
              specificDescription, which names the expected directive>

  2. ...

── 🟡 Data Validation (scalar constraints · input/output typing) ────────────
   (remaining rules whose id starts with "graphql-data-", same per-issue
    format; write "(none)" if empty)

── 🟠 Other Findings ─────────────────────────────────────────────────────────
   (any rule not matched above, same per-issue format; write "(none)" if empty)

── ℹ️  Warnings (not scored) ─────────────────────────────────────────────────
   (the `warnings[...]` lines: description and up to three locations each;
    omit the section when there are none. Warnings never block the SQG and are
    not fix candidates unless the user asks.)
```

If the report has **no scored findings** (score 100, no `rules[...]` block),
say so, show any warnings, and skip the consent gate — there is nothing to fix.

Number issues sequentially across all tiers so the user can reference them by
number in their consent response.

If the schema is **invalid** (`valid: false`), skip the tiers entirely and
render the `validationErrors` list under a `── 🟣 Schema Validity ──` heading
instead. A common case: `directive: <name> undefined` means a constraint
directive is applied but its `directive @<name>(...) on ...` definition is
missing — that is fixed in Step 4 by adding the definitions, not by removing
the directive uses.

---

## Step 3 — Consent Gate

After rendering the report, call `AskUserQuestion`:
- **question**: `"I found N finding(s) across Resource Limiting and Data Validation. [Platform mode: The SQG (<sqg-name>) is FAILING — <blocking rules in plain English>.] To raise the score I propose the following changes to <filename>: 1. [issue title] → [one-line fix description] 2. ... What would you like to do?"`
- **options**: `["Yes — apply all fixes now", "Show me the diff first", "No — skip fixes for now"]`

If the user chooses **"Show me the diff first"**, display the proposed change for each
issue one at a time in unified diff format, then call `AskUserQuestion`:
- **question**: `"Apply this change?"` — **options**: `["Yes", "No — skip this one"]`

Only advance to the next fix after the user confirms the current one.

When SQG blocking is score-based, make the plan explicit in the consent
question: e.g. `"...the SQG requires a score of 50 and the schema is at 38.2;
I'll fix the highest-impact issues first and re-audit until the gate passes."`

**Contract vs enforcement — say this once, before applying fixes:**
Constraint and cost directives added to the schema are **contract metadata**.
The 42Crunch audit and scan use them, but your GraphQL server only enforces
them if its engine is configured to (e.g. a cost-analysis or constraint
plugin). Include one line in the consent message noting that server-side
enforcement is a separate step the user may want to schedule.

---

## Step 4 — Context-Aware Fix Analysis

For each finding the user has approved, resolve its location via
`index[logicalLocation]` and `absoluteLocation` (`[startLine, startCol,
endLine, endCol]` in the schema file), read the surrounding SDL, and apply
the minimum correct fix. The occurrence's `specificDescription` names the
directive the audit expects — follow it, not intuition.

### Directive remediation library

The audit recognizes the constraint-directive vocabulary below (from the
GraphQL Constraints RFC and the IBM Cost Directives spec). **The directive
definitions must be declared in the SDL before use** — applying an undefined
directive makes the schema invalid (`directive: <name> undefined`). Add the
definitions block once at the top of the schema (only the directives you
actually use):

```graphql
directive @stringValue(
  minLength: Int
  maxLength: Int
  startsWith: String
  endsWith: String
  includes: String
  pattern: String
  oneOf: [String]
  equals: String
) on SCALAR | FIELD_DEFINITION | INPUT_FIELD_DEFINITION | ARGUMENT_DEFINITION

directive @numberValue(
  min: Float
  max: Float
  exclusiveMin: Float
  exclusiveMax: Float
  multipleOf: Float
  oneOf: [Float]
  equals: Float
) on SCALAR | FIELD_DEFINITION | INPUT_FIELD_DEFINITION | ARGUMENT_DEFINITION

directive @list(
  minItems: Int
  maxItems: Int
  uniqueItems: Boolean
) on FIELD_DEFINITION | INPUT_FIELD_DEFINITION | ARGUMENT_DEFINITION

directive @cost(weight: String!) on ARGUMENT_DEFINITION | ENUM | FIELD_DEFINITION | INPUT_FIELD_DEFINITION | OBJECT | SCALAR
```

Fix patterns by rule family (verified against the audit engine):

| Finding | Fix |
|---|---|
| Built-in scalar (`ID`/`String`/`Int`/`Float`) in input or output | Replace with a custom scalar (e.g. `scalar BookId`) and constrain it (next row). Derive names from the domain (`EmailAddress`, `Year`), not generic (`MyString`). |
| Custom scalar missing a value-restriction directive | Add `@stringValue(...)` / `@numberValue(...)` **on the scalar definition**. Bounded strings need `minLength` **and** `maxLength` **and** a `pattern` — the audit checks all three; `oneOf`/`equals` alone still leaves pattern/length findings. The argument must be named `pattern`: the audit does not recognize `regex` (used by some constraint-directive specs), and `*-string-scalar-pattern-needed` never clears with it. Numbers need `min` and `max`. |
| List in output missing a size restriction | Add `@list(maxItems: N)` on the field definition. Choose `N` from context (pagination limits, domain size); when unknown, pick a defensible upper bound and mention it in the diff. |
| Output missing a cost directive / cost weight | Add `@cost(weight: "N")` on the field or object type. Note `weight` is a **String** (`"5"`, not `5`). Give list-returning and resolver-heavy fields higher weights; object types a baseline `"1"`. |

**Expect rule progression, not one-shot clearance.** Fixing one layer
surfaces the next more-specific layer — e.g. replacing built-in scalars with
custom scalars clears `*-custom-scalar-*-needed` but raises
`*-custom-scalar-directive-needed`; adding `@stringValue(pattern:)` may then
raise `*-minlength-needed`/`*-maxlength-needed` until explicit bounds are
set. The re-audit is the oracle: iterate fix → re-run → parse until the gate
clears. Treat a changed rule set with a rising score as progress, not
failure.

If a rule was `truncated` (more locations exist than were shown), fixing the
listed locations does not clear it — the remaining, unseen occurrences still
count. Repeat fix-and-re-audit until `counter` for that rule reaches `0`.

After all fixes are applied, re-run the audit (**Step 1**) to confirm:
- **Platform mode**: `sqg["acceptance"]` is `"yes"` in the new `sqg.json`.
- **Token mode**: the new score meets `target_score`.
- Otherwise repeat Steps 3–4 for the remaining highest-impact rules.

After confirming, compute the before/after score delta and pass it to the
final summary:

```python
delta_score = round(final_score - initial_score, 1)

def fmt_delta(d):
    return f"+{d}" if d > 0 else (f"-{abs(d)}" if d < 0 else "±0")
```

Format the `Score change:` line as:

```
Score change:   <initial_score> → <final_score>  (<fmt_delta(delta_score)>)
```

Omit the `Score change:` line entirely when no fixes were applied (user
declined at the consent gate, or there were no findings).

---

## Flags Reference

```
--output-format json|yaml     output format (default json)
--output <file>               write report to file instead of stdout
--report-sqg                  include sqg_pass in the report (platform mode)
--tag <category>:<tagname>    apply platform tag
--max-impacted-issues <n>     limit reported impacted issues (default 30)
--graphql-type <type>         schema flavor: "graphql" (default, plain SDL) or
                              "graphql-data-definition" (SDL already annotated
                              with constraint directives)
```
