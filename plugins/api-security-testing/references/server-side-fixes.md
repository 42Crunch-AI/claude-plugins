# Server-side / Implementation Fixes

Read this only when a scan produced **SQG-blocking findings** and Step 12e-1 of
`./scan-workflow.md` gated into code fixes. OAS fixes document the contract but
do not secure the API — every SQG-blocking finding has a root cause in the
server-side code, which this document locates and fixes.

## Consent gate for code fixes

Call `AskUserQuestion`:
- **question**: `"The OAS has been updated. The following SQG-blocking issues also require server-side code fixes — the API implementation is the root cause. Should I locate and fix the code? <list all SQG-blocking findings by operation>"`
- **options**: `["Yes — find and fix the code", "Show me the relevant code first", "No — skip code fixes"]`

If **"Show me the relevant code first"** is chosen, locate each handler (next
section) and display the relevant code block without making any changes, then
call `AskUserQuestion` again with the same options to proceed.

## Locate route handlers

For each SQG-blocking finding:

1. Search the codebase for files that register or handle the affected HTTP method + path. Use grep for the path fragment and common framework patterns: `router.get/post/put/delete/patch`, `@app.route`, `@GetMapping`, `@PostMapping`, `@RestController`, `app.get(`, `Route::get(`, etc.
2. If not found by path, widen the search to the operation ID or a handler name derived from the path.
3. Read the identified handler file and any middleware it calls (auth middleware, serializers, validators, permission decorators).
4. Report: `"Found handler for <METHOD> <path> in <file>:<line>."`
5. If no handler is found after the widened search, report it as not found and skip the fix for that operation — do not block the remaining fixes.

## Apply fix by finding type

| Finding type | Root cause to look for in the code | Server-side fix |
|---|---|---|
| **BOLA** (OWASP API1) | Handler fetches a resource by a path/query ID without verifying that it belongs to the authenticated user | Add an ownership check after the resource is fetched: compare `resource.owner_id` (or equivalent field) to the authenticated user's ID; return `403 Forbidden` if they do not match |
| **BFLA** (OWASP API5) | Handler for a privileged/admin operation does not check the caller's role, scope, or group membership before executing | Add a role/scope/permission check at the top of the handler; return `403 Forbidden` if the caller lacks the required privilege |
| **Conformance — undocumented response fields** | Response serializer or ORM query returns fields not present in the OAS schema | Call `AskUserQuestion`: _"The response for `<METHOD> <path>` includes fields not declared in the OAS: `<field list>`. Are these intentional?"_ — **options**: `["Add them to the OAS (field is intentional)", "Remove them from the code (field should not be returned)"]`. Apply the chosen fix: extend the OAS schema, or filter/exclude the fields in the serializer/handler |
| **Conformance — missing required response fields** | Handler response omits a field marked `required` in the OAS schema | Add the missing field to the response payload or serializer |
| **Conformance — wrong response status code** | Handler returns a status code that differs from what the OAS declares as the success code | Update the handler to return the status code declared in the OAS |
| **Conformance — wrong or missing Content-Type / headers** | Handler does not set the `Content-Type` or other response headers required by the OAS | Add the required headers to the response |
| **Conformance — schema type/format mismatch** | Handler returns a field with a different type or format than declared (e.g., returns a string where the OAS declares integer) | Coerce or cast the field to the declared type/format in the serializer or handler |

## Diff and confirm before writing

For each proposed code change, display it in unified diff format and call `AskUserQuestion`:
- **question**: `"Apply this fix to <file>?"` — **options**: `["Yes", "No — skip this one"]`

Only write the change after explicit confirmation. Advance to the next finding only after the current one is confirmed or skipped.

## Summary

After all code fixes are applied or skipped, append to the final output:

```
── Server-side Fixes ────────────────────────────────────────────────────
  Fixed:   <n> issue(s) across <m> file(s)
  Skipped: <k> issue(s) (user declined or handler not found)
─────────────────────────────────────────────────────────────────────────
```

Return to `./scan-workflow.md` Step 12f (verification-scan gate) once fixes are
applied or skipped.
