# Binary Setup

Full installation and update procedure for the `42c-ast` binary.

---

## Caller Verbosity

This procedure is used in two contexts:
- **`42crunch-setup` skill** — verbose: announce each major step to the user.
- **`pre-flight.md`** (all other skills) — silent: suppress all output except:
  - `"42c-ast updated from vX to vY."` if an update was applied.
  - Any error that prevents the binary from functioning.

The caller specifies which mode applies. Default is silent.

The pre-flight cache fast path (Step 0.5) applies **only in silent mode**. In
verbose mode (`42crunch-setup`), always perform the live version check — the
user explicitly asked to install, update, or verify, so skip Step 0.5 and go
straight from Step 0 to Step 1.

---

## Step 0 — Check for an existing binary

Resolve the canonical path for the current OS:
- macOS/Linux: `$HOME/.42crunch/bin/42c-ast`
- Windows: `%APPDATA%\42Crunch\bin\42c-ast.exe`

Initialize `BIN_DIR` and `BINARY_PATH` for binary version check:

```bash
# macOS / Linux
BIN_DIR="$HOME/.42crunch/bin"
BINARY_PATH="$BIN_DIR/42c-ast"
```

```powershell
# Windows
$BIN_DIR = "$env:APPDATA\42Crunch\bin"
$BINARY_PATH = "$BIN_DIR\42c-ast.exe"
```

- Binary **missing or broken** (`--version` exits non-zero or file absent) →
  continue to **Step 1** (detect OS/arch).
- Binary **present** and `--version` exits 0 → capture the installed version:

  ```bash
  INSTALLED_VERSION=$("$BINARY_PATH" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
  ```

  In **silent mode**, continue to **Step 0.5** (consult the pre-flight cache)
  before deciding whether a network round-trip is even needed. In **verbose
  mode**, skip Step 0.5 and continue directly to **Step 1**. Either way, do
  **not** exit here — always verify that the installed version is current
  before declaring setup complete.

---

## Step 0.5 — Consult the pre-flight cache (silent mode only)

The manifest fetch in Step 2 is a network call — skip it when a recent check
already confirmed the binary is current. Resolve the cache file path:

- macOS/Linux: `$HOME/.42crunch/conf/.preflight-cache`
- Windows: `%APPDATA%\42Crunch\conf\.preflight-cache`

```bash
# macOS / Linux
CACHE_FILE="$HOME/.42crunch/conf/.preflight-cache"
TTL="${PREFLIGHT_CACHE_TTL_SECONDS:-86400}"
CACHE_FRESH=0
if [ -f "$CACHE_FILE" ]; then
  CHECKED_AT=$(grep '^CHECKED_AT=' "$CACHE_FILE" | cut -d= -f2)
  NOW=$(date +%s)
  if [ -n "$CHECKED_AT" ] && [ $((NOW - CHECKED_AT)) -lt "$TTL" ]; then
    CACHE_FRESH=1
  fi
fi
```

```powershell
# Windows
$CacheFile = "$env:APPDATA\42Crunch\conf\.preflight-cache"
$Ttl = if ($env:PREFLIGHT_CACHE_TTL_SECONDS) { [int]$env:PREFLIGHT_CACHE_TTL_SECONDS } else { 86400 }
$CacheFresh = $false
if (Test-Path $CacheFile) {
  $CheckedAtLine = Select-String -Path $CacheFile -Pattern "^CHECKED_AT=" | Select-Object -First 1
  if ($CheckedAtLine) {
    $CheckedAt = [int]($CheckedAtLine.Line -replace "^CHECKED_AT=", "")
    $Now = [int][double]::Parse((Get-Date -UFormat %s))
    if (($Now - $CheckedAt) -lt $Ttl) { $CacheFresh = $true }
  }
}
```

- **`CACHE_FRESH` is `1` / `$true`** → the binary was verified current within
  the cache window. Skip Step 1 and Step 2 entirely. `INSTALLED_VERSION` (from
  Step 0) is the confirmed version. Return to the caller — no network call,
  no manifest fetch, no cache rewrite (the existing window is left as-is).
- **`CACHE_FRESH` is `0` / `$false`** (missing, expired, or malformed cache) →
  continue to **Step 1** as normal.

Override the default 24-hour window by setting `PREFLIGHT_CACHE_TTL_SECONDS`
before invoking a skill (e.g. `0` to force a live check every time).

---

## Step 1 — Detect OS and architecture

Determine the current platform and resolve `BIN_DIR` and `BINARY_PATH`:

| OS | Architecture | Platform key | BIN_DIR | BINARY_PATH |
|----|-------------|--------------|---------|-------------|
| macOS | arm64 | `darwin-arm64` | `$HOME/.42crunch/bin` | `$BIN_DIR/42c-ast` |
| macOS | x86_64 | `darwin-amd64` | `$HOME/.42crunch/bin` | `$BIN_DIR/42c-ast` |
| Linux | x86_64 | `linux-amd64` | `$HOME/.42crunch/bin` | `$BIN_DIR/42c-ast` |
| Linux | arm64 | `linux-arm64` | `$HOME/.42crunch/bin` | `$BIN_DIR/42c-ast` |
| Windows | x86_64 | `windows-amd64` | `%APPDATA%\42Crunch\bin` | `%BIN_DIR%\42c-ast.exe` |
| Windows | arm64 | `windows-arm64` | `%APPDATA%\42Crunch\bin` | `%BIN_DIR%\42c-ast.exe` |

```bash
# macOS / Linux
ARCH=$(uname -m)
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
case "$ARCH" in
  arm64|aarch64) ARCH_KEY="arm64" ;;
  x86_64|amd64)  ARCH_KEY="amd64" ;;
  *) echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac
PLATFORM_KEY="${OS}-${ARCH_KEY}"
BIN_DIR="$HOME/.42crunch/bin"
BINARY_PATH="$BIN_DIR/42c-ast"
mkdir -p "$BIN_DIR"
```

```powershell
# Windows
if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") {
  $PLATFORM_KEY = "windows-arm64"
} else {
  $PLATFORM_KEY = "windows-amd64"
}
$BIN_DIR = "$env:APPDATA\42Crunch\bin"
$BINARY_PATH = "$BIN_DIR\42c-ast.exe"
New-Item -ItemType Directory -Force -Path $BIN_DIR | Out-Null
```

---

## Step 2 — Fetch the manifest and resolve download details

```bash
# macOS / Linux
if command -v curl &>/dev/null; then
  curl -fsSL https://repo.42crunch.com/downloads/42c-ast-manifest.json \
    -o /tmp/42c-ast-manifest.json
elif command -v wget &>/dev/null; then
  wget -q -O /tmp/42c-ast-manifest.json \
    https://repo.42crunch.com/downloads/42c-ast-manifest.json
else
  echo "ERROR: curl or wget is required to download the manifest"; exit 1
fi
```

```powershell
# Windows
$ManifestPath = Join-Path $env:TEMP "42c-ast-manifest.json"
Invoke-WebRequest -Uri "https://repo.42crunch.com/downloads/42c-ast-manifest.json" -OutFile $ManifestPath
```

The manifest is a JSON array. Filter entries by the `architecture` field
matching `PLATFORM_KEY`. From the matching entry, extract:

| Field | Variable |
|-------|----------|
| `version` | `LATEST_VERSION` |
| `downloadUrl` | `DOWNLOAD_URL` |
| `sha256` | `EXPECTED_SHA256` |

```bash
# macOS / Linux
if command -v python3 &>/dev/null; then
  MANIFEST_OUTPUT=$(python3 - "$PLATFORM_KEY" << 'EOF'
import json, sys
with open("/tmp/42c-ast-manifest.json") as f:
    entries = json.load(f)
platform = sys.argv[1]
match = next((e for e in entries if e.get("architecture") == platform), None)
if not match:
    print(f"ERROR: no manifest entry for {platform}", file=sys.stderr)
    sys.exit(1)
print(match["version"])
print(match["downloadUrl"])
print(match["sha256"])
EOF
)
elif command -v jq &>/dev/null; then
  MANIFEST_OUTPUT=$(printf '%s\n%s\n%s\n' \
    "$(jq -r --arg p "$PLATFORM_KEY" '.[] | select(.architecture==$p) | .version' /tmp/42c-ast-manifest.json)" \
    "$(jq -r --arg p "$PLATFORM_KEY" '.[] | select(.architecture==$p) | .downloadUrl' /tmp/42c-ast-manifest.json)" \
    "$(jq -r --arg p "$PLATFORM_KEY" '.[] | select(.architecture==$p) | .sha256'  /tmp/42c-ast-manifest.json)")
else
  echo "ERROR: python3 or jq is required to parse the manifest"; exit 1
fi

LATEST_VERSION=$(echo "$MANIFEST_OUTPUT" | sed -n '1p')
DOWNLOAD_URL=$(echo "$MANIFEST_OUTPUT"   | sed -n '2p')
EXPECTED_SHA256=$(echo "$MANIFEST_OUTPUT" | sed -n '3p')
```

```powershell
# Windows
$ManifestEntries = Get-Content $ManifestPath -Raw | ConvertFrom-Json
$Match = $ManifestEntries | Where-Object { $_.architecture -eq $PLATFORM_KEY } | Select-Object -First 1
if (-not $Match) {
  Write-Error "ERROR: no manifest entry for $PLATFORM_KEY"
  exit 1
}

$LATEST_VERSION = $Match.version
$DOWNLOAD_URL = $Match.downloadUrl
$EXPECTED_SHA256 = $Match.sha256
```

If `INSTALLED_VERSION` (from Step 0) equals `LATEST_VERSION` → binary is
up to date. Skip Step 3 and continue to **Step 4** (update the pre-flight
cache).

If the installed version is older (or the binary was absent) → continue to
Step 3.

---

## Step 3 — Download, verify, install

```bash
# macOS / Linux
TMP_BIN="/tmp/42c-ast-download"
if command -v curl &>/dev/null; then
  curl -fsSL "$DOWNLOAD_URL" -o "$TMP_BIN"
elif command -v wget &>/dev/null; then
  wget -q -O "$TMP_BIN" "$DOWNLOAD_URL"
else
  echo "ERROR: curl or wget is required to download the binary"; exit 1
fi

# Verify SHA-256
if command -v sha256sum &>/dev/null; then
  ACTUAL_SHA=$(sha256sum "$TMP_BIN" | awk '{print $1}')
else
  ACTUAL_SHA=$(shasum -a 256 "$TMP_BIN" | awk '{print $1}')
fi
if [ "$ACTUAL_SHA" != "$EXPECTED_SHA256" ]; then
  echo "SHA-256 mismatch — aborting install."
  rm -f "$TMP_BIN"
  exit 1
fi

mv "$TMP_BIN" "$BINARY_PATH"
chmod +x "$BINARY_PATH"
"$BINARY_PATH" --version
```

```powershell
# Windows
$TmpBin = "$env:TEMP\42c-ast-download.exe"
Invoke-WebRequest -Uri $DOWNLOAD_URL -OutFile $TmpBin

$ActualSha = (Get-FileHash -Algorithm SHA256 $TmpBin).Hash.ToLower()
if ($ActualSha -ne $EXPECTED_SHA256) {
    Write-Error "SHA-256 mismatch — aborting install."
    Remove-Item $TmpBin
    exit 1
}

Move-Item -Force $TmpBin $BINARY_PATH
& $BINARY_PATH --version
```

Confirm that `--version` exits 0. If it does not, report the failure and
stop — do not proceed to credential setup. If it does, continue to **Step 4**
(update the pre-flight cache).

---

## Step 4 — Update the pre-flight cache

Record that the binary was just verified against the manifest, so the next
**silent-mode** pre-flight run (within the TTL window) can skip Steps 1–2 via
Step 0.5. Run this step in **both** modes — even though verbose mode never
reads the cache, writing it here primes it for the very next pre-flight call
after setup finishes.

```bash
# macOS / Linux
mkdir -p "$HOME/.42crunch/conf"
CURRENT_VERSION="${LATEST_VERSION:-$INSTALLED_VERSION}"
cat > "$HOME/.42crunch/conf/.preflight-cache" << EOF
CHECKED_AT=$(date +%s)
BINARY_VERSION=$CURRENT_VERSION
EOF
```

```powershell
# Windows
New-Item -ItemType Directory -Force -Path "$env:APPDATA\42Crunch\conf" | Out-Null
$CurrentVersion = if ($LATEST_VERSION) { $LATEST_VERSION } else { $INSTALLED_VERSION }
$Now = [int][double]::Parse((Get-Date -UFormat %s))
@"
CHECKED_AT=$Now
BINARY_VERSION=$CurrentVersion
"@ | Set-Content -Path "$env:APPDATA\42Crunch\conf\.preflight-cache"
```

Return to the caller.
