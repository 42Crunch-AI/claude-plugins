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

1. **Resolve the OAS file.** Use the file currently open in the editor, or
   accept a path provided by the user.

2. **Setup prerequisite** — always run before proceeding.

   **A. Binary version check (always runs):**

   Resolve the canonical binary path for the current OS:
   - macOS/Linux: `$HOME/.42crunch/bin/42c-ast`
   - Windows: `$env:APPDATA\42Crunch\bin\42c-ast.exe`

   Before running any check, announce:
   > "Checking for `42c-ast`..."

   Check if the binary exists:
   - **Missing** → announce `"The 42c-ast binary isn't installed yet — running setup now."` then invoke `42crunch-setup` for full setup. Do not proceed if setup fails.
   - **Present** → run silently:
     1. Get installed version: `"$BINARY_PATH" --version`
     2. Announce: `"Checking for updates to 42c-ast..."` then fetch the manifest:
        `curl -fsSL https://repo.42crunch.com/downloads/42c-ast-manifest.json`
        The manifest is a **JSON array**. Filter entries by the current platform
        `architecture` key (e.g. `darwin-arm64`, `linux-amd64`, `windows-amd64` —
        see `42crunch-setup/references/binary-setup.md` Step 1 for the full mapping table).
        Read the `version` field from the matching entry — this is `LATEST_VERSION`.
        If no entry matches the current platform, skip the update check and proceed.
     3. Compare the installed version string to `LATEST_VERSION` for the current platform.
     4. **Outdated** → silently download and replace the binary using the same
        install steps as `42crunch-setup` (download → SHA-256 verify → chmod +x).
        Inform the user: `42c-ast updated from v<old> to v<new>.`
     5. **Up to date** → proceed silently.
     6. **Manifest fetch fails** → announce: `"Could not reach the update server to check for a newer version — continuing with installed 42c-ast v<version>. Run 42crunch-setup to retry later."` then continue.

   **B. Credentials check (runs after binary is confirmed):**

   ```bash
   grep -E "^(FREEMIUM_TOKEN|API_KEY)=" "$HOME/.42crunch/conf/env" 2>/dev/null
   ```

   - **Credentials missing** → invoke `42crunch-setup` (credentials flow
     only). Do not proceed if setup fails.
   - **Credentials present** → proceed silently to Step 3.

3. **Credential check** — run silently.

   Read `~/.42crunch/conf/env` (macOS/Linux) or `%APPDATA%\42Crunch\conf\env`
   (Windows) — the config written by `42crunch-setup`:

   ```bash
   grep -E "^(FREEMIUM_TOKEN|API_KEY)=" "$HOME/.42crunch/conf/env" 2>/dev/null
   ```

   - **`FREEMIUM_TOKEN`** is set → **Freemium mode**. Use
     `--freemium-host stateless.42crunch.com:443` and `--token <FREEMIUM_TOKEN>`
     in all commands. Proceed silently.
   - **`API_KEY`** starts with `api_` or `ide_` → **Platform mode**. Read
     `PLATFORM_HOST` from the same file (default
     `https://demolabs.42crunch.cloud`). Proceed silently.
   - **Neither found** → stop with: "I don't see any 42Crunch credentials configured yet. Run `42crunch-setup` to set up your token — it only takes a couple of minutes and I'll walk you through every step."

4. **Tag detection** — platform mode only. Run silently. Read
   `references/tag-detection.md`. In freemium mode, skip tag detection
   entirely. If a tag is found, announce it to the user before asking for
   Phase 1 permission. If no tag is found, stop as described in
   `references/tag-detection.md`.

5. **Ask for Phase 1 permission.** Call `AskUserQuestion`:
   - **question**: `"Ready to run a 42Crunch Audit on <filename>. This will analyse your OAS file and produce a scored report. Shall I proceed?"`
   - **options**: `["Yes, proceed", "No, cancel"]`

6. **Execute Phase 1 — Audit.** Read `references/audit-workflow.md`.
   The workflow runs the audit, then presents a **developer-readable,
   risk-classified report** (SQG-Blocking / Security / Data Validation tiers)
   with plain-English titles and risk descriptions — no raw rule IDs. It then
   pauses and asks the user to consent before applying any fixes. Fixes are
   only applied after explicit confirmation.

7. **Ask for Phase 2 permission.** Call `AskUserQuestion`:
   - **question**: `"The audit is complete. Ready to run a 42Crunch Scan against the live API to test conformance and authorization. Shall I proceed?"`
   - **options**: `["Yes, proceed", "No, cancel"]`

8. **Execute Phase 2 — Scan.** Read `references/scan-workflow.md`.
   The workflow runs the scan, then presents a **risk-classified findings
   report** (Authorization failures / SQG-blocking conformance /
   informational conformance). Fix candidates are determined by SQG-blocking
   rules and authorization failures — not severity alone. The skill pauses and
   asks the user to consent before applying any OAS changes.

9. **Present the final combined summary** (see Output Format below).

10. **Recommend next steps** based on the outcome:

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
  SQG:            PASSED  (Freemium — score ≥ 70 and no MEDIUM+ issues)    ← freemium, passed
  SQG:            FAILED  (Freemium — score < 70 or MEDIUM+ issues present)    ← freemium, failed
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
Step 4 of `references/audit-workflow.md`. Omit it when no audit fixes were
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
| `PLATFORM_HOST`   | Platform  | Platform base URL                         | `https://demolabs.42crunch.cloud`  |
| `FREEMIUM_TOKEN`  | Freemium  | Base64 token, passed as `--token`         | —                                  |
| `SCAN42C_HOST`    | Both      | Scan target base URL (overrides OAS `servers[0]`) | None                       |

**Platform mode**: `API_KEY` and `PLATFORM_HOST` are set for every command. `--tag` and `--report-sqg` are applied when a tag is resolved.

**Freemium mode**: `--freemium-host stateless.42crunch.com:443` and `--token <FREEMIUM_TOKEN>` are used for every command. No `--tag` or `--report-sqg`.
