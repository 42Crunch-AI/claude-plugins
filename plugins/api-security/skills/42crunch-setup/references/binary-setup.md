# Binary Setup Reference

Follow this procedure to ensure the `42c-ast` binary is available.
All detection steps run silently — surface output only on failure or user prompts.

---

## Step 0 — Check for Existing Binary

Detect the OS and resolve the canonical binary path:

| OS            | `BINARY_PATH`                                   |
|---------------|-------------------------------------------------|
| macOS / Linux | `$HOME/.42crunch/bin/42c-ast`                   |
| Windows       | `$env:APPDATA\42Crunch\bin\42c-ast.exe`         |

Check whether the binary exists and runs:

```bash
# macOS / Linux
test -x "$HOME/.42crunch/bin/42c-ast" && "$HOME/.42crunch/bin/42c-ast" --version
```

```powershell
# Windows
if (Test-Path "$env:APPDATA\42Crunch\bin\42c-ast.exe") {
    & "$env:APPDATA\42Crunch\bin\42c-ast.exe" --version
}
```

- **Binary missing or does not run** → continue to Step 1.
- **Binary present and `--version` exits 0** → continue to Step 2 (fetch manifest
  and compare versions). Do **not** skip to credentials — version must be verified
  first.
  - Parse the semver string from the `--version` output (e.g. extract `X.Y.Z`).
    Store as `INSTALLED_VERSION`.
  - If `INSTALLED_VERSION` **equals** `LATEST_VERSION`: binary is up to date.
    **Exit this procedure with success** — skip to credential setup.
  - If `INSTALLED_VERSION` is **older** (or version cannot be parsed): inform
    the user and continue to Step 3 to download and replace the binary.

---

## Step 1 — Detect OS and Architecture

```bash
OS=$(uname -s)     # Darwin, Linux, or MINGW*/CYGWIN*/MSYS*
ARCH=$(uname -m)   # arm64, aarch64, x86_64
```

Map to manifest `architecture` key:

| `uname -s`                  | `uname -m`        | `architecture`  | Binary filename    |
|-----------------------------|-------------------|-----------------|--------------------|
| Darwin                      | arm64             | darwin-arm64    | 42c-ast            |
| Darwin                      | x86_64            | darwin-amd64    | 42c-ast            |
| Linux                       | arm64 / aarch64   | linux-arm64     | 42c-ast            |
| Linux                       | x86_64            | linux-amd64     | 42c-ast            |
| MINGW* / CYGWIN* / MSYS*    | x86_64            | windows-amd64   | 42c-ast.exe        |

On **Windows**, detect via PowerShell if `uname` is unavailable:

```powershell
$env:OS                          # "Windows_NT"
$env:PROCESSOR_ARCHITECTURE      # "AMD64" → windows-amd64
```

Resolve path variables:

| Variable      | macOS / Linux                    | Windows                                   |
|---------------|----------------------------------|-------------------------------------------|
| `BIN_DIR`     | `$HOME/.42crunch/bin`            | `$env:APPDATA\42Crunch\bin`               |
| `BINARY_PATH` | `$HOME/.42crunch/bin/42c-ast`    | `$env:APPDATA\42Crunch\bin\42c-ast.exe`   |

---

## Step 2 — Fetch Manifest and Resolve Download URL

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

If the manifest fetch fails (network error) and no binary is installed, stop with:
> Could not fetch the 42c-ast manifest. Check your network connection and retry.

---

## Step 3 — Download and Install

### 3.1 — Create Directories

```bash
# macOS / Linux
mkdir -p "$HOME/.42crunch/bin"

# Windows (PowerShell)
New-Item -ItemType Directory -Force -Path "$env:APPDATA\42Crunch\bin" | Out-Null
```

### 3.2 — Download

```bash
# macOS / Linux — curl with wget fallback
curl -fsSL "$DOWNLOAD_URL" -o "$BINARY_PATH" \
  || wget -q "$DOWNLOAD_URL" -O "$BINARY_PATH"

# Windows (PowerShell)
Invoke-WebRequest -Uri "$DOWNLOAD_URL" -OutFile "$env:APPDATA\42Crunch\bin\42c-ast.exe"
```

### 3.3 — Verify SHA-256

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

### 3.4 — Set Permissions (macOS / Linux only)

```bash
chmod +x "$BINARY_PATH"
```

### 3.5 — Confirm

```bash
"$BINARY_PATH" --version
```

If this exits 0: inform the user `42c-ast v<version> installed at <BINARY_PATH>.`

If it fails, stop:
> `42c-ast` could not run after installation. The binary may be incompatible with
> your system. Check your OS/architecture and retry.

---

## Error Handling

| Situation | Action |
|---|---|
| Manifest fetch fails (network error) — no binary installed | Report the error. Stop — cannot install without the manifest |
| Manifest fetch fails (network error) — binary already installed | Warn that version currency cannot be verified; continue to credential setup |
| Installed `--version` unparseable | Treat as outdated; proceed with download |
| No manifest entry for current platform | Report unsupported platform; stop |
| Download fails | Report error with `DOWNLOAD_URL` for manual download |
| Checksum mismatch | Delete partial file and stop; ask user to retry |
| Cannot write to `BIN_DIR` | Report permission error; suggest elevated privileges |
