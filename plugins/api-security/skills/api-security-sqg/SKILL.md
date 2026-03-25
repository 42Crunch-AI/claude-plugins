---
name: api-security-sqg
description: >
  SQG-targeted 42Crunch API security hardening: run the audit tool (`42c-ast`) with platform
  credentials and fix only the issues that block SQG (Security Quality Gate) acceptance, then
  run a conformance scan and fix only the code vulnerabilities that appear in the SQG blocking rules.
  Stops as soon as the SQG passes.

  Trigger this skill when the user wants to: fix only what the SQG requires, pass the 42Crunch
  security quality gate, remediate SQG-blocking issues only, use the SQG as the acceptance criterion,
  or run api-security-sqg.

  Strong trigger phrases: "/api-security-sqg", "fix sqg issues", "pass the sqg", "sqg-targeted
  remediation", "fix only sqg blocking issues", "make the sqg pass".

  Do NOT trigger for: full remediation to 100/100 (use `api-security-remediate`), running only
  an audit (use `audit-remediate`), running only a conformance scan (use `scan-remediate`),
  or any workflow that does not involve the 42Crunch platform SQG.
disable-model-invocation: true
argument-hint: <oas-file-path> [api-base-url]
---

# API Security SQG Skill

SQG-targeted API security hardening using the `42c-ast` binary with platform credentials:

1. **Audit** — run audit with platform API key and tag, read `sqg.json`, fix only SQG-blocking issues (forbidden IDs + score-category threshold violations), verify once.
2. **Conformance scan** — run scan with platform credentials and tag, capture SQG result from stdout, fix only the code issues that correspond to `blockingRules`.

**Usage:**
- `/api-security-sqg openapi.json` — SQG-scoped audit + OAS fixes + SQG-scoped scan (base URL auto-detected from OAS `servers[0].url`)
- `/api-security-sqg openapi.json https://localhost:8080` — same, with explicit base URL override

---

## Phase 1 — Locate the Binary

Find `42c-ast` portably. Never hardcode any path. Try in order — stop at the first match.

```bash
AST_BIN=""

# 1. Canonical install location — fastest, no subprocess
for candidate in \
  "$HOME/.42crunch/bin/42c-ast" \
  "$USERPROFILE/.42crunch/bin/42c-ast.exe"; do
  [ -x "$candidate" ] && AST_BIN="$candidate" && break
done

# 2. PATH lookup
[ -z "$AST_BIN" ] && AST_BIN=$(command -v 42c-ast 2>/dev/null)

# 3. VSCode extensions — last resort, slow
[ -z "$AST_BIN" ] && AST_BIN=$(find "$HOME/.vscode/extensions" \
  \( -name "42c-ast" -o -name "42c-ast.exe" \) 2>/dev/null | head -1)
```

If `AST_BIN` is still empty, stop:
> `42c-ast` was not found. Install the **42Crunch OpenAPI Editor** VSCode extension (publisher: `42crunch`). It bundles the binary at `~/.42crunch/bin/42c-ast`.

Generate a unique run identifier and record skill start time:

```bash
RUN_ID="42c-skill-$(date +%s)"
SKILL_START=$(date +%s)
```

---

## Phase 2 — Validate the OAS File

- Resolve `$ARGUMENTS[0]` to an absolute path (relative to CWD if not absolute).
- Confirm the file exists and ends in `.json`, `.yaml`, or `.yml`.
- Read the file to confirm an `openapi:` or `swagger:` key exists at the root.
- Store the absolute path as `OAS_FILE` and the extension as `OAS_EXT`.

If validation fails, stop with a clear error.

---

## Phase 3 — Read the Implementation for Context

Before making any changes to the OAS or source code, build a complete picture of what the API actually does.

**Discover source files:**

Use Glob to find route files, controller files, middleware, and model schemas in the directories adjacent to or containing `OAS_FILE`. Typical layouts:

```
<project-root>/
  rest-api/
    routes/          ← route handlers (auth.js, productOrder.js, …)
    controllers/     ← business logic (authController.js, …)
    app.js           ← express app, route mounting, middleware chain
  shared/
    middleware/      ← auth.js — token verification logic
    models/          ← mongoose/DB schemas (User.js, Order.js, …)
```

**Read every file found in those directories.**

From the source code, record:

| What to extract | Where to look |
|---|---|
| Which routes exist (method + path) | route files and app.js `app.use(...)` mounts |
| Which routes have auth middleware applied | route files — look for `authenticate` / `auth` in route definitions |
| Which routes are intentionally public | routes with NO auth middleware |
| What request fields are accepted | route handlers and controller functions — destructured `req.body` / `req.query` fields |
| What response shape is returned | `res.json(...)` / `res.status(...).json(...)` calls — list every field |
| What status codes are returned | all `res.status(...)` calls per route |
| How authentication works | middleware — is the JWT signature verified or just decoded? what payload fields are used? |
| Authorization logic (ownership, role checks) | look for `req.user.isAdmin`, ownership comparisons — note if they are commented out |
| Model field names and types | schema definitions — use these to set accurate OAS schema constraints |

Store all of this as working context. Every fix you apply — OAS or code — must be consistent with this picture.

---

## Phase 4 — Create Temp Workspace

```bash
WORK_DIR=$(mktemp -d)
cp "$OAS_FILE" "$WORK_DIR/openapi.$OAS_EXT"
```

Keep `WORK_DIR` for the duration of the skill.

---

## Phase 0.5 — Discover Platform Credentials and Tag

**Perform this phase after Phase 4.** Collect `API_KEY`, `PLATFORM_HOST`, and `API_TAG` without hardcoding anything.

### Step A — API Key

Check the shell environment first:
```bash
[ -n "$API_KEY" ] && echo "Using API_KEY from environment"
```

If `API_KEY` is unset, walk upward from `OAS_FILE` looking for a `.env` file and extract `API_KEY` from it:

```bash
_dir="$(dirname "$OAS_FILE")"
while [ "$_dir" != "/" ]; do
  if [ -f "$_dir/.env" ]; then
    API_KEY=$(grep -E '^API_KEY=' "$_dir/.env" | head -1 | cut -d'=' -f2-)
    [ -n "$API_KEY" ] && echo "Using API_KEY from $_dir/.env" && break
  fi
  _dir="$(dirname "$_dir")"
done
```

If `API_KEY` is still unset after searching `.env` files, use the AskUserQuestion tool to prompt: `"Please enter your 42Crunch platform API key:"` and store the response as `API_KEY`.

If the user provides an empty value, stop:
```
No API key provided — cannot proceed without platform credentials.
```

### Step B — Platform Host

```bash
[ -z "$PLATFORM_HOST" ] && PLATFORM_HOST="https://demolabs.42crunch.cloud"
PLATFORM_HOST="${PLATFORM_HOST%/}"  # strip trailing slash
```

### Step C — API Tag

Walk upward from `OAS_FILE` to find `.42c/conf.yaml` and get the alias:

```bash
PROJ_ROOT=""
_dir="$(dirname "$OAS_FILE")"
while [ "$_dir" != "/" ]; do
  if [ -f "$_dir/.42c/conf.yaml" ]; then
    PROJ_ROOT="$_dir"
    break
  fi
  _dir="$(dirname "$_dir")"
done

OAS_REL="${OAS_FILE#$PROJ_ROOT/}"
API_ALIAS=$(python3 -c "
import yaml
conf = yaml.safe_load(open('$PROJ_ROOT/.42c/conf.yaml'))
entry = conf.get('apis', {}).get('$OAS_REL', {})
print(entry.get('alias', ''))
" 2>/dev/null)
```

Query the workspace SQLite DB for the tag assigned to this OAS file. The workspace DB is in a UUID-named directory under `workspaceStorage`. Find the right DB by checking which one contains a key for the 42Crunch extension:

```python
import json, os, glob, subprocess

home = os.path.expanduser("~")
ws_dir = f"{home}/Library/Application Support/Code/User/workspaceStorage"
api_tag = ""

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
        tags_data = data.get("openapi-42crunch.environment-tags-data", {})
        if OAS_FILE in tags_data:
            for tag_entry in tags_data[OAS_FILE]:
                api_tag = f"{tag_entry['categoryName']}:{tag_entry['tagName']}"
                break
        if api_tag:
            break
    except Exception:
        continue

print(api_tag)
```

Store as `API_TAG`. If empty, stop:
```
No tag found for this OAS file in the 42Crunch extension.
Apply a tag via the 42Crunch OpenAPI Editor (right-click the file → "Set Tag") then re-run.
```

### Step D — Print Credential Summary

```
Platform: <PLATFORM_HOST>
Tag:       <API_TAG>
API key:   ***<last-4-chars>
```

---

## Phase 5 — SQG-Guided Audit (Single Pass)

Run audit once with platform credentials, identify ALL SQG-blocking issues, fix them all in one batch, then verify once.

---

### Step A — Run Audit with Platform Credentials

Sync OAS to work dir first:
```bash
cp "$OAS_FILE" "$WORK_DIR/openapi.$OAS_EXT"
```

Run audit:
```bash
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

If `AUDIT_EXIT` is non-zero and neither `$WORK_DIR/todo.json` nor `$WORK_DIR/sqg.json` exists, stop:
```
Audit binary failed (exit $AUDIT_EXIT). No report was produced.
Common causes: invalid API key, platform unreachable, malformed OAS, or quota exceeded.
```

### Step B — Parse SQG Result

Read `sqg.json` (written alongside `report.json` when platform credentials are provided):

```python
import json

sqg = json.load(open(f"{WORK_DIR}/sqg.json"))
sqg_passed = sqg["acceptance"] == "yes"
sqg_name = sqg["sqgsDetail"][0]["name"]
sqg_directives = sqg["sqgsDetail"][0]["directives"]

# Blocking rules (only populated when sqg_passed == False)
blocking_rules = []
for d in sqg.get("processingDetails", []):
    blocking_rules.extend(d.get("blockingRules", []))

# SQG thresholds and forbidden IDs
forbidden_ids = set(sqg_directives.get("issueRules", []))
min_scores = sqg_directives.get("minimumAssessmentScores", {})
# e.g. {"global": 80, "dataValidation": 45, "security": 15}
```

Read `todo.json` for the full issue list:

```python
with open(f"{WORK_DIR}/todo.json") as f:
    d = json.load(f)

score = d.get("score", 0)
index = d.get("index", [])
SEVERITY = {0: "INFO", 1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}

# Map section key → SQG category name
SECTION_TO_SQG_CATEGORY = {"security": "security", "data": "dataValidation"}

issues = []
for section in ["security", "data"]:
    sqg_category = SECTION_TO_SQG_CATEGORY[section]
    # Get current category score (if available in report.json)
    # Fall back to inferring from blocking_rules
    for issue_id, issue_data in d.get(section, {}).get("issues", {}).items():
        crit = issue_data.get("criticality", 0)
        desc = issue_data.get("description", "")
        locations = issue_data.get("issues", [])
        pointers = [
            index[loc["pointer"]]
            for loc in locations
            if loc.get("pointer", -1) < len(index)
        ]
        issues.append({
            "id": issue_id,
            "section": section,
            "sqg_category": sqg_category,
            "severity": crit,
            "label": SEVERITY.get(crit, str(crit)),
            "description": desc,
            "count": len(locations),
            "pointers": pointers,
        })

issues.sort(key=lambda x: -x["severity"])
```

Print the audit result:

```
## Audit Result
Score: <score>/100
SQG: <sqg_name> — PASSED ✓ | FAILED ✗

Blocking rules:
  - minimum audit score not reached: the audit sqg expects 80, got 33.17
  - minimum data validation score not reached: the audit sqg expects 45, got 3.17
  - forbidden issues found: v3-schema-request-string-pattern
  - forbidden issues found: v3-schema-request-object-additionalproperties-true
```

**If `sqg_passed`:** print `SQG already passes — no OAS changes needed.` → jump to Phase 6.

---

### Step C — Build SQG-Scoped Fix Plan

Classify each issue as SQG-blocking or not:

```python
# Parse blocking_rules to determine which score categories are below threshold
# e.g. "minimum data validation score not reached: the audit sqg expects 45, got 3.17"
# → the "dataValidation" category is below threshold
import re

low_score_categories = set()
for rule in blocking_rules:
    m = re.match(r"minimum (\w[\w ]*?) score not reached", rule)
    if m:
        cat_phrase = m.group(1).strip()
        # Map phrase to SQG category key
        if cat_phrase == "audit":
            # "minimum audit score" = global threshold → all issues contribute
            low_score_categories.add("global")
        elif cat_phrase == "data validation":
            low_score_categories.add("dataValidation")
        elif cat_phrase == "security":
            low_score_categories.add("security")

fix_issues = []
skip_issues = []

for issue in issues:
    reason = None
    if issue["id"] in forbidden_ids:
        reason = "forbidden by SQG"
    elif "global" in low_score_categories:
        reason = f"contributes to overall score ({score:.1f} < {min_scores.get('global', '?')})"
    elif issue["sqg_category"] in low_score_categories:
        cat = issue["sqg_category"]
        reason = f"{cat} score below SQG threshold (< {min_scores.get(cat, '?')})"

    if reason:
        fix_issues.append({**issue, "sqg_reason": reason})
    else:
        skip_issues.append(issue)
```

Print the plan:

```
## Fix Plan (SQG-scoped)
Fixing <n> SQG-blocking issues | Skipping <m> non-blocking issues

Will fix:
  [CRITICAL] v3-schema-request-string-pattern  ← forbidden by SQG
  [HIGH]     v3-schema-request-body-username-maxlength  ← data validation score 3.17 < 45
  ...

Skipping (not SQG-blocking):
  [MEDIUM]   v3-schema-response-string-pattern — not referenced in blocking rules
  ...
```

**If `fix_issues` is empty:** print the skip list and jump to Phase 6 — no OAS changes can be made.

---

### Step D — Apply All Fixes at Once

Back up the OAS file:
```bash
BACKUP=$(mktemp "/tmp/42c-sqg-audit-XXXXXX.$OAS_EXT")
cp "$OAS_FILE" "$BACKUP"
```

Apply **all** `fix_issues` using the Edit tool in rapid succession — no pauses between edits.

For each fix:
- For `v3-schema-*` issues: use the fix patterns in [references/report-guide.md](references/report-guide.md).
- For `global-*` issues: fetch the KDB at `https://platform.42crunch.com/kdb/audit-with-yaml.json` (only once, only if `global-*` IDs are present) and use the `remediation` field.
- Use Phase 3 context to make the fix accurate:
  - Auth scheme type, name, and `bearerFormat` must match what the middleware actually implements.
  - Response schemas must match what the routes actually return (`res.json(...)` field names and types).
  - Request body schemas must reflect what the routes validate (`req.body` destructuring).
  - Per-operation `security` overrides must match whether that specific route has auth middleware applied.
- One Edit call per logical fix. Do not batch unrelated changes into one edit.
- Preserve file formatting: indentation, key order, comments.

Show the diff after all edits:
```bash
git diff "$OAS_FILE"
```

If the diff is empty despite issues being listed, stop and explain — do not proceed.

---

### Step E — Verification Audit

Sync edits to work dir and re-run audit once to confirm SQG acceptance:

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

Read the new `sqg.json`:

```python
sqg_verify = json.load(open(f"{WORK_DIR}/sqg.json"))
sqg_passed_verify = sqg_verify["acceptance"] == "yes"
verify_score = json.load(open(f"{WORK_DIR}/report-verify.json")).get("score", 0)
remaining_blocking = []
for d in sqg_verify.get("processingDetails", []):
    remaining_blocking.extend(d.get("blockingRules", []))
```

Print:
```
## Audit Verification
Score: <verify_score>/100
SQG: <PASSED ✓ | FAILED ✗>

Remaining blocking rules (if any):
  - <rule>
```

If still failing, list remaining blocking rules — these require manual decisions. Proceed to Phase 6 regardless.

`rm "$BACKUP"`

---

## Phase 6 — SQG-Guided Scan and Code Remediation

Always runs after Phase 5. Skip to Phase 7 only if no base URL can be resolved.

---

### Step A — Resolve Base URL

Determine the scan target host in priority order. Stop at the first non-empty value:

```bash
BASE_URL=""
BASE_URL_SOURCE=""

# 1. Explicit argument from user
[ -n "$ARGUMENTS[1]" ] && BASE_URL="$ARGUMENTS[1]" && BASE_URL_SOURCE="argument"

# 2. SCAN42C_HOST already set in the shell environment
[ -z "$BASE_URL" ] && [ -n "$SCAN42C_HOST" ] && BASE_URL="$SCAN42C_HOST" && BASE_URL_SOURCE="SCAN42C_HOST env"

# 3. Extract servers[0].url from the OAS file (JSON)
if [ -z "$BASE_URL" ]; then
  BASE_URL=$(python3 -c "
import json, sys
try:
    d = json.load(open('$OAS_FILE'))
    servers = d.get('servers', [])
    if servers:
        print(servers[0].get('url', ''))
except Exception:
    pass
" 2>/dev/null)
  [ -n "$BASE_URL" ] && BASE_URL_SOURCE="OAS servers[0].url"
fi

# Strip trailing slash
BASE_URL="${BASE_URL%/}"
```

**If `BASE_URL` is still empty:** skip to Phase 7, record `Conformance: skipped — no base URL resolvable`.

**Otherwise:** print `Using base URL: <BASE_URL>  (source: <BASE_URL_SOURCE>)`

---

### Step A.5 — Verify API Reachability

```bash
if ! curl -s --max-time 8 --head "$BASE_URL" >/dev/null 2>&1; then
  echo "Warning: Cannot reach $BASE_URL — skipping conformance scan."
  # Jump to Phase 7, record: Conformance: skipped — API not reachable
fi
```

Only proceed to Step B if this check passes.

---

### Step B — Locate or Generate the Scan Configuration

#### Part 1 — Locate existing scanconf via `.42c/conf.yaml`

```bash
SCANCONF=""
API_ALIAS=""

PROJ_ROOT=""
_dir="$(dirname "$OAS_FILE")"
while [ "$_dir" != "/" ]; do
  if [ -f "$_dir/.42c/conf.yaml" ]; then
    PROJ_ROOT="$_dir"
    break
  fi
  _dir="$(dirname "$_dir")"
done

if [ -n "$PROJ_ROOT" ]; then
  OAS_REL="${OAS_FILE#$PROJ_ROOT/}"
  API_ALIAS=$(python3 -c "
import yaml
conf = yaml.safe_load(open('$PROJ_ROOT/.42c/conf.yaml'))
entry = conf.get('apis', {}).get('$OAS_REL', {})
print(entry.get('alias', ''))
" 2>/dev/null)
fi

if [ -n "$API_ALIAS" ]; then
  CANDIDATE="$PROJ_ROOT/.42c/scan/$API_ALIAS/scanconf.json"
  [ -f "$CANDIDATE" ] && SCANCONF="$CANDIDATE"
fi

if [ -z "$SCANCONF" ]; then
  SCANCONF=$(find "${PROJ_ROOT:-$(dirname "$OAS_FILE")}" \
    -path "*/.42c/scan/*/scanconf.json" 2>/dev/null | head -1)
fi
```

If an existing scanconf was found, use it. Print:
```
Using existing scan config: <SCANCONF>  (alias: <API_ALIAS>)
```
Then skip to Step C.

#### Part 2 — Generate base scanconf (no existing config found)

```bash
"$AST_BIN" scan conf generate "$WORK_DIR/openapi.$OAS_EXT" \
  --output "$WORK_DIR/scanconf.json" \
  --output-format json
SCANCONF="$WORK_DIR/scanconf.json"
```

#### Part 2b — Detect authentication mode

```python
import json
scanconf = json.load(open("$WORK_DIR/scanconf.json"))
scheme_name = list(scanconf["authenticationDetails"][0].keys())[0]
creds = scanconf["authenticationDetails"][0][scheme_name]["credentials"]
first_cred = creds[list(creds.keys())[0]]
auth_mode = "static" if "credential" in first_cred else "dynamic"
```

#### Part 3 — Analyze OAS for BOLA/BFLA candidates

Read `$OAS_FILE` and inspect every operation in `paths`:

**BOLA candidates** — authenticated operations on individual resources by ID:
- Method is `GET`, `PATCH`, `PUT`, or `DELETE`
- Path contains at least one `{paramName}` path parameter
- The operation has a security requirement

**BFLA candidates** — potentially privileged/admin-only operations:
- Operation `description`, `summary`, or `operationId` contains: `admin`, `delete user`, `manage`
- OR: method is `DELETE` on a path matching `/users/{id}` or `/auth/user/{id}` pattern

Print:
```
## Authorization Risk Analysis
BOLA candidates: [<METHOD> <path>] <operationId>
BFLA candidates: [<METHOD> <path>] <operationId>
```

#### Part 4 — Ask for credentials (if generated scanconf only)

If an existing scanconf was found (Step B Part 1 succeeded), skip to Step C — it already has credentials configured.

If generated, ask for credentials depending on `auth_mode` and BOLA/BFLA findings (same prompts as `api-security-remediate` skill Step B Part 4).

#### Part 5 — Inject authorization tests (if generated scanconf only)

If generated, inject BOLA/BFLA authorization tests into the scanconf (same logic as `api-security-remediate` skill Step B Part 5).

---

### Step C — Run the Scan with Platform Credentials

```bash
rm -f "$WORK_DIR/scan-report.json"
```

Capture both stdout and the report file — the SQG result is ONLY in stdout:

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
SCAN_EXIT=$?
```

If `AUTH_MODE=static` (generated scanconf), prepend the collected token env vars before `API_KEY`:
```bash
SCAN42C_SECURITY_USERTOKEN="$TOKEN_USER" \
SCAN42C_SECURITY_USER2TOKEN="$TOKEN_USER2" \
SCAN42C_SECURITY_ADMINTOKEN="$TOKEN_ADMIN" \
API_KEY="$API_KEY" PLATFORM_HOST="$PLATFORM_HOST" \
...
```

**After the scan completes, reset the database** to remove test residues:

```bash
_db_reset=""
_dir="$(dirname "$OAS_FILE")"
while [ "$_dir" != "/" ]; do
  if [ -f "$_dir/scripts/reset_database.sh" ]; then
    _db_reset="$_dir/scripts/reset_database.sh"
    break
  fi
  _dir="$(dirname "$_dir")"
done

if [ -n "$_db_reset" ]; then
  echo "==> Resetting database to clean scan residues..."
  bash "$_db_reset"
fi
```

---

### Step D — Parse Scan SQG from Stdout

The SQG result is NOT in `scan-report.json` — it is in the binary stdout JSON:

```python
import json

cli_output = json.loads(SCAN_STDOUT) if SCAN_STDOUT.strip() else {}
scan_sqg_passed = cli_output.get("sqgPass")    # True / False / None
scan_sqg_details = cli_output.get("sqgDetails", [])

# Extract all blocking rules
scan_blocking_rules = []
for d in scan_sqg_details:
    scan_blocking_rules.extend(d.get("blockingRules", []))
# e.g. ["severity_threshold", "forbidden_test:authentication-swapping-bfla"]
```

Also parse `scan-report.json` for conformance details:

```python
scan_report = json.load(open(f"{WORK_DIR}/scan-report.json"))
summary = scan_report.get("summary", {})
```

Print the scan result:

```
## Scan Results
Target: <BASE_URL>
State: <summary.state>
Operations: <success> passed | <happyPathFailure> happy-path failures | <executed.failed> failed
Issues: Critical: <n> | High: <n> | Medium: <n> | Low: <n>

SQG: <PASSED ✓ | FAILED ✗>

SQG Blocking rules:
  - severity_threshold
  - forbidden_test:authentication-swapping-bfla
```

**If `scan_sqg_passed` is `True` or `None` (no SQG applied):** print `Scan SQG passed — no code changes needed.` and jump to Phase 7.

---

### Step E — Build SQG-Scoped Code Fix Plan

Map each `blockingRule` to what needs to be fixed in the code:

```python
# severity_threshold → fix all HIGH and CRITICAL conformance issues from scan-report.json
# forbidden_test:<test-key> → fix the specific authorization test issue

issue_type_counters = (
    summary.get("issues", {})
    .get("issueTypeCounters", {})
)

fix_issue_types = set()
for rule in scan_blocking_rules:
    if rule == "severity_threshold":
        # Collect all high/critical issue types from scan-report.json
        for category in issue_type_counters.values():
            for issue_type in category.keys():
                fix_issue_types.add(issue_type)
    elif rule.startswith("forbidden_test:"):
        test_key = rule.split(":", 1)[1]
        fix_issue_types.add(test_key)
```

Print the scoped code fix plan:

```
## Code Fix Plan (SQG-scoped)
Blocking rules to address:
  - severity_threshold → will fix all critical/high conformance issues
  - forbidden_test:authentication-swapping-bfla → will fix BFLA authorization check

Issues to fix:
  authentication-swapping-bfla: <n> operations
  schema-type-wrong-boolean: <n> operations
  ...

Issues NOT in SQG scope (skipping):
  method-not-allowed: <n>  (not referenced by blocking rules)
```

---

### Step F — Apply SQG-Scoped Code Fixes

For each issue type in `fix_issue_types`, apply the code fix. Use implementation context from Phase 3.

**Issue type → code fix mapping:**

| Issue Type | Root Cause | Code Fix |
|---|---|---|
| `authentication-swapping-bola` | User A can access User B's resource (ownership not enforced) | After fetching the resource, compare its owner field to `req.user.customerId`; return 403 if they differ |
| `authentication-swapping-bfla` | Non-privileged user can reach a privileged operation | Add a role check: `if (!req.user.isAdmin) return res.status(403).json(...)` |
| `partial-security-accepted` | Auth middleware accepts JWTs without full signature verification | **May be intentional.** Check Phase 3 context — if `jwt.decode()` is used deliberately and documented, leave it and annotate it; otherwise replace with `jwt.verify(token, secret)` |
| `schema-type-wrong-*` / `schema-maxlength-scan` / `schema-pattern-scan` / `schema-minlength-scan` / `schema-required-scan` / `schema-additionalproperties-scan` | No server-side input validation | Create shared validation matching every OAS schema constraint; call at the top of each route handler |
| `parameter-header-contenttype-wrong-scan` | Server accepts wrong or missing `Content-Type` | Add global middleware: reject without `Content-Type: application/json` with 415 |
| `security-scheme-not-enforced` | Route accessible without a valid auth token | Add auth middleware to the route |
| `response-body-conformance` | `res.json(...)` returns undeclared fields | Return exactly the fields in the OAS response schema |
| `response-status-conformance` | Route returns undeclared status code | Use the correct status code |

For each fix:
1. Print: `Fixing <issue-type> in <file> — <route> (SQG blocking rule: <rule>)`
2. Use the **Edit tool** — minimal change, match existing code style, add brief inline comment for security fixes.
3. If already fixed: print `Already implemented — skipping.`

After all code fixes:
```
## Code Fixes Applied
<n> files modified:
  <relative-path>: <description>
```

---

### Step F.5 — Rebuild the API

Walk upward from `OAS_FILE` to locate `scripts/manage.sh`:

```bash
_manage=""
_dir="$(dirname "$OAS_FILE")"
while [ "$_dir" != "/" ]; do
  if [ -f "$_dir/scripts/manage.sh" ]; then
    _manage="$_dir/scripts/manage.sh"
    break
  fi
  _dir="$(dirname "$_dir")"
done

if [ -n "$_manage" ]; then
  echo "==> Rebuilding API..."
  bash "$_manage" rest rebuild
  REBUILD_EXIT=$?
else
  echo "Note: scripts/manage.sh not found — restart the server manually before verification."
fi
```

---

### Step G — Verify Rebuild and Re-scan

**Step G1 — Confirm new code is live**

If `$REBUILD_EXIT` is non-zero, skip probe and print the stale-server warning — do NOT run verification scan.

Otherwise, probe a sentinel behaviour that distinguishes old code from new. If the server is stale, stop and print:
```
⚠️  Rebuild completed but server is still serving old code.
Restart the server manually, then re-run: /api-security-sqg <oas-file>
Code changes applied (pending live pickup): <list>
```

**Step G2 — Run verification scan**

Re-run the scan command from Step C, saving output to `$WORK_DIR/verify-scan-report.json` and capturing stdout as `VERIFY_STDOUT`.

Parse `sqgPass` from `VERIFY_STDOUT`. Compare scan issues between first and verify runs:

```
## Verification Scan Results
Scan SQG: <PASSED ✓ | FAILED ✗>

Resolved: <n> SQG-blocking issues fixed
Remaining: <n> still present
New issues introduced: <n>  (flag if > 0)
```

After verification, reset the database again:
```bash
[ -n "$_db_reset" ] && bash "$_db_reset"
```

---

## Phase 7 — Cleanup and Final Report

```bash
rm -rf "$WORK_DIR"
SKILL_END=$(date +%s)
ELAPSED=$(( SKILL_END - SKILL_START ))
ELAPSED_MINS=$(( ELAPSED / 60 ))
ELAPSED_SECS=$(( ELAPSED % 60 ))
```

```
## Final Report

OAS File:       <OAS_FILE>
Tag:            <API_TAG>
Platform:       <PLATFORM_HOST>
SQG (Audit):    <sqg_name>

Audit SQG:      <PASSED ✓ | FAILED ✗>
  Score:        <verify_score>/100  (was: <initial_score>/100)
  OAS Fixes:    <n> SQG-scoped applied | <m> non-blocking skipped

Scan SQG:       <PASSED ✓ | FAILED ✗>  (or "skipped — no base URL / API not reachable")
  Code Fixes:   <n> SQG-scoped applied | <m> non-blocking skipped
  Verification: <n> resolved / <n> remaining  (or "not run")

Total Time:     <ELAPSED_MINS>m <ELAPSED_SECS>s

### Remaining Manual Items (if any)
<blocking rule>
  Why: <explanation>
  Suggested action: <guidance>
```

---

## Invariants

- **Never hardcode** paths, usernames, or machine-specific strings — always use shell variables.
- **Context before fixes** — every OAS edit must be consistent with what the implementation actually does.
- **SQG scope only** — do not fix issues that are not referenced by SQG blocking rules. Scope creep undermines the purpose of this skill.
- **One Edit call per logical fix** — do not batch unrelated changes.
- **YAML/JSON fidelity** — match existing file indentation, preserve comments and key order.
- **Surgical code fixes** — change only what is necessary. Do not refactor surrounding code.
- **Scan SQG lives in stdout** — `scan-report.json` has no SQG fields. Always capture and parse the binary stdout JSON.
- For full field reference of `report.json`, `sqg.json`, and `scan-report.json`, see [references/report-guide.md](references/report-guide.md).
