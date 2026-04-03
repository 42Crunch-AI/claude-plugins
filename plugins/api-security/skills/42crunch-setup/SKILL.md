---
name: 42crunch-setup
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
1. Ensure the `42c-ast` binary is installed at the canonical path.
2. Configure and store credentials.

---

## Entry Point

### Step 1 — Introduce the setup

Greet the user and briefly explain what will happen:

> I'll set up your 42Crunch environment in two steps:
> 1. Ensure the `42c-ast` binary is available on this machine.
> 2. Configure your credentials so audit and scan can authenticate.
>
> Let's get started.

### Step 2 — Binary setup

Follow `references/binary-setup.md` completely.

The procedure covers, in order:
- **Step 0** — Check whether the binary already exists at the canonical path:
  - macOS/Linux: `$HOME/.42crunch/bin/42c-ast`
  - Windows: `%APPDATA%\42Crunch\bin\42c-ast.exe`

  If the binary is present and `--version` exits 0 → binary setup is complete.
  Skip directly to Step 3 (Credential setup).

- **Step 1** — Detect OS and architecture; resolve `BIN_DIR` and `BINARY_PATH`.
- **Step 2** — Fetch the manifest, resolve `LATEST_VERSION` / `DOWNLOAD_URL` / `EXPECTED_SHA256`.
- **Step 3** — Download, verify SHA-256, install, set permissions (`chmod +x` on
  macOS/Linux), confirm.

Stop and surface a clear error if the binary cannot be installed. Do not proceed to Step 3.

### Step 3 — Credential setup

Follow `references/credential-setup.md` completely.

The procedure covers, in order:
- Silently check whether credentials are already present in
  `~/.42crunch/conf/env` (macOS/Linux) or `%APPDATA%\42Crunch\conf\env`
  (Windows). If already configured: show mode + masked key, offer to keep or replace.
- If not configured (or replacing): walk the user through the guided flow:
  - **Are you an existing 42Crunch user?**
    - Yes → enter API Key → select Platform URL (US / EU / Other)
    - No → **Are you a registered 42Crunch Freemium user?**
      - Yes → enter Freemium Token
      - No → show registration link (`https://42crunch.com/freemium/`) and stop
- Write credentials to `~/.42crunch/conf/env`, set `chmod 600` on macOS/Linux.

### Step 4 — Final verification

Run a quick end-to-end check:

```bash
# Binary (macOS / Linux)
"$HOME/.42crunch/bin/42c-ast" --version
```

```powershell
# Binary (Windows)
& "$env:APPDATA\42Crunch\bin\42c-ast.exe" --version
```

```bash
# Credentials (macOS / Linux)
grep -E "^(API_KEY|FREEMIUM_TOKEN)=" "$HOME/.42crunch/conf/env"
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
| Credential mode  | <Platform | Freemium>                               |
| API key          | <prefix_>••••••••  (stored in <path>)               |
| Platform host    | <url>  ← omit this row for freemium mode            |
```

---

## General Constraints

- All detection steps (binary check, credential check) run silently. Surface
  output only on failure or when prompting the user.
- Never print the API key or Freemium token in plaintext after the user enters
  it. Always mask it (`api_••••••••` / `ide_••••••••` for platform tokens,
  `••••••••` for freemium).
- Use `bash_tool` for all shell commands; use `str_replace_editor` or
  `create_file` when writing config files — never shell redirection.
- Use `curl` for downloads; fall back to `wget` if `curl` is unavailable. On
  Windows use `Invoke-WebRequest`.
- On Windows: binary filename is `42c-ast.exe`, paths use `\`, config lives in
  `%APPDATA%\42Crunch\conf\env`, skip `chmod 600` (Windows ACLs protect `APPDATA`).

## Environment Variables

| Variable        | Default                          | Mode            |
|-----------------|----------------------------------|-----------------|
| `API_KEY`       | *(required)*                     | Platform        |
| `PLATFORM_HOST` | *(set during setup)*             | Platform only   |
| `FREEMIUM_TOKEN`| *(required)*                     | Freemium        |
