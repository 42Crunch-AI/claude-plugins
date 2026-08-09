# Validate Traffic Workflow

Compare an OpenAPI contract against HTTP traffic in **HAR** files or **Postman**
collections using `42c-ast openapi validate-traffic`. Produces a compact JSON
report with coverage metrics and structured drift findings.

Used by the `validate-oas-traffic` skill and the post-generation step in
`generate-oas` when a compatible traffic source is available.

> **Command conventions used throughout this file**
> - `<binary>` — full path resolved in Step 0. Never call `42c-ast` by name
>   alone unless it is confirmed to be on PATH.
> - This command is **local** — it does not require 42Crunch credentials.
> - **Never write literal credential values** into commands (not applicable here).

---

## Step 0 — Resolve the Binary

Resolve `<binary>` in this order (first match wins):

### 0a — Local dev overlay (optional, not committed)

If `validate-traffic-dev-binary.md` exists alongside this file
(`plugins/api-security-testing/references/validate-traffic-dev-binary.md`),
read it and follow its binary-resolution instructions exactly. Stop here if it
yields an executable `<binary>`. Shared with `enrich-workflow.md` (same
pre-release AST). That filename is gitignored — local-only; do not commit it.

### 0b — Environment variable override

If `AST_VALIDATE_TRAFFIC_BINARY` is set and the path is executable, use it as
`<binary>`.

```bash
# macOS / Linux
if [ -n "$AST_VALIDATE_TRAFFIC_BINARY" ] && [ -x "$AST_VALIDATE_TRAFFIC_BINARY" ]; then
  echo "BINARY=$AST_VALIDATE_TRAFFIC_BINARY"
fi
```

```powershell
# Windows
if ($env:AST_VALIDATE_TRAFFIC_BINARY -and (Test-Path $env:AST_VALIDATE_TRAFFIC_BINARY)) {
  Write-Output "BINARY=$env:AST_VALIDATE_TRAFFIC_BINARY"
}
```

### 0c — Standard public 42c-ast (default when validate-traffic ships)

Use the canonical installed binary:

```bash
# macOS / Linux
BINARY_PATH="$HOME/.42crunch/bin/42c-ast"
```

```powershell
# Windows
$BINARY_PATH = "$env:APPDATA\42Crunch\bin\42c-ast.exe"
```

Verify it exists and responds to `--version`. If missing, tell the user to
run `42crunch-setup`, or to set `AST_VALIDATE_TRAFFIC_BINARY` if they are
testing a pre-release AST build.

### Sanity check

Before proceeding, confirm the subcommand is available:

```bash
<binary> openapi validate-traffic --help
```

If this fails with "unknown command" or similar, the installed AST does not
yet include `openapi validate-traffic`. Direct the user to set
`AST_VALIDATE_TRAFFIC_BINARY` to a build that includes the command, or to
upgrade via `42crunch-setup` when the public AST ships it.

Store the resolved path as `<binary>` for all steps below.

---

## Step 1 — Resolve Inputs

The caller must supply (or the skill must collect):

| Input | Required | Notes |
|-------|----------|-------|
| `SPEC_PATH` | Yes | Path to the OpenAPI file (`.json`, `.yaml`, `.yml`). |
| `TRAFFIC_INPUTS` | Yes | One or more HAR or Postman collection paths (repeat `--input`). |
| `POSTMAN_ENV` | No | Postman environment export JSON; only when a Postman collection is among the inputs. |
| `CODEBASE_WAS_SOURCE` | No | Set `true` when `generate-oas` also used a codebase — affects interpretation of `declaredButNotSeen` findings (see Step 4). |

**Supported traffic formats:** HAR (`.har`, JSON log) and Postman collection
(v2.0/v2.1 JSON). **Insomnia exports are not supported** as traffic input.

If the caller is `generate-oas` and only Insomnia or codebase was used (no
Postman), **skip this entire workflow** and note in the generation summary
that traffic validation was not run.

---

## Step 2 — Run validate-traffic

Write JSON output to a temp file:

```bash
# macOS / Linux
OUTPUT_DIR=/tmp/42c-validate-traffic
mkdir -p "$OUTPUT_DIR"
REPORT_PATH="$OUTPUT_DIR/report.json"
```

```powershell
# Windows
$OUTPUT_DIR = "$env:TEMP\42c-validate-traffic"
New-Item -ItemType Directory -Force -Path $OUTPUT_DIR | Out-Null
$REPORT_PATH = "$OUTPUT_DIR\report.json"
```

Run with `--drift-side=all` for the first pass (full picture):

```bash
<binary> openapi validate-traffic \
  --spec "$SPEC_PATH" \
  --input "$TRAFFIC_INPUT_1" \
  [--input "$TRAFFIC_INPUT_2" ...] \
  [--postman-env "$POSTMAN_ENV"] \
  --filter-traffic=true \
  --drift-side=all \
  > "$REPORT_PATH"
```

```powershell
<binary> openapi validate-traffic `
  --spec $SPEC_PATH `
  --input $TRAFFIC_INPUT_1 `
  [--input $TRAFFIC_INPUT_2 ...] `
  [--postman-env $POSTMAN_ENV] `
  --filter-traffic=true `
  --drift-side=all `
  | Out-File -Encoding utf8 $REPORT_PATH
```

If the command exits non-zero, surface stderr and stop.

---

## Step 3 — Parse the Report

Read `REPORT_PATH` as JSON.

### Envelope (important)

`42c-ast` wraps the drift payload. Prefer this resolution order:

1. If the root has `report` (object), use **`report`** as the analysis root
   (`report.specInfo`, `report.stats`). Root may also have `astVersion`,
   `statusCode`, `statusMessage`.
2. Else if the root has `stats` directly, use the root as the analysis root
   (older / unwrapped shape).

Treat a non-zero root `statusCode` (when present) as failure even if some
fields exist. Below, `stats` / `specInfo` always mean fields on the
**analysis root** after unwrapping.

### Coverage (always show)

From `stats.openapiPaths` and `stats.openapiOperations`:
- `matched`, `unmatched`, `coveragePercent`, `templateMatched` (paths only)

From `stats.trafficCoverage`:
- Unique traffic paths/operations and traffic-only counts

From `stats.inputs`:
- Interaction counts before/after filtering

### Gap lists

- `stats.openapiOnlyEntries` — spec operations with no matching traffic
- `stats.trafficOnlyEntries` — traffic operations not in the spec
- `stats.matchedEntries[]` — operations in both; each may have `findings[]`,
  `hasDrift`, `driftItemCount`, `count`

### Finding fields

Each `DriftFinding` may include: `kind`, `side` (`declaredButNotSeen` |
`seenButNotDeclared`), `scope`, `paramIn`, `name`, `responseCode`,
`contentType`, `jsonPointer`.

---

## Step 4 — Classify Findings for the User

Present findings in three tiers (developer-readable titles, not raw `kind`
alone):

### Blockers — likely errors or omissions

- Any `trafficOnlyEntries` (traffic shows an operation the spec lacks)
- `seenButNotDeclared` on: response codes, request/response body content types,
  required path/query params, `observed_property_not_in_schema` when
  `additionalProperties: false`
- `openapiOperations.coveragePercent` below **50%** when traffic is expected
  to be representative

### Warnings — review required

- `declaredButNotSeen` findings on matched operations (possible AI invention
  **or** codebase inference not exercised in traffic — see note below)
- `openapiOnlyEntries` when traffic is a partial Postman suite
- Low path coverage (`openapiPaths.coveragePercent` < 80%) with known partial
  traffic
- `schema_type_mismatch`, `schema_enum_value_never_observed`,
  `observed_enum_value_not_declared`

### Informational

- Optional headers never sent/observed
- Rare response codes declared but not seen in the capture
- `declared_security_requirement_never_satisfied` when auth headers were
  stripped from the collection export

**Codebase + traffic note:** When `CODEBASE_WAS_SOURCE=true`, prefix
`declaredButNotSeen` items with:
> *May be codebase inference not present in this traffic capture — verify
> before removing.*

Do **not** auto-delete spec content solely because of `declaredButNotSeen`
when a codebase was also used as a source.

---

## Step 5 — Present the Report

Output a summary in this shape:

```
Traffic Validation Complete
  Spec:              <SPEC_PATH>
  Traffic inputs:    <comma-separated input paths>
  Binary:            <binary>   ← omit full path in user-facing output if long; show basename only

Coverage
  Spec paths:        <matched>/<total> matched (<coveragePercent>%)
  Spec operations:   <matched>/<total> matched (<coveragePercent>%)
  Traffic-only ops:  <count>   ← from trafficCoverage or trafficOnlyEntries length
  Spec-only ops:     <count>   ← openapiOnlyEntries length

Drift summary
  Blockers:          <N>
  Warnings:          <N>
  Informational:     <N>

Top findings
  - <tier> · <METHOD> <path> · <plain-English description of kind/side>
  - ...

Full JSON report: <REPORT_PATH>
```

List up to **10** top findings; if more exist, say how many were omitted.

---

## Step 6 — Optional Remediation Loop

After presenting the report, call `AskUserQuestion`:

- **question**: `"The spec differs from the traffic capture in the ways above. Should I update the OpenAPI file to align with the traffic evidence?"`
- **options**: `["Yes — fix blockers and clear omissions", "Yes — fix all drift", "No — keep the spec as-is"]`

If the user declines, stop and recommend `/42crunch-audit` when appropriate.

If the user accepts:

1. Edit `SPEC_PATH` to address agreed findings:
   - **traffic-only operations** → add missing paths/methods from traffic
   - **seenButNotDeclared** → add missing params, codes, properties, content types
   - **declaredButNotSeen** → remove or relax only when user chose "fix all"
     or the finding is clearly invented (no codebase source)
2. Re-run Step 2 once with the updated spec.
3. Present a before/after coverage comparison.
4. Do not loop more than **one** remediation pass without explicit user request.

---

## Step 7 — Recommend Next Steps

**If validation passed cleanly** (no blockers, coverage ≥ 80% on operations):
> "Traffic validation looks good. Run `/42crunch-audit` for security analysis,
> or `/42crunch-scan` if the API is running."

**If blockers remain after remediation:**
> "Some traffic gaps remain — review the JSON report. Partial Postman suites
> often cause spec-only or traffic-only operations; capture more traffic or
> merge with codebase analysis if available."

**If invoked from `generate-oas`:**
> Include a `Traffic validation:` subsection in the generation summary with
> coverage percentages and blocker/warning counts.

---

## Finding Kind Reference (quick lookup)

| `kind` | Typical `side` | Meaning |
|--------|------------------|---------|
| `declared_response_code_never_observed` | `declaredButNotSeen` | Status declared, not seen in traffic |
| `observed_response_code_not_declared` | `seenButNotDeclared` | Status seen, not in spec |
| `required_header_never_sent` | `declaredButNotSeen` | Required header missing from traffic |
| `extra_request_header_in_traffic` | `seenButNotDeclared` | Undeclared request header |
| `required_query_param_never_sent` | `declaredButNotSeen` | Required query param missing |
| `extra_query_param_in_traffic` | `seenButNotDeclared` | Undeclared query param |
| `observed_property_not_in_schema` | `seenButNotDeclared` | Extra JSON field vs schema |
| `required_schema_property_never_observed` | `declaredButNotSeen` | Required property not in bodies |
| `schema_type_mismatch` | varies | Value incompatible with type |
| `declared_security_requirement_never_satisfied` | `declaredButNotSeen` | No interaction satisfies security |

Full command and flag reference: see product docs for `openapi validate-traffic`.
