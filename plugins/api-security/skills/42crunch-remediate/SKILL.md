---
description: >
  42Crunch API security: audit an OpenAPI spec with platform credentials, show a full
  report summary, fix all SQG-blocking issues, then run a conformance scan and fix
  authorization vulnerabilities and critical conformance issues in source code.

  Trigger this skill when the user wants to: run 42Crunch on an API, audit and scan
  an OpenAPI file, fix SQG-blocking issues, check API security with 42Crunch, run
  42c-ast audit or scan, harden an API against the platform SQG, or use the
  42Crunch platform to assess an API — even if the user just says "run 42crunch",
  "check my api", or "/42crunch".

  Strong trigger phrases: "/42crunch", "run 42crunch", "audit my api", "42crunch scan",
  "check my openapi with 42crunch", "run the 42crunch tool", "fix sqg issues",
  "audit and scan my api", "42crunch this api".

  Do NOT trigger for: full remediation to 100/100 without SQG (use api-security-remediate),
  audit-only to 100/100 (use audit-remediate), scan-only (use scan-remediate),
  generating or converting OpenAPI specs, or tasks unrelated to 42Crunch security tooling.
disable-model-invocation: true
argument-hint: "[oas-file-path] [api-base-url]"
---

# 42Crunch Skill

Platform-authenticated API security assessment and remediation using `42c-ast`:

1. **Audit** — run with platform credentials and tag, display full report summary, fix all SQG-blocking issues.
2. **Scan** — run conformance scan, fix authorization vulnerabilities (BOLA/BFLA) and critical conformance issues in source code.

**Usage:**
- `/42crunch` — uses the OAS file open in the editor; base URL auto-detected from `servers[0].url`
- `/42crunch openapi.json` — explicit OAS file path
- `/42crunch openapi.json https://localhost:8080` — explicit OAS file and base URL override

See [references/reports.md](references/reports.md) for report file formats (sqg.json, todo.json, scan SQG).
See [references/fixes.md](references/fixes.md) for code fix patterns and OAS schema fix patterns.

---

## Phase 1 — Locate the Binary

Find `42c-ast` portably. Never hardcode any path. Try in order — stop at the first match.

```bash
AST_BIN=""

# 1. Canonical install location (set by VSCode extension on first run)
#    macOS / Linux:  ~/.42crunch/bin/42c-ast
#    Windows:        %USERPROFILE%\.42crunch\bin\42c-ast.exe
for candidate in \
  "$HOME/.42crunch/bin/42c-ast" \
  "$USERPROFILE/.42crunch/bin/42c-ast.exe"; do
  [ -x "$candidate" ] && AST_BIN="$candidate" && break
done

# 2. PATH
[ -z "$AST_BIN" ] && AST_BIN=$(command -v 42c-ast 2>/dev/null)

# 3. VSCode extensions directory — last resort, slow
#    macOS:   ~/Library/Application Support/Code/Extensions/
#    Linux:   ~/.vscode/extensions/
#    Windows: %USERPROFILE%\.vscode\extensions\
[ -z "$AST_BIN" ] && AST_BIN=$(find "$HOME/.vscode/extensions" \
  \( -name "42c-ast" -o -name "42c-ast.exe" \) 2>/dev/null | head -1)
```

If `AST_BIN` is still empty, stop:
> `42c-ast` not found. Install the **42Crunch OpenAPI Editor** VSCode extension (publisher: `42crunch`). It installs the binary at `~/.42crunch/bin/42c-ast`.

Generate a unique run ID (avoids freemium quota errors) and record start time:

```bash
RUN_ID="42c-skill-$(date +%s)"
SKILL_START=$(date +%s)
```

---

## Phase 2 — Resolve the OAS File

Resolve `OAS_FILE` in priority order — stop at the first valid result:

1. **Explicit argument** — if `$ARGUMENTS[0]` is provided and the path exists, use it.
2. **Editor context** — if the conversation contains an `ide_opened_file` tag pointing to a `.json`, `.yaml`, or `.yml` file, use that path.
3. **Ask the user** — if neither of the above yields a file, use AskUserQuestion: `"Please provide the path to your OpenAPI definition file."`

Store the absolute path as `OAS_FILE` and the extension (without the dot) as `OAS_EXT`.

Validate:
- File must exist on disk.
- File must have an `openapi:` or `swagger:` key at the root.

If validation fails, stop with a clear error.

---

## Phase 3 — Read the Implementation for Context

Before making any changes, build a complete picture of what the API actually does. This is the foundation for every fix — OAS edits that contradict the implementation introduce bugs, not security.

Use Glob to find source files adjacent to or containing `OAS_FILE`. Typical layouts:

```
<project-root>/
  rest-api/
    routes/          ← route handlers
    controllers/     ← business logic
    app.js           ← express app, route mounting, middleware chain
  shared/
    middleware/      ← auth middleware (token verification logic)
    models/          ← DB schemas (field names and types)
```

Read every file found. Record:

| What | Where to look |
|---|---|
| Routes (method + path) | route files + app.js `app.use(...)` mounts |
| Auth middleware per route | route files — `authenticate` / `auth` in route definitions |
| Intentionally public routes | routes with NO auth middleware |
| Request fields accepted | `req.body` / `req.query` destructuring in handlers |
| Response shape | `res.json(...)` calls — list every field returned |
| Status codes | all `res.status(...)` calls per route |
| How auth works | middleware — `jwt.verify` vs `jwt.decode`? what payload fields? |
| Authorization checks | ownership comparisons, role checks — note if commented out |
| Model field names and types | schema definitions |

---

## Phase 4 — Create Temp Workspace

```bash
WORK_DIR=$(mktemp -d)
cp "$OAS_FILE" "$WORK_DIR/openapi.$OAS_EXT"
```

All binary invocations read from `WORK_DIR`. OAS edits go directly to `OAS_FILE` via the Edit tool.

---

## Phase 5 — Discover Platform Credentials and Tag

Collect `API_KEY`, `PLATFORM_HOST`, and `API_TAG`. Do this silently — no output unless something is missing.

### Step A — API Key

```bash
# Check environment first
[ -n "$API_KEY" ] && echo "API_KEY already set"

# Walk upward from OAS_FILE looking for a .env file
_dir="$(dirname "$OAS_FILE")"
while [ "$_dir" != "/" ]; do
  if [ -f "$_dir/.env" ]; then
    API_KEY=$(grep -E '^API_KEY=' "$_dir/.env" | head -1 | cut -d'=' -f2-)
    [ -n "$API_KEY" ] && break
  fi
  _dir="$(dirname "$_dir")"
done
```

If still unset, use AskUserQuestion: `"Please enter your 42Crunch platform API key:"`

If the user provides an empty value, stop: `No API key provided — cannot run platform-authenticated audit.`

### Step B — Platform Host

```bash
[ -z "$PLATFORM_HOST" ] && PLATFORM_HOST="https://demolabs.42crunch.cloud"
PLATFORM_HOST="${PLATFORM_HOST%/}"
```

### Step C — API Tag (silently from VSCode workspace DB)

Tags are stored by the 42Crunch VSCode extension in a SQLite workspace DB — not in any config file.

```python
import json, os, glob, subprocess

oas_file = "$OAS_FILE"

# Workspace DB location varies by OS:
#   macOS:   ~/Library/Application Support/Code/User/workspaceStorage
#   Linux:   ~/.config/Code/User/workspaceStorage
#   Windows: %APPDATA%\Code\User\workspaceStorage
ws_dirs = [
    os.path.expanduser("~/Library/Application Support/Code/User/workspaceStorage"),
    os.path.expanduser("~/.config/Code/User/workspaceStorage"),
    os.path.expandvars("%APPDATA%\\Code\\User\\workspaceStorage"),
]

api_tag = ""
for ws_dir in ws_dirs:
    for db_path in glob.glob(f"{ws_dir}/*/state.vscdb"):
        try:
            result = subprocess.run(
                ["sqlite3", db_path,
                 "SELECT value FROM ItemTable WHERE key='42Crunch.vscode-openapi';"],
                capture_output=True, text=True, timeout=5
            )
            val = result.stdout.strip()
            if not val:
                continue
            data = json.loads(val)
            tags = data.get("openapi-42crunch.environment-tags-data", {}).get(oas_file, [])
            if tags:
                api_tag = f"{tags[0]['categoryName']}:{tags[0]['tagName']}"
                break
        except Exception:
            continue
    if api_tag:
        break

print(api_tag)
```

Store as `API_TAG`. If empty, stop:
```
No tag found for this OAS file.
Assign a tag via the 42Crunch OpenAPI Editor (right-click the file → Set Tag), then re-run.
```

### Step D — Print Credential Summary

```
Platform: <PLATFORM_HOST>
Tag:      <API_TAG>
API key:  ***<last-4-chars>
```

---

## Phase 6 — Audit: Run, Report, Fix SQG-Blocking Issues

### Step A — Run Audit

Sync OAS to work dir, then run with platform credentials:

```bash
cp "$OAS_FILE" "$WORK_DIR/openapi.$OAS_EXT"

API_KEY="$API_KEY" PLATFORM_HOST="$PLATFORM_HOST" \
"$AST_BIN" audit run "$WORK_DIR/openapi.$OAS_EXT" \
  --tag "$API_TAG" \
  --output "$WORK_DIR/report.json" \
  --output-format json \
  --enrich=false \
  --verbose error \
  --org "$RUN_ID" --repo "$RUN_ID" --user "$RUN_ID"
AUDIT_EXIT=$?
```

If `AUDIT_EXIT` is non-zero and neither `todo.json` nor `sqg.json` was written, stop:
```
Audit failed (exit $AUDIT_EXIT). No report produced.
Common causes: invalid API key, platform unreachable, malformed OAS, quota exceeded.
```

### Step B — Parse and Display Report Summary

Read `sqg.json` and `todo.json` (written to `WORK_DIR` alongside `report.json`).
See [references/reports.md](references/reports.md) for full field reference.

```python
import json, re

sqg = json.load(open(f"{WORK_DIR}/sqg.json"))
sqg_passed = sqg["acceptance"] == "yes"
sqg_name   = sqg["sqgsDetail"][0]["name"]
directives = sqg["sqgsDetail"][0]["directives"]
forbidden_ids = set(directives.get("issueRules", []))
min_scores    = directives.get("minimumAssessmentScores", {})
blocking_rules = [r for d in sqg.get("processingDetails", [])
                    for r in d.get("blockingRules", [])]

d = json.load(open(f"{WORK_DIR}/todo.json"))
score = d.get("score", 0)
index = d.get("index", [])
SEVERITY = {0: "INFO", 1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}

issues = []
for section in ["security", "data"]:
    for issue_id, issue_data in d.get(section, {}).get("issues", {}).items():
        crit = issue_data.get("criticality", 0)
        locations = issue_data.get("issues", [])
        pointers = [index[loc["pointer"]] for loc in locations
                    if loc.get("pointer", -1) < len(index)]
        issues.append({
            "id": issue_id, "section": section, "severity": crit,
            "label": SEVERITY.get(crit, str(crit)),
            "description": issue_data.get("description", ""),
            "count": len(locations), "pointers": pointers,
        })
issues.sort(key=lambda x: -x["severity"])
```

Display the full audit summary:

```
## Audit Report
Score:  <score>/100
SQG:    <sqg_name> — PASSED ✓ | FAILED ✗

SQG Thresholds:
  Global: <min_scores.global> | Data Validation: <min_scores.dataValidation> | Security: <min_scores.security>

Blocking rules:
  - <blocking_rule>
  ...

All Issues (<total> total):
  [CRITICAL] <id>: <description>  (<count> location(s)) — <first pointer>
  [HIGH]     <id>: <description>  ...
  [MEDIUM]   ...
  [LOW]      ...
  [INFO]     ...
```

**If `sqg_passed`:** print `SQG already passes — skipping OAS fixes.` → jump to Phase 7.

### Step C — Identify SQG-Blocking Issues

Classify each issue as blocking or non-blocking based on the `blocking_rules`:

```python
# Determine which score categories are below threshold
low_score_categories = set()
for rule in blocking_rules:
    m = re.match(r"minimum (\w[\w ]*?) score not reached", rule)
    if m:
        phrase = m.group(1).strip()
        if phrase == "audit":
            low_score_categories.add("global")
        elif "data" in phrase:
            low_score_categories.add("dataValidation")
        elif phrase == "security":
            low_score_categories.add("security")

SECTION_TO_CATEGORY = {"security": "security", "data": "dataValidation"}

fix_issues, skip_issues = [], []
for issue in issues:
    reason = None
    if issue["id"] in forbidden_ids:
        reason = "forbidden by SQG"
    elif "global" in low_score_categories:
        reason = f"contributes to overall score ({score:.1f} < {min_scores.get('global', '?')})"
    elif SECTION_TO_CATEGORY.get(issue["section"]) in low_score_categories:
        cat = SECTION_TO_CATEGORY[issue["section"]]
        reason = f"{cat} score below threshold (< {min_scores.get(cat, '?')})"
    (fix_issues if reason else skip_issues).append({**issue, "sqg_reason": reason})
```

Print the fix scope:

```
## Fix Plan (SQG-scoped)
Fixing <n> blocking issues | Skipping <m> non-blocking

Will fix:
  [CRITICAL] <id>  ← <sqg_reason>
  [HIGH]     <id>  ← <sqg_reason>

Skipping:
  [MEDIUM] <id> — not SQG-blocking
```

If `fix_issues` is empty: print the skip list → jump to Phase 7.

### Step D — Apply OAS Fixes

Back up before editing:
```bash
BACKUP=$(mktemp "/tmp/42c-audit-XXXXXX.$OAS_EXT")
cp "$OAS_FILE" "$BACKUP"
```

Apply all fixes to `OAS_FILE` using the Edit tool in rapid succession. For each fix:
- `v3-schema-*` issues: use the fix patterns in [references/fixes.md](references/fixes.md).
- `global-*` issues: fetch `https://platform.42crunch.com/kdb/audit-with-yaml.json` once (only if `global-*` IDs are present) and use the `remediation` field. Cache — do not re-fetch.
- Use Phase 3 context to make fixes accurate: auth scheme type must match middleware, response schemas must match `res.json(...)` shapes, per-operation security overrides must match whether auth middleware is applied.
- One Edit call per logical fix. Preserve indentation, key order, and comments.

Show diff after all edits:
```bash
git diff "$OAS_FILE"
```

If the diff is empty despite issues listed, stop and explain. Otherwise, `rm "$BACKUP"`.

### Step E — Verify Audit

Sync and re-run once:

```bash
cp "$OAS_FILE" "$WORK_DIR/openapi.$OAS_EXT"

API_KEY="$API_KEY" PLATFORM_HOST="$PLATFORM_HOST" \
"$AST_BIN" audit run "$WORK_DIR/openapi.$OAS_EXT" \
  --tag "$API_TAG" \
  --output "$WORK_DIR/report-verify.json" \
  --output-format json \
  --enrich=false \
  --verbose error \
  --org "$RUN_ID" --repo "$RUN_ID" --user "$RUN_ID"
```

Parse `sqg.json` again and print:
```
## Audit Verification
Score: <score>/100
SQG: PASSED ✓ | FAILED ✗

Remaining blocking rules (if any):
  - <rule>
```

If still failing, list what remains — these require manual decisions. Proceed to Phase 7 regardless.

---

## Phase 7 — Scan: Conformance and Authorization Testing

Always runs after Phase 6. Skip to Phase 8 only if no base URL can be resolved or API is unreachable.

### Step 0 — Confirm Scan with User

Before doing anything else in this phase, use AskUserQuestion:

> "Are you happy to run the 42Crunch Scan?"

- If the user confirms (yes / proceed / run / any positive response) → continue to Step A.
- If the user declines (no / skip / cancel / any negative response) → skip directly to Phase 8, recording `Scan: skipped — user declined`.

### Step A — Resolve Base URL

```bash
BASE_URL=""
BASE_URL_SOURCE=""

# 1. Explicit argument
[ -n "$ARGUMENTS[1]" ] && BASE_URL="$ARGUMENTS[1]" && BASE_URL_SOURCE="argument"

# 2. Shell environment
[ -z "$BASE_URL" ] && [ -n "$SCAN42C_HOST" ] && BASE_URL="$SCAN42C_HOST" && BASE_URL_SOURCE="env"

# 3. OAS servers[0].url
if [ -z "$BASE_URL" ]; then
  BASE_URL=$(python3 -c "
import json, yaml, sys
try:
    d = json.load(open('$OAS_FILE'))
except Exception:
    d = yaml.safe_load(open('$OAS_FILE'))
servers = d.get('servers', [])
if servers: print(servers[0].get('url', ''))
" 2>/dev/null)
  [ -n "$BASE_URL" ] && BASE_URL_SOURCE="OAS servers[0].url"
fi

BASE_URL="${BASE_URL%/}"
```

If empty: skip to Phase 8, record `Scan: skipped — no base URL`.

Verify reachability:
```bash
curl -s --max-time 8 --head "$BASE_URL" >/dev/null 2>&1 || {
  echo "Cannot reach $BASE_URL — skipping scan."
  # Jump to Phase 8
}
```

Print: `Using base URL: <BASE_URL>  (source: <BASE_URL_SOURCE>)`

### Step B — Locate or Generate Scan Config

#### Part 1 — Look for an existing scanconf

Walk upward from `OAS_FILE` for `.42c/conf.yaml`, extract the API alias, find `.42c/scan/<alias>/scanconf.json`. Fall back to a broad `find` if not found via conf.yaml.

```bash
SCANCONF=""
API_ALIAS=""
PROJ_ROOT=""

_dir="$(dirname "$OAS_FILE")"
while [ "$_dir" != "/" ]; do
  [ -f "$_dir/.42c/conf.yaml" ] && PROJ_ROOT="$_dir" && break
  _dir="$(dirname "$_dir")"
done

if [ -n "$PROJ_ROOT" ]; then
  OAS_REL="${OAS_FILE#$PROJ_ROOT/}"
  API_ALIAS=$(python3 -c "
import yaml
conf = yaml.safe_load(open('$PROJ_ROOT/.42c/conf.yaml'))
print(conf.get('apis', {}).get('$OAS_REL', {}).get('alias', ''))
" 2>/dev/null)
fi

[ -n "$API_ALIAS" ] && CANDIDATE="$PROJ_ROOT/.42c/scan/$API_ALIAS/scanconf.json" && \
  [ -f "$CANDIDATE" ] && SCANCONF="$CANDIDATE"

[ -z "$SCANCONF" ] && SCANCONF=$(find "${PROJ_ROOT:-$(dirname "$OAS_FILE")}" \
  -path "*/.42c/scan/*/scanconf.json" 2>/dev/null | head -1)
```

If found: print `Using existing scan config: <SCANCONF>` → skip to Step C.

#### Part 2 — Generate scanconf if none exists

```bash
"$AST_BIN" scan conf generate "$WORK_DIR/openapi.$OAS_EXT" \
  --output "$WORK_DIR/scanconf.json" --output-format json
SCANCONF="$WORK_DIR/scanconf.json"
```

Detect auth mode, collect credentials, and inject BOLA/BFLA authorization tests. Follow the same logic as the `api-security-remediate` skill (detect static vs dynamic, analyze OAS for BOLA/BFLA candidates, ask for credentials, inject tests). See [references/fixes.md](references/fixes.md) for the credential injection patterns.

### Step C — Run the Scan with Platform Credentials

```bash
SCAN_STDOUT=$(
  API_KEY="$API_KEY" PLATFORM_HOST="$PLATFORM_HOST" \
  SCAN42C_HOST="$BASE_URL" \
  "$AST_BIN" scan run "$WORK_DIR/openapi.$OAS_EXT" \
    --tag "$API_TAG" \
    --conf-file "$SCANCONF" \
    --output "$WORK_DIR/scan-report.json" \
    --output-format json \
    --enrich=false \
    --verbose error \
    --org "$RUN_ID" --repo "$RUN_ID" --user "$RUN_ID" \
    2>/dev/null
)
```

For generated scanconf with static token auth, prepend `SCAN42C_SECURITY_USERTOKEN`, `SCAN42C_SECURITY_USER2TOKEN`, `SCAN42C_SECURITY_ADMINTOKEN` as needed.

After scan completes, reset the database to remove test residues — walk upward from `OAS_FILE` looking for `scripts/reset_database.sh`:
```bash
_dir="$(dirname "$OAS_FILE")"
while [ "$_dir" != "/" ]; do
  [ -f "$_dir/scripts/reset_database.sh" ] && bash "$_dir/scripts/reset_database.sh" && break
  _dir="$(dirname "$_dir")"
done
```

### Step D — Parse Scan Results

The SQG result is in `SCAN_STDOUT` only — it is NOT written to `scan-report.json`.
See [references/reports.md](references/reports.md) for the full stdout JSON structure.

```python
import json

cli_output = json.loads(SCAN_STDOUT) if SCAN_STDOUT.strip() else {}
scan_sqg_passed  = cli_output.get("sqgPass")
scan_blocking    = [r for d in cli_output.get("sqgDetails", [])
                      for r in d.get("blockingRules", [])]

report = json.load(open(f"{WORK_DIR}/scan-report.json"))
summary = report.get("summary", {})
```

Display the scan summary:

```
## Scan Report
Target: <BASE_URL>
State:  <summary.state>
Operations: <success> passed | <happyPathFailure> happy-path failures | <failed> failed
Issues: Critical: <n> | High: <n> | Medium: <n> | Low: <n>

SQG: PASSED ✓ | FAILED ✗ | not applied
SQG Blocking Rules:
  - severity_threshold
  - forbidden_test:authentication-swapping-bfla

Authorization Issues:
  [<method> <path>] <operationId>: <test-key>

Conformance Issues by Type:
  <issueType>: <count>
```

### Step E — Determine What to Fix

Fix the following from scan findings:
1. **All authorization issues** (`authentication-swapping-bola`, `authentication-swapping-bfla`) — these are always fixed regardless of severity or SQG status.
2. **Critical conformance issues** — fix any conformance issue type with severity CRITICAL across all affected operations.

Skip: high/medium/low conformance issues, `method-not-allowed` tests.

Print the code fix plan:
```
## Code Fix Plan
Fixing:
  authentication-swapping-bfla: <n> operations  ← authorization issue
  schema-type-wrong-boolean: <n> operations     ← CRITICAL conformance
  ...
Skipping:
  schema-minlength-scan: <n>                    ← high severity
  parameter-header-accept-wrong: <n>            ← medium severity
```

### Step F — Apply Code Fixes

For each issue type to fix, apply the code change. Use Phase 3 context for exact file and line.
See [references/fixes.md](references/fixes.md) for the full issue-type → code-fix mapping.

For each fix:
1. Print: `Fixing <issue-type> in <file> — <route>`
2. Use the Edit tool — minimal change, match existing code style, add brief inline comment for security fixes.
3. If already implemented: print `Already implemented — skipping.`

After all fixes:
```
## Code Fixes Applied
<n> files modified:
  <file>: <description>
```

### Step G — Rebuild and Verify

Walk upward from `OAS_FILE` for `scripts/manage.sh`. If found:
```bash
bash "$_manage" rest rebuild
```

Probe a sentinel behaviour to confirm new code is live (e.g., if Content-Type validation was added, send `Content-Type: text/plain` and expect 415). If the server is still serving old code, stop and explain without running verification.

If server is up to date, re-run the scan (same config, same credentials) and compare:

```
## Scan Verification
Resolved: <n> issues fixed
Remaining: <n> still present
New issues introduced: <n>
```

Reset the database again after verification scan.

---

## Phase 8 — Final Report

```bash
rm -rf "$WORK_DIR"
SKILL_END=$(date +%s)
ELAPSED=$(( SKILL_END - SKILL_START ))
```

```
## Final Report

OAS File:    <OAS_FILE>
Tag:         <API_TAG>
Platform:    <PLATFORM_HOST>

Audit SQG:   <sqg_name> — PASSED ✓ | FAILED ✗
  Score:     <final-score>/100
  OAS Fixes: <n> SQG-blocking applied | <m> non-blocking skipped

Scan SQG:    PASSED ✓ | FAILED ✗  (or: skipped — <reason>)
  Code Fixes: <n> applied
  Resolved:   <n> / <remaining> remaining

Total Time: <elapsed>m <s>s

### Remaining Manual Items (if any)
<issue>
  Why: <reason>
  Suggested action: <guidance>
```

---

## Invariants

- **Never hardcode** paths, tokens, or machine-specific strings.
- **Context before fixes** — every OAS edit must reflect what the implementation actually does.
- **Authorization issues are always fixed** — do not scope them to SQG status.
- **One Edit call per logical fix** — never batch unrelated changes.
- **YAML/JSON fidelity** — preserve indentation, key order, and comments.
- **Scan SQG lives in stdout** — `scan-report.json` has no SQG fields. Always parse `SCAN_STDOUT`.
- **Surgical code edits** — touch only what is needed; do not refactor surrounding code.
