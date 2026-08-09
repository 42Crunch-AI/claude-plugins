# API Security Testing — Recipes

Quick-reference for common scenarios. Each recipe shows what to say to the
AI assistant and what will happen.

---

## Recipe 1 — Full Audit (Standard)

**When to use**: You want to run a fresh audit on your OAS file, review the
findings, and optionally apply fixes.

**What to say**:
> "Run 42crunch audit on my API"

**What happens**:
1. Pre-flight checks (binary, credentials, OAS file detection)
2. Permission prompt before the audit runs
3. Audit executes and produces a risk-classified findings report
4. Consent gate — you choose whether to apply fixes
5. Final summary with score, SQG status, and issues fixed

---

## Recipe 2 — Fix-Only Audit (Existing Report)

**When to use**: You already have an audit report (`report.json`)
from a previous run and want to skip re-running the audit and go straight to
applying the fixes it requires.

**What to say**:
> "Fix the audit issues in `report.json` for `openapi.json`"

or

> "I have an existing audit report at `<path-to-report>`. Apply the fixes to
> `<path-to-oas-file>` without re-running the audit."

**What happens**:
1. Pre-flight checks (binary, credentials, OAS file detection)
2. Audit step is **skipped** — the skill reads your existing report file
3. Findings are parsed and displayed as a risk-classified report
4. Consent gate — you choose which fixes to apply
5. Fixes are applied to the OAS file
6. Final summary (no score-change delta since no fresh audit was run)

**Notes**:
- The report file must be in `json` format produced by `42c-ast audit run` or by the 42crunch extension audit function and exported to JSON format.
- After fixes are applied you may want to run a fresh audit to confirm SQG now passes.

---

## Recipe 3 — Audit Without Fixes (Review Only)

**When to use**: You want to see the audit findings but are not ready to apply
fixes yet — for example, you want to review issues with your team first.

**What to say**:
> "Audit my API and show me the findings, but don't apply any fixes"

**What happens**:
1. Pre-flight and permission prompt
2. Audit runs and the full findings report is shown
3. At the consent gate, the skill notes you've chosen review-only mode and skips fixes
4. Summary is shown with "User reviewed findings — no fixes applied"

---

## Recipe 4 — Full Pipeline (Audit + Scan)

**When to use**: You want to run both the static audit and a live scan against
a running API instance in a single session.

**What to say**:
> "Run the full 42crunch security check on my API"

or

> "Run audit and scan"

**What happens**:
1. Phase 1 — Audit (same as Recipe 1)
2. Scan target URL is resolved (from OAS `servers[0]` or `SCAN42C_HOST`)
3. Reachability probe confirms the API is reachable
4. Phase 2 permission prompt with a preview of what the scan will test
5. Phase 2 — Scan (conformance + authorization testing)
6. Final combined summary with both phase results

**Notes**:
- Your API server must be running and reachable before Phase 2 starts.
- Set `SCAN42C_HOST` environment variable to override the URL from the OAS file.

---

## Recipe 5 — Scan Only (Audit Already Passing)

**When to use**: Your OAS file is already audit-clean (SQG passing) and you
want to run a live conformance and authorization scan without re-auditing.

**What to say**:
> "Run a 42crunch scan against my API"

or

> "Run conformance test on my API"

**What happens**:
1. Pre-flight checks
2. Scan target URL resolved and reachability check run
3. Permission prompt before scan starts
4. Scan runs (BOLA, BFLA, conformance testing)
5. Risk-classified findings report shown
6. Consent gate for any OAS fixes the scan identifies
7. Final scan summary

---

## Recipe 6 — Generate OAS, Then Audit

**When to use**: You don't have an OAS file yet — you want to generate one
from your API source code, a Postman or Insomnia collection, or both, and
then immediately audit it.

**What to say**:
> "Generate an OpenAPI spec from my code and then audit it"

or

> "Generate an OpenAPI spec from my Postman collection and then audit it"

or

> "Generate an OpenAPI spec from my Insomnia collection and then audit it"

**What happens**:
1. `generate-oas` skill asks whether you have a codebase and/or a Postman or
   Insomnia collection, then writes `openapi.json` from whichever source(s)
   you provide.
2. If a Postman collection was used, traffic validation runs automatically
   and drift findings are included in the generation summary.
3. `42crunch-audit` skill runs on the generated file
4. Findings shown and fixes optionally applied

---

## Recipe 7 — Setup Only

**When to use**: First-time setup — you need to install the `42c-ast` binary
and configure credentials before running any audit or scan.

**What to say**:
> "Set up 42crunch"

or

> "Install 42c-ast and configure my API key"

**What happens**:
1. Binary discovery and install (downloads `42c-ast` to `~/.42crunch/bin/`)
2. Credential configuration (API key + platform host written to `~/.42crunch/conf/env`)
3. Confirmation that setup is complete and the next step is to run an audit

---

## Recipe 8 — Validate OAS Against Traffic

**When to use**: You have an OpenAPI file and a HAR or Postman capture and
want to check whether the spec matches observed traffic — for example after
AI-generated documentation or to catch invented endpoints and fields.

**What to say**:
> "Validate my OpenAPI spec against this Postman collection"

or

> "Check traffic drift on openapi.json using capture.har"

**What happens**:
1. Resolves the OAS file and traffic input(s)
2. Runs `42c-ast openapi validate-traffic` (local, no credentials required)
3. Coverage and drift report with blocker/warning/informational tiers
4. Optional consent to update the OAS to align with traffic evidence
5. Suggestion to run `/42crunch-audit` when validation looks clean

**Notes**:
- Insomnia exports cannot be used as traffic input — use Postman or HAR.
- For pre-release AST builds, set `AST_VALIDATE_TRAFFIC_BINARY` to the binary path.

---

## Recipe 9 — Enrich OAS From Traffic

**When to use**: You have an OpenAPI 3.0.x file and a HAR or Postman capture
and want to add real request/response `examples` into slots the spec already
declares — without inventing new paths or operations.

**What to say**:
> "Enrich my OpenAPI spec with examples from this Postman collection"

or

> "Quick enrich openapi.json using capture.har"

**What happens**:
1. Resolves the OAS file and traffic input(s)
2. Confirms overwrite of the same OpenAPI file
3. Runs `42c-ast openapi enrich` (local, no credentials required)
4. Summarizes example counts before/after
5. Suggests `/validate-oas-traffic` or `/42crunch-audit` as optional follow-ups

**Notes**:
- Standalone skill — not run automatically from `/generate-oas`.
- Insomnia exports cannot be used as traffic input — use Postman or HAR.
- Same pre-release binary env var (`AST_VALIDATE_TRAFFIC_BINARY`) as Recipe 8.

---

## Choosing the Right Recipe

| Situation | Recipe |
|-----------|--------|
| First time using 42Crunch | Recipe 7 (Setup), then Recipe 1 |
| Audit a new or changed OAS file | Recipe 1 |
| Already have an audit report, just want fixes | Recipe 2 |
| Review findings with your team before fixing | Recipe 3 |
| Audit + live scan in one session | Recipe 4 |
| OAS is clean, server is running — scan only | Recipe 5 |
| No OAS file yet, generate from code and/or Postman/Insomnia first | Recipe 6 |
| Spec may not match traffic / check for AI hallucinations | Recipe 8 |
| Add traffic examples into an existing OAS | Recipe 9 |
