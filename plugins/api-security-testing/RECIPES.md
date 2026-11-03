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
2. `42crunch-audit` skill runs on the generated file
3. Findings shown and fixes optionally applied

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

## Recipe 8 — GraphQL Schema Audit

**When to use**: Your API is GraphQL — you want a scored security audit of the
schema (SDL) with AI-assisted directive fixes.

**What to say**:
> "Run a 42crunch audit on my GraphQL schema"

or

> "Audit `schema.graphql`"

**What happens**:
1. Pre-flight checks (binary, credentials, schema file detection)
2. Permission prompt before the audit runs
3. GraphQL audit executes and produces a findings report classified into
   Resource Limiting (query cost, list sizes) and Data Validation (scalar
   constraints) tiers
4. Consent gate — you choose whether to apply fixes; fixes annotate the
   schema with constraint and cost directives (`@stringValue`, `@numberValue`,
   `@list`, `@cost`) and declare their definitions in the SDL
5. Re-audit confirms the score improvement / SQG passage
6. Final summary with score and SQG status

**Notes**:
- Directives added to the schema are contract metadata — configure your
  GraphQL engine (cost-analysis / constraint plugins) to enforce them at
  runtime.
- To also test the live endpoint, follow with Recipe 9.

---

## Recipe 9 — GraphQL Conformance Scan

**When to use**: Your GraphQL schema is audit-clean and you want to test the
running endpoint's conformance to the schema contract.

**What to say**:
> "Run a 42crunch scan on my GraphQL API"

or

> "Scan `schema.graphql` against http://localhost:4000/graphql"

**What happens**:
1. Pre-flight checks (binary, credentials, schema detection)
2. Target URL confirmed and reachability probe run
3. You're asked how the API authenticates (login mutation / bearer token /
   API-key header / none), plus a second user or an admin when the schema has
   BOLA/BFLA candidates — a GraphQL schema declares no auth
4. Operations (queries + mutations) are classified and any dependency chains
   (e.g. `book(id)` needs `addBook` first) proposed for your confirmation
5. A happy-path validation run, then the full scan (conformance fuzzing plus
   BOLA/BFLA tests) after your consent
6. Authorization findings confirmed against the response data, then findings
   classified into authorization, SQG-blocking and informational tiers;
   consent gate before any schema or resolver fixes

**Notes**:
- Set `SCAN42C_HOST` to override the endpoint URL.

---

## Recipe 10 — GraphQL Audit + Scan

**When to use**: Full pipeline on a GraphQL API — audit the schema, then scan
the live endpoint, in one session.

**What to say**:
> "Run the full 42crunch check on my GraphQL API"

**What happens**:
1. Phase 1 — GraphQL schema audit (Recipe 8)
2. Phase 2 — GraphQL scan (Recipe 9)
3. Combined summary across both phases

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
| GraphQL API — audit the schema | Recipe 8 |
| GraphQL API — scan the live endpoint | Recipe 9 |
| GraphQL API — audit + scan in one session | Recipe 10 |
