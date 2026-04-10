# Pre-flight Checks

Shared entry point for all 42Crunch skills. Run these steps in order before
any skill-specific logic. Do not proceed if any step fails or the user cancels.

---

## Step 1 — Setup

Read `../../references/setup-check.md` and follow it completely.

---

## Step 2 — Resolve the OAS File

- If the user provided a path → use it.
- If exactly one OAS file (`.json` or `.yaml` containing `openapi:`) is open
  in the editor → use it.
- If **multiple** OAS files are open → call `AskUserQuestion`:
  - **question**: `"I see multiple OpenAPI files open. Which one should I use?"` — list each filename as an option.
- If **no** OAS file can be resolved → call `AskUserQuestion`:
  - **question**: `"I couldn't find an OpenAPI file. Would you like me to generate one from your source code first?"` — options: `["Yes — generate from source code", "No — I'll provide a path"]`
  - If **Yes** → invoke the `code-to-oas` skill, then resume with the generated file.
  - If **No** → ask the user to provide the file path and wait.

---

## Step 3 — Tag Detection (platform mode only)

Run silently. Read `../../references/tag-detection.md`. In freemium mode, skip
tag detection entirely. If a tag is found, announce it to the user before
asking for permission. If no tag is found, stop as described in
`../../references/tag-detection.md`.

---

## Environment Variables

| Variable          | Mode      | Purpose                                   |
|-------------------|-----------|-------------------------------------------|
| `API_KEY`         | Platform  | `api_*` or `ide_*` token                 |
| `PLATFORM_HOST`   | Platform  | Platform base URL                         |
| `FREEMIUM_TOKEN`  | Freemium  | Base64 token, passed as `--token`         |

**Platform mode**: `API_KEY` and `PLATFORM_HOST` set for every command.
`--tag` and `--report-sqg` applied when a tag is resolved.

**Freemium mode**: `--freemium-host stateless.42crunch.com:443` and
`--token <FREEMIUM_TOKEN>` for every command. No `--tag` or `--report-sqg`.

---

## General Constraints

- Use `bash_tool` to execute all `42c-ast` commands.
- Use `str_replace` or `create_file` to apply fixes to the OAS file.
- Never modify the OAS file without first describing what will change.
- All credential inputs are ephemeral in-session values. Do not write tokens
  or passwords to disk outside of scan config files that already expect them.
- Surface brief status lines before slow network operations (manifest fetch,
  binary download, tag detection). Do not surface individual sub-steps like
  SHA-256 verification or file writes.
