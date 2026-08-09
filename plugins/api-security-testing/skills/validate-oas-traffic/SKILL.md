---
name: validate-oas-traffic
description: >
  Compare an OpenAPI specification against HTTP traffic in HAR files or Postman
  collections to detect contract drift and possible AI hallucinations. Use this
  skill when the user wants to validate an OAS against captured traffic, check
  spec fidelity, find drift between spec and traffic, or verify a generated
  OpenAPI against a Postman collection or HAR. Triggers on phrases like
  "validate traffic", "validate oas against traffic", "check spec against
  postman", "traffic drift", "contract vs traffic", "hallucination check",
  "validate-traffic", or "compare openapi to har".
---

# Validate OAS Against Traffic

Runs **contract-vs-traffic drift analysis** using `42c-ast openapi
validate-traffic`. Compares what the OpenAPI file declares against what was
observed in HAR or Postman traffic. Does **not** require 42Crunch credentials.

Use after generating an OAS from traffic (guardrail against invention or
omission), or any time you want empirical verification of a spec.

---

## Entry Point

1. **Resolve the OAS file.**

   If the user did not provide a path, search the workspace for `.json`/`.yaml`
   files containing `openapi:` (same heuristics as pre-flight OAS detection).
   If multiple candidates exist, call `AskUserQuestion`:
   - **question**: `"I see multiple OpenAPI files. Which one should I validate against traffic?"`
   - List each filename as an option.

   Store the chosen path as `SPEC_PATH`.

2. **Resolve traffic input(s).**

   At least one HAR or Postman collection is required. If not provided, call
   `AskUserQuestion`:
   - **question**: `"Which traffic capture should I compare against the spec?"`
   - **options**: `["Postman collection (I'll provide the path)", "HAR file (I'll provide the path)", "Both Postman and HAR"]`

   Collect absolute or workspace-relative paths. Store as `TRAFFIC_INPUTS[]`.

   **Postman only:** if an environment file may apply, call `AskUserQuestion`:
   - **question**: `"Do you have a Postman environment file to use with the collection?"`
   - **options**: `["Yes — I'll provide the path", "No"]`

   Store optional path as `POSTMAN_ENV`.

   **Unsupported:** Insomnia exports cannot be used as traffic input. If the
   user only has Insomnia, explain they need a HAR capture or Postman
   collection, or run `/generate-oas` with Postman/codebase instead.

3. **Codebase context (optional).**

   If the user mentions the spec was also derived from source code, set
   `CODEBASE_WAS_SOURCE=true` for finding interpretation (see workflow Step 4).
   When invoked standalone, default to `false` unless the user says otherwise.

4. **Ask for permission.** Call `AskUserQuestion`:
   - **question**: `"Ready to compare <spec-filename> against <N> traffic file(s). This checks coverage and drift between the contract and observed traffic. Proceed?"`
   - **options**: `["Yes, proceed", "No, cancel"]`

5. **Execute the workflow.** Read `../../references/validate-traffic-workflow.md`
   and run Steps 0–7. Pass `SPEC_PATH`, `TRAFFIC_INPUTS`, optional
   `POSTMAN_ENV`, and `CODEBASE_WAS_SOURCE`.

6. **Present the final summary** using the workflow output format (Step 5).

---

## Output Format

After the workflow completes, ensure the user sees:

```
Traffic Validation Complete
  Spec:              <path>
  Traffic inputs:    <paths>
  ...

Coverage
  Spec paths:        ...
  Spec operations:   ...

Drift summary
  Blockers:          ...
  Warnings:          ...
  Informational:     ...
```

If remediation was applied, add:

```
Remediation
  Spec updated:      <SPEC_PATH>
  Coverage before:   <paths%> paths · <ops%> operations
  Coverage after:    <paths%> paths · <ops%> operations
```

---

## Recommend Next Steps

Follow Step 7 of the workflow. In addition:

- If the user generated the spec with `/generate-oas` in the same session,
  suggest `/42crunch-audit` as the natural follow-up.
- If blockers indicate traffic-only operations, mention that the traffic
  capture may include endpoints not yet in the spec (omission) or the spec
  may have invented endpoints not in traffic (`openapiOnlyEntries`).

Only continue after explicit user confirmation at the permission and
remediation prompts.
