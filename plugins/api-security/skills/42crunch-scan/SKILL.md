---
name: 42crunch-scan
description: >
  Run a 42Crunch live conformance and authorization scan against an API and fix
  SQG-blocking scan findings. Use this skill whenever the user wants to run a
  conformance test, authorization scan, BOLA test, BFLA test, generate or
  configure a scan config, or fix scan-reported issues. Triggers on phrases
  like "run scan", "scan only", "conformance test", "BOLA test", "BFLA test",
  "42crunch scan", "scan config", or any request focused on live API testing
  without running a static audit. Use 42crunch-v2 when the user wants both
  audit and scan together.
---

# 42Crunch Scan Skill

Runs a single phase: **Scan** (live conformance + authorization testing and
SQG-blocking fix loop). Requires explicit user permission before execution.
Does **not** run a static audit — use the `42crunch-audit` skill for that.

Assumes the OAS file is already audit-clean (or the user is explicitly
running scan only). If the user mentions audit issues before scanning, suggest
running `42crunch-audit` first.

---

## Entry Point

1. **Setup prerequisite** — always run before proceeding. Read
   `../../references/setup-check.md` and follow it completely. Do not proceed
   if setup fails or the user cancels.

2. **Resolve the OAS file.**
   - If the user provided a path → use it.
   - If exactly one OAS file (`.json` or `.yaml` containing `openapi:`) is open in the editor → use it.
   - If **multiple** OAS files are open → call `AskUserQuestion`:
     - **question**: `"I see multiple OpenAPI files open. Which one should I scan?"` — list each filename as an option.
   - If **no** OAS file can be resolved → call `AskUserQuestion`:
     - **question**: `"I couldn't find an OpenAPI file to scan. Would you like me to generate one from your source code first?"` — options: `["Yes — generate from source code", "No — I'll provide a path"]`
     - If **Yes** → invoke the `code-to-oas` skill, then resume with the generated file.
     - If **No** → ask the user to provide the file path and wait.

3. **Resolve the scan target URL.**

   Read `servers[0].url` from the OAS file.

   - If `SCAN42C_HOST` environment variable is set → announce silently:
     > "Using scan target from SCAN42C_HOST: `<url>`"
     Store as `SCAN_TARGET_URL` and proceed.
   - If not set → call `AskUserQuestion`:
     - **question**: `"The OAS points to <servers[0].url> as the API target. Is this the right URL to scan against?"` — options: `["Yes — use this URL", "No — I'll provide a different URL"]`
     - If **No** → ask the user to provide the URL and store it as `SCAN_TARGET_URL`.
     - If **Yes** → store `servers[0].url` as `SCAN_TARGET_URL`.

   **Reachability check** — run immediately after `SCAN_TARGET_URL` is confirmed.
   Uses a two-stage probe to distinguish "server is down" from "wrong base URL".

   **Stage 1** — probe the base URL:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" --max-time 5 <SCAN_TARGET_URL>/
   ```
   - **2xx, 3xx, 401, 403, or 405** → API is reachable. Proceed silently.
   - **Connection refused or timeout** → call `AskUserQuestion`:
     - **question**: `"I couldn't reach <SCAN_TARGET_URL> — the connection timed out or was refused. How would you like to proceed?"`
     - **options**: `["Try a different URL", "Continue anyway — the API may be temporarily down", "Cancel"]`
     - If **Try a different URL** → ask for new URL, store as `SCAN_TARGET_URL`, re-run from Stage 1.
     - If **Continue anyway** → proceed with warning noted.
     - If **Cancel** → stop.
   - **404** → ambiguous (server may be up but nothing is mounted at root). Proceed to Stage 2.

   **Stage 2** — probe the first simple OAS path (only reached when Stage 1 returns 404):
   Find the first `GET` path in the OAS that has no required path parameters. Strip any
   `{param}`-style segments and probe:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" --max-time 5 <SCAN_TARGET_URL><first_simple_path>
   ```
   - **Any HTTP response** → server is up; root just has no handler. Proceed silently.
   - **Connection refused or timeout** → same `AskUserQuestion` as Stage 1.
   - **404 again** → call `AskUserQuestion`:
     - **question**: `"The server responded but both / and <path> returned 404 — the base URL may be incorrect (the API may be mounted at a different prefix). How would you like to proceed?"`
     - **options**: `["Try a different URL", "Continue anyway", "Cancel"]`
     - If **Try a different URL** → ask for new URL, store as `SCAN_TARGET_URL`, re-run from Stage 1.
     - If **Continue anyway** → proceed with warning noted.
     - If **Cancel** → stop.

4. **Tag detection** — platform mode only. Run silently. Read
   `../../references/tag-detection.md`. In freemium mode, skip tag detection
   entirely. If a tag is found, announce it to the user before asking for
   permission. If no tag is found, stop as described in
   `../../references/tag-detection.md`.

5. **OAS analysis for scan preview** — run silently before asking permission.

   Read the OAS file and collect:
   - Total operation count
   - Auth scheme types from `securitySchemes` (Bearer/JWT, API Key, Basic, OAuth2)
   - BOLA candidate count: operations where the path has `{…Id}`, `{…Key}`, `{…Ref}`, or similar resource-ID placeholders AND the method is GET, PUT, PATCH, or DELETE
   - Whether the OAS contains sample data: any operation with `example`, `examples`, or `default` values on its request body or parameter schemas

6. **Ask for permission to configure the scan.** Call `AskUserQuestion`:
   - **question**: (show the scan preview first, then ask)
     ```
     Ready to configure the scan?
       Target:   <SCAN_TARGET_URL>  ✓ reachable  /  ⚠ reachability unknown
       OAS:      <filename>  (<N> operations)
       Auth:     <scheme types>  [+  second user needed — <N> BOLA candidate(s)]
       Samples:  OAS has sample data  /  No samples — you'll need to provide test data
       Tag:      <category>:<tagname>           ← platform mode only
       Mode:     Platform / Freemium
     ```
     `"I'm ready to start configuring the scan. I'll ask for credentials, classify your operations, and set up test scenarios — then run a happy path validation before the full scan. Shall I proceed?"`
   - **options**: `["Yes, let's configure", "No, cancel"]`

7. **Execute the Scan.** Read `../../references/scan-workflow.md`.
   The workflow sets up the scan config, collects credentials, gathers test data,
   classifies operations, validates happy paths, then asks for permission again
   before running the full scan. It presents a **risk-classified findings report**
   (Authorization failures / SQG-blocking conformance / informational conformance)
   and pauses for consent before applying any OAS changes.

   **Freemium mode**: no SQG is enforced for scan. Present all findings for
   information. The user decides which (if any) to fix.

8. **Present the final scan summary** (see Output Format below).

Only continue after explicit user confirmation at each permission prompt.

---

## Output Format

After the scan completes, produce a summary in this shape:

```
Scan Complete
  Mode:           Platform / Freemium
  SQG:            PASSED  (Security-Guardrails — your org's security quality gate is met)    ← platform mode, passed
  SQG:            FAILED  (Security-Guardrails — the quality gate is not met; fixes above are required)    ← platform mode, failed
  SQG:            N/A  (Freemium — scan findings are informational; no gate enforced)    ← freemium mode
  Tag:            <category>:<tagname>             ← platform mode only
  Authorization:  BOLA confirmed on 1 operation — fixed in OAS
  Conformance:    1 SQG-blocking issue fixed · 3 informational findings surfaced
  OAS updated:    <path/to/openapi.json>
```

Show only the one SQG line that matches the current mode and result.

If the user declined to apply fixes or no issues were found, note that instead.

---

## General Constraints

- Use `bash_tool` to execute all `42c-ast` commands.
- Use `str_replace` or `create_file` to apply fixes to the OAS file.
- Never modify the OAS file without first describing what will change.
- All credential inputs are ephemeral in-session values. Do not write tokens
  or passwords to disk outside of scan config files that already expect them.
- Surface brief status lines before slow network operations (manifest fetch, binary download, tag detection). Do not surface individual sub-steps like SHA-256 verification or file writes.

---

## Environment Variables

| Variable          | Mode      | Purpose                                   | Default                            |
|-------------------|-----------|-------------------------------------------|------------------------------------|
| `API_KEY`         | Platform  | `api_*` or `ide_*` token                 | —                                  |
| `PLATFORM_HOST`   | Platform  | Platform base URL                         | —                                  |
| `FREEMIUM_TOKEN`  | Freemium  | Base64 token, passed as `--token`         | —                                  |
| `SCAN42C_HOST`    | Both      | Scan target base URL (overrides OAS `servers[0]`) | None                       |

**Platform mode**: `API_KEY` and `PLATFORM_HOST` set for every command. `--tag` applied when a tag is resolved. SQG enforced from platform.

**Freemium mode**: `--freemium-host stateless.42crunch.com:443` and `--token <FREEMIUM_TOKEN>` used for every command. No `--tag`. No scan SQG enforcement — present all findings informally.
