# api-security-testing

AI-powered API security for Claude Code, backed by 42Crunch — audit OpenAPI specs, detect OWASP API Security vulnerabilities, run live conformance and authorization scans, and apply fixes, all through natural language.

## What you get

- **42crunch-setup** — Install the `42c-ast` binary and configure credentials (one-time)
- **42crunch-audit** — Static security audit of an OpenAPI Specification file with scored findings and AI-assisted fixes
- **42crunch-scan** — Live conformance and authorization scan (BOLA/BFLA) against a running API
- **42crunch-api-security-testing** — Full audit + scan pipeline in a single session
- **code-to-oas** — Generate a complete `openapi.json` from your API source code

## Prerequisites

- [Claude Code](https://claude.ai/code) (CLI, desktop app, or IDE extension)
- A 42Crunch account — [freemium](https://42crunch.com/freemium/) or paid (Platform API key)
- For `42crunch-scan`: a running API server reachable at the URL in `servers[0]` of your OAS (or via `SCAN42C_HOST`)

The `42c-ast` binary is downloaded and kept up to date automatically on first use.

## Getting Started

1. **Install the plugin** — add this marketplace to Claude Code.
2. **Set up the environment** — say: *"set up 42crunch"*
3. **Audit your API** — say: *"run a 42Crunch audit"* (Claude will offer to generate an OAS from source code if you don't have one)
4. **Fix issues** — Claude presents findings by severity and asks your consent before changing anything
5. **Scan your API** — say: *"run a conformance scan"* against your running server

## Skills

### `42crunch-setup`

Installs the `42c-ast` binary for your OS/architecture, verifies its checksum, and walks you through credential configuration. Supports Platform (API key) and Freemium (token) modes. Credentials are stored in `~/.42crunch/conf/env` with `600` permissions.

> **Trigger:** "set up 42crunch", "configure 42crunch", "install 42c-ast", "update 42c-ast", "set api key", "42crunch not working", "binary not found"

---

### `42crunch-audit`

Runs a static analysis of an OpenAPI Specification and produces a 0–100 security score. Findings are classified into three tiers:

- **SQG-Blocking** — must fix to pass the Security Quality Gate
- **Security** — recommended fixes
- **Data Validation** — informational

Claude asks your explicit consent before applying any changes, then re-runs the audit to confirm passage.

**Platform mode:** SQG threshold enforced from your platform policy.  
**Freemium mode:** No automated SQG gate; you set the target score and blocking severity for the session.

> **Trigger:** "run audit", "42crunch audit", "fix audit issues", "SQG audit", "audit score"

---

### `42crunch-scan`

Runs a live conformance and authorization test against a running API server. Claude confirms the target URL, checks reachability, analyses the OAS (operations, auth schemes, BOLA candidates), and presents a scan preview before any configuration begins. After a happy-path validation run, Claude asks your consent before starting the full fuzzing scan.

Findings are classified into three tiers:

- **Authorization failures** — BOLA/BFLA confirmed
- **SQG-Blocking conformance** — must fix to pass the Security Quality Gate
- **Informational conformance** — surfaced for review

Claude asks your consent before applying any fixes — both OAS contract updates and server-side code changes.

**Platform mode:** SQG enforced from platform policy.  
**Freemium mode:** All findings presented informally; you decide what to fix.

> **Trigger:** "run scan", "scan only", "conformance test", "BOLA test", "BFLA test", "42crunch scan", "scan config"

---

### `42crunch-api-security-testing`

Orchestrates Audit (Phase 1) and Scan (Phase 2) in sequence. Resolves the OAS file and confirms the scan target URL up front. Each phase requires separate user consent. Produces a combined summary covering both phases.

> **Trigger:** "run audit and scan", "full 42crunch pipeline", "full security check", "audit then scan", "SQG"

---

### `code-to-oas`

Analyses your API codebase and generates a complete `openapi.json`. Detects routes, parameters, request/response schemas, auth middleware, data models, and server config. Performs a self-review pass before writing the file.

Supported frameworks: Express, Fastify, Koa, Hapi, NestJS, FastAPI, Flask, Django, Starlette, Spring Boot, Quarkus, Micronaut, Gin, Echo, Chi, Gorilla/mux, Rails, Sinatra, Grape, ASP.NET Core, and more.

> **Trigger:** "generate OAS from code", "create OpenAPI spec", "document my API", "reverse-engineer spec", "write openapi.json from my codebase"

---

## Configuration

Credentials are read from `~/.42crunch/conf/env` (macOS/Linux) or `%APPDATA%\42Crunch\conf\env` (Windows), written by `42crunch-setup`. Never edit this file manually while a skill is running.

| Variable | Description | Mode |
|---|---|---|
| `API_KEY` | Platform token (`api_*` or `ide_*`) | Platform |
| `PLATFORM_HOST` | 42Crunch platform base URL (e.g. `https://us.42crunch.cloud`) | Platform |
| `FREEMIUM_TOKEN` | Freemium token (Base64) | Freemium |
| `SCAN42C_HOST` | Override scan target URL (overrides `servers[0]` in OAS) | Both |

Credentials are never printed in plaintext after entry.

## Links

- [42Crunch Documentation](https://docs.42crunch.com)
- [42Crunch on GitHub](https://github.com/42Crunch)
- Support: support@42crunch.com

## License

Apache 2.0
