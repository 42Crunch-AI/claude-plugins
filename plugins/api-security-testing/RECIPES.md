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
