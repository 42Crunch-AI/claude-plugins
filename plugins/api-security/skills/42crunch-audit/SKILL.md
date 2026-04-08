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

1. **Setup prerequisite** — always run before proceeding. Read
   `../../references/setup-check.md` and follow it completely. Do not proceed
   if setup fails or the user cancels.

2. **Resolve the OAS file.**
   - If the user provided a path → use it.
   - If exactly one OAS file (`.json` or `.yaml` containing `openapi:`) is open in the editor → use it.
   - If **multiple** OAS files are open → call `AskUserQuestion`:
     - **question**: `"I see multiple OpenAPI files open. Which one should I audit?"` — list each filename as an option.
   - If **no** OAS file can be resolved → call `AskUserQuestion`:
     - **question**: `"I couldn't find an OpenAPI file to audit. Would you like me to generate one from your source code first?"` — options: `["Yes — generate from source code", "No — I'll provide a path"]`
     - If **Yes** → invoke the `code-to-oas` skill, then resume with the generated file.
     - If **No** → ask the user to provide the file path and wait.

3. **Tag detection** — platform mode only. Run silently. Read
   `../../references/tag-detection.md`. In freemium mode, skip tag detection
   entirely. If a tag is found, announce it to the user before asking for
   permission. If no tag is found, stop as described in
   `../../references/tag-detection.md`.

4. **Ask for permission.** Call `AskUserQuestion`:
   - **question**: `"Ready to run a 42Crunch Audit on <filename>. This will analyse your OAS file and produce a scored report. Shall I proceed?"`
   - **options**: `["Yes, proceed", "No, cancel"]`

5. **Execute the Audit.** Read `../../references/audit-workflow.md`.
   The workflow runs the audit, then presents a **developer-readable,
   risk-classified report** (SQG-Blocking / Security / Data Validation tiers)
   with plain-English titles and risk descriptions — no raw rule IDs. It then
   pauses and asks the user to consent before applying any fixes. Fixes are
   only applied after explicit confirmation.

6. **Present the final audit summary** (see Output Format below).

7. **Recommend next steps** based on the outcome:

   **If SQG PASSED:**
   > "Your audit is complete and the SQG is passing. The natural next step is to
   > run a live scan to test conformance and authorization against a running
   > instance of your API. Just say `run scan` when your API server is available."

   **If SQG FAILED (user declined to fix):**
   > "Your audit findings are saved above. When you're ready to address the
   > SQG-blocking issues, run `42crunch-audit` again on this file and I'll apply
   > the fixes. Once the audit passes, run `42crunch-scan` to test the live API."

   **If no issues found:**
   > "No issues found — your API has a clean audit result. Run `42crunch-scan`
   > to verify the live API matches its contract."

Only continue after explicit user confirmation at each permission prompt.

---

## Output Format

After the audit completes, produce a summary in this shape:

```
Audit Complete
  Score:          <score> / 100  (Security: <sec-score> · Data Validation: <data-score>)
  Score change:   <initial-score> → <score>  (<delta>)  |  Data: <initial-data> → <data-score>  (<data-delta>)   ← omit if no fixes applied
  SQG:            PASSED  (Security-Guardrails — your org's security quality gate is met)    ← platform mode, passed
  SQG:            FAILED  (Security-Guardrails — the quality gate is not met; fixes above are required)    ← platform mode, failed
  SQG:            N/A  (Freemium — no automated gate; user-defined thresholds applied this session)    ← freemium mode
  Mode:           Platform / Freemium
  Tag:            <category>:<tagname>             ← platform mode only
  Issues fixed:   2 SQG-blocking  (0 security · 2 data validation)
  OAS updated:    <path/to/openapi.json>
```

Show only the one SQG line that matches the current mode and result.

The `Score change:` row is produced from the delta values computed in Step 4 of
`../../references/audit-workflow.md`. Omit it when no fixes were applied (user
declined at the consent gate, or there were no SQG-blocking issues).

If the user declined to apply fixes, note that instead.

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

**Platform mode**: `API_KEY` and `PLATFORM_HOST` set for every command. `--tag` and `--report-sqg` applied when a tag is resolved.

**Freemium mode**: `--freemium-host stateless.42crunch.com:443` and `--token <FREEMIUM_TOKEN>` used for every command. No `--tag` or `--report-sqg`. No automated SQG gate — user is prompted for a target score and blocking severity threshold at the start of the audit flow; these are session-scoped only.
