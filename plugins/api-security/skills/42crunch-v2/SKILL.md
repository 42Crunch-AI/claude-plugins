---
name: 42crunch-v2
description: >
  Run 42Crunch API Security audit and scan workflows against an OpenAPI
  Specification file. Use this skill whenever the user wants to audit an OAS
  file for security issues, run a conformance or authorization scan, fix
  SQG-blocking issues, test for BOLA or BFLA vulnerabilities, or generate and
  configure a 42Crunch scan. Triggers on phrases like "run audit", "run scan",
  "42crunch", "SQG", "conformance test", "fix audit issues", "BOLA test",
  "BFLA test", or any reference to API security scoring or scan configuration.
  Always use this skill when the user is working with 42Crunch tooling even if
  they only mention one phase.
---

# 42Crunch API Security Skill

Orchestrates two phases: **Audit** (static OAS analysis and SQG fix loop) and
**Scan** (live conformance + authorization testing). Each phase requires
explicit user permission before execution.

---

## Entry Point

1. **Resolve the OAS file.** Use the file currently open in the editor, or
   accept a path provided by the user.

2. **Setup prerequisite** — always run silently before proceeding.

   **A. Binary version check (always runs):**

   Resolve the canonical binary path for the current OS:
   - macOS/Linux: `$HOME/.42crunch/bin/42c-ast`
   - Windows: `$env:APPDATA\42Crunch\bin\42c-ast.exe`

   Check if the binary exists:
   - **Missing** → invoke `42crunch-setup-v2` for full setup. Do not proceed if
     setup fails.
   - **Present** → run silently:
     1. Get installed version: `"$BINARY_PATH" --version`
     2. Fetch manifest: `curl -fsSL https://repo.42crunch.com/downloads/42c-ast-manifest.json`
     3. Compare installed version to `LATEST_VERSION` for the current platform.
     4. **Outdated** → silently download and replace the binary using the same
        install steps as `42crunch-setup-v2` (download → SHA-256 verify → chmod +x).
        Inform the user: `42c-ast updated from v<old> to v<new>.`
     5. **Up to date** → proceed silently.
     6. **Manifest fetch fails** → warn but continue with the installed binary.

   **B. Credentials check (runs after binary is confirmed):**

   ```bash
   grep -E "^(FREEMIUM_TOKEN|API_KEY)=" "$HOME/.42crunch/conf/env" 2>/dev/null
   ```

   - **Credentials missing** → invoke `42crunch-setup-v2` (credentials flow
     only). Do not proceed if setup fails.
   - **Credentials present** → proceed silently to Step 3.

3. **Credential check** — run silently.

   Read `~/.42crunch/conf/env` (macOS/Linux) or `%APPDATA%\42Crunch\conf\env`
   (Windows) — the config written by `42crunch-setup-v2`:

   ```bash
   grep -E "^(FREEMIUM_TOKEN|API_KEY)=" "$HOME/.42crunch/conf/env" 2>/dev/null
   ```

   - **`FREEMIUM_TOKEN`** is set → **Freemium mode**. Use
     `--freemium-host stateless.42crunch.com:443` and `--token <FREEMIUM_TOKEN>`
     in all commands. Proceed silently.
   - **`API_KEY`** starts with `api_` or `ide_` → **Platform mode**. Read
     `PLATFORM_HOST` from the same file (default
     `https://demolabs.42crunch.cloud`). Proceed silently.
   - **Neither found** → stop: "No credential found. Run `42crunch-setup-v2`
     to configure your token."

4. **Tag detection** — platform mode only. Run silently. Read
   `references/tag-detection.md`. In freemium mode, skip tag detection
   entirely. If a tag is found, announce it to the user before asking for
   Phase 1 permission. If no tag is found, stop as described in
   `references/tag-detection.md`.

5. **Ask for Phase 1 permission.**
   > "Ready to run a 42Crunch Audit on `<filename>`. This will analyse your
   > OAS file and produce a scored report. Shall I proceed?"

6. **Execute Phase 1 — Audit.** Read `references/audit-workflow.md`.
   The workflow runs the audit, then presents a **developer-readable,
   risk-classified report** (SQG-Blocking / Security / Data Validation tiers)
   with plain-English titles and risk descriptions — no raw rule IDs. It then
   pauses and asks the user to consent before applying any fixes. Fixes are
   only applied after explicit confirmation.

7. **Ask for Phase 2 permission.**
   > "The audit is complete. Ready to run a 42Crunch Scan against the live API
   > to test conformance and authorization. Shall I proceed?"

8. **Execute Phase 2 — Scan.** Read `references/scan-workflow.md`.
   The workflow runs the scan, then presents a **risk-classified findings
   report** (Authorization failures / SQG-blocking conformance /
   informational conformance). Fix candidates are determined by SQG-blocking
   rules and authorization failures — not severity alone. The skill pauses and
   asks the user to consent before applying any OAS changes.

9. **Present the final combined summary** (see Output Format below).

Only continue after explicit user confirmation at each permission prompt.

---

## Output Format

After both phases complete, produce a summary in this shape:

```
Phase 1 — Audit Complete
  Score:          <score> / 100  (Security: <sec-score> · Data Validation: <data-score>)
  Score change:   <initial-score> → <score>  (<delta>)  |  Data: <initial-data> → <data-score>  (<data-delta>)   ← omit if no fixes applied
  Mode:           Platform                          ← or "Freemium"
  SQG:            PASSED  (Security-Guardrails)     ← platform: from sqg.json
  SQG:            PASSED  (Freemium)                ← freemium: score ≥ 70, no MEDIUM+
  Tag:            <category>:<tagname>              ← platform mode only
  Issues fixed:   2 SQG-blocking  (0 security · 2 data validation)
  OAS updated:    <path/to/openapi.json>

Phase 2 — Scan Complete
  Mode:           Platform                          ← or "Freemium"
  SQG:            PASSED  (Security-Guardrails)     ← platform mode
  SQG:            N/A  (Freemium — no scan SQG)     ← freemium mode
  Authorization:  BOLA confirmed on 1 operation — fixed in OAS
  Conformance:    1 SQG-blocking issue fixed · 3 informational findings surfaced
  OAS updated:    <path/to/openapi.json>
```

The `Score change:` row in Phase 1 is produced from the delta values computed in
Step 4 of `references/audit-workflow.md`. Omit it when no audit fixes were
applied (user declined at the consent gate, or there were no SQG-blocking issues).

Show only the SQG line appropriate for the active mode.

If a phase was skipped (user declined), note that instead of its results.

---

## General Constraints

- Use `bash_tool` to execute all `42c-ast` commands.
- Use `str_replace` or `create_file` to apply fixes to the OAS file.
- Never modify the OAS file without first describing what will change.
- All credential inputs are ephemeral in-session values. Do not write tokens
  or passwords to disk outside of scan config files that already expect them.
- Do not log, print, or surface any intermediate step of binary discovery or
  tag detection unless there is a failure.

---

## Environment Variables

| Variable          | Mode      | Purpose                                   | Default                            |
|-------------------|-----------|-------------------------------------------|------------------------------------|
| `API_KEY`         | Platform  | `api_*` or `ide_*` token                 | —                                  |
| `PLATFORM_HOST`   | Platform  | Platform base URL                         | `https://demolabs.42crunch.cloud`  |
| `FREEMIUM_TOKEN`  | Freemium  | Base64 token, passed as `--token`         | —                                  |
| `SCAN42C_HOST`    | Both      | Scan target base URL (overrides OAS `servers[0]`) | None                       |

**Platform mode**: `API_KEY` and `PLATFORM_HOST` are set for every command. `--tag` and `--report-sqg` are applied when a tag is resolved.

**Freemium mode**: `--freemium-host stateless.42crunch.com:443` and `--token <FREEMIUM_TOKEN>` are used for every command. No `--tag` or `--report-sqg`.
