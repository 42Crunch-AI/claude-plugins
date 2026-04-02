# Credential Setup Reference

Follow this procedure to configure credentials used by all 42Crunch skills.
All detection steps run silently — surface output only on failure or user prompts.

Credentials are stored exclusively in `~/.42crunch/conf/env` (macOS/Linux) or
`%APPDATA%\42Crunch\conf\env` (Windows). No project-level `.env` files are
used.

---

## Step 1 — Check for Existing Credentials

Silently check `~/.42crunch/conf/env` for either credential variable:

```bash
# macOS / Linux
grep -E "^(FREEMIUM_TOKEN|API_KEY)=" "$HOME/.42crunch/conf/env" 2>/dev/null
```

```powershell
# Windows
Select-String -Path "$env:APPDATA\42Crunch\conf\env" -Pattern "^(FREEMIUM_TOKEN|API_KEY)=" 2>$null
```

**Mode detection from the file:**

- `FREEMIUM_TOKEN` is present → **Freemium mode**
- `API_KEY` starts with `api_` or `ide_` → **Platform mode**

**If a credential is found**, inform the user (masking the value):

> Credentials already configured in `~/.42crunch/conf/env` — running in
> **<mode>** mode. Key: `<masked>`.
>
> Would you like to keep the existing credentials or replace them?

Masking rules: `api_••••••••` / `ide_••••••••` for platform tokens; `••••••••`
for freemium.

If keeping → **credential setup complete.**
If replacing → continue to Step 2.

---

## Step 2 — Request the Token

Present this to the user:

> Please enter your 42Crunch token. The format determines which mode the tools
> run in:
>
> | Value format    | Variable written  | Mode           |
> |-----------------|-------------------|----------------|
> | `api_…`         | `API_KEY`         | Platform mode  |
> | `ide_…`         | `API_KEY`         | Platform mode  |
> | Base64 string   | `FREEMIUM_TOKEN`  | Freemium mode  |
>
> Platform tokens are available in the 42Crunch Platform under
> **Settings → API Tokens**. IDE tokens come from the IDE extension settings.
> Freemium tokens are provided by the 42Crunch freemium service.

Wait for the user to paste the token.

---

## Step 3 — Detect Mode and Collect Platform Host

Inspect the token:

**`api_` or `ide_` prefix → Platform mode.**

Ask:
> What is your 42Crunch Platform URL?
> (Press Enter to use the default: `https://demolabs.42crunch.cloud`)

Store as `PLATFORM_HOST`. If empty, default to `https://demolabs.42crunch.cloud`.
Trim any trailing slashes.

**Anything else → Freemium mode.** No host prompt needed.

---

## Step 4 — Write the Credentials File

Create the directory if it does not exist:

```bash
# macOS / Linux
mkdir -p "$HOME/.42crunch/conf"
```

```powershell
# Windows
New-Item -ItemType Directory -Force -Path "$env:APPDATA\42Crunch\conf" | Out-Null
```

Write the file. Do not quote values. Do not add spaces around `=`.

**Platform mode** — write to `~/.42crunch/conf/env`:

```
API_KEY=<value>
PLATFORM_HOST=<value>
```

**Freemium mode** — write to `~/.42crunch/conf/env`:

```
FREEMIUM_TOKEN=<value>
```

**Set restrictive permissions (macOS / Linux only):**

```bash
chmod 600 "$HOME/.42crunch/conf/env"
```

Skip on Windows — `APPDATA` is already protected by Windows ACLs.

---

## Step 5 — Verify

Re-read the file and confirm the correct variable is present:

**Platform mode:**
```bash
grep "^API_KEY=" "$HOME/.42crunch/conf/env"
```

**Freemium mode:**
```bash
grep "^FREEMIUM_TOKEN=" "$HOME/.42crunch/conf/env"
```

Display confirmation with the value **masked**:

**Platform mode:**
> Credentials saved to `~/.42crunch/conf/env`.
> Mode: **Platform** | Key: `api_••••••••` | Host: `https://demolabs.42crunch.cloud`

**Freemium mode:**
> Credentials saved to `~/.42crunch/conf/env`.
> Mode: **Freemium** | Token: `••••••••`

---

## Error Handling

| Situation | Action |
|---|---|
| User provides empty token | Re-prompt once; if still empty, stop with a warning that binary is installed but credentials are not configured |
| User provides empty Platform URL | Use the default `https://demolabs.42crunch.cloud` |
| Cannot write to credentials file | Report the permission error; suggest `chmod u+w ~/.42crunch/conf/env` or creating the directory manually |
