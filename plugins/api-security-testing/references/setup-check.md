# Setup Check

Run this as the first step of any 42Crunch skill. Complete both sections before proceeding.

---

## A. Binary Version Check (always runs)

Resolve the canonical binary path for the current OS:
- macOS/Linux: `$HOME/.42crunch/bin/42c-ast`
- Windows: `$env:APPDATA\42Crunch\bin\42c-ast.exe`

Before running any check, announce:
> "Checking for `42c-ast`..."

Check if the binary exists:
- **Missing** → announce `"The 42c-ast binary isn't installed yet — running setup now."` then invoke `42crunch-setup` for full setup. Do not proceed if setup fails.
- **Present** → run silently:
  1. Get installed version: `"$BINARY_PATH" --version`
  2. Announce: `"Checking for updates to 42c-ast..."` then fetch the manifest:
     `curl -fsSL https://repo.42crunch.com/downloads/42c-ast-manifest.json`
     The manifest is a **JSON array**. Filter entries by the current platform
     `architecture` key (e.g. `darwin-arm64`, `linux-amd64`, `windows-amd64` —
     see `skills/42crunch-setup/references/binary-setup.md` Step 1 for the full mapping table).
     Read the `version` field from the matching entry — this is `LATEST_VERSION`.
     If no entry matches the current platform, skip the update check and proceed.
  3. Compare the installed version string to `LATEST_VERSION` for the current platform.
  4. **Outdated** → silently download and replace the binary using the same
     install steps as `42crunch-setup` (download → SHA-256 verify → chmod +x).
     Inform the user: `42c-ast updated from v<old> to v<new>.`
  5. **Up to date** → proceed silently.
  6. **Manifest fetch fails** → announce: `"Could not reach the update server to check for a newer version — continuing with installed 42c-ast v<version>. Run 42crunch-setup to retry later."` then continue.

---

## B. Credentials Check (runs after binary is confirmed)

Read `~/.42crunch/conf/env` (macOS/Linux) or `%APPDATA%\42Crunch\conf\env` (Windows):

```bash
grep -E "^(FREEMIUM_TOKEN|API_KEY)=" "$HOME/.42crunch/conf/env" 2>/dev/null
```

- **`FREEMIUM_TOKEN`** is set → **Freemium mode**. Use
  `--freemium-host stateless.42crunch.com:443` and `--token <FREEMIUM_TOKEN>`
  in all commands. Proceed silently.
- **`API_KEY`** starts with `api_` or `ide_` → **Platform mode**. Read
  `PLATFORM_HOST` from the same file (required — run `42crunch-setup` to
  reconfigure if missing). Proceed silently.
- **Neither found** → call `AskUserQuestion`:
  - **question**: `"I don't see any 42Crunch credentials configured yet. I can walk you through setup now, or you can run 42crunch-setup manually when you're ready."`
  - **options**: `["Set up now", "Cancel — I'll run 42crunch-setup manually"]`
  - If **Set up now** → invoke `42crunch-setup` (full setup). Do not proceed if setup fails.
  - If **Cancel** → stop.
