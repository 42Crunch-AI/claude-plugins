# Enrich OAS Workflow

Enrich an **OpenAPI 3.0.x** document with HTTP examples extracted from **HAR**
files and/or **Postman** collections using `42c-ast openapi enrich`.

Writes `examples` under existing operations only (responses, requestBody, and
header parameters already declared in the spec). Does **not** invent new
paths, methods, or response codes.

Used only by the `enrich-oas` skill (not wired into `generate-oas`).

> **Command conventions used throughout this file**
> - `<binary>` — full path resolved in Step 0. Never call `42c-ast` by name
>   alone unless it is confirmed to be on PATH.
> - This command is **local** — it does not require 42Crunch credentials.
> - **Never write literal credential values** into commands (not applicable here).

---

## Step 0 — Resolve the Binary

Resolve `<binary>` in this order (first match wins). Same resolution chain as
`validate-traffic-workflow.md` (shared pre-release overlay and env var).

### 0a — Local dev overlay (optional, not committed)

If `validate-traffic-dev-binary.md` exists alongside this file
(`plugins/api-security-testing/references/validate-traffic-dev-binary.md`),
read it and follow its binary-resolution instructions exactly. Stop here if it
yields an executable `<binary>`. That filename is gitignored — local-only; do
not commit it.

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

### 0c — Standard public 42c-ast (default when openapi enrich ships)

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
<binary> openapi enrich --help
```

If this fails with "unknown command" or similar, the installed AST does not
yet include `openapi enrich`. Direct the user to set
`AST_VALIDATE_TRAFFIC_BINARY` to a build that includes the command, or to
upgrade via `42crunch-setup` when the public AST ships it.

Store the resolved path as `<binary>` for all steps below.

---

## Step 1 — Resolve Inputs

The caller must supply (or the skill must collect):

| Input | Required | Notes |
|-------|----------|-------|
| `SPEC_PATH` | Yes | Path to the OpenAPI 3.0.x file (`.json`, `.yaml`, `.yml`). |
| `TRAFFIC_INPUTS` | Yes | One or more HAR or Postman collection paths (repeat `--input`). |
| `POSTMAN_ENV` | No | Postman environment export JSON; only when a Postman collection is among the inputs. |

**Supported traffic formats:** HAR (`.har`, JSON log) and Postman collection
(v2.0/v2.1 JSON). **Insomnia exports are not supported** as traffic input.

**OpenAPI version:** Enrich targets **OpenAPI 3.0.x** only. If the document
is Swagger 2.0 or OpenAPI 3.1, warn the user and stop unless they confirm they
still want to attempt the run.

---

## Step 2 — Snapshot Before Enrichment (optional metrics)

Before mutating the file, count existing OpenAPI `examples` maps under
`paths` (response `content`, `requestBody.content`, and header `parameters`).
Store as `EXAMPLES_BEFORE`.

Also note file size / last-modified for the summary.

Do not fail the workflow if counting is imperfect — metrics are advisory.

---

## Step 3 — Confirm Overwrite

Enrich **overwrites** `SPEC_PATH` in place (after a temp write). Call
`AskUserQuestion` unless the skill already obtained explicit overwrite consent:

- **question**: `"Enrich will write traffic examples into <spec-filename> (same file). Existing example keys may be added or updated. Proceed?"`
- **options**: `["Yes — overwrite the spec", "No, cancel"]`

If the user declines, stop without running the command.

---

## Step 4 — Run openapi enrich

Detect `OUTPUT_FORMAT` from `SPEC_PATH`:

- `.yaml` / `.yml` → `yaml`
- otherwise → `json`

Write to a temp file first, then replace `SPEC_PATH` only on success:

```bash
# macOS / Linux
OUTPUT_DIR=/tmp/42c-enrich
mkdir -p "$OUTPUT_DIR"
TMP_OUT="$OUTPUT_DIR/enriched-spec"
# preserve extension for clarity
case "$SPEC_PATH" in
  *.yaml|*.yml) TMP_OUT="$TMP_OUT.yaml" ;;
  *)            TMP_OUT="$TMP_OUT.json" ;;
esac

<binary> -o "$TMP_OUT" --output-format "$OUTPUT_FORMAT" \
  openapi enrich \
  --spec "$SPEC_PATH" \
  --input "$TRAFFIC_INPUT_1" \
  [--input "$TRAFFIC_INPUT_2" ...] \
  [--postman-env "$POSTMAN_ENV"] \
  --filter-traffic=true

# On success (exit 0 and non-empty TMP_OUT):
mv "$TMP_OUT" "$SPEC_PATH"
```

```powershell
# Windows
$OUTPUT_DIR = "$env:TEMP\42c-enrich"
New-Item -ItemType Directory -Force -Path $OUTPUT_DIR | Out-Null
$TmpOut = Join-Path $OUTPUT_DIR "enriched-spec.json"
# use .yaml extension when SPEC_PATH is yaml

& <binary> -o $TmpOut --output-format $OUTPUT_FORMAT `
  openapi enrich `
  --spec $SPEC_PATH `
  --input $TRAFFIC_INPUT_1 `
  [--input $TRAFFIC_INPUT_2 ...] `
  [--postman-env $POSTMAN_ENV] `
  --filter-traffic=true

Move-Item -Force $TmpOut $SPEC_PATH
```

**Flag placement:** `-o` / `--output` and `--output-format` are **global** CLI
flags and must appear **before** `openapi enrich`.

If the command exits non-zero, surface stderr, leave `SPEC_PATH` unchanged,
and stop.

---

## Step 5 — Present the Report

Recount `examples` under `paths` → `EXAMPLES_AFTER`.

Output a summary in this shape:

```
OAS Enrichment Complete
  Spec:              <SPEC_PATH>
  Traffic inputs:    <comma-separated input paths>
  Binary:            <basename of binary>
  Filter traffic:    true

Examples
  Before:            <EXAMPLES_BEFORE> example entries under paths
  After:             <EXAMPLES_AFTER> example entries under paths
  Delta:             +<N> (or "unchanged" / net change)

Notes
  - Enrich only fills slots already declared in the OpenAPI document.
  - Example keys use {statusCode}_{Reason} (e.g. 200_OK).
  - Insomnia is not a supported traffic input.
```

If `EXAMPLES_AFTER` equals `EXAMPLES_BEFORE` and traffic was non-empty, mention
possible causes: no matching operations, empty recorded responses, or slots
already populated with the same keys.

---

## Step 6 — Recommend Next Steps

**After a successful enrich:**
> "Examples were written into the spec. Run `/validate-oas-traffic` if you want
> to check contract drift, or `/42crunch-audit` for security analysis."

**If enrich wrote few or no new examples:**
> "Little or no new example data was added. Confirm the traffic matches
> declared paths/methods, or capture responses in Postman/HAR and retry."

Do **not** auto-run validate-traffic or audit unless the user asks.
