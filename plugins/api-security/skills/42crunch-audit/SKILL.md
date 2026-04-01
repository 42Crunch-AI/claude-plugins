---
name: 42crunch-audit
description: >
  Run a 42Crunch API Security Audit and fix SQG-blocking issues in an OpenAPI
  Specification file. Use this skill whenever the user wants to audit an OAS
  file for security issues, fix SQG-blocking issues, score an API, apply data
  dictionary enrichment, or remediate audit findings. Triggers on phrases like
  "run audit", "audit only", "fix audit issues", "SQG audit", "42crunch audit",
  "audit score", or any request focused on static OAS analysis and remediation
  without running a live scan.
---

# 42Crunch Audit Skill

Runs a single phase: **Audit** (static OAS analysis, SQG reporting, and
SQG-blocking fix loop). Requires explicit user permission before execution.
Does **not** run a live scan — use the `42crunch-scan` skill for that.

---

## Entry Point

1. **Resolve the OAS file.** Use the file currently open in the editor, or
   accept a path provided by the user.

2. **Binary discovery** — run silently. Read `references/binary-discovery.md`
   for the full multi-IDE location logic (Step 0 checks the persistent cache
   first). Surface output to the user only if discovery fails.

3. **Credential check** — run silently.
   Token format rules: platform API tokens start with `api_`; platform IDE
   tokens start with `ide_`; freemium tokens are Base64 strings with neither
   prefix.

   Check in this order (environment first, then walk upward from the OAS
   directory checking `.env` files, stopping at the repository root):

   a. **`API_KEY`** — if found, detect mode from the value:
      - Starts with `api_` → **Platform mode** (API token). Set `PLATFORM_HOST`
        (default `https://demolabs.42crunch.cloud`). Proceed silently.
      - Starts with `ide_` → **Platform mode** (IDE token). Same command
        behavior as `api_`. Proceed silently.
      - Neither prefix (Base64 string) → **Freemium mode**. Use
        `--freemium-host stateless.42crunch.com:443` and `--token <API_KEY>`
        in all commands. Proceed silently.

   b. **Nothing found** → stop: "No credential found. Set `API_KEY` to your
      42Crunch token — `api_*` for a platform API token, `ide_*` for an IDE
      token, or a Base64 string for freemium access. Place it in your
      environment or a `.env` file and re-run."

4. **Tag detection** — platform mode only. Run silently. Read
   `references/tag-detection.md`. In freemium mode, skip tag detection
   entirely. If a tag is found, announce it to the user before asking for
   permission. If no tag is found, stop as described in
   `references/tag-detection.md`.

5. **Ask for permission.**
   > "Ready to run a 42Crunch Audit on `<filename>`. This will analyse your
   > OAS file and produce a scored report. Shall I proceed?"

6. **Execute the Audit.** Read `references/audit-workflow.md`.
   The workflow runs the audit, then presents a **developer-readable,
   risk-classified report** (SQG-Blocking / Security / Data Validation tiers)
   with plain-English titles and risk descriptions — no raw rule IDs. It then
   pauses and asks the user to consent before applying any fixes. Fixes are
   only applied after explicit confirmation.

7. **Present the final audit summary** (see Output Format below).

Only continue after explicit user confirmation at each permission prompt.

---

## Output Format

After the audit completes, produce a summary in this shape:

```
Audit Complete
  Score:          <score> / 100  (Security: <sec-score> · Data Validation: <data-score>)
  Score change:   <initial-score> → <score>  (<delta>)  |  Data: <initial-data> → <data-score>  (<data-delta>)   ← omit if no fixes applied
  SQG:            PASSED  (Security-Guardrails)    ← platform mode
  SQG:            PASSED  (Freemium)               ← freemium mode
  Mode:           Platform / Freemium
  Tag:            <category>:<tagname>             ← platform mode only
  Issues fixed:   2 SQG-blocking  (0 security · 2 data validation)
  OAS updated:    <path/to/openapi.json>
```

The `Score change:` row is produced from the delta values computed in Step 4 of
`references/audit-workflow.md`. Omit it when no fixes were applied (user
declined at the consent gate, or there were no SQG-blocking issues).

If the user declined to apply fixes, note that instead.

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

**Platform mode**: `API_KEY` and `PLATFORM_HOST` set for every command. `--tag` and `--report-sqg` applied when a tag is resolved.

**Freemium mode**: `--freemium-host stateless.42crunch.com:443` and `--token <API_KEY>` used for every command. No `--tag` or `--report-sqg`. Hardcoded SQG: score ≥ 70, issues with criticality ≥ MEDIUM are blocking.
