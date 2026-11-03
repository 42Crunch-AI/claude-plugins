---
name: 42crunch-api-security-testing
description: >
  Run both a 42Crunch Audit and a live Scan together in a single pipeline.
  Use this skill when the user wants to run audit and scan together, complete
  the full security pipeline, or when the request is ambiguous about which
  phase to run. Triggers on phrases like "run audit and scan", "full 42crunch
  pipeline", "full security check", "audit then scan", "42crunch", or "SQG".
  Do NOT use this skill if the user explicitly requests only an audit (use
  42crunch-audit) or only a scan (use 42crunch-scan).
---

# 42Crunch API Security Skill

Orchestrates two phases: **Audit** (static analysis of an OpenAPI definition
or GraphQL schema, plus SQG fix loop) and **Scan** (live conformance and
BOLA/BFLA authorization testing). Each phase requires explicit user
permission before execution.

---

## Entry Point

1. **Pre-flight checks.** Read `../../references/pre-flight.md` and complete
   all steps (setup, API definition resolution, tag detection). When prompting
   for file selection, use the context `"pipeline"` (e.g. "Which one should I
   run through the pipeline?"). Pre-flight sets `API_TYPE` (`oas` or
   `graphql`) — carry it forward. Do not proceed if any step fails or the
   user cancels.

   The pipeline runs both phases for `oas` and `graphql`. **Bracketed
   `[GraphQL: …]` notes below give the substitution** when `API_TYPE=graphql`.

2. **Ask for Phase 1 permission.** Call `AskUserQuestion`:
   - **question**: `"Ready to run a 42Crunch Audit on <filename>. This will analyse your <OAS file / GraphQL schema> and produce a scored report. Shall I proceed?"`
   - **options**: `["Yes, proceed", "No, cancel"]`

3. **Execute Phase 1 — Audit.** Mode is already resolved from pre-flight — do
   not re-derive it. Read the workflow file for the resolved `API_TYPE` — and
   only that file:
   - `API_TYPE=oas` → `../../references/audit-workflow.md`
   - `API_TYPE=graphql` → `../../references/graphql-audit-workflow.md`

   Apply only the commands for the identified mode throughout.
   The workflow runs the audit, then presents a **developer-readable,
   risk-classified report** (OAS: SQG-Blocking / Security / Data Validation /
   Spec Conformance tiers; GraphQL: Resource Limiting / Data Validation
   tiers) with plain-English titles and risk descriptions — no raw rule IDs.
   It then pauses and asks the user to consent before applying any fixes.
   Fixes are only applied after explicit confirmation.

4. **Resolve the scan target URL.**

   Read `servers[0].url` from the OAS file. `[GraphQL: SDL has no servers
   block — rely on SCAN42C_HOST or ask for the endpoint URL.]`

   - If `SCAN42C_HOST` environment variable is set → announce silently:
     > "Using scan target from SCAN42C_HOST: `<url>`"
     Store as `SCAN_TARGET_URL` and proceed.
   - If not set → call `AskUserQuestion`:
     - **question**: `"The OAS points to <servers[0].url> as the API target. Is this the right URL to scan against?"` — options: `["Yes — use this URL", "No — I'll provide a different URL"]`  `[GraphQL: "What URL should I scan the GraphQL endpoint against?"]`
     - If **No** → ask the user to provide the URL and store it as `SCAN_TARGET_URL`.
     - If **Yes** → store `servers[0].url` as `SCAN_TARGET_URL`.

5. **API-definition analysis for Phase 2 preview** — run silently after Phase 1
   completes, before asking for Phase 2 permission.

   **`API_TYPE=oas`** — read the OAS file and collect:
   - Total operation count
   - Auth scheme types from `securitySchemes` (Bearer/JWT, API Key, Basic, OAuth2)
   - BOLA candidate count: operations that reference a specific existing resource by a client-supplied id/key/ref — in a **path** parameter (`{…Id}`, `{…Key}`, `{…Ref}`), a **query** parameter (`?orderId=`), or a **request-body field** (`POST /lookup {orderId}`, `POST /transfer {fromAccountId, toAccountId}`). Method does not gate candidacy; only pure collection or create-new operations are excluded
   - Whether the OAS contains sample data: any operation with `example`, `examples`, or `default` values on its request body or parameter schemas

   **`API_TYPE=graphql`** — read the schema and collect the query + mutation
   count, dependency candidates (non-nullable id/reference arguments), BOLA
   candidates (operations taking a client-supplied reference to an existing
   object), and BFLA candidates (admin/management, other-user, bulk or
   destructive operations). GraphQL declares no auth schemes — credentials
   are collected in the workflow.

   Carry these results forward — the scan workflow reuses them instead of
   re-reading the definition.

6. **Ask for Phase 2 permission.** Output the scan preview as a chat message
   first.

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

7. **Execute Phase 2 — Scan.** Mode is already resolved from pre-flight — do
   not re-derive it.

   **Reachability check** — read `../../references/reachability-check.md` and run
   the two-stage probe now. Return here once it completes (or stop if the user cancels).

   Read the scan workflow file for the resolved `API_TYPE` — and only that file:
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

  **Mandatory checkpoint:** during Phase 2, after any direct edit to
  `CONF_FILE` (including `environments.default.variables.*`, auth wiring, or
  scenario chains), run the config validation checkpoint and resolve all
  errors before continuing to happy-path or full scan runs. `[GraphQL: run scan conf validate --graphql plus the two extra checks in graphql-scan-workflow.md Step 7.]`

8. **Present the final combined summary** (see Output Format below).

9. **Recommend next steps** based on the outcome:

    **If both phases passed and fixes were applied:**
    > "Both audit and scan are passing. Your OAS is more precise and your
    > security contract is enforced. Consider committing the updated OAS file
    > and rerunning `42crunch-api-security-testing` after any significant API change."

    `[GraphQL: "Your GraphQL schema is more precise and its conformance is
    verified against the live endpoint. If your server doesn't yet enforce the
    constraint and cost directives added during the audit, wiring that up is
    the natural next step."]`

    **If either phase failed or the user declined fixes:**
    > "Here's what's still open: [list remaining SQG-failing issues or unfixed
    > scan findings by tier]. When you're ready to address them, run
    > `42crunch-audit` or `42crunch-scan` individually."

    **If no issues were found in either phase:**
    > "Clean result — your API passed both static analysis and live testing.
    > This is a good baseline to maintain."

Only continue after explicit user confirmation at each permission prompt.

---

## Output Format

After both phases complete, produce a summary in this shape.

**`API_TYPE=graphql`** — In Phase 1, GraphQL reports carry a single score:
drop the `(Security: … · Data Validation: …)` suffix from the `Score:` row and
the `Data:` segment from the `Score change:` row. In Phase 2, authorization fixes
are resolver (server-side) changes. Label the file rows
`Schema updated:` instead of `OAS updated:` in both phases.

```
Phase 1 — Audit Complete
  Score:          <score> / 100  (Security: <sec-score> · Data Validation: <data-score>)
  Score change:   <initial-score> → <score>  (<delta>)  |  Data: <initial-data> → <data-score>  (<data-delta>)   ← omit if no fixes applied
  Mode:           Platform                          ← or "Token"
  SQG:            PASSED  (<sqg-name> — your org's security quality gate is met)     ← platform mode, passed
  SQG:            FAILED  (<sqg-name> — the quality gate is not met; fixes above are required)    ← platform mode, failed
  SQG:            N/A  (Token mode — no automated gate; user-defined thresholds applied this session)    ← token mode
  Tag:            <category>:<tagname>              ← platform mode only, when a tag is assigned; omit this row if no tag
  Issues fixed:   2 SQG-blocking  (0 security · 2 data validation)
  OAS updated:    <path/to/openapi.json>

Phase 2 — Scan Complete
  Mode:           Platform                          ← or "Token"
  SQG:            PASSED  (<sqg-name> — your org's security quality gate is met)    ← platform mode, passed
  SQG:            FAILED  (<sqg-name> — the quality gate is not met; fixes above are required)    ← platform mode, failed
  SQG:            N/A  (Token mode — scan findings are informational; no gate enforced)    ← token mode
  Authorization:  BOLA confirmed on 1 operation — OAS updated · server-side fix applied
  Conformance:    1 SQG-blocking issue fixed (OAS + code) · 3 informational findings surfaced
  OAS updated:    <path/to/openapi.json>

```

Show only the one SQG line per phase that matches the current mode and result.

The `Score change:` row in Phase 1 is produced from the delta values computed in
Step 4 of `../../references/audit-workflow.md`. Omit it when no audit fixes were
applied (user declined at the consent gate, or there were no SQG-blocking issues).

If a phase was skipped (user declined), note that instead of its results.

---

## Environment Variables

| Variable       | Purpose |
|----------------|---------|
| `SCAN42C_HOST` | Scan target base URL (overrides OAS `servers[0]`) — Both modes |

All other variables (`API_KEY`, `PLATFORM_HOST`, `TRIAL_TOKEN`) and general
constraints are defined in `../../references/pre-flight.md`.
