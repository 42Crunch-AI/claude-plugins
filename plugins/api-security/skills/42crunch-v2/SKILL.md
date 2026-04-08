---
name: 42crunch-v2
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

Orchestrates two phases: **Audit** (static OAS analysis and SQG fix loop) and
**Scan** (live conformance + authorization testing). Each phase requires
explicit user permission before execution.

---

## Entry Point

1. **Setup prerequisite** — always run before proceeding. Read
   `../../references/setup-check.md` and follow it completely. Do not proceed
   if setup fails or the user cancels.

2. **Resolve the OAS file.**
   - If the user provided a path → use it.
   - If exactly one OAS file (`.json` or `.yaml` containing `openapi:`) is open in the editor → use it.
   - If **multiple** OAS files are open → call `AskUserQuestion`:
     - **question**: `"I see multiple OpenAPI files open. Which one should I run through the pipeline?"` — list each filename as an option.
   - If **no** OAS file can be resolved → call `AskUserQuestion`:
     - **question**: `"I couldn't find an OpenAPI file. Would you like me to generate one from your source code first?"` — options: `["Yes — generate from source code", "No — I'll provide a path"]`
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
   Phase 1 permission. If no tag is found, stop as described in
   `../../references/tag-detection.md`.

5. **Ask for Phase 1 permission.** Call `AskUserQuestion`:
   - **question**: `"Ready to run a 42Crunch Audit on <filename>. This will analyse your OAS file and produce a scored report. Shall I proceed?"`
   - **options**: `["Yes, proceed", "No, cancel"]`

6. **Execute Phase 1 — Audit.** Read `../../references/audit-workflow.md`.
   The workflow runs the audit, then presents a **developer-readable,
   risk-classified report** (SQG-Blocking / Security / Data Validation tiers)
   with plain-English titles and risk descriptions — no raw rule IDs. It then
   pauses and asks the user to consent before applying any fixes. Fixes are
   only applied after explicit confirmation.

7. **OAS analysis for Phase 2 preview** — run silently after Phase 1 completes,
   before asking for Phase 2 permission.

   Read the OAS file and collect:
   - Total operation count
   - Auth scheme types from `securitySchemes` (Bearer/JWT, API Key, Basic, OAuth2)
   - BOLA candidate count: operations where the path has `{…Id}`, `{…Key}`, `{…Ref}`, or similar resource-ID placeholders AND the method is GET, PUT, PATCH, or DELETE
   - Whether the OAS contains sample data: any operation with `example`, `examples`, or `default` values on its request body or parameter schemas

8. **Ask for Phase 2 permission.** Call `AskUserQuestion`:
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

9. **Execute Phase 2 — Scan.** Read `../../references/scan-workflow.md`.
   The workflow runs the scan, then presents a **risk-classified findings
   report** (Authorization failures / SQG-blocking conformance /
   informational conformance). Fix candidates are determined by SQG-blocking
   rules and authorization failures — not severity alone. The skill pauses and
   asks the user to consent before applying any OAS changes.

10. **Present the final combined summary** (see Output Format below).

11. **Recommend next steps** based on the outcome:

    **If both phases passed and fixes were applied:**
    > "Both audit and scan are passing. Your OAS is more precise and your
    > security contract is enforced. Consider committing the updated OAS file
    > and rerunning `42crunch-v2` after any significant API change."

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

After both phases complete, produce a summary in this shape:

```
Phase 1 — Audit Complete
  Score:          <score> / 100  (Security: <sec-score> · Data Validation: <data-score>)
  Score change:   <initial-score> → <score>  (<delta>)  |  Data: <initial-data> → <data-score>  (<data-delta>)   ← omit if no fixes applied
  Mode:           Platform                          ← or "Freemium"
  SQG:            PASSED  (Security-Guardrails — your org's security quality gate is met)     ← platform, passed
  SQG:            FAILED  (Security-Guardrails — the quality gate is not met; fixes above are required)    ← platform, failed
  SQG:            N/A  (Freemium — no automated gate; user-defined thresholds applied this session)    ← freemium mode
  Tag:            <category>:<tagname>              ← platform mode only
  Issues fixed:   2 SQG-blocking  (0 security · 2 data validation)
  OAS updated:    <path/to/openapi.json>

Phase 2 — Scan Complete
  Mode:           Platform                          ← or "Freemium"
  SQG:            PASSED  (Security-Guardrails — your org's security quality gate is met)    ← platform, passed
  SQG:            FAILED  (Security-Guardrails — the quality gate is not met; fixes above are required)    ← platform, failed
  SQG:            N/A  (Freemium — scan findings are informational; no gate enforced)    ← freemium mode
  Authorization:  BOLA confirmed on 1 operation — fixed in OAS
  Conformance:    1 SQG-blocking issue fixed · 3 informational findings surfaced
  OAS updated:    <path/to/openapi.json>
```

Show only the one SQG line per phase that matches the current mode and result.

The `Score change:` row in Phase 1 is produced from the delta values computed in
Step 4 of `../../references/audit-workflow.md`. Omit it when no audit fixes were
applied (user declined at the consent gate, or there were no SQG-blocking issues).

If a phase was skipped (user declined), note that instead of its results.

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

**Platform mode**: `API_KEY` and `PLATFORM_HOST` are set for every command. `--tag` and `--report-sqg` are applied when a tag is resolved.

**Freemium mode**: `--freemium-host stateless.42crunch.com:443` and `--token <FREEMIUM_TOKEN>` are used for every command. No `--tag` or `--report-sqg`.
