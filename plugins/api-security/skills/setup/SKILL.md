---
description: >
  Set up the 42Crunch AST binary on the user's machine. Use this skill whenever
  the user wants to install, set up, or configure the 42Crunch AST tool, or when
  another skill requires the AST binary and it is not yet present. Triggers on
  phrases like "set up 42crunch", "install 42c-ast", "configure AST binary",
  "42crunch setup", or when the AST binary is missing and must be installed
  before proceeding.
---

# 42Crunch AST Binary Setup

Checks whether the latest 42Crunch AST binary is installed, installs the latest version
if it is not, creates the required directory structure, and activates the binary
with the user's Platform URL and API token.

---

## Step 1 — Detect the Operating System and Architecture

Determine the user's OS and CPU architecture so the correct binary can be
selected:

- **macOS:** `uname -s` returns `Darwin`. Architecture: run `uname -m` — `arm64`
  maps to `darwin-arm64`, `x86_64` maps to `darwin-amd64`.
- **Linux:** `uname -s` returns `Linux`. Architecture: run `uname -m` — `aarch64`
  or `arm64` maps to `linux-arm64`, `x86_64` maps to `linux-amd64`.
- **Windows:** PowerShell — `$env:OS` contains `Windows_NT`. Architecture:
  `$env:PROCESSOR_ARCHITECTURE` — `AMD64` maps to `windows-amd64`.

Record the resolved `architecture` string (e.g. `darwin-arm64`, `linux-amd64`,
`windows-amd64`). This will be used to look up the correct manifest entry.

---

## Step 2 — Resolve Installation Paths

Based on the detected OS, set the following path variables for use in all
subsequent steps:

| Variable | macOS / Linux | Windows |
|---|---|---|
| `BIN_DIR` | `$HOME/.42crunch/bin` | `$env:APPDATA\42Crunch\bin` |
| `BINARY_PATH` | `$HOME/.42crunch/bin/42c-ast` | `$env:APPDATA\42Crunch\bin\42c-ast.exe` |
| `CONF_DIR` | `$HOME/.42crunch/conf` | `$env:APPDATA\42Crunch\conf` |
| `ENV_FILE` | `$HOME/.42crunch/conf/env` | `$env:APPDATA\42Crunch\conf\env` |

---

## Step 3 — Check Whether the Binary is Already Installed

Test whether the binary exists at `BINARY_PATH`:

- **macOS / Linux:**
  ```bash
  test -f "$HOME/.42crunch/bin/42c-ast" && echo "found" || echo "not found"
  ```
- **Windows (PowerShell):**
  ```powershell
  Test-Path "$env:APPDATA\42Crunch\bin\42c-ast.exe"
  ```

Record whether the binary is **present** or **absent**, then continue to Step 4
regardless of the outcome. The manifest must always be fetched to determine the
latest version.

---

## Step 4 — Fetch the Latest Version from the Manifest

Fetch the manifest to identify the latest version and download URL for the
correct platform binary:

```
https://repo.42crunch.com/downloads/42c-ast-manifest.json
```

Parse the JSON array. Each entry has the following shape:

```json
{
  "name": "42c-ast-darwin-arm64-3.54.2",
  "architecture": "darwin-arm64",
  "version": "3.54.2",
  "releaseDate": "2026-03-19T10:55:20Z",
  "downloadUrl": "https://repo.42crunch.com/downloads/42c-ast-darwin-arm64-3.54.2",
  "sha256": "<checksum>"
}
```

Select the entry whose `architecture` field matches the architecture string
resolved in Step 1. Record the `downloadUrl`, `version` (call it `LATEST_VERSION`),
and `sha256` of the matching entry.

If no matching entry is found, report the error:
> "No 42Crunch AST binary is available for your platform (`<architecture>`).
> Please visit https://42crunch.com for manual installation instructions."
Then stop.

### 4.1 — Compare Versions (binary already present)

If the binary was found in Step 3, check its currently installed version:

- **macOS / Linux:**
  ```bash
  "$HOME/.42crunch/bin/42c-ast" --version 2>&1
  ```
- **Windows (PowerShell):**
  ```powershell
  & "$env:APPDATA\42Crunch\bin\42c-ast.exe" --version 2>&1
  ```

Parse the version string from the output (look for a semver pattern like
`3.54.2`). Store it as `INSTALLED_VERSION`.

Compare `INSTALLED_VERSION` against `LATEST_VERSION` using semver ordering:

- If `INSTALLED_VERSION` **equals** `LATEST_VERSION`:
  > "42Crunch AST v`<LATEST_VERSION>` is already installed and up to date.
  > Proceeding to activation."
  Skip to [Step 6 — Activate the Binary](#step-6--activate-the-binary).

- If `INSTALLED_VERSION` is **older** than `LATEST_VERSION`:
  > "42Crunch AST v`<INSTALLED_VERSION>` is installed but v`<LATEST_VERSION>`
  > is available. Updating now."
  Continue to Step 5 to replace the binary.

- If the version **cannot be determined** (command fails or output is
  unparseable), treat the binary as outdated and continue to Step 5.

### 4.2 — Binary not present

If the binary was absent in Step 3, continue directly to Step 5.

---

## Step 5 — Download and Install the Binary

### 5.1 — Create the Directory Structure

Create `BIN_DIR` and `CONF_DIR` if they do not already exist:

- **macOS / Linux:**
  ```bash
  mkdir -p "$HOME/.42crunch/bin" "$HOME/.42crunch/conf"
  ```
- **Windows (PowerShell):**
  ```powershell
  New-Item -ItemType Directory -Force -Path "$env:APPDATA\42Crunch\bin" | Out-Null
  New-Item -ItemType Directory -Force -Path "$env:APPDATA\42Crunch\conf" | Out-Null
  ```

### 5.2 — Download the Binary

Download the binary to `BINARY_PATH`:

- **macOS / Linux (curl):**
  ```bash
  curl -fsSL "<downloadUrl>" -o "$HOME/.42crunch/bin/42c-ast"
  ```
  If `curl` is not available, fall back to `wget`:
  ```bash
  wget -q "<downloadUrl>" -O "$HOME/.42crunch/bin/42c-ast"
  ```

- **Windows (PowerShell):**
  ```powershell
  Invoke-WebRequest -Uri "<downloadUrl>" -OutFile "$env:APPDATA\42Crunch\bin\42c-ast.exe"
  ```

### 5.3 — Verify the Checksum

After downloading, verify the SHA-256 checksum against the value from the
manifest to ensure integrity:

- **macOS:**
  ```bash
  echo "<sha256>  $HOME/.42crunch/bin/42c-ast" | shasum -a 256 -c -
  ```
- **Linux:**
  ```bash
  echo "<sha256>  $HOME/.42crunch/bin/42c-ast" | sha256sum -c -
  ```
- **Windows (PowerShell):**
  ```powershell
  (Get-FileHash "$env:APPDATA\42Crunch\bin\42c-ast.exe" -Algorithm SHA256).Hash -eq "<sha256>"
  ```

If the checksum does not match, delete the downloaded file and stop with an
error:
> "Checksum verification failed for the downloaded binary. The file may be
> corrupted. Please retry or download manually from:
> `<downloadUrl>`"

### 5.4 — Make the Binary Executable (macOS / Linux only)

```bash
chmod +x "$HOME/.42crunch/bin/42c-ast"
```

Skip this step on Windows.

### 5.5 — Confirm Installation

Inform the user:
> "42Crunch AST v`<version>` installed successfully at `<BINARY_PATH>`."

---

## Step 6 — Activate the Binary

The binary requires a Platform URL and an API token to communicate with the
42Crunch platform. These are stored in the `env` configuration file.

### 6.1 — Check for Existing Configuration

If `ENV_FILE` already exists, read it. If both `PLATFORM_HOST` and `API_KEY`
are present and non-empty, the binary is already configured. Inform the user:
> "42Crunch AST is already configured with platform host `<value>`. Setup is
> complete."
Then stop, unless the user explicitly asked to reconfigure.

### 6.2 — Prompt for the Platform URL

Ask the user:
> "Please provide your 42Crunch Platform URL (e.g. `https://platform.42crunch.com`):"

Wait for the user's response. Trim any trailing slashes from the value.
Store it as `PLATFORM_HOST_VALUE`.

### 6.3 — Prompt for the API Token

Ask the user:
> "Please provide your 42Crunch API token:"

Wait for the user's response. Store it as `API_KEY_VALUE`.

### 6.4 — Write the Configuration File

Write `ENV_FILE` with the following content, using the values provided:

```
PLATFORM_HOST=<PLATFORM_HOST_VALUE>
API_KEY=<API_KEY_VALUE>
```

- **macOS / Linux:**
  ```bash
  printf 'PLATFORM_HOST=%s\nAPI_KEY=%s\n' "<PLATFORM_HOST_VALUE>" "<API_KEY_VALUE>" > "$HOME/.42crunch/conf/env"
  ```
- **Windows (PowerShell):**
  ```powershell
  @"
PLATFORM_HOST=<PLATFORM_HOST_VALUE>
API_KEY=<API_KEY_VALUE>
"@ | Set-Content -Path "$env:APPDATA\42Crunch\conf\env" -Encoding UTF8
  ```

Do **not** quote the values in the env file — write them as bare strings after
the `=` sign. Do **not** add any extra whitespace around the `=` sign.

Set restrictive permissions on the file to protect the API token:
- **macOS / Linux:**
  ```bash
  chmod 600 "$HOME/.42crunch/conf/env"
  ```
- **Windows:** skip this step (Windows ACLs protect the user's `APPDATA` folder).

---

## Step 7 — Report Completion

Output a final summary to the user:

```
42Crunch AST Setup Complete
  Binary:        <BINARY_PATH>
  Version:       <version>
  Platform URL:  <PLATFORM_HOST_VALUE>
  Config file:   <ENV_FILE>

The 42Crunch AST binary is ready to use.
```

---

## Error Handling

| Situation | Action |
|---|---|
| Manifest fetch fails (network error) | Report the error and provide the manual download URL: `https://repo.42crunch.com/downloads/42c-ast-manifest.json`. If the binary is already installed, skip to Step 6 and warn that version currency could not be verified |
| Installed binary `--version` fails or returns unparseable output | Treat the binary as outdated and proceed with the download in Step 5 |
| No manifest entry for current platform | Report unsupported platform; suggest visiting https://42crunch.com |
| Download fails | Report the error with the `downloadUrl` for manual download |
| Checksum mismatch | Delete partial download and stop; ask user to retry |
| Cannot write to `BIN_DIR` or `CONF_DIR` | Report the permission error and suggest running with elevated privileges |
| User provides empty Platform URL or API token | Re-prompt once; if still empty, stop with a warning that the binary is installed but not activated |
