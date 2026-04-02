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

2. **Setup prerequisite** — invoke the `42crunch-setup-v2` skill before
   proceeding. Setup ensures the `42c-ast` binary is installed and up to date,
   and that credentials are configured. If the binary cache
   (`~/.42crunch/.resolved-binary`) already points to a working binary and
   credentials are already present, setup exits immediately without user
   interaction. Surface output to the user only if setup requires input or fails.
   Do not proceed if setup fails.

3. **Credential check** — run silently.
   Token format rules: platform API tokens start with `api_`; platform IDE
   tokens start with `ide_`; freemium tokens are Base64 strings with neither
   prefix.

   Check in this order (environment first, then walk upward from the OAS
   directory checking `.env` files, stopping at the repository root, then the
   global config written by `42crunch-setup-v2`):

   a. **`API_KEY`** — if found, detect mode from the value:
      - Starts with `api_` → **Platform mode** (API token). Set `PLATFORM_HOST`
        (default `https://demolabs.42crunch.cloud`). Proceed silently.
      - Starts with `ide_` → **Platform mode** (IDE token). Same command
        behavior as `api_`. Proceed silently.
      - Neither prefix (Base64 string) → **Freemium mode**. Use
        `--freemium-host stateless.42crunch.com:443` and `--token <API_KEY>`
        in all commands. Proceed silently.

   b. **Nothing found in environment or `.env` walk-up** → check
      `~/.42crunch/conf/env` (macOS/Linux) or `%APPDATA%\42Crunch\conf\env`
      (Windows) — the global config written by `42crunch-setup-v2`. Read
      `API_KEY` and `PLATFORM_HOST` from here and apply the same mode
      detection above.

   c. **Nothing found anywhere** → stop: "No credential found. Set `API_KEY`
      to your 42Crunch token — `api_*` for a platform API token, `ide_*` for
      an IDE token, or a Base64 string for freemium access. Place it in your
      environment or a `.env` file and re-run."

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

| Variable          | Mode              | Purpose                                                                                                 | Default                            |
|-------------------|-------------------|---------------------------------------------------------------------------------------------------------|------------------------------------|
| `API_KEY`         | Platform/Freemium | Token determines mode: `api_*` = platform API, `ide_*` = platform IDE, Base64 = freemium (`--token`)   | —                                  |
| `PLATFORM_HOST`   | Platform          | Platform base URL                                                                                       | `https://demolabs.42crunch.cloud`  |
| `SCAN42C_HOST`    | Both              | Scan target base URL (overrides OAS `servers[0]`)                                                       | None                               |

**Platform mode**: `API_KEY` and `PLATFORM_HOST` set for every command. `--tag` applied when a tag is resolved. SQG enforced from platform.

**Freemium mode**: `--freemium-host stateless.42crunch.com:443` and `--token <API_KEY>` used for every command. No `--tag`. No scan SQG enforcement — present all findings informally.
