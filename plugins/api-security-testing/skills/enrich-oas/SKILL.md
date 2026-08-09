---
name: enrich-oas
description: >
  Enrich an OpenAPI 3.0 specification with request/response examples extracted
  from HAR files or Postman collections using 42c-ast openapi enrich. Use this
  skill when the user wants to add traffic examples into an existing OAS, quick
  enrich a spec, fill OpenAPI examples from Postman or HAR, or populate
  example values without inventing new paths. Triggers on phrases like "enrich
  oas", "enrich openapi", "quick enrich", "add examples from postman", "add
  examples from har", "openapi enrich", or "fill openapi examples from traffic".
---

# Enrich OAS From Traffic

Runs **quick enrich** using `42c-ast openapi enrich`. Adds OpenAPI `examples`
under existing path operations from HAR or Postman traffic. Does **not**
require 42Crunch credentials.

Enrich only fills slots the spec already declares (responses, requestBody,
header parameters). It does not invent new paths, methods, or status codes.

This skill is **standalone** — it is not invoked automatically from
`generate-oas`.

---

## Entry Point

1. **Resolve the OAS file.**

   If the user did not provide a path, search the workspace for `.json`/`.yaml`
   files containing `openapi:` (same heuristics as pre-flight OAS detection).
   If multiple candidates exist, call `AskUserQuestion`:
   - **question**: `"I see multiple OpenAPI files. Which one should I enrich with traffic examples?"`
   - List each filename as an option.

   Store the chosen path as `SPEC_PATH`.

   If `openapi` is not `3.0.x`, warn that enrich currently targets OpenAPI
   3.0.x and ask whether to continue or cancel.

2. **Resolve traffic input(s).**

   At least one HAR or Postman collection is required. If not provided, call
   `AskUserQuestion`:
   - **question**: `"Which traffic capture should I use to enrich the spec?"`
   - **options**: `["Postman collection (I'll provide the path)", "HAR file (I'll provide the path)", "Both Postman and HAR"]`

   Collect absolute or workspace-relative paths. Store as `TRAFFIC_INPUTS[]`.

   **Postman only:** if an environment file may apply, call `AskUserQuestion`:
   - **question**: `"Do you have a Postman environment file to use with the collection?"`
   - **options**: `["Yes — I'll provide the path", "No"]`

   Store optional path as `POSTMAN_ENV`.

   **Unsupported:** Insomnia exports cannot be used as traffic input. If the
   user only has Insomnia, explain they need a HAR capture or Postman
   collection.

3. **Ask for permission (includes overwrite).** Call `AskUserQuestion`:
   - **question**: `"Ready to enrich <spec-filename> from <N> traffic file(s) and overwrite that same OpenAPI file with added examples. Proceed?"`
   - **options**: `["Yes, enrich and overwrite", "No, cancel"]`

4. **Execute the workflow.** Read `../../references/enrich-workflow.md` and
   run Steps 0–6. Pass `SPEC_PATH`, `TRAFFIC_INPUTS`, and optional
   `POSTMAN_ENV`. Step 3 overwrite confirmation may be skipped if this entry
   prompt already covered it.

5. **Present the final summary** using the workflow output format (Step 5).

---

## Output Format

After the workflow completes, ensure the user sees:

```
OAS Enrichment Complete
  Spec:              <path>
  Traffic inputs:    <paths>
  ...

Examples
  Before:            ...
  After:             ...
  Delta:             ...
```

---

## Recommend Next Steps

Follow Step 6 of the workflow. In addition:

- Suggest `/validate-oas-traffic` when the user also cares about contract drift.
- Suggest `/42crunch-audit` as the natural security follow-up.

Only continue after explicit user confirmation at the permission prompt.
