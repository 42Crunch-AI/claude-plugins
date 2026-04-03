# Credential Setup Reference

Follow this procedure to configure credentials used by all 42Crunch skills.
All detection steps run silently — surface output only on failure or user prompts.

Credentials are stored exclusively in `~/.42crunch/conf/env` (macOS/Linux) or
`%APPDATA%\42Crunch\conf\env` (Windows). No project-level `.env` files are
used.

---

## Step 1 — Check for Existing Credentials

Silently check for an existing credentials file:

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

## Step 2 — Determine User Type

Ask the user:

> Are you an existing 42Crunch user?

---

### Path A — Existing User (Platform mode)

Ask:
> Please enter your API Key:

Wait for input. Then ask:
> What is your 42Crunch Platform URL?
>
> [1] US  — https://us.42crunch.cloud/
> [2] EU  — https://eu.42crunch.cloud/
> [3] Other — enter your platform URL:

- If **[1]** chosen: `PLATFORM_HOST=https://us.42crunch.cloud`
- If **[2]** chosen: `PLATFORM_HOST=https://eu.42crunch.cloud`
- If **[3]** chosen: prompt for the URL; store as `PLATFORM_HOST`. Trim any trailing slashes.

Store values as `API_KEY` and `PLATFORM_HOST`. Continue to Step 3.

---

### Path B — Not an Existing User

Ask:
> Are you a registered 42Crunch Freemium user?

#### Path B-1 — Registered Freemium user

Ask:
> Please enter your 42Crunch Freemium Token:

Wait for input. Store value as `FREEMIUM_TOKEN`. Continue to Step 3.

#### Path B-2 — Not registered

Inform the user:
> To use 42Crunch tools, you need a free account.
> Register here: https://42crunch.com/freemium/
>
> Once you have registered, rerun setup and choose "Yes" when asked if you are
> a registered Freemium user.

**Stop — do not proceed.** Credential setup is incomplete. Do not write any credentials file.

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

## Step 4 — Verify

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
> Mode: **Platform** | Key: `api_••••••••` | Host: `<PLATFORM_HOST>`

**Freemium mode:**
> Credentials saved to `~/.42crunch/conf/env`.
> Mode: **Freemium** | Token: `••••••••`

---

## Error Handling

| Situation | Action |
|---|---|
| User provides empty API Key | Re-prompt once; if still empty, stop with a warning that binary is installed but credentials are not configured |
| User provides empty Platform URL (Other) | Re-prompt once; if still empty, stop with a warning |
| User provides empty Freemium Token | Re-prompt once; if still empty, stop with a warning |
| Cannot write to credentials file | Report the permission error; suggest `chmod u+w ~/.42crunch/conf/env` or creating the directory manually |
