# Pre-flight Checks

Shared entry point for all 42Crunch skills. Run these steps in order before
any skill-specific logic. Do not proceed if any step fails or the user cancels.

---

## Fast Path — Skip Redundant Checks

Before Step 1, check whether pre-flight has already completed successfully
earlier in **this same conversation**, with no intervening credential change
(the user has not run `42crunch-setup`, nor gone through `token-limit.md`'s
reconfiguration, since):

- **Yes** → skip Step 1 (Binary Check) and Step 2 (Credential Check) entirely.
  Reuse the mode, credentials, and binary path already established. Continue
  directly to Step 3 (Resolve the OAS File).
  - If Step 3 resolves to the **same** OAS file as the previous run in this
    conversation → also skip Step 4 (Tag Detection) and reuse the previously
    resolved tag.
  - If Step 3 resolves to a **different** OAS file → still run Step 4 for
    the new file (a different file may carry a different tag, or none).
- **No** (first pre-flight run this conversation, or credentials changed since
  the last run) → run all steps in order starting from Step 1.

This is a same-conversation shortcut only. It does not apply across separate
conversations — Step 1 has its own cross-session cache (the `.preflight-cache`
check inlined below).

---

## Step 1 — Binary Check

Announce: `"Checking for 42c-ast..."` then classify the binary state with one
command — do **not** read `./binary-setup.md` yet:

```bash
# macOS / Linux
BINARY_PATH="$HOME/.42crunch/bin/42c-ast"
CACHE_FILE="$HOME/.42crunch/conf/.preflight-cache"
TTL="${PREFLIGHT_CACHE_TTL_SECONDS:-86400}"
if [ ! -x "$BINARY_PATH" ]; then
  echo "BINARY=missing"
elif CHECKED_AT=$(grep '^CHECKED_AT=' "$CACHE_FILE" 2>/dev/null | cut -d= -f2) \
  && [ -n "$CHECKED_AT" ] && [ $(( $(date +%s) - CHECKED_AT )) -lt "$TTL" ] \
  && "$BINARY_PATH" --version >/dev/null 2>&1; then
  echo "BINARY=fresh"
else
  echo "BINARY=check"
fi
```

```powershell
# Windows
$BinaryPath = "$env:APPDATA\42Crunch\bin\42c-ast.exe"
$CacheFile = "$env:APPDATA\42Crunch\conf\.preflight-cache"
$Ttl = if ($env:PREFLIGHT_CACHE_TTL_SECONDS) { [int]$env:PREFLIGHT_CACHE_TTL_SECONDS } else { 86400 }
if (-not (Test-Path $BinaryPath)) { "BINARY=missing" }
else {
  $fresh = $false
  $line = Select-String -Path $CacheFile -Pattern '^CHECKED_AT=' -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($line) {
    $CheckedAt = [int]($line.Line -replace '^CHECKED_AT=', '')
    $Now = [int][double]::Parse((Get-Date -UFormat %s))
    if (($Now - $CheckedAt) -lt $Ttl) {
      & $BinaryPath --version *> $null
      if ($LASTEXITCODE -eq 0) { $fresh = $true }
    }
  }
  if ($fresh) { "BINARY=fresh" } else { "BINARY=check" }
}
```

- **`BINARY=fresh`** → binary present, verified against the manifest within
  the cache TTL, and runs. Skip `./binary-setup.md` entirely — do not read
  it — and continue to Step 2.
- **`BINARY=check`** → binary present but the cache is missing or stale.
  Silently follow `./binary-setup.md` (silent mode — see Caller Verbosity
  section in that file). The only output is `"42c-ast updated from vX to vY."`
  if an update was applied. If the manifest is unreachable, announce:
  `"Could not reach the update server — continuing with installed 42c-ast v<version>."` then continue to Step 2.
- **`BINARY=missing`** → announce `"The 42c-ast binary isn't installed yet — running setup now."` then invoke `42crunch-setup` as a **subroutine** (pass caller context: `pre-flight`). Do not proceed if setup fails. On success, setup's credential pass has just classified (or freshly configured) the credential mode — **skip Step 2's classification**, reuse that mode, and continue directly to Step 3.

---

## Step 2 — Credential Check

**Never read or print the raw value of `API_KEY` / `TRIAL_TOKEN`.** This step
only needs a mode classification — get it without the secret ever entering a
command, tool output, or chat message:

```bash
# macOS / Linux
ENV_FILE="$HOME/.42crunch/conf/env"
if grep -q '^TRIAL_TOKEN=' "$ENV_FILE" 2>/dev/null; then
  # .trial-expired is the legacy sentinel name written by older plugin versions
  if [ -f "$HOME/.42crunch/conf/.token-limit" ] || [ -f "$HOME/.42crunch/conf/.trial-expired" ]; then
    echo "MODE=token_limit"
  else
    echo "MODE=token"
  fi
elif grep -qE '^API_KEY=(api_|ide_)' "$ENV_FILE" 2>/dev/null; then
  echo "MODE=platform"
elif grep -q '^API_KEY=' "$ENV_FILE" 2>/dev/null; then
  echo "MODE=badformat"
else
  echo "MODE=none"
fi
```

```powershell
# Windows
$EnvFile = "$env:APPDATA\42Crunch\conf\env"
if (Select-String -Path $EnvFile -Pattern '^TRIAL_TOKEN=' -Quiet -ErrorAction SilentlyContinue) {
  # .trial-expired is the legacy sentinel name written by older plugin versions
  if ((Test-Path "$env:APPDATA\42Crunch\conf\.token-limit") -or (Test-Path "$env:APPDATA\42Crunch\conf\.trial-expired")) {
    Write-Output "MODE=token_limit"
  } else {
    Write-Output "MODE=token"
  }
} elseif (Select-String -Path $EnvFile -Pattern '^API_KEY=(api_|ide_)' -Quiet -ErrorAction SilentlyContinue) {
  Write-Output "MODE=platform"
} elseif (Select-String -Path $EnvFile -Pattern '^API_KEY=' -Quiet -ErrorAction SilentlyContinue) {
  Write-Output "MODE=badformat"
} else {
  Write-Output "MODE=none"
}
```

- **`MODE=token`** → **Token mode**. Use `--freemium-host stateless.42crunch.com:443` and `--token <TRIAL_TOKEN>` in all commands (the token is substituted directly into the `42c-ast` invocation — never echoed on its own). Proceed silently.
- **`MODE=token_limit`** → a previous run already discovered this token plan hit its usage limit (Starter trial ended, or Individual / Individual Pro monthly tokens exhausted). Skip Step 3 onward entirely — follow `./token-limit.md` now, without attempting any `42c-ast` call.
- **`MODE=platform`** → **Platform mode**. Read `PLATFORM_HOST` separately — it's a URL, not a secret, safe to print in full:
  ```bash
  grep '^PLATFORM_HOST=' "$ENV_FILE"
  ```
  Required — run `42crunch-setup` to reconfigure if missing. Proceed silently.
- **`MODE=badformat`** → warn the user: `"Your API key doesn't match the expected format (api_... or ide_...). Please check it or run 42crunch-setup to reconfigure."` Stop — do not proceed.
- **`MODE=none`** → call `AskUserQuestion`:
  - **question**: `"I don't see any 42Crunch credentials configured yet. I can walk you through setup now, or you can run 42crunch-setup manually when you're ready."`
  - **options**: `["Set up now", "Cancel — I'll run 42crunch-setup manually"]`
  - If **Set up now** → invoke `42crunch-setup` as a **subroutine** (pass caller context: `pre-flight`). Do not proceed if setup fails. On success, continue to Step 3.
  - If **Cancel** → stop.

---

## Step 3 — Resolve the OAS File

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

## Step 4 — Tag Detection (platform mode only)

Read `./tag-detection.md` and follow all steps. In token mode, skip
tag detection entirely. The tag detection flow handles all outcomes — tag
found, user assigns a tag, or user proceeds without one — before returning
to the calling skill.

---

## Environment Variables

| Variable          | Mode      | Purpose                                   |
|-------------------|-----------|-------------------------------------------|
| `API_KEY`         | Platform  | `api_*` or `ide_*` token                 |
| `PLATFORM_HOST`   | Platform  | Platform base URL                         |
| `TRIAL_TOKEN`  | Token     | Base64 access token — Starter (Free Trial), Individual, or Individual Pro — passed as `--token`. Variable name kept for backward compatibility with existing config files. |

**Platform mode**: `API_KEY` and `PLATFORM_HOST` set for every command.
`--report-sqg` always applied. `--tag <category>:<tagname>` applied only
when a tag is assigned.

**Token mode**: `--freemium-host stateless.42crunch.com:443` and
`--token <TRIAL_TOKEN>` for every command. No `--tag` or `--report-sqg`.

---

## General Constraints

- Use the `Bash` tool to execute all `42c-ast` commands.
- Use the `Edit` or `Write` tools to apply fixes to the OAS file.
- Never modify the OAS file without first describing what will change.
- All credential inputs are ephemeral in-session values. Do not write tokens
  or passwords to disk outside of scan config files that already expect them.
- Surface brief status lines before slow network operations (manifest fetch,
  binary download, tag detection). Do not surface individual sub-steps like
  SHA-256 verification or file writes.
