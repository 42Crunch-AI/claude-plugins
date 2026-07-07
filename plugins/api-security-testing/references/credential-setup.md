# Credential Setup Reference

Follow this procedure to configure credentials used by all 42Crunch skills.
All detection steps run silently — surface output only on failure or user prompts.

Credentials are stored exclusively in `~/.42crunch/conf/env` (macOS/Linux) or
`%APPDATA%\42Crunch\conf\env` (Windows). No project-level `.env` files are
used.

---

## Step 1 — Check for Existing Credentials

Silently check for an existing credentials file. **Never read or print more
than the 4-character prefix needed for masking** — the rest of the secret
must not enter any command, tool output, or chat message:

```bash
# macOS / Linux
ENV_FILE="$HOME/.42crunch/conf/env"
if grep -q '^TRIAL_TOKEN=' "$ENV_FILE" 2>/dev/null; then
  echo "MODE=token"
  grep -oE '^TRIAL_TOKEN=.{4}' "$ENV_FILE" | sed 's/^TRIAL_TOKEN=/PREFIX=/'
elif grep -qE '^API_KEY=(api_|ide_)' "$ENV_FILE" 2>/dev/null; then
  echo "MODE=platform"
  grep -oE '^API_KEY=(api_|ide_)' "$ENV_FILE" | sed 's/^API_KEY=/PREFIX=/'
elif grep -q '^API_KEY=' "$ENV_FILE" 2>/dev/null; then
  echo "MODE=badformat"
else
  echo "MODE=none"
fi
```

```powershell
# Windows
$EnvFile = "$env:APPDATA\42Crunch\conf\env"
if (Select-String -Path $EnvFile -Pattern '^TRIAL_TOKEN=(.{4})' -ErrorAction SilentlyContinue |
    Select-Object -First 1 -OutVariable m) {
  Write-Output "MODE=token"
  Write-Output ("PREFIX=" + $m[0].Matches[0].Groups[1].Value)
} elseif (Select-String -Path $EnvFile -Pattern '^API_KEY=(api_|ide_)' -ErrorAction SilentlyContinue |
    Select-Object -First 1 -OutVariable m) {
  Write-Output "MODE=platform"
  Write-Output ("PREFIX=" + $m[0].Matches[0].Groups[1].Value)
} elseif (Select-String -Path $EnvFile -Pattern '^API_KEY=' -Quiet -ErrorAction SilentlyContinue) {
  Write-Output "MODE=badformat"
} else {
  Write-Output "MODE=none"
}
```

**Mode detection from the output:**

- `MODE=token` → **Token mode** (covers Starter (Free Trial), Individual, and Individual Pro — they all use the same personal access token)
- `MODE=platform` → **Platform mode** (Team 10, Team 25, and Enterprise — a Platform account with an API key)
- `MODE=badformat` / `MODE=none` → no usable credential found; proceed to Step 2 as if none exists.

**If `MODE=token` or `MODE=platform`** (a credential is found):

- **Called as a subroutine** (caller context is set — e.g. `pre-flight` only
  needed a binary install): keep the existing credentials automatically.
  Announce `"Existing <mode> credentials found (<masked>) — keeping them."`
  and finish — **credential setup complete**. Do not ask the keep-or-replace
  question; the caller needed the environment completed, not re-credentialed.
- **Called directly by the user**: call `AskUserQuestion`:
  - **question**: `"Credentials already configured in ~/.42crunch/conf/env — running in <mode> mode. Key: <masked>. Would you like to keep the existing credentials or replace them?"`
  - **options**: `["Keep existing credentials", "Replace credentials"]`

Build `<masked>` directly from `PREFIX` — never from the full secret:
`api_••••••••` / `ide_••••••••` for platform tokens; `<PREFIX>••••••••` for
tokens (e.g. `eyJh••••••••`).

If keeping → **credential setup complete.**
If replacing → continue to Step 2.

---

## Step 2 — Determine Existing Access

Call `AskUserQuestion`:
- **question**: `"Do you have a 42Crunch Subscription?"`
- **options**: `["No — I want to subscribe to the Starter (Free Trial) plan", "Yes — I have a subscription (or an existing Starter (Free Trial) account)"]`

**If No** — continue to Path C.

**If Yes** — call `AskUserQuestion`:
- **question**: `"Is it a token-based plan (Starter (Free Trial), Individual, or Individual Pro) or a Platform account with an API key (Team 10, Team 25, or Enterprise)?"`
- **options**: `["Token", "Platform account (API key)"]`

- **Token** chosen → continue to Path B.
- **Platform account (API key)** chosen → continue to Path A.

---

### Path A — Platform mode (Team 10, Team 25, Enterprise)

Call `AskUserQuestion`:
- **question**: `"Please enter your API Key (it usually starts with api_ or ide_):"`

Wait for input. Then call `AskUserQuestion`:
- **question**: `"Which region hosts your 42Crunch platform? (Your organisation's IT or security team can confirm this — it's also visible in the URL when you log in.)"`
- **options**: `["US — https://us.42crunch.cloud/", "EU — https://eu.42crunch.cloud/", "Other — I'll enter my platform URL manually"]`

- If **US** chosen: `PLATFORM_HOST=https://us.42crunch.cloud`
- If **EU** chosen: `PLATFORM_HOST=https://eu.42crunch.cloud`
- If **Other** chosen: call `AskUserQuestion` — **question**: `"Please enter your platform URL (e.g. https://your-org.42crunch.cloud):"` — store response as `PLATFORM_HOST`. Trim any trailing slashes.

Store values as `API_KEY` and `PLATFORM_HOST`. Continue to Step 3.

---

### Path B — Token-based (Starter (Free Trial), Individual, Individual Pro)

Call `AskUserQuestion`:
- **question**: `"Please paste your token (it's a long Base64 string):"`

Wait for input. Store value as `TRIAL_TOKEN`. Continue to Step 3.

---

### Path C — No Existing Access

Inform the user:
> No problem — getting a free account takes a minute.
>
> 1. Visit **[42Crunch Starter (Free Trial)](https://42crunch.com/freemium/?source=claude)**.
> 2. Fill in your email address, accept terms and conditions and click Submit.
> 3. Check your inbox for a confirmation email that includes your token.
>
> Prefer to skip the trial and go straight to a paid plan? Visit
> **[42Crunch Pricing](https://42crunch.com/pricing/)** to choose one:
> - **Individual** — 1,000 Security Tokens / month, same token-based setup you'd use here.
> - **Individual Pro** — 3,000 Security Tokens / month, same token-based setup.
> - **Team 10** — unlimited Security Tokens for teams of up to 10. Uses a Platform account with an API key instead of a token.
> - **Team 25** — unlimited Security Tokens for teams of up to 25. Uses a Platform account with an API key instead of a token.
> - **Enterprise** — for teams and companies needing CI/CD integration, API Protection, and more. Uses a company Platform account with an API key instead of a token.
>
> When you're ready, just say "continue" or "I have my token" and I'll pick up
> exactly where we left off — you won't need to restart setup.

**Stop — do not proceed.** Credential setup is incomplete. Do not write any credentials file.

**On resume** (user says "continue" or similar): call `AskUserQuestion`:
- **question**: `"Did you sign up for a token-based plan, or a plan that uses a Platform account?"`
- **options**: `["Token-based (Starter (Free Trial), Individual, or Individual Pro)", "Platform account (Team 10, Team 25, or Enterprise)"]`

- **Token-based** chosen → continue to Path B.
- **Platform account** chosen → continue to Path A.

---

## Step 3 — Write the Credentials File

Create the directory if it does not exist:

```bash
# macOS / Linux
mkdir -p "$HOME/.42crunch/conf"
```

```powershell
# Windows
New-Item -ItemType Directory -Force -Path "$env:APPDATA\42Crunch\conf" | Out-Null
```

**This step fully replaces the credentials file — it is never a merge.** Use
the `Write` tool specifically (not `Edit`) so the result contains **only**
the keys for the resolved mode below, with nothing left over from a
previous mode. This matters most when switching modes: `pre-flight.md`'s
mode detection checks `TRIAL_TOKEN` before `API_KEY`, so a leftover
`TRIAL_TOKEN` line after switching to Platform mode would cause the system
to keep misidentifying the account as Token mode.

Write the file. Do not quote values. Do not add spaces around `=`.

**Platform mode**

macOS / Linux — write to `~/.42crunch/conf/env`:

```
API_KEY=<value>
PLATFORM_HOST=<value>
```

Windows — write to `%APPDATA%\42Crunch\conf\env`:

```
API_KEY=<value>
PLATFORM_HOST=<value>
```

**Token mode**

macOS / Linux — write to `~/.42crunch/conf/env`:

```
TRIAL_TOKEN=<value>
```

Windows — write to `%APPDATA%\42Crunch\conf\env`:

```
TRIAL_TOKEN=<value>
```

**Set restrictive permissions (macOS / Linux only):**

```bash
chmod 600 "$HOME/.42crunch/conf/env"
```

Skip on Windows — `APPDATA` is already protected by Windows ACLs.

**Clear the token-limit sentinel, if present.** Any successful write here —
regardless of which mode it resolves to — means the account state has just
changed, so a previously-recorded limit state no longer applies. Remove both
the current sentinel name and the legacy one written by older plugin versions:

```bash
# macOS / Linux
rm -f "$HOME/.42crunch/conf/.token-limit" "$HOME/.42crunch/conf/.trial-expired"
```

```powershell
# Windows
Remove-Item "$env:APPDATA\42Crunch\conf\.token-limit","$env:APPDATA\42Crunch\conf\.trial-expired" -ErrorAction SilentlyContinue
```

---

## Step 4 — Verify

Confirm the correct variable is present — a presence check only, never the
value. Use `-q` / `-Quiet` so the secret cannot appear in the tool output:

**Platform mode (macOS / Linux):**
```bash
grep -q "^API_KEY=" "$HOME/.42crunch/conf/env" && echo "OK" || echo "MISSING"
```

**Platform mode (Windows):**
```powershell
if (Select-String -Path "$env:APPDATA\42Crunch\conf\env" -Pattern "^API_KEY=" -Quiet) { "OK" } else { "MISSING" }
```

**Token mode (macOS / Linux):**
```bash
grep -q "^TRIAL_TOKEN=" "$HOME/.42crunch/conf/env" && echo "OK" || echo "MISSING"
```

**Token mode (Windows):**
```powershell
if (Select-String -Path "$env:APPDATA\42Crunch\conf\env" -Pattern "^TRIAL_TOKEN=" -Quiet) { "OK" } else { "MISSING" }
```

If `MISSING` → report the failure (see Error Handling below) and stop; do
not present the summary in Step 5.

Display confirmation with the value **masked**, built from the `PREFIX`
already captured in Step 1 (existing credential) or from the value the user
just typed in Step 2 (new credential) — do not re-read the secret from disk
to build this display:

**Platform mode (macOS / Linux):**
> Credentials saved to `~/.42crunch/conf/env`.
> Mode: **Platform** | Key: `api_••••••••` | Host: `<PLATFORM_HOST>`

**Platform mode (Windows):**
> Credentials saved to `%APPDATA%\42Crunch\conf\env`.
> Mode: **Platform** | Key: `api_••••••••` | Host: `<PLATFORM_HOST>`

**Token mode (macOS / Linux):**
> Credentials saved to `~/.42crunch/conf/env`.
> Mode: **Token** | Token: `<first-4-chars>••••••••`  ← show first 4 chars of the token

**Token mode (Windows):**
> Credentials saved to `%APPDATA%\42Crunch\conf\env`.
> Mode: **Token** | Token: `<first-4-chars>••••••••`  ← show first 4 chars of the token

---

## Error Handling

| Situation | Action |
|---|---|
| User provides empty API Key | Re-prompt once with: "It looks like the key didn't come through — please paste it again (it usually starts with `api_` or `ide_`). If you're not sure where to find it, check the 42Crunch platform under **Settings → API Keys**." If still empty, stop with: "I wasn't able to capture your API key. Your binary is installed and working — when you're ready, run `42crunch-setup` again to finish credential setup." |
| User provides empty Platform URL (Other) | Re-prompt once with: "I didn't catch the URL — please paste your platform address (it should look like `https://your-org.42crunch.cloud`)." If still empty, stop with: "I wasn't able to capture your platform URL. Your binary is installed — run `42crunch-setup` again whenever you have the details ready." |
| User provides empty token | Re-prompt once with: "The token didn't come through — please paste it again." If still empty, stop with: "I wasn't able to capture your token. Your binary is installed — run `42crunch-setup` again whenever you have the token ready." |
| Cannot write to credentials file | Report the permission error. On macOS/Linux, suggest `chmod u+w ~/.42crunch/conf/env` or creating `~/.42crunch/conf` manually. On Windows, suggest verifying write access to `%APPDATA%\42Crunch\conf` and creating the folder manually if needed. |
