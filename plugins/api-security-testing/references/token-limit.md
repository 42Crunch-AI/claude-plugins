# Token Plan Limit Reached

## Purpose

Handle the case where a token-plan credential has hit its usage limit
(`statusCode: 3` / `statusMessage: limits_reached` from a `42c-ast` call).
Every token plan surfaces the same status, and the token itself does not
reveal which plan it belongs to:

- **Starter (Free Trial)** — the 14-day trial has ended.
- **Individual / Individual Pro** — this month's Security Tokens (1,000 /
  3,000) are used up; the quota resets with the next monthly cycle.

Guide the user to upgrade — Individual or Individual Pro (stay on the same
token mechanism) or Team 10, Team 25, or Enterprise (switch to Platform mode
with an API key) — to wait for their monthly reset, or to postpone, and
persist whichever outcome occurs so future runs don't repeat a doomed call.

This doc is only ever reached as a sub-flow — from `pre-flight.md`'s sentinel
check, or reactively from `audit-workflow.md` / `scan-workflow.md` when a
command's status object reports the limit. It is never invoked directly by
the user.

---

## Step 1 — Mark the limit as reached

Ensure the sentinel file exists. This is idempotent — if `pre-flight.md`
routed here because the sentinel already existed, this is a no-op.

```bash
# macOS / Linux
mkdir -p "$HOME/.42crunch/conf"
touch "$HOME/.42crunch/conf/.token-limit"
```

```powershell
# Windows
New-Item -ItemType Directory -Force -Path "$env:APPDATA\42Crunch\conf" | Out-Null
New-Item -ItemType File -Force -Path "$env:APPDATA\42Crunch\conf\.token-limit" | Out-Null
```

---

## Step 2 — Announce and ask how to proceed

Announce:
> "Your 42Crunch token plan has reached its usage limit. On **Starter (Free
> Trial)** this means the 14-day trial has ended; on **Individual** or
> **Individual Pro** it means this month's Security Tokens are used up (the
> quota resets with your next monthly cycle)."

Call `AskUserQuestion`:
- **question**: `"How would you like to proceed?"`
- **options**: `["Upgrade my plan now", "I'm on Individual / Individual Pro — I'll wait for my monthly reset", "Not now — cancel"]`

**If "Not now — cancel"** → stop. The sentinel from Step 1 stays in place, so
the next time a skill runs, `pre-flight.md` routes straight back here without
attempting another doomed call.

**If "I'll wait for my monthly reset"** → clear the sentinel (both the current
and the legacy name), announce, and stop:

```bash
# macOS / Linux
rm -f "$HOME/.42crunch/conf/.token-limit" "$HOME/.42crunch/conf/.trial-expired"
```

```powershell
# Windows
Remove-Item "$env:APPDATA\42Crunch\conf\.token-limit","$env:APPDATA\42Crunch\conf\.trial-expired" -ErrorAction SilentlyContinue
```

> "Okay — run any skill again after your monthly reset and it will pick up
> normally. If the limit is still in effect, you'll land right back here."

**If "Upgrade my plan now"** → continue to Step 3.

---

## Step 3 — Point to pricing and wait

Show:

> Visit **[42Crunch Pricing](https://42crunch.com/pricing/)** to choose a plan:
> - **Individual** — 1,000 Security Tokens / month, same token-based setup you're using now.
> - **Individual Pro** — 3,000 Security Tokens / month, same token-based setup.
> - **Team 10** — unlimited Security Tokens for teams of up to 10. Uses a Platform account with an API key instead of a token.
> - **Team 25** — unlimited Security Tokens for teams of up to 25. Uses a Platform account with an API key instead of a token.
> - **Enterprise** — for teams and companies needing CI/CD integration, API Protection, and more. Uses a company Platform account with an API key instead of a token.
>
> Already on Individual and hitting the monthly cap regularly? Individual Pro
> or a Team plan removes the squeeze.
>
> Once you've upgraded, just say "continue" and I'll pick up right here.

**Stop — do not proceed.** Wait for the user to come back. Credential setup
is incomplete until they do.

---

## Step 4 — On resume, determine which credential type

What matters here is the credential mechanism, not the exact plan name —
Individual and Individual Pro issue a token, while Team 10, Team 25, and
Enterprise use a Platform account with an API key, so one question routes
to the right path:

Call `AskUserQuestion`:
- **question**: `"How do you access your new plan?"`
- **options**: `["I have a new access token (Individual or Individual Pro)", "I have a Platform API key (Team 10, Team 25, or Enterprise)"]`

### Path A — Token-based plans (Individual, Individual Pro)

Call `AskUserQuestion`:
- **question**: `"Please paste your new plan token (same format as your previous token):"`

Wait for input. Store value as `TRIAL_TOKEN`. Continue to Step 5.

### Path B — Platform plans (Team 10, Team 25, Enterprise)

Call `AskUserQuestion`:
- **question**: `"Please enter your Platform API Key (it usually starts with api_ or ide_):"`

Wait for input. Then call `AskUserQuestion`:
- **question**: `"Which region hosts your 42Crunch platform? (Your organisation's IT or security team can confirm this — it's also visible in the URL when you log in.)"`
- **options**: `["US — https://us.42crunch.cloud/", "EU — https://eu.42crunch.cloud/", "Other — I'll enter my platform URL manually"]`

- If **US** chosen: `PLATFORM_HOST=https://us.42crunch.cloud`
- If **EU** chosen: `PLATFORM_HOST=https://eu.42crunch.cloud`
- If **Other** chosen: call `AskUserQuestion` — **question**: `"Please enter your platform URL (e.g. https://your-org.42crunch.cloud):"` — store response as `PLATFORM_HOST`. Trim any trailing slashes.

Store values as `API_KEY` and `PLATFORM_HOST`. Continue to Step 5.

---

## Step 5 — Persist and verify

Follow `./credential-setup.md` **Step 3 (Write the Credentials File)** and
**Step 4 (Verify)** using the mode and value(s) collected above — do **not**
run that file's Step 1 or Step 2, mode and credentials are already known.

Step 3's full-overwrite behavior replaces the file with only the new mode's
keys, and its sentinel-clearing step removes the limit sentinel (both current
and legacy names) automatically — no separate cleanup needed here.

---

## Step 6 — Resume the original skill

Once Step 4 verification passes, briefly confirm the account is reconfigured,
then return control to the caller: resume `pre-flight.md` from **Step 3**
(Resolve the OAS File) onward — the same continuation pattern used when
`42crunch-setup` completes as a subroutine. Completing pre-flight this way
naturally carries the calling skill (audit/scan/pipeline) into its workflow
file fresh, so the operation that originally hit the limit gets retried
automatically with the new credentials — no separate "retry" step needed here.

---

## Error Handling

| Situation | Action |
|---|---|
| User provides empty token (any token-based plan) | Re-prompt once: "That didn't come through — please paste your new token again." If still empty, stop with: "I wasn't able to capture your token. Your plan limit remains in place — run the skill again whenever you're ready and I'll pick up from here." |
| User provides empty API Key | Re-prompt once: "It looks like the key didn't come through — please paste it again (it usually starts with `api_` or `ide_`)." If still empty, stop with: "I wasn't able to capture your API key. Your plan limit remains in place — run the skill again whenever you're ready." |
| User provides empty Platform URL (Other) | Re-prompt once: "I didn't catch the URL — please paste your platform address (it should look like `https://your-org.42crunch.cloud`)." If still empty, stop with the same message as above. |
