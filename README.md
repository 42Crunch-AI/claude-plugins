# 42Crunch API Security Plugin for Claude Code

Automate API security directly in Claude Code with 42Crunch - automatically audit OpenAPI specs, detect vulnerabilities aligned with OWASP API Security risks (including BOLA/BFLA), and apply AI-powered fixes. Designed for AI-assisted development workflows, it provides continuous guardrails through an **audit->scan->remediate->validate** loop, ensuring APIs meet enterprise security standards before deployment.

## Overview

This repository is a **Claude Code plugin marketplace** that registers the `api-security-testing` plugin. The plugin delivers skills that Claude can invoke by natural language, covering everything from generating an OpenAPI spec to running live audits and conformance scans against a running API.

```
.claude-plugin/
  marketplace.json              # Plugin registry manifest
plugins/
  api-security-testing/
    .claude-plugin/
      plugin.json               # Plugin metadata
    skills/
      42crunch-setup/           # Install, configure, and credential setup
      42crunch-audit/           # Static OAS security audit
      42crunch-scan/            # Live conformance & authorization scan
      42crunch-api-security-testing/  # Combined audit + scan pipeline
      code-to-oas/              # Generate an OAS from source code
```

## Skills

### `42crunch-setup` — Install & Configure 42Crunch

Prepares the environment in two phases:

1. **Binary setup** — detects your OS and architecture, downloads the latest `42c-ast` binary from the 42Crunch release server, verifies its SHA-256 checksum, and installs it to the canonical path (`~/.42crunch/bin/` on macOS/Linux, `%APPDATA%\42Crunch\bin\` on Windows).
2. **Credential setup** — walks you through a guided flow:
   - Existing 42Crunch user → enter API Key + select Platform URL (US / EU / custom)
   - Registered Freemium user → enter Freemium Token
   - New user → shows registration link and stops

Credentials are stored in `~/.42crunch/conf/env` (file permissions `600` on macOS/Linux). If credentials are already present, shows the mode and masked key with an option to keep or replace.

**Trigger phrases:** "set up 42crunch", "configure 42crunch", "install 42c-ast", "update 42c-ast", "set api key", "42crunch not working", "binary not found"

---

### `42crunch-audit` — Static OAS Security Audit

Runs a static analysis of an OpenAPI Specification file and produces a scored report (0–100). Verifies the environment first — silently confirms the `42c-ast` binary is installed and up to date (auto-updating if needed) and that credentials are configured, invoking `42crunch-setup` automatically if either is missing — then resolves the OAS file to analyse.

Findings are classified into three tiers:

- **SQG-Blocking** (red) — must fix to pass the Security Quality Gate
- **Security** (orange) — recommended fixes
- **Data Validation** (yellow) — informational

After presenting findings, Claude asks for your explicit consent before applying any fixes. It then re-runs the audit to confirm passage.

**Platform mode:** SQG is enforced from the platform policy. Tag detection runs silently to locate the API collection.

**Freemium mode:** No automated SQG gate. After the audit runs, Claude asks you to set a target score and blocking severity for the session. No tag detection.

If no OAS file is open or provided, Claude offers to generate one from your source code using the `code-to-oas` skill before continuing.

**Trigger phrases:** "run audit", "audit only", "42crunch audit", "fix audit issues", "SQG audit", "audit score"

---

### `42crunch-scan` — Live Conformance & Authorization Scan

Runs a live test against a running API server. Verifies the environment first (binary + credentials), resolves the OAS file, then confirms the scan target URL — prompting you if the `servers[0].url` value needs adjusting — and immediately checks reachability before any configuration begins.

Once the target is confirmed, Claude performs a quick OAS analysis (operation count, auth schemes, BOLA candidates, sample data presence) and presents a scan preview before asking for permission to configure the scan. Configuration collects credentials, identifies BOLA/BFLA candidates, asks whether to use OAS sample data or a Postman collection for test data, classifies every operation (Standalone / Dependency / Manual-data / Throwaway-user), and builds scenario chains. A happy path validation run follows; after all happy paths pass Claude asks for explicit consent before running the full fuzzing scan.

Findings are classified into three tiers:

- **Authorization failures** (red) — BOLA/BFLA confirmed; always a fix candidate
- **SQG-Blocking conformance** (orange) — must fix to pass the Security Quality Gate
- **Informational conformance** (yellow) — surfaced for review; not auto-fixed

Claude asks for your consent before applying any fixes — both OAS contract updates and server-side code changes.

**Platform mode:** SQG is enforced from the platform policy.

**Freemium mode:** No SQG enforcement for scan. All findings are presented informally; the user decides which to fix.

If no OAS file is open or provided, Claude offers to generate one from your source code using the `code-to-oas` skill before continuing.

**Trigger phrases:** "run scan", "scan only", "conformance test", "BOLA test", "BFLA test", "42crunch scan", "scan config"

---

### `42crunch-api-security-testing` — Full Audit + Scan Pipeline

Orchestrates the Audit and Scan skills in sequence as Phase 1 and Phase 2. Verifies the environment (binary + credentials), resolves the OAS file, and confirms the scan target URL with a reachability check — all before Phase 1 begins. Each phase requires separate user consent. Before Phase 2, Claude runs a silent OAS analysis and presents a scan configuration preview (target URL, operation count, auth schemes, BOLA candidates, sample data availability) so you know exactly what the scan setup will involve. Produces a combined summary at the end covering both phases.

**Trigger phrases:** "run audit and scan", "full 42crunch pipeline", "full security check", "audit then scan", "42crunch", "SQG"

---

### `code-to-oas` — Generate an OpenAPI Spec from Source Code

Analyzes your API codebase (read-only) and produces a complete `openapi.json`. Supports all major frameworks including Express, Fastify, Koa, Hapi, NestJS, FastAPI, Flask, Django, Starlette, Spring Boot, Quarkus, Micronaut, Gin, Echo, Chi, Gorilla/mux, Rails, Sinatra, Grape, ASP.NET Core, and more. Detects routes, parameters, request/response schemas, auth middleware, data models, and server config. Performs a self-review pass before writing the file.

**Trigger phrases:** "generate OAS from code", "create OpenAPI spec", "document my API", "reverse-engineer spec", "write openapi.json from my codebase"

---

## Prerequisites

- [Claude Code](https://claude.ai/code) (CLI, desktop app, or IDE extension)
- A 42Crunch account — either a **freemium token** or a **platform API key** (`api_*` / `ide_*`)
- For the `42crunch-scan` skill: a running API server reachable at the URL in `servers[0]` of your OAS (or via the `SCAN42C_HOST` env variable)

The `42c-ast` binary is installed and kept up to date automatically. It is also bundled by the 42Crunch IDE extension for VS Code, Cursor, and Windsurf.

## Configuration

Credentials are read exclusively from `~/.42crunch/conf/env` (macOS/Linux) or `%APPDATA%\42Crunch\conf\env` (Windows), written by `42crunch-setup`.

| Variable | Description | Mode |
|---|---|---|
| `API_KEY` | Platform token — `api_*` (API) or `ide_*` (IDE) | Platform |
| `PLATFORM_HOST` | 42Crunch platform base URL | Platform |
| `FREEMIUM_TOKEN` | Freemium token (Base64), passed as `--token` | Freemium |
| `SCAN42C_HOST` | Scan target base URL (overrides `servers[0]` in OAS) | Both |

Credentials are never printed in plaintext after entry. The env file is stored with `600` permissions on macOS/Linux.

## Installation

### 1. Add the marketplace

Run the following command inside Claude Code (CLI, desktop app, or IDE extension):

```
/plugin marketplace add 42crunch-AI/claude-plugin
```

This registers the 42Crunch marketplace from GitHub. Claude Code fetches the marketplace manifest and makes the `api-security-testing` plugin available for installation.

### 2. Install the plugin

```
/plugin install api-security-testing@42crunch-marketplace
```

The plugin installs to your user scope by default (`~/.claude/settings.json`), making it available across all your projects. To install at project scope instead (committed to `.claude/settings.json` and shared with your team):

```
/plugin install api-security-testing@42crunch-marketplace --scope project
```

### 3. Verify

```
/plugin list
```

You should see `api-security-testing` listed as installed.

---

## Getting Started

1. **Run setup** — ask Claude: *"set up 42crunch"*. Claude will install the `42c-ast` binary and walk you through credential configuration.
2. **Audit your API** — ask Claude: *"run a 42Crunch audit on my OpenAPI spec"*. If you don't have an OAS file yet, Claude will offer to generate one from your source code first.
3. **Fix issues** — Claude presents findings and asks your consent before applying any changes.
4. **Scan your API** — ask Claude: *"run a conformance scan"* against your running server.

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.

## Links

- [42Crunch Documentation](https://docs.42crunch.com)
- [42Crunch on GitHub](https://github.com/42Crunch)
- Support: support@42crunch.com
