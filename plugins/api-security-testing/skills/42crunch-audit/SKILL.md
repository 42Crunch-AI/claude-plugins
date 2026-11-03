---
name: 42crunch-audit
description: >
  Run a 42Crunch API Security Audit and fix SQG-blocking issues in an OpenAPI
  Specification file or GraphQL schema. Use this skill whenever the user wants
  to audit an OAS file or GraphQL schema for security issues, fix SQG-blocking
  issues, score an API, or remediate audit findings. Triggers on phrases like
  "run audit", "audit only", "fix audit issues", "SQG audit", "42crunch audit",
  "audit score", "audit my graphql schema", "graphql audit", or any request
  focused on static API-definition analysis and remediation without running a
  live scan.
---

# 42Crunch Audit Skill

Runs a single phase: **Audit** (static analysis of an OpenAPI definition or
GraphQL schema, SQG reporting, and SQG-blocking fix loop). Requires explicit
user permission before execution. Does **not** run a live scan — use the
`42crunch-scan` skill for that.

---

## Entry Point

1. **Pre-flight checks.** Read `../../references/pre-flight.md` and complete
   all steps (setup, API definition resolution, tag detection). When prompting
   for file selection, use the context `"audit"` (e.g. "Which one should I
   audit?"). Pre-flight sets `API_TYPE` (`oas` or `graphql`) — carry it
   forward. Do not proceed if any step fails or the user cancels.

2. **Ask for permission.** Call `AskUserQuestion`:
   - **question**: `"Ready to run a 42Crunch Audit on <filename>. This will analyse your <OAS file / GraphQL schema> and produce a scored report. Shall I proceed?"`
   - **options**: `["Yes, proceed", "No, cancel"]`

3. **Execute the Audit.** Mode is already resolved from pre-flight — do not
   re-derive it. Read the workflow file for the resolved `API_TYPE` — and
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

4. **Present the final audit summary** (see Output Format below).

5. **Recommend next steps** based on the outcome:

   **If SQG PASSED (`API_TYPE=oas`):**
   > "Your audit is complete and the SQG is passing. The natural next step is to
   > run a live scan to test conformance and authorization against a running
   > instance of your API. Just say `run scan` when your API server is available."

   **If SQG FAILED (user declined to fix):**
   > "Your audit findings are saved above. When you're ready to address the
   > SQG-blocking issues, run `42crunch-audit` again on this file and I'll apply
   > the fixes. Once the audit passes, run `42crunch-scan` to test the live API."

   **If no issues found (`API_TYPE=oas`):**
   > "No issues found — your API has a clean audit result. Run `42crunch-scan`
   > to verify the live API matches its contract."

   **`API_TYPE=graphql` (passed or clean):** replace the scan suggestion with:
   > "The natural next step is a live conformance scan against your running
   > GraphQL endpoint — say `run scan` when the server is available. If your
   > server's GraphQL engine doesn't yet enforce the constraint and cost
   > directives added here, wiring that up is worth scheduling too."

Only continue after explicit user confirmation at each permission prompt.

---

## Output Format

After the audit completes, produce a summary in this shape.

**`API_TYPE=graphql`** — GraphQL reports carry a single score: drop the
`(Security: … · Data Validation: …)` suffix from the `Score:` row and the
`Data:` segment from the `Score change:` row; label the file row
`Schema updated:` instead of `OAS updated:`. Everything else is identical.

```
Audit Complete
  Score:          <score> / 100  (Security: <sec-score> · Data Validation: <data-score>)
  Score change:   <initial-score> → <score>  (<delta>)  |  Data: <initial-data> → <data-score>  (<data-delta>)   ← omit if no fixes applied
  SQG:            PASSED  (<sqg-name> — your org's security quality gate is met)    ← platform mode, passed
  SQG:            FAILED  (<sqg-name> — the quality gate is not met; fixes above are required)    ← platform mode, failed
  SQG:            N/A  (Token mode — no automated gate; user-defined thresholds applied this session)    ← token mode
  Mode:           Platform / Token
  Tag:            <category>:<tagname>             ← platform mode only, when a tag is assigned; omit this row if no tag
  Issues fixed:   2 SQG-blocking  (0 security · 2 data validation)
  OAS updated:    <path/to/openapi.json>

```

Show only the one SQG line that matches the current mode and result.

The `Score change:` row is produced from the delta values computed in Step 4 of
`../../references/audit-workflow.md`. Omit it when no fixes were applied (user
declined at the consent gate, or there were no SQG-blocking issues).

If the user declined to apply fixes, note that instead.
