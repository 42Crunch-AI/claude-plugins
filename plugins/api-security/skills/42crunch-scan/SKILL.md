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

1. **Resolve the OAS file.** Use the file currently open in the editor, or
   accept a path provided by the user.

2. **Setup prerequisite** — always run silently before proceeding.

   **A. Binary version check (always runs):**

   Resolve the canonical binary path for the current OS:
   - macOS/Linux: `$HOME/.42crunch/bin/42c-ast`
   - Windows: `$env:APPDATA\42Crunch\bin\42c-ast.exe`

   Check if the binary exists:
   - **Missing** → invoke `42crunch-setup` for full setup. Do not proceed if
     setup fails.
   - **Present** → run silently:
     1. Get installed version: `"$BINARY_PATH" --version`
        Parse the semver string from the output (e.g. extract `X.Y.Z`).
        If the version cannot be parsed, treat as outdated.
     2. Fetch manifest: `curl -fsSL https://repo.42crunch.com/downloads/42c-ast-manifest.json`
     3. Compare `INSTALLED_VERSION` to `LATEST_VERSION` for the current platform.
     4. **Outdated** (or version unparseable) → silently download and replace the
        binary using the same install steps as `42crunch-setup`
        (download → SHA-256 verify → chmod +x).
        Inform the user: `42c-ast updated from v<old> to v<new>.`
     5. **Up to date** → proceed silently.
     6. **Manifest fetch fails** → warn but continue with the installed binary.

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
   - **Neither found** → stop: "No credential found. Run `42crunch-setup`
     to configure your token."

4. **Tag detection** — platform mode only. Run silently. Read
   `references/tag-detection.md`. In freemium mode, skip tag detection
   entirely. If a tag is found, announce it to the user before asking for
   permission. If no tag is found, stop as described in
   `references/tag-detection.md`.

5. **Ask for permission.**
   > "Ready to run a 42Crunch Scan against the live API to test conformance
   > and authorization on `<filename>`. Shall I proceed?"

6. **Execute the Scan.** Read `references/scan-workflow.md`.
   The workflow sets up the scan config, collects credentials, classifies
   operations, validates happy paths, runs the full scan, and presents a
   **risk-classified findings report** (Authorization failures /
   SQG-blocking conformance / informational conformance). It then pauses and
   asks the user to consent before applying any OAS changes.

   **Freemium mode**: no SQG is enforced for scan. Present all findings for
   information. The user decides which (if any) to fix.

7. **Present the final scan summary** (see Output Format below).

Only continue after explicit user confirmation at each permission prompt.

---

## Output Format

After the scan completes, produce a summary in this shape:

```
Scan Complete
  Mode:           Platform / Freemium
  SQG:            PASSED  (Security-Guardrails)    ← platform mode
  SQG:            N/A  (Freemium — no scan SQG)    ← freemium mode
  Tag:            <category>:<tagname>             ← platform mode only
  Authorization:  BOLA confirmed on 1 operation — fixed in OAS
  Conformance:    1 SQG-blocking issue fixed · 3 informational findings surfaced
  OAS updated:    <path/to/openapi.json>
```

If the user declined to apply fixes or no issues were found, note that instead.

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

**Platform mode**: `API_KEY` and `PLATFORM_HOST` set for every command. `--tag` applied when a tag is resolved. SQG enforced from platform.

**Freemium mode**: `--freemium-host stateless.42crunch.com:443` and `--token <FREEMIUM_TOKEN>` used for every command. No `--tag`. No scan SQG enforcement — present all findings informally.
