---
name: api-security-remediate
description: >
  End-to-end 42Crunch API security hardening: run the audit tool (`42c-ast`) on an
  OpenAPI spec and iteratively fix all flagged issues until the security score reaches
  100/100, then run a conformance scan against the live API and fix implementation
  vulnerabilities (BOLA, BFLA, missing validation, Content-Type enforcement) in source code.

  Trigger this skill when the user wants to: run full API security remediation end-to-end,
  audit AND scan an OpenAPI spec, fix both OAS issues and code vulnerabilities in one pass,
  get to 100/100 audit score and then verify the live API, or do complete 42Crunch security
  hardening — even if "42Crunch" is not mentioned by name.

  Strong trigger phrases: "/api-security-remediate", "full api security remediation",
  "audit and scan my api", "fix everything end to end", "run both audit and scan",
  "42crunch full remediation", "harden my api completely".

  Do NOT trigger for: running only an audit (use `audit-remediate`), running only
  a conformance scan (use `scan-remediate`), fixing BOLA/BFLA in source code only,
  debugging JWT middleware, reviewing OpenAPI specs for style or readability, converting
  Swagger to OpenAPI, or generating specs from code.
disable-model-invocation: true
argument-hint: <oas-file-path> [api-base-url]
---

# API Security Remediate Skill

End-to-end API security hardening using the `42c-ast` binary:

1. **Audit loop** — run audit, fix all issues, re-audit, repeat until score is 100/100.
2. **Conformance scan** — run a scan against the live API and fix implementation issues in source code.

**Usage:**
- `/api-security-remediate openapi.json` — audit + iterative OAS fixes to 100/100 + conformance scan (base URL auto-detected from OAS `servers[0].url`)
- `/api-security-remediate openapi.json https://localhost:8080` — same, with explicit base URL override

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

If `AST_BIN` is still empty, stop and tell the user:

> `42c-ast` was not found. Install the **42Crunch OpenAPI Editor** VSCode extension (publisher: `42crunch`). It bundles the binary at `~/.42crunch/bin/42c-ast`.

Generate a unique run identifier for all binary calls. Using `--org local` hits a freemium `limits_reached` error; a unique org name avoids it. Also record the skill start time for the final report:

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

Before making any changes to the OAS or source code, build a complete picture of what the API actually does. This context is required to produce correct, non-breaking fixes in both the OAS and code phases.

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

Keep `WORK_DIR` for the duration of the skill. The audit binary reads from here; all OAS fixes are applied to `OAS_FILE` directly via the Edit tool.

---

## Phase 5 — Audit + Fix Iteration Loop

Run this loop until the audit score reaches **100/100** or it becomes clear no further auto-remediable issues remain. Cap at **10 iterations** to prevent runaway loops.

Initialize: `ITERATION=1`. Fetch the KDB only if a `global-*` issue ID appears in the report — the KDB contains no `v3-schema-*` entries, so fetching it for schema-only reports wastes tokens.

---

### Step A — Run the Audit

First, sync any OAS edits from the previous iteration into the work directory (required for every iteration, not just the first):

```bash
cp "$OAS_FILE" "$WORK_DIR/openapi.$OAS_EXT"
```

Then run the audit:

```bash
"$AST_BIN" audit run "$WORK_DIR/openapi.$OAS_EXT" \
  --output "$WORK_DIR/report.json" \
  --output-format json \
  --enrich=false \
  --verbose error \
  --org "$RUN_ID" --repo "$RUN_ID" --user "$RUN_ID"
AUDIT_EXIT=$?
```

If `AUDIT_EXIT` is non-zero **and** `$WORK_DIR/todo.json` does not exist, stop immediately:
```
Audit binary failed (exit $AUDIT_EXIT). No report was produced.
Common causes: malformed OAS, network error reaching the platform, or quota exceeded.
```
If `todo.json` exists despite a non-zero exit, continue — the binary sometimes exits non-zero on partial results.

Parse `$WORK_DIR/todo.json` (written alongside `report.json`) — it contains the same issues but includes the `index[]` array that maps integer pointers to OAS paths (see [references/report-guide.md](references/report-guide.md)):

```python
import json

with open(f"{WORK_DIR}/todo.json") as f:
    d = json.load(f)

score = d.get("score", 0)
index = d.get("index", [])
SEVERITY = {0: "INFO", 1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}

issues = []
for section in ["security", "data"]:
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
            "id": issue_id, "severity": crit,
            "label": SEVERITY.get(crit, str(crit)),
            "description": desc, "count": len(locations), "pointers": pointers,
        })

issues.sort(key=lambda x: -x["severity"])
```

Display the iteration header and issue list:

```
## Audit — Iteration <ITERATION>
Score: <score>/100
Critical: <n> | High: <n> | Medium: <n> | Low: <n> | Info: <n>

Issues:
  [CRITICAL] <id>: <description>  (<first OAS path>)
  [HIGH]     <id>: <description>  (<first OAS path>)
  ...
```

**If `score == 100`:** print `Score reached 100/100 after <ITERATION> iteration(s).` and jump to Phase 6.

---

### Step B — Fetch KDB (only when `global-*` issues are present)

The KDB at `https://platform.42crunch.com/kdb/audit-with-yaml.json` contains **only `global-*` entries** (authentication, transport, OAuth). It has no `v3-schema-*` entries.

- **If no `global-*` issue IDs appear in the current iteration's issues:** skip this step entirely — the `v3-schema-*` fix patterns are in [references/report-guide.md](references/report-guide.md).
- **If at least one `global-*` issue is present:** fetch the KDB once using WebFetch, cache as `KDB`. Do NOT re-fetch on subsequent iterations.

Each KDB entry is keyed by issue ID and contains: `title`, `shortDescription`, `description`, `example`, `exploit`, `remediation` (HTML with YAML/JSON code blocks), `group`, `subgroup`.

---

### Step C — Build the Fix Plan

From the current iteration's issues:

1. **Deduplicate** by `id` — the same issue ID may appear at multiple `pointer` locations but requires only one root-level fix.
2. **Sort by severity**: Critical → High → Medium → Low → Info.
3. **Classify each issue** using the fix patterns in [references/report-guide.md](references/report-guide.md) (for `v3-schema-*`) or the KDB (for `global-*`), combined with implementation context from Phase 3:
   - **Auto-remediable** — a clear, unambiguous schema or security definition change. No user decision needed.
   - **Context-resolved** — the correct fix depends on how the implementation works (e.g., which auth scheme matches the middleware; which fields the route actually validates). Use Phase 3 context to resolve.
   - **Manual** — requires a user decision that cannot be inferred from code (e.g., choosing between multiple auth strategies when the implementation is ambiguous).

Print the plan:

```
## Fix Plan — Iteration <ITERATION>
<n> fixable issues | <m> manual (will skip)

Will fix:
  [CRITICAL] <id>: <title>
  [HIGH]     <id>: <title>
  ...

Skipping (manual decision required):
  [HIGH] <id>: <title> — <reason>
  ...
```

**If there are no fixable issues** in this iteration, print the manual list and jump to Phase 6.

---

### Step D — Apply Fixes

Fixes are applied in bulk: all fixable issues for the iteration at once, then a diff is shown for review.

1. Back up the OAS file before this iteration's edits:
   ```bash
   BACKUP=$(mktemp "/tmp/42c-iter${ITERATION}-XXXXXX.$OAS_EXT")
   cp "$OAS_FILE" "$BACKUP"
   ```

2. Apply all fixable issues to `OAS_FILE` using the Edit tool in rapid succession — no pauses between edits.

   For each fix:
   - For `v3-schema-*` issues: use the fix patterns in [references/report-guide.md](references/report-guide.md). For `global-*` issues: use the KDB `remediation` field.
   - Use Phase 3 context to make the fix accurate:
     - Auth scheme type, name, and `bearerFormat` must match what the middleware actually implements.
     - Response schemas must match what the routes actually return (`res.json(...)` field names and types).
     - Request body schemas must reflect what the routes validate (`req.body` destructuring).
     - Per-operation `security` overrides must match whether that specific route has auth middleware applied.
   - One Edit call per logical fix. Do not batch unrelated changes into one edit.
   - Preserve file formatting: indentation, key order, comments.

3. Show the diff inline immediately after all edits:
   ```bash
   git diff "$OAS_FILE"
   ```

4. **Auto-proceed rules** — do NOT prompt the user unless one of these is true:
   - The diff is **empty** (no lines changed despite issues being listed — something went wrong).
   - The diff contains **conflict markers** (`<<<<<<<`, `=======`, `>>>>>>>`).

   In either case, stop and explain what happened. Ask the user how to proceed.

   Otherwise: `rm "$BACKUP"` → increment `ITERATION` → go to Step A. No user confirmation needed.

---

### Step E — Stop Conditions

The loop ends when any of these are true:
- **Score == 100** — success.
- **No fixable issues** remain in the current iteration — only manual items left.
- **ITERATION > 10** — safeguard against infinite loops.

In all non-100 exit cases, continue to Phase 6 and list the remaining manual issues.

---

## Phase 6 — Conformance Scan and Code Remediation

Always runs after the audit loop completes. Skip to Phase 7 only if no base URL can be resolved (see Step A).

---

### Step A — Resolve Base URL

Determine the scan target host in priority order. Stop at the first non-empty value:

```bash
BASE_URL=""
BASE_URL_SOURCE=""

# 1. Explicit argument from user
[ -n "" ] && BASE_URL="" && BASE_URL_SOURCE="argument"

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

# 4. Fallback: YAML OAS
if [ -z "$BASE_URL" ]; then
  BASE_URL=$(python3 -c "
import yaml, sys
try:
    d = yaml.safe_load(open('$OAS_FILE'))
    servers = d.get('servers', [])
    if servers:
        print(servers[0].get('url', ''))
except Exception:
    pass
" 2>/dev/null)
  [ -n "$BASE_URL" ] && BASE_URL_SOURCE="OAS servers[0].url"
fi

# Strip trailing slash to prevent double-slash URLs (e.g. https://host//path)
BASE_URL="${BASE_URL%/}"
```

**If `BASE_URL` is still empty:** print the following, skip to Phase 7, and record `Conformance: skipped — no base URL resolvable` in the final report.

```
Warning: No base URL could be determined (no , no $SCAN42C_HOST, and no servers[0].url in the OAS).
Skipping conformance scan. To run it, re-invoke with: /api-security-remediate <oas-file> <base-url>
```

**Otherwise**, print:
```
Using base URL: <BASE_URL>  (source: <BASE_URL_SOURCE>)
```

---

### Step A.5 — Verify API Reachability

Before proceeding to scanconf setup and credential collection, confirm the target is actually up:

```bash
if ! curl -s --max-time 8 --head "$BASE_URL" >/dev/null 2>&1; then
  echo "Warning: Cannot reach $BASE_URL (connection refused or timeout after 8s)"
  echo "Skipping conformance scan — start the API server and re-run with the base URL to scan."
  # Jump to Phase 7, record: Conformance: skipped — API not reachable at <BASE_URL>
fi
```

Only proceed to Step B if this check passes.

---

### Step B — Locate or Generate the Scan Configuration

#### Part 1 — Locate an existing scanconf via `.42c/conf.yaml`

The `.42c/conf.yaml` file maps each OAS file path (relative to project root) to an alias. The scan config for that OAS lives at `.42c/scan/<alias>/scanconf.json`. Walk upward from `OAS_FILE` to find `conf.yaml`, derive the alias, then construct the deterministic path. Fall back to a broad `find` only when `conf.yaml` is absent or the OAS is not listed.

```bash
SCANCONF=""
API_ALIAS=""

# 1. Walk upward from OAS_FILE to find the project root containing .42c/conf.yaml
PROJ_ROOT=""
_dir="$(dirname "$OAS_FILE")"
while [ "$_dir" != "/" ]; do
  if [ -f "$_dir/.42c/conf.yaml" ]; then
    PROJ_ROOT="$_dir"
    break
  fi
  _dir="$(dirname "$_dir")"
done

# 2. If conf.yaml found, extract the alias for this OAS file
if [ -n "$PROJ_ROOT" ]; then
  OAS_REL="${OAS_FILE#$PROJ_ROOT/}"
  API_ALIAS=$(python3 -c "
import yaml, sys
conf = yaml.safe_load(open('$PROJ_ROOT/.42c/conf.yaml'))
apis = conf.get('apis', {})
entry = apis.get('$OAS_REL', {})
print(entry.get('alias', ''))
" 2>/dev/null)
fi

# 3. If alias found, construct the deterministic scanconf path
if [ -n "$API_ALIAS" ]; then
  CANDIDATE="$PROJ_ROOT/.42c/scan/$API_ALIAS/scanconf.json"
  [ -f "$CANDIDATE" ] && SCANCONF="$CANDIDATE"
fi

# 4. Fallback — broad find (no conf.yaml, OAS not listed, or scanconf missing)
if [ -z "$SCANCONF" ]; then
  SCANCONF=$(find "${PROJ_ROOT:-$(dirname "$OAS_FILE")}" \
    -path "*/.42c/scan/*/scanconf.json" 2>/dev/null | head -1)
fi
```

If an existing scanconf was found, use it — it already has authentication credentials, scenario chains, and authorization tests configured. Print:
```
Using existing scan config: <SCANCONF>  (alias: <API_ALIAS>)
```
Then skip to Step C.

---

#### Part 2 — Generate base scanconf (no existing config found)

```bash
"$AST_BIN" scan conf generate "$WORK_DIR/openapi.$OAS_EXT" \
  --output "$WORK_DIR/scanconf.json" \
  --output-format json
SCANCONF="$WORK_DIR/scanconf.json"
```

---

#### Part 2b — Detect authentication mode

Read `$WORK_DIR/scanconf.json` and inspect the first credential entry under `authenticationDetails[0].{schemeName}.credentials.{firstKey}`:

- **`"credential"` key present** (flat `"{{varName}}"` string, no `requests[]`) → **static token mode**: the scan reads a pre-obtained bearer token from a `SCAN42C_SECURITY_*` env var
- **`"requests"` key present** (login flow array) → **dynamic login mode**: the scan logs in automatically using username/password

```python
import json
scanconf = json.load(open("$WORK_DIR/scanconf.json"))
scheme_name = list(scanconf["authenticationDetails"][0].keys())[0]  # e.g. "bearerAuth"
creds = scanconf["authenticationDetails"][0][scheme_name]["credentials"]
first_cred = creds[list(creds.keys())[0]]
auth_mode = "static" if "credential" in first_cred else "dynamic"
# For static mode, find the env var name for the token
if auth_mode == "static":
    env_vars = scanconf["environments"]["default"]["variables"]
    token_var_name = env_vars[list(env_vars.keys())[0]]["name"]  # e.g. "SCAN42C_SECURITY_BEARERAUTH"
```

Store as `AUTH_MODE` and `SCHEME_NAME`. Print:
```
Authentication mode: static token  (requires SCAN42C_SECURITY_<SCHEME> env var)
```
or
```
Authentication mode: dynamic login  (scan logs in using provided credentials)
```

---

#### Part 3 — Analyze OAS for BOLA/BFLA candidates

Read `$OAS_FILE` and inspect every operation in `paths`:

**BOLA candidates** — authenticated operations on individual resources by ID:
- Method is `GET`, `PATCH`, `PUT`, or `DELETE`
- Path contains at least one `{paramName}` path parameter
- The operation has a security requirement

**BFLA candidates** — potentially privileged/admin-only operations:
- Operation `description`, `summary`, or `operationId` contains: `admin`, `delete user`, `manage`
- OR: method is `DELETE` on a path matching `/users/{id}` or `/auth/user/{id}` pattern
- OR: operation is explicitly described as administrator-only

Display the findings:

```
## Authorization Risk Analysis

BOLA candidates (authenticated operations on individual resources by ID):
  [<METHOD> <path>] <operationId>

BFLA candidates (potentially privileged operations):
  [<METHOD> <path>] <operationId>
```

If no candidates are found for either type, proceed to Step C with the basic generated scanconf — no credential prompt needed.

---

#### Part 4 — Ask for credentials

The prompt and what the user must supply depends on `AUTH_MODE`.

**If `AUTH_MODE=static`** — print only the sections relevant to risks found:

```
This scan config uses static token authentication (no automated login).
Please provide bearer tokens for the accounts needed:

Primary user token (used for all authenticated operations):
  Bearer token: <wait>

[if BOLA found]
User 2 token (the BOLA test will use this token to attempt accessing user 1's resources):
  User 2 bearer token: <wait>

[if BFLA found]
Admin token (the BFLA test will use the primary user token to attempt this admin operation):
  Admin bearer token: <wait>
```

Store as `TOKEN_USER`, and optionally `TOKEN_USER2` (BOLA), `TOKEN_ADMIN` (BFLA).

**If `AUTH_MODE=dynamic`** — print only the sections relevant to risks found:

```
This scan config uses dynamic login. Please provide credentials:

User 1 (primary user — used for all authenticated happy-path operations):
  Username: <wait>
  Password: <wait>

[if BOLA found]
User 2 (attacker — used by the BOLA test):
  Username: <wait>
  Password: <wait>

[if BFLA found]
Admin user (used by the BFLA test):
  Username: <wait>
  Password: <wait>

Note: User 1 and the BFLA regular-user role are often the same account.
```

Store as `USER1_USERNAME`, `USER1_PASSWORD`, and optionally `USER2_USERNAME`/`USER2_PASSWORD` (BOLA), `ADMIN_USERNAME`/`ADMIN_PASSWORD` (BFLA).

---

#### Part 5 — Inject authorization tests into the generated scanconf

Read `$WORK_DIR/scanconf.json` using Python and apply modifications based on `AUTH_MODE`.

**5a — Build credential entries**

*Static token mode:*

Rename the default credential to `user` and assign a new env var for its token. Add additional entries for `user2` (BOLA) and `admin` (BFLA), each referencing their own env var. Register all new vars in `environments.default.variables`. Remove the original default credential key:

```python
import json, copy
scanconf = json.load(open("$WORK_DIR/scanconf.json"))
scheme_name = list(scanconf["authenticationDetails"][0].keys())[0]
creds = scanconf["authenticationDetails"][0][scheme_name]["credentials"]
env_vars = scanconf["environments"]["default"]["variables"]
original_key = list(creds.keys())[0]  # e.g. "bearerAuth"

creds["user"] = {"description": "Primary user token", "credential": "{{userToken}}"}
env_vars["userToken"] = {"from": "environment", "name": "SCAN42C_SECURITY_USERTOKEN", "required": True}

if BOLA_FOUND:
    creds["user2"] = {"description": "User 2 token (BOLA)", "credential": "{{user2Token}}"}
    env_vars["user2Token"] = {"from": "environment", "name": "SCAN42C_SECURITY_USER2TOKEN", "required": True}

if BFLA_FOUND:
    creds["admin"] = {"description": "Admin token (BFLA)", "credential": "{{adminToken}}"}
    env_vars["adminToken"] = {"from": "environment", "name": "SCAN42C_SECURITY_ADMINTOKEN", "required": True}

if original_key not in ("user", "user2", "admin"):
    del creds[original_key]
    del env_vars[original_key]  # remove old var mapping too if it existed
```

After the scan config is saved, print the env vars the user must set before running the scan:
```
Before running the scan, set:
  SCAN42C_SECURITY_USERTOKEN=<primary user token>
  SCAN42C_SECURITY_USER2TOKEN=<user 2 token>    [if BOLA]
  SCAN42C_SECURITY_ADMINTOKEN=<admin token>      [if BFLA]
```

*Dynamic login mode:*

Clone the default credential (which has `requests[]`) for each named user. Detect the username/password keys dynamically — the keys in `requests[].environment` whose names hint at username/password:

```python
default_cred = copy.deepcopy(creds[list(creds.keys())[0]])

def make_cred(username, password):
    c = copy.deepcopy(default_cred)
    for req in c.get("requests", []):
        env = req.get("environment", {})
        for k in list(env.keys()):
            lk = k.lower()
            if "username" in lk or ("user" in lk and "password" not in lk):
                env[k] = username
            elif "password" in lk or "pass" in lk:
                env[k] = password
    return c

creds["user"] = make_cred(USER1_USERNAME, USER1_PASSWORD)
if BOLA_FOUND:
    creds["user2"] = make_cred(USER2_USERNAME, USER2_PASSWORD)
if BFLA_FOUND:
    creds.setdefault("user", make_cred(USER1_USERNAME, USER1_PASSWORD))
    creds["admin"] = make_cred(ADMIN_USERNAME, ADMIN_PASSWORD)
```

**5b — Add global `authorizationTests` dict** (same for both modes)

```python
auth_tests = {}
if BOLA_FOUND:
    auth_tests["bola"] = {
        "key": "authentication-swapping-bola",
        "source": [f"{scheme_name}/user"],
        "target": [f"{scheme_name}/user2"]
    }
if BFLA_FOUND:
    auth_tests["bfla"] = {
        "key": "authentication-swapping-bfla",
        "source": [f"{scheme_name}/user"],
        "target": [f"{scheme_name}/admin"]
    }
scanconf["authorizationTests"] = auth_tests
```

**5c — Wire per-operation authorization tests** (same for both modes)

```python
for op_id in BOLA_OPS:
    op = scanconf["operations"].setdefault(op_id, {})
    if "bola" not in op.setdefault("authorizationTests", []):
        op["authorizationTests"].append("bola")
for op_id in BFLA_OPS:
    op = scanconf["operations"].setdefault(op_id, {})
    if "bfla" not in op.setdefault("authorizationTests", []):
        op["authorizationTests"].append("bfla")
```

**5d — Save and report**

```python
json.dump(scanconf, open("$WORK_DIR/scanconf.json", "w"), indent=2)
```

Print:
```
Scan config enriched:
  Auth mode: <static token | dynamic login>
  BOLA: <n> operations tagged  (or "not detected")
  BFLA: <n> operations tagged  (or "not detected")
  Credentials: <list of credential names>
```

---

### Step C — Run the Conformance Scan

```bash
rm -f "$WORK_DIR/scan-report.json"
```

If `AUTH_MODE=static` (generated scanconf with static token auth), prepend the collected token env vars:

```bash
SCAN42C_SECURITY_USERTOKEN="$TOKEN_USER" \
SCAN42C_SECURITY_USER2TOKEN="$TOKEN_USER2" \
SCAN42C_SECURITY_ADMINTOKEN="$TOKEN_ADMIN" \
SCAN42C_HOST="$BASE_URL" \
"$AST_BIN" scan run "$WORK_DIR/openapi.$OAS_EXT" \
  --conf-file "$SCANCONF" \
  --output "$WORK_DIR/scan-report.json" \
  --output-format json \
  --enrich=false \
  --verbose error \
  --org "$RUN_ID" --repo "$RUN_ID" --user "$RUN_ID"
```

Omit `SCAN42C_SECURITY_USER2TOKEN` if no BOLA operations were found; omit `SCAN42C_SECURITY_ADMINTOKEN` if no BFLA operations were found.

If `AUTH_MODE=dynamic` or an existing scanconf was used (no `AUTH_MODE` set), run without token env vars:

```bash
SCAN42C_HOST="$BASE_URL" \
"$AST_BIN" scan run "$WORK_DIR/openapi.$OAS_EXT" \
  --conf-file "$SCANCONF" \
  --output "$WORK_DIR/scan-report.json" \
  --output-format json \
  --enrich=false \
  --verbose error \
  --org "$RUN_ID" --repo "$RUN_ID" --user "$RUN_ID"
```

**After the scan completes (regardless of which branch ran it), reset the database** to remove test residues (scan-created users and orders) so the next scan run starts from a clean state:

```bash
# Find reset_database.sh — walk upward from OAS_FILE to locate the project root
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
else
  echo "Note: reset_database.sh not found — scan residues (test users/orders) remain in the database."
fi
```

---

### Step D — Analyze the Scan Report

Read `$WORK_DIR/scan-report.json`.

Extract (see [references/report-guide.md](references/report-guide.md)):
- `summary.state` — `"success"` or `"failed"`
- `summary.operations` — `success`, `happyPathFailure`, `executed.failed` counts
- `summary.issues.total` / `.critical` / `.high` / `.medium` / `.low`
- `summary.issues.issueTypeCounters` — dict with `conformanceTests`, `authorizationTests`, `methodNotAllowedTests` sub-dicts (each `issueType → count`)
- `operations` — **dict keyed by operationId**; each value has `path`, `method`, `reason`, `authorizationRequestsResults[]`

Display the scan summary:

```
## Conformance Scan Results
Target: <BASE_URL>
State: <summary.state>
Operations: <success> passed | <happyPathFailure> happy-path failures | <executed.failed> failed
Issues: Critical: <n> | High: <n> | Medium: <n> | Low: <n>

### Authorization Findings (BOLA/BFLA)
[<method> <path>] <operationId>: <test.key> — <test.description>
  ...

### Conformance Issue Types
<issueType>: <count>
  ...
```

Group all issues by type to identify systemic problems (e.g., many `schema-type-wrong-*` entries = missing server-side validation; `authentication-swapping-bola` on multiple routes = missing ownership checks).

---

### Step E — Map Issues to Code Fixes

For each unique issue type found, determine what code change is needed. Use the implementation context from Phase 3 to identify the exact file and lines to change.

**Issue type → code fix mapping:**

| Issue Type | Root Cause | Code Fix |
|---|---|---|
| `authentication-swapping-bola` | User A can access/modify User B's resource (ownership not enforced) | After fetching the resource, compare its owner field to `req.user.customerId`; return 403 if they differ |
| `authentication-swapping-bfla` | Non-privileged user can reach a privileged operation (role not enforced) | Add a role check before the operation: `if (!req.user.isAdmin) return res.status(403).json(...)` |
| `partial-security-accepted` | Auth middleware accepts JWTs without full signature verification | **May be intentional** (e.g., a demo/CTF environment). Check Phase 3 context first — if `jwt.decode()` is used deliberately and documented, leave it in place and annotate it; otherwise replace with `jwt.verify(token, secret)` using the application's secret |
| `schema-type-wrong-*` / `schema-maxlength-scan` / `schema-pattern-scan` / `schema-minlength-scan` / `schema-required-scan` / `schema-additionalproperties-scan` | No server-side input validation — API accepts any value regardless of OAS constraints | Create a shared validation module with field validators matching every OAS schema constraint (type, minLength, maxLength, pattern, minimum, maximum, required, no extra fields); call validators at the top of each route handler before any DB access |
| `parameter-header-contenttype-wrong-scan` | Server accepts POST/PATCH/PUT requests with wrong or missing `Content-Type` | Add global middleware: reject requests without `Content-Type: application/json` with 415 |
| `security-scheme-not-enforced` | Route is accessible without a valid auth token | Add auth middleware to the route definition |
| `response-body-conformance` | `res.json(...)` returns fields not declared in the OAS response schema | Update route/controller to return exactly the fields listed in the OAS response schema |
| `response-status-conformance` | Route returns a status code not listed in the OAS | Use the correct status code, or add it to the OAS if intentional |

---

### Step F — Apply Code Fixes

For each identified code fix:

1. Print before the edit:
   ```
   Fixing <issue-type> in <file> — <route method + path>
   <one-sentence explanation of what the scan found and why it matters>
   ```

2. Use the **Edit tool** on the relevant source file:
   - Match the existing code style exactly (indentation, `const`/`let`, error handling pattern).
   - Minimal change — only touch the lines needed for the fix.
   - For security fixes (BOLA, BFLA, auth bypass), add a brief inline comment explaining the check:
     ```js
     // Authorization: only the resource owner or an admin may access this
     if (req.user.customerId !== order.customerId && !req.user.isAdmin) {
       return res.status(403).json({ error: 'Forbidden' });
     }
     ```
   - Do not refactor, rename, or clean up surrounding code.

3. If the fix is already in place (e.g., an authorization check exists and is not commented out): print `Already implemented — skipping.` and move on.

After all code fixes, print:

```
## Code Fixes Applied
<n> files modified:
  <relative-path>: <brief description of change>
  ...
```

---

### Step F.5 — Rebuild the API

After writing code fixes to disk, rebuild and restart the API so the changes take effect before the verification scan.

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
```

If found, run the rebuild:

```bash
if [ -n "$_manage" ]; then
  echo "==> Rebuilding API..."
  bash "$_manage" rest rebuild
  REBUILD_EXIT=$?
  if [ $REBUILD_EXIT -ne 0 ]; then
    echo "Warning: manage.sh rest rebuild exited with code $REBUILD_EXIT — the server may not have restarted cleanly."
  else
    echo "==> API rebuilt successfully."
  fi
else
  echo "Note: scripts/manage.sh not found — skipping rebuild. Restart the server manually if needed before verification."
fi
```

After the rebuild completes, continue to Step G1 to confirm the new code is live.

---

### Step G — Verify Rebuild and Re-scan to Confirm Code Fixes

The rebuild ran in Step F.5. Before scanning, confirm the new code is actually live by probing a sentinel behaviour that differs between old and new code.

**Step G1 — Check if the server has picked up the changes**

If `$REBUILD_EXIT` is set and non-zero (rebuild failed in Step F.5), skip this probe and go directly to the stale-server message — the server is definitely not running updated code.

Otherwise, choose a quick probe that distinguishes old code from new code. Good choices:
- If Content-Type middleware was added: send a POST with `Content-Type: text/plain` and expect HTTP 415 (old code would return something else).
- If input validation was added: send a request with an invalid field value (e.g., `"username": true`) and expect HTTP 400 (old code returns 401 or 200).

```bash
PROBE_RESULT=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
  -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: text/plain" \
  -d '{}')
echo "Probe result: $PROBE_RESULT"
```

- If the probe returns the **expected new behaviour** (e.g., 415): the server is up to date. Proceed to the scan.
- If the probe returns the **old behaviour** (e.g., 401 or 400): the server is still running stale code despite the rebuild.

**If the server is stale** (or rebuild failed): print the following and **stop** — do NOT run the verification scan against stale code, as the results would be misleading:

```
⚠️  Rebuild completed but server is still serving old code.

The rebuild ran (Step F.5) but the probe shows <BASE_URL> is still responding
with the previous version. Check the rebuild output for errors.

If the rebuild reported success, try restarting the server manually, then
re-run this skill to verify:
  /api-security-remediate <oas-file>

Code changes applied (pending live pickup):
  <list each file:change from Step F>
```

**If the server is up to date**: print `Server is running updated code. Proceeding with verification scan.` and continue.

---

**Step G2 — Run the verification scan**

After applying code fixes, re-run the conformance scan to confirm the issues are resolved. Use the exact same `SCANCONF`, `BASE_URL`, `AUTH_MODE`, and token/credential variables from Step C — no new credential prompts.

Run the scan command from Step C again, saving output to `$WORK_DIR/verify-report.json`. Then compare:

- **Resolved**: issues present in the first scan report but absent in the verify report
- **Remaining**: issues still present in both reports
- **New**: issues in the verify report not in the first scan (flag these — a code fix may have broken something)

Print:

```
## Verification Scan Results
Resolved: <n> issues fixed
Remaining: <n> issues still present
New issues introduced: <n>  (flag if > 0)

Remaining issues:
  [<severity>] <issueType> — <operationId>
```

If the verify scan also passes cleanly (0 remaining), note it prominently in the final report.

Skip this step if the original conformance scan was skipped (no base URL or API not reachable).

---

## Phase 7 — Cleanup and Final Report

```bash
rm -rf "$WORK_DIR"
```

Compute elapsed time from when the skill started:

```bash
SKILL_END=$(date +%s)
SKILL_ELAPSED=$((SKILL_END - SKILL_START))
ELAPSED_MINS=$((SKILL_ELAPSED / 60))
ELAPSED_SECS=$((SKILL_ELAPSED % 60))
```

Print the consolidated summary:

```
## Final Report

OAS File:      <OAS_FILE>
Audit Score:   <final-score>/100  (reached after <N> iteration(s))
OAS Fixes:     <n> applied across <N> iterations
Manual Items:  <n> unresolved (listed below if any)
Conformance:   <passed>/<total> operations  (target: <BASE_URL>)
               or "skipped — no base URL resolvable"
               or "skipped — API not reachable at <BASE_URL>"
Code Fixes:    <n> applied  (or "not run")
Verification:  <n> resolved / <n> remaining after code fixes  (or "not run")
Total Time:    <ELAPSED_MINS>m <ELAPSED_SECS>s

### Remaining Manual Issues  (if any)
[HIGH] <id>: <title>
  Why it requires manual decision: <reason>
  Guidance: <remediation excerpt from KDB>
```

---

## Invariants

- **Never hardcode** paths, usernames, or machine-specific strings in commands — always use shell variables.
- **Context before fixes** — every OAS edit must be consistent with what the implementation actually does. A fix that contradicts the code is incorrect.
- **Iterate until done** — do not stop the audit loop after one pass. Only stop when score is 100 or no fixable issues remain.
- **One Edit call per logical fix** — do not batch unrelated changes into one Edit call; it makes diffs hard to review.
- **YAML/JSON fidelity** — match existing file indentation (2-space or 4-space), preserve comments and key order, do not convert between YAML and JSON.
- **Surgical code fixes** — when remediating conformance issues, change only what is necessary. Do not refactor surrounding code.
- For full field reference of `report.json` and `scan-report.json`, see [references/report-guide.md](references/report-guide.md).
