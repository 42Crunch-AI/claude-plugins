---
name: 42crunch-scan
description: >
  Run a 42Crunch live conformance and authorization scan against a REST or
  GraphQL API and fix SQG-blocking scan findings. Use this skill whenever the
  user wants to run a conformance test, authorization scan, BOLA test, BFLA
  test, scan a GraphQL API, generate or configure a scan config, or fix
  scan-reported issues. Triggers on phrases like "run scan", "scan only",
  "conformance test", "BOLA test", "BFLA test", "42crunch scan", "scan config",
  "scan my graphql api", or any request focused on live API testing without
  running a static audit. Use 42crunch-api-security-testing when the user wants
  both audit and scan together.
---

# 42Crunch Scan Skill

Runs a single phase: **Scan** (live conformance + authorization testing and
SQG-blocking fix loop). Requires explicit user permission before execution.
Does **not** run a static audit — use the `42crunch-audit` skill for that.

Handles both OpenAPI and GraphQL APIs; pre-flight sets `API_TYPE` and this
skill selects the matching workflow. For GraphQL, the scan covers live
**conformance** and **authorization** (BOLA/BFLA) testing.

Assumes the API definition is already audit-clean (or the user is explicitly
running scan only). If the user mentions audit issues before scanning, suggest
running `42crunch-audit` first.

---

## Entry Point

1. **Pre-flight checks.** Read `../../references/pre-flight.md` and complete
   all steps (setup, API definition resolution, tag detection). When prompting
   for file selection, use the context `"scan"` (e.g. "Which one should I
   scan?"). Do not proceed if any step fails or the user cancels.

   Pre-flight sets `API_TYPE` (`oas` or `graphql`) — carry it forward. The
   steps below apply to both; **bracketed `[GraphQL: …]` notes give the
   substitution** when `API_TYPE=graphql`.

2. **Resolve the scan target URL.**

   Read `servers[0].url` from the OAS file. `[GraphQL: SDL has no servers block
   — read the endpoint from the schema's default host if present, otherwise
   rely on SCAN42C_HOST or ask.]`

   - If `SCAN42C_HOST` environment variable is set → announce silently:
     > "Using scan target from SCAN42C_HOST: `<url>`"
     Store as `SCAN_TARGET_URL` and proceed.
   - If not set → call `AskUserQuestion`:
     - **question**: `"The OAS points to <servers[0].url> as the API target. Is this the right URL to scan against?"` — options: `["Yes — use this URL", "No — I'll provide a different URL"]`  `[GraphQL: "What URL should I scan the GraphQL endpoint against (e.g. http://localhost:4000/graphql)?"]`
     - If **No** → ask the user to provide the URL and store it as `SCAN_TARGET_URL`.
     - If **Yes** → store `servers[0].url` as `SCAN_TARGET_URL`.

3. **API-definition analysis for scan preview** — run silently before asking permission.

   **`API_TYPE=oas`** — read the OAS file and collect:
   - Total operation count
   - Auth scheme types from `securitySchemes` (Bearer/JWT, API Key, Basic, OAuth2)
   - BOLA candidate count: operations that reference a specific existing resource by a client-supplied id/key/ref — in a **path** parameter (`{…Id}`, `{…Key}`, `{…Ref}`), a **query** parameter (`?orderId=`), or a **request-body field** (`POST /lookup {orderId}`, `POST /transfer {fromAccountId, toAccountId}`). Method does not gate candidacy; only pure collection or create-new operations are excluded
   - Whether the OAS contains sample data: any operation with `example`, `examples`, or `default` values on its request body or parameter schemas

   **`API_TYPE=graphql`** — read the schema and collect:
   - Query + mutation count (these are the operations)
   - Dependency candidates: queries/mutations whose non-nullable arguments are
     ids/references to objects another mutation creates
   - BOLA candidates: queries/mutations taking a client-supplied reference to
     an existing object (`ID`-typed or `*Id`/`*Key`/`*Ref` argument, including
     input-object fields) that act on or return it — not pure lists or
     create-new mutations
   - BFLA candidates: admin/management fields, operations on other users'
     accounts, bulk or destructive mutations
   - GraphQL SDL declares no auth schemes — credentials are collected in the
     workflow.

   Carry these results forward — the workflow reuses them instead of re-reading
   the definition.

4. **Ask for permission to configure the scan.** Output the scan preview as a
   chat message first.

   **`API_TYPE=oas`:**
   ```
   Ready to configure the scan?
     Target:   <SCAN_TARGET_URL>
     OAS:      <filename>  (<N> operations)
     Auth:     <scheme types>  [+  second user needed — <N> BOLA candidate(s)]
     Samples:  OAS has sample data  /  No samples — you'll need to provide test data
     Tag:      <category>:<tagname>           ← platform mode only, when a tag is assigned; omit if no tag
     Mode:     Platform / Token
   ```

   **`API_TYPE=graphql`:**
   ```
   Ready to configure the GraphQL scan?
     Target:   <SCAN_TARGET_URL>
     Schema:   <filename>  (<Q> queries · <M> mutations)
     Auth:     to be collected — GraphQL schema carries no auth info  [+  second user needed — <N> BOLA candidate(s)]  [+  admin user needed — <N> BFLA candidate(s)]
     Tests:    conformance + authorization (BOLA/BFLA)    ← say "conformance only" when there are no candidates
     Tag:      <category>:<tagname>           ← platform mode only, when a tag is assigned; omit if no tag
     Mode:     Platform / Token
   ```

   Then call `AskUserQuestion`:
   - **question**: `"I'm ready to start configuring the scan. I'll ask for credentials, classify your operations, and set up test scenarios — then run a happy path validation before the full scan. Shall I proceed?"`
   - **options**: `["Yes, let's configure", "No, cancel"]`

5. **Execute the Scan.** Mode is already resolved from pre-flight — do not
   re-derive it.

   **Reachability check** — read `../../references/reachability-check.md` and run
   the two-stage probe now. Return here once it completes (or stop if the user cancels).

   Read the workflow file for the resolved `API_TYPE` — and only that file:
   - `API_TYPE=oas` → `../../references/scan-workflow.md`
   - `API_TYPE=graphql` → `../../references/graphql-scan-workflow.md`

   Apply only the commands for the identified mode throughout.
   The workflow sets up the scan config, collects credentials, gathers test data,
   shows a complete operation-by-operation classification table, validates happy paths,
   then asks for permission again before running the full scan. It presents a **risk-classified findings report**
   (OAS: Authorization failures / SQG-blocking conformance / informational conformance;
   GraphQL: the same three tiers, with authorization findings confirmed against the response data).
   Fix candidates are determined by SQG-blocking rules and authorization failures — not severity alone.
   The skill pauses and asks the user to consent before applying any OAS/schema changes or server-side code fixes.
   Optionally prompt user to restart the API after server-side code fixes are applied,
   or skipped, before the final scan summary.

  **Mandatory checkpoint:** after any direct edit to `CONF_FILE` (including
  `environments.default.variables.*`, auth wiring, or scenario chains), run
  the config validation checkpoint and resolve all errors before continuing to
  happy-path or full scan runs. `[GraphQL: run scan conf validate --graphql plus the two extra checks in graphql-scan-workflow.md Step 7.]`

   **Token mode**: no SQG is enforced for scan. Present all findings for
   information. The user decides which (if any) to fix.

6. **Render findings and ask for fix permission before final Scan summary.**

   After the full scan completes, do **not** jump directly to the final
   "Scan Complete" summary when findings exist. First complete the workflow's
   Step 12 in order:
   - render the full scan report (three tiers — Authorization failures /
     SQG-blocking conformance / informational conformance; for GraphQL, confirm
     authorization findings with graphql-scan-workflow.md Step 12a-0 first);
   - assemble the fix candidate lists from that report and the SQG blocking
     rules;
   - ask the user the Step 12c consent question with the proposed fix lists.

   Only proceed to OAS/schema or server-side code fixes after the user
   explicitly chooses to apply fixes. If the user declines fixes, or after the
   fix and optional verification loop completes, then present the final scan
   summary (see Output Format below).

Only continue after explicit user confirmation at each permission prompt.

---

## Output Format

After the scan completes, produce a summary in this shape.

**`API_TYPE=graphql`** — label the file row `Schema updated:` instead of
`OAS updated:`; authorization fixes are resolver (server-side) changes.

```
Scan Complete
  Mode:           Platform / Token
  SQG:            PASSED  (<sqg-name> — your org's security quality gate is met)    ← platform mode, passed
  SQG:            FAILED  (<sqg-name> — the quality gate is not met; fixes above are required)    ← platform mode, failed
  SQG:            N/A  (Token mode — scan findings are informational; no gate enforced)    ← token mode
  Tag:            <category>:<tagname>             ← platform mode only, when a tag is assigned; omit this row if no tag
  Authorization:  BOLA confirmed on 1 operation — OAS updated · server-side fix applied
  Conformance:    1 SQG-blocking issue fixed (OAS + code) · 3 informational findings surfaced
  OAS updated:    <path/to/openapi.json>

```

Show only the one SQG line that matches the current mode and result.

If the user declined to apply fixes or no issues were found, note that instead.

---

## Environment Variables

| Variable       | Purpose |
|----------------|---------|
| `SCAN42C_HOST` | Scan target base URL (overrides OAS `servers[0]`) — Both modes |

All other variables (`API_KEY`, `PLATFORM_HOST`, `TRIAL_TOKEN`) and general
constraints are defined in `../../references/pre-flight.md`.
