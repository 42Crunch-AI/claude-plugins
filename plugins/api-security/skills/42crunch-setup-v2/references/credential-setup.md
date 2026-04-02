# Credential Setup Reference

Follow this procedure to configure the API key used by all 42Crunch skills.
All detection steps run silently — surface output only on failure or user prompts.

---

## Step 1 — Check for Existing Credentials

Before asking the user for anything, silently scan for an existing `API_KEY`.

**Check environment variable:**
```bash
[ -n "$API_KEY" ] && echo "found in environment"
```

**Walk upward from the current directory, checking `.env` files, stopping at the repo root:**
```bash
dir="$PWD"
while [ "$dir" != "/" ]; do
  [ -f "$dir/.env" ] && grep -q "^API_KEY=" "$dir/.env" && echo "$dir/.env" && break
  dir="$(dirname "$dir")"
done
```

**Check global location:**
```bash
# macOS / Linux
grep "^API_KEY=" "$HOME/.42crunch/conf/env" 2>/dev/null

# fallback global location
grep "^API_KEY=" "$HOME/.42crunch/.env" 2>/dev/null
```

**If an `API_KEY` is found:**

Detect mode:
- Starts with `api_` or `ide_` → **Platform mode**
- Otherwise → **Freemium mode**

Inform the user (masking the key):
> An API key is already configured (`<masked-key>`) in `<source>` — running in
> **<mode>** mode.
>
> Would you like to keep the existing key or replace it with a new one?

If keeping → **credential setup complete.**
If replacing → continue to Step 2.

---

## Step 2 — Request the API Key

Present this to the user:

> Please enter your 42Crunch API key. The key type determines which mode the
> tools run in:
>
> | Prefix    | Type                  | Mode           |
> |-----------|-----------------------|----------------|
> | `api_…`   | Platform API token    | Platform mode  |
> | `ide_…`   | Platform IDE token    | Platform mode  |
> | *(other)* | Freemium Base64 token | Freemium mode  |
>
> You can find your key in the 42Crunch Platform under **Settings → API Tokens**,
> or use the token from the IDE extension settings for IDE tokens.

Wait for the user to paste the key.

---

## Step 3 — Detect Mode and Collect Platform Host

Inspect the key prefix:

**`api_` or `ide_` → Platform mode.**
Ask:
> What is your 42Crunch Platform URL?
> (Press Enter to use the default: `https://demolabs.42crunch.cloud`)

Store the answer as `PLATFORM_HOST`. If empty, default to `https://demolabs.42crunch.cloud`.
Trim any trailing slashes.

**Anything else → Freemium mode.** No host prompt needed.

---

## Step 4 — Choose Storage Location

Ask the user where to store the credentials:

> Where should the API key be saved?
>
> **Option A — Project `.env`** (`./.env` in the current working directory)
> Good for per-project configuration. Make sure `.env` is in `.gitignore`.
>
> **Option B — Global config** (`~/.42crunch/conf/env`)
> Good for personal workstations where all projects share the same credentials.

---

## Step 5 — Write the Credentials File

### Option A — Project `.env`

Write or append to `./.env`:

```
API_KEY=<value>
PLATFORM_HOST=<value>   # omit for freemium mode
```

Do not quote values. Do not add spaces around `=`.

Check whether `.env` is already in `.gitignore`:
```bash
grep -qE '^\.env$|^\.env\b' .gitignore 2>/dev/null || echo "not ignored"
```

If not ignored (and a git repo exists), remind the user:
> Add `.env` to your `.gitignore` to prevent accidentally committing your API key.

### Option B — Global config (`~/.42crunch/conf/env`)

Create the directory if needed:
```bash
mkdir -p "$HOME/.42crunch/conf"
```

Write the file:
```
PLATFORM_HOST=<value>   # omit for freemium mode
API_KEY=<value>
```

**Windows (PowerShell):**
```powershell
New-Item -ItemType Directory -Force -Path "$env:APPDATA\42Crunch\conf" | Out-Null
@"
PLATFORM_HOST=<value>
API_KEY=<value>
"@ | Set-Content -Path "$env:APPDATA\42Crunch\conf\env" -Encoding UTF8
```

**Set restrictive permissions on the file to protect the token:**
```bash
# macOS / Linux only
chmod 600 "$HOME/.42crunch/conf/env"
```
Skip on Windows — `APPDATA` is already protected by Windows ACLs.

---

## Step 6 — Verify

Re-read the file and confirm `API_KEY` is present:
```bash
grep "^API_KEY=" <chosen-file>
```

Display confirmation with the key **masked** (`prefix_••••••••` for platform
tokens, `••••••••` for freemium):

**Platform mode:**
> API key saved to `<path>`.
> Mode: **Platform** | Key: `api_••••••••` | Host: `https://demolabs.42crunch.cloud`

**Freemium mode:**
> API key saved to `<path>`.
> Mode: **Freemium** | Key: `••••••••`

---

## Error Handling

| Situation | Action |
|---|---|
| User provides empty API key | Re-prompt once; if still empty, stop with a warning that binary is installed but not activated |
| User provides empty Platform URL | Use the default `https://demolabs.42crunch.cloud` |
| Cannot write to credentials file | Report the permission error; suggest running with elevated privileges or choosing the other storage option |
