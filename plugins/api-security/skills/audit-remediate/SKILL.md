---
description: >
  Run the 42Crunch audit tool (`42c-ast`) on an OpenAPI spec and iteratively fix all
  flagged issues until the security score reaches 100/100. Does NOT run a conformance
  scan — use the `scan-remediate` skill for that.

  Trigger this skill when the user wants to: run a 42Crunch audit on an OpenAPI spec,
  fix audit issues in an OAS file, improve a 42Crunch audit score ("get to 100/100",
  "fix the audit issues", "my score is 54/100"), remediate OAS security findings such
  as missing auth schemes, absent response schemas, or missing length/pattern constraints
  — even if "42Crunch" is not mentioned by name.

  Strong trigger phrases: "/audit-remediate", "audit my openapi spec",
  "fix audit issues", "get my API to 100/100", "42crunch audit", "fix the oas security
  issues", "my 42crunch score is bad", "remediate the audit findings".

  Do NOT trigger for: running a conformance scan, fixing BOLA/BFLA in source code,
  debugging JWT middleware, reviewing OpenAPI specs for style or readability, converting
  Swagger to OpenAPI, generating specs from code, or anything involving a live running API.
disable-model-invocation: true
argument-hint: <oas-file-path>
---

# 42Crunch Audit Remediate Skill

OAS security hardening using the `42c-ast` binary: run the audit, fix all issues, re-audit, repeat until score is 100/100.

**Usage:**
- `/audit-remediate openapi.json` — audit + iterative OAS fixes until 100/100

**Next step after 100/100:** run `/scan-remediate openapi.json [base-url]` to test your API implementation against the hardened spec.

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

Before making any changes to the OAS, build a complete picture of what the API actually does. This context is required to produce correct, non-breaking OAS fixes.

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

Store all of this as working context. Every OAS fix must be consistent with this picture.

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

**If `score == 100`:** print `Score reached 100/100 after <ITERATION> iteration(s).` and jump to Phase 7.

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

**If there are no fixable issues** in this iteration, print the manual list and jump to Phase 7.

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

In all non-100 exit cases, continue to Phase 7 and list the remaining manual issues.

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
Total Time:    <ELAPSED_MINS>m <ELAPSED_SECS>s

### Remaining Manual Issues  (if any)
[HIGH] <id>: <title>
  Why it requires manual decision: <reason>
  Guidance: <remediation excerpt from KDB>

---
Next step: run `/scan-remediate <oas-file> [base-url]` to test your
API implementation against the hardened spec.
```

---

## Invariants

- **Never hardcode** paths, usernames, or machine-specific strings in commands — always use shell variables.
- **Context before fixes** — every OAS edit must be consistent with what the implementation actually does. A fix that contradicts the code is incorrect.
- **Iterate until done** — do not stop the audit loop after one pass. Only stop when score is 100 or no fixable issues remain.
- **One Edit call per logical fix** — do not batch unrelated changes into one Edit call; it makes diffs hard to review.
- **YAML/JSON fidelity** — match existing file indentation (2-space or 4-space), preserve comments and key order, do not convert between YAML and JSON.
- For full field reference of `report.json` and `todo.json`, see [references/report-guide.md](references/report-guide.md).
