# Binary Setup Reference

Follow this procedure to ensure the `42c-ast` binary is available and up to date.
All detection steps run silently — surface output only on failure or user prompts.

---

## Step 0 — Check Existing Cache

Before anything else, check whether a working binary is already cached:

```bash
cat ~/.42crunch/.resolved-binary 2>/dev/null
```

If the file exists, verify the binary still works:

```bash
"$(cat ~/.42crunch/.resolved-binary)" --version 2>/dev/null
```

If this exits 0, the binary is present. **Proceed to Step 4 (version check) using
this path as `BINARY_PATH` — skip Steps 1–3.**

---

## Step 1 — Detect VS Code

Check silently whether the session is running inside VS Code:

```bash
echo "$TERM_PROGRAM"   # "vscode" when in the VS Code integrated terminal
echo "$VSCODE_PID"     # non-empty when VS Code spawned this process
```

If `TERM_PROGRAM` equals `vscode` **or** `VSCODE_PID` is non-empty → proceed to Step 2.
Otherwise → skip to Step 3 (OS detection).

---

## Step 2 — Check for the 42Crunch VS Code Extension

Check whether the 42Crunch OpenAPI Editor extension is installed:

```bash
code --list-extensions 2>/dev/null | grep -i "42Crunch.vscode-openapi"
```

**If found:** locate the bundled binary in the extension directory:

```bash
# macOS
find ~/Library/Application\ Support/Code/Extensions/42crunch.vscode-openapi-*/node_modules/@xliic/ast-42c-*/bin/ -name "42c-ast" 2>/dev/null | head -1

# Linux
find ~/.vscode/extensions/42crunch.vscode-openapi-*/node_modules/@xliic/ast-42c-*/bin/ -name "42c-ast" 2>/dev/null | head -1
```

If a path is returned, cache and verify it:

```bash
echo "<found-path>" > ~/.42crunch/.resolved-binary
"<found-path>" --version
```

If `--version` exits 0 → set `BINARY_PATH` to this path and **proceed to Step 4
(version check).**

**If not found:** offer to install the extension (see Step 2.1).

### Step 2.1 — Offer VS Code Extension Install

Present this choice:

> The 42Crunch OpenAPI Editor extension is not installed in VS Code.
>
> **Option A** — Install it now (recommended). The extension bundles `42c-ast` and
> keeps it updated automatically.
>
> **Option B** — Skip and download the binary directly.

**If Option A chosen:**

Check that the `code` CLI is on PATH:

```bash
command -v code 2>/dev/null
```

If not found, instruct the user:
> Open the VS Code Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`) and run
> **"Shell Command: Install 'code' command in PATH"**, then retry.

Once available, install:

```bash
code --install-extension 42Crunch.vscode-openapi
```

Inform the user:
> Extension installed. Please reload your VS Code window
> (`Cmd+Shift+P` → "Developer: Reload Window") so the binary is activated.
> Binary setup is complete — the extension manages updates automatically.

**Mark binary step complete.** The `42crunch-setup-v2` prerequisite step in
audit/scan/v2 skills will resolve the binary after reload.

**If Option B chosen:** continue to Step 3.

---

## Step 3 — Detect OS and Architecture

```bash
OS=$(uname -s)     # Darwin, Linux, or MINGW*/CYGWIN*/MSYS*
ARCH=$(uname -m)   # arm64, aarch64, x86_64
```

Map to manifest `architecture` key:

| `uname -s`            | `uname -m`        | `architecture`  | Binary filename    |
|-----------------------|-------------------|-----------------|--------------------|
| Darwin                | arm64             | darwin-arm64    | 42c-ast            |
| Darwin                | x86_64            | darwin-amd64    | 42c-ast            |
| Linux                 | arm64 / aarch64   | linux-arm64     | 42c-ast            |
| Linux                 | x86_64            | linux-amd64     | 42c-ast            |
| MINGW* / CYGWIN* / MSYS* | x86_64        | windows-amd64   | 42c-ast.exe        |

On **Windows**, detect via PowerShell if `uname` is unavailable:

```powershell
$env:OS            # "Windows_NT"
$env:PROCESSOR_ARCHITECTURE  # "AMD64" → windows-amd64
```

Resolve path variables:

| Variable      | macOS / Linux                    | Windows                                   |
|---------------|----------------------------------|-------------------------------------------|
| `BIN_DIR`     | `$HOME/.42crunch/bin`            | `$env:APPDATA\42Crunch\bin`               |
| `BINARY_PATH` | `$HOME/.42crunch/bin/42c-ast`    | `$env:APPDATA\42Crunch\bin\42c-ast.exe`   |

---

## Step 4 — Fetch Manifest and Check Versions

Fetch the public manifest:

```bash
curl -fsSL https://repo.42crunch.com/downloads/42c-ast-manifest.json
# fallback if curl is unavailable:
wget -qO- https://repo.42crunch.com/downloads/42c-ast-manifest.json
```

**Windows (PowerShell):**

```powershell
Invoke-WebRequest -Uri "https://repo.42crunch.com/downloads/42c-ast-manifest.json" -UseBasicParsing | Select-Object -ExpandProperty Content
```

Parse the JSON array and find the entry whose `architecture` matches. Record:
- `LATEST_VERSION` — the `version` field
- `DOWNLOAD_URL` — the `downloadUrl` field
- `EXPECTED_SHA256` — the `sha256` field

If no matching entry exists, stop with:
> No binary is available for your platform (`<architecture>`).
> Please visit https://42crunch.com for manual installation instructions.

**If a binary is already at `BINARY_PATH` (from Step 0 or Step 2):**

Check its installed version:

```bash
"$BINARY_PATH" --version 2>&1
```

Parse the semver string from the output. Store as `INSTALLED_VERSION`.

- `INSTALLED_VERSION` **equals** `LATEST_VERSION` → binary is up to date.
  Inform the user: `42c-ast v<version> is already installed and up to date.`
  **Run the VS Code extension upgrade check (Step 4.1), then skip to the
  credential-setup phase.**
- `INSTALLED_VERSION` is **older** → inform the user:
  `42c-ast v<INSTALLED_VERSION> is installed; v<LATEST_VERSION> is available. Updating now.`
  Continue to Step 5.
- Version **cannot be determined** → treat as outdated and continue to Step 5.

**If no binary exists yet:** continue to Step 5.

---

## Step 4.1 — VS Code Extension Upgrade Check (cache-hit path only)

This step runs **only** when Step 0 (cache hit) short-circuited Steps 1–3, and the
binary was confirmed up to date in Step 4. It ensures users running inside VS Code
are still offered the extension even when a downloaded binary is already cached.

**Skip this step if any of the following are true:**
- `VSCODE_PID` is empty **and** `TERM_PROGRAM` is not `vscode` (not in VS Code)
- The cached `BINARY_PATH` contains `vscode-openapi` or `.vscode/extensions`
  (binary already came from the extension — no upgrade needed)

**Otherwise**, check whether the 42Crunch extension is installed:

```bash
code --list-extensions 2>/dev/null | grep -i "42Crunch.vscode-openapi"
```

If the extension is **already installed**, skip this step silently.

If the extension is **not installed**, present this offer:

> A valid `42c-ast` binary was found at `<BINARY_PATH>`, but the 42Crunch
> OpenAPI Editor VS Code extension is not installed. Installing it gives you
> automatic binary updates.
>
> **Option A** — Install the extension now (recommended).
> **Option B** — Keep using the cached binary.

**If Option A chosen:**

Check that `code` is on PATH:

```bash
command -v code 2>/dev/null
```

If not found, instruct the user:
> Open the VS Code Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`) and run
> **"Shell Command: Install 'code' command in PATH"**, then retry.

Once available, install:

```bash
code --install-extension 42Crunch.vscode-openapi
```

Then locate the extension's bundled binary and update the cache:

```bash
# macOS
find ~/Library/Application\ Support/Code/Extensions/42crunch.vscode-openapi-*/node_modules/@xliic/ast-42c-*/bin/ -name "42c-ast" 2>/dev/null | head -1

# Linux
find ~/.vscode/extensions/42crunch.vscode-openapi-*/node_modules/@xliic/ast-42c-*/bin/ -name "42c-ast" 2>/dev/null | head -1
```

If a path is returned and `--version` exits 0, update the cache:

```bash
echo "<extension-binary-path>" > ~/.42crunch/.resolved-binary
```

Inform the user:
> Extension installed and binary cache updated. VS Code will manage future
> updates automatically.

If the extension binary path cannot be found immediately (VS Code may need a
reload to activate it), inform the user:
> Extension installed. Please reload your VS Code window
> (`Cmd+Shift+P` → "Developer: Reload Window") so the binary is activated.
> The cache will be updated on the next run.

**If Option B chosen:** proceed silently to the credential-setup phase.

---

## Step 5 — Download and Install

### 5.1 — Create Directories

```bash
# macOS / Linux
mkdir -p "$HOME/.42crunch/bin"

# Windows (PowerShell)
New-Item -ItemType Directory -Force -Path "$env:APPDATA\42Crunch\bin" | Out-Null
```

### 5.2 — Download

```bash
# macOS / Linux — curl with wget fallback
curl -fsSL "$DOWNLOAD_URL" -o "$BINARY_PATH" \
  || wget -q "$DOWNLOAD_URL" -O "$BINARY_PATH"

# Windows (PowerShell)
Invoke-WebRequest -Uri "$DOWNLOAD_URL" -OutFile "$env:APPDATA\42Crunch\bin\42c-ast.exe"
```

### 5.3 — Verify SHA-256

```bash
# macOS
echo "$EXPECTED_SHA256  $BINARY_PATH" | shasum -a 256 -c -

# Linux
echo "$EXPECTED_SHA256  $BINARY_PATH" | sha256sum -c -
```

```powershell
# Windows
(Get-FileHash "$env:APPDATA\42Crunch\bin\42c-ast.exe" -Algorithm SHA256).Hash -eq "$EXPECTED_SHA256"
```

If the checksum does **not** match, delete the file and stop:
> Checksum verification failed. The download may be corrupted. Retry or download
> manually from: `<DOWNLOAD_URL>`

### 5.4 — Set Permissions (macOS / Linux only)

```bash
chmod +x "$BINARY_PATH"
```

### 5.5 — Update Cache

```bash
# macOS / Linux
echo "$BINARY_PATH" > ~/.42crunch/.resolved-binary

# Windows (PowerShell)
"$env:APPDATA\42Crunch\bin\42c-ast.exe" | Set-Content "$env:APPDATA\.42crunch\.resolved-binary"
```

### 5.6 — Confirm

```bash
"$BINARY_PATH" --version
```

If this exits 0: inform the user `42c-ast v<version> installed at <BINARY_PATH>.`

If it fails, stop:
> `42c-ast` could not run after installation. The binary may be incompatible with
> your system. Check your OS/architecture and retry, or install the 42Crunch
> OpenAPI Editor VS Code extension which bundles the correct binary automatically.

---

## Error Handling

| Situation | Action |
|---|---|
| Manifest fetch fails (network error) | Report the error. If binary already installed and up to date, warn that version currency cannot be verified and proceed to credential setup |
| No manifest entry for current platform | Report unsupported platform; stop |
| Download fails | Report error with `DOWNLOAD_URL` for manual download |
| Checksum mismatch | Delete partial file and stop; ask user to retry |
| Installed `--version` unparseable | Treat as outdated; proceed with download |
| Cannot write to `BIN_DIR` | Report permission error; suggest elevated privileges |
| `code` CLI not on PATH (VS Code path) | Instruct user to run "Shell Command: Install 'code' command in PATH" from Command Palette |
