---
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

2. **Binary discovery** — run silently. Read `references/binary-discovery.md`
   for the full multi-IDE location logic (Step 0 checks the persistent cache
   first). Surface output to the user only if discovery fails.

3. **Credential check** — run silently.
   Token format rules: platform API tokens start with `api_`; platform IDE
   tokens start with `ide_`; freemium tokens have neither prefix.

   Check in this order (environment first, then walk upward from the OAS
   directory checking `.env` files, stopping at the repository root):

   a. **`API_KEY`** — if found:
      - Value starts with `api_` or `ide_` → **Platform mode**. Store the
        value as `API_KEY` and `PLATFORM_HOST` (default
        `https://demolabs.42crunch.cloud`). Proceed silently.
      - Other format → stop: "API_KEY looks like a freemium token. Use
        `FREEMIUM_TOKEN` for freemium credentials."

   b. **`IDE_TOKEN`** — if `API_KEY` not found and `IDE_TOKEN` starts with
      `ide_` → **Platform mode**. Use the value as `API_KEY` in all
      subsequent commands.

   c. **`FREEMIUM_TOKEN`** — if neither platform credential found:
      - If found → **Freemium mode**. Use `--token <FREEMIUM_TOKEN>` and
        `PLATFORM_HOST="https://platform.42crunch.com"` in all commands.
        Proceed silently.

   d. **Nothing found** → stop: "No credential found. Set `API_KEY` (starts
      with `api_`) or `IDE_TOKEN` (starts with `ide_`) for platform access,
      or `FREEMIUM_TOKEN` for freemium access. Place in your environment or
      a `.env` file and re-run."

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

| Variable          | Mode      | Purpose                                                       | Default                            |
|-------------------|-----------|---------------------------------------------------------------|------------------------------------|
| `API_KEY`         | Platform  | 42Crunch platform API key (starts with `api_`)                | —                                  |
| `IDE_TOKEN`       | Platform  | 42Crunch IDE token (starts with `ide_`), used as API_KEY      | —                                  |
| `PLATFORM_HOST`   | Platform  | Platform base URL                                             | `https://<your-platform-host>`     |
| `FREEMIUM_TOKEN`  | Freemium  | Freemium token, passed via `--token` flag                     | —                                  |
| `SCAN42C_HOST`    | Both      | Scan target base URL (overrides OAS `servers[0]`)             | None                               |

**Platform mode**: `API_KEY` (resolved from `API_KEY` or `IDE_TOKEN`) and `PLATFORM_HOST` are set for every command. `--tag` and `--report-sqg` are applied when a tag is resolved.

**Freemium mode**: `PLATFORM_HOST=https://platform.42crunch.com` and `--token <FREEMIUM_TOKEN>` are used for every command. No `--tag` or `--report-sqg`.
