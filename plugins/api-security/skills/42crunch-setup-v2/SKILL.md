---
name: 42crunch-setup-v2
description: >
  Set up the 42Crunch environment so that audit and scan skills can run
  without friction. Use this skill whenever the user wants to configure
  42Crunch for the first time, install or update the 42c-ast binary, configure
  an API key, or troubleshoot missing credentials or binary errors. Triggers
  on phrases like "setup 42crunch", "configure 42crunch", "install 42c-ast",
  "update 42c-ast", "set api key", "42crunch not working", "binary not found",
  or any request to prepare the environment before running an audit or scan.
---

# 42Crunch Setup

Prepares the environment for 42Crunch audit and scan workflows in two phases:
1. Ensure the `42c-ast` binary is installed and up to date.
2. Configure and store the API key.

---

## Entry Point

### Step 1 — Introduce the setup

Greet the user and briefly explain what will happen:

> I'll set up your 42Crunch environment in two steps:
> 1. Ensure the `42c-ast` binary is available and up to date on this machine.
> 2. Configure your API key so audit and scan can authenticate.
>
> Let's get started.

### Step 2 — Binary setup

Follow `references/binary-setup.md` completely.

The procedure covers, in order:
- **Step 0** — Check the binary cache (`~/.42crunch/.resolved-binary`); skip all
  remaining checks if a working binary is already there, but still run the version
  check against the manifest.
- **Step 1** — Detect VS Code via `$TERM_PROGRAM` / `$VSCODE_PID`.
- **Step 2** — If VS Code: check for the 42Crunch extension; offer to install it
  via `code --install-extension`. If installed, mark binary complete.
- **Step 3** — If not VS Code (or user declines extension install): detect OS and
  architecture; resolve `BIN_DIR` and `BINARY_PATH` for the platform.
- **Step 4** — Fetch the manifest, resolve `LATEST_VERSION` / `DOWNLOAD_URL` /
  `EXPECTED_SHA256`; compare against any installed version and skip download if
  already up to date.
- **Step 5** — Download, verify SHA-256, install, set permissions (`chmod +x` on
  macOS/Linux), update the cache file.

Stop and surface a clear error if no binary can be located or installed after all
options are exhausted. Do not proceed to Step 3.

### Step 3 — Credential setup

Follow `references/credential-setup.md` completely.

The procedure covers, in order:
- Silently check whether `API_KEY` is already set (environment variable, `.env`
  walk-up from current directory to repo root, global `~/.42crunch/conf/env`).
- If already configured: show mode + masked key, offer to keep or replace.
- If not configured (or replacing): ask the user to paste their key, detect mode
  from the prefix (`api_`/`ide_` → Platform, other → Freemium), optionally
  collect `PLATFORM_HOST` (Platform mode only, default:
  `https://demolabs.42crunch.cloud`), prompt for storage location (project `.env`
  or global `~/.42crunch/conf/env`), write the file, set `chmod 600` on
  macOS/Linux, and remind about `.gitignore` for project `.env`.

### Step 4 — Final verification

Run a quick end-to-end check:

```bash
# Binary
"$(cat ~/.42crunch/.resolved-binary)" --version

# Credentials
grep "^API_KEY=" <chosen-env-file>
```

If either check fails, report the specific failure and guide the user to resolve
it before continuing.

### Step 5 — Present summary

Display the setup summary (see Output Format below).

### Step 6 — Recommend next steps

> Your environment is ready. You can now run:
> - `42crunch-audit` — static security analysis of an OpenAPI file
> - `42crunch-scan` — live conformance and authorization testing against a running API
> - `42crunch-v2` — combined audit + scan in one workflow

---

## Output Format

```
## 42Crunch Setup Complete

| Item             | Status                                              |
|------------------|-----------------------------------------------------|
| Binary           | <BINARY_PATH> v<version>                            |
| Binary source    | <VS Code extension | Downloaded (<arch>) | Cached>  |
| Credential mode  | <Platform | Freemium>                               |
| API key          | <prefix_>••••••••  (stored in <path>)               |
| Platform host    | <url>  ← omit this row for freemium mode            |
```

---

## General Constraints

- All detection steps (cache check, VS Code check, extension check, credential
  walk-up) run silently. Surface output only on failure or when prompting the user.
- Never overwrite `~/.42crunch/.resolved-binary` when it already points to a
  working, up-to-date binary.
- Never print the API key in plaintext after the user enters it. Always mask it
  (`prefix_••••••••` for platform tokens, `••••••••` for freemium).
- Use `bash_tool` for all shell commands; use `str_replace_editor` or
  `create_file` when writing `.env` / config files — never shell redirection.
- Use `curl` for downloads; fall back to `wget` if `curl` is unavailable. On
  Windows use `Invoke-WebRequest`.
- If `code --install-extension` is attempted but `code` is not on PATH, instruct
  the user to run **"Shell Command: Install 'code' command in PATH"** from the
  VS Code Command Palette before retrying.
- On Windows: binary filename is `42c-ast.exe`, paths use `\`, config lives in
  `%APPDATA%\42Crunch\conf\env`, skip `chmod 600` (Windows ACLs protect `APPDATA`).

## Environment Variables

| Variable        | Default                              | Mode            |
|-----------------|--------------------------------------|-----------------|
| `API_KEY`       | *(required)*                         | Both            |
| `PLATFORM_HOST` | `https://demolabs.42crunch.cloud`    | Platform only   |
