# 42Crunch Plugin for Claude Code

Automate API security directly in your Claude Code workflow. This plugin brings 42Crunch's audit, scan, and remediation capabilities into the Claude Code agent as a set of AI-driven skills — giving you a continuous **audit → scan → remediate → validate** security loop without leaving your IDE.

## Overview

This repository is a **Claude Code plugin marketplace** that registers the `api-security-automation` plugin. The plugin delivers skills that Claude can invoke by natural language, covering everything from generating an OpenAPI spec to running live audits and conformance scans against a running API.

```
.claude-plugin/
  marketplace.json              # Plugin registry manifest
plugins/
  api-security/
    .claude-plugin/
      plugin.json               # Plugin metadata
    skills/
      setup/                    # Install & configure the 42c-ast binary
      42crunch-audit/           # Static OAS security audit
      42crunch-scan/            # Live conformance & authorization scan
      42crunch-v2/              # Combined audit + scan pipeline
      code-to-oas/              # Generate an OAS from source code
      oas-to-arazzo/            # Generate an Arazzo workflow spec from an OAS
```

## Skills

### `setup` — Install the 42Crunch AST Binary
Detects your OS and architecture, downloads the latest `42c-ast` binary from the 42Crunch release server, verifies its SHA-256 checksum, and writes your credentials to `~/.42crunch/conf/env`.

**Trigger phrases:** "set up 42crunch", "install 42c-ast", "configure AST binary"

---

### `42crunch-audit` — Static OAS Security Audit
Runs a static analysis of an OpenAPI Specification file and produces a scored report (0–100). Findings are classified into three tiers:

- **SQG-Blocking** (red) — must fix to pass the Security Quality Gate
- **Security** (orange) — recommended fixes
- **Data Validation** (yellow) — informational

After presenting findings, Claude asks for your explicit consent before applying any fixes. It then re-runs the audit to confirm passage.

**Trigger phrases:** "run audit", "42crunch audit", "fix audit issues", "SQG audit"

---

### `42crunch-scan` — Live Conformance & Authorization Scan
Runs a live test against a running API server. Generates or validates a `scanconf.json` configuration, automatically identifies BOLA and BFLA candidates, builds dependency chains for operations that require IDs from prior calls, and runs a full fuzzing scan. Reports authorization failures and conformance issues, then offers to apply code fixes after consent.

**Trigger phrases:** "run scan", "conformance test", "BOLA test", "BFLA test", "scan config"

---

### `42crunch-v2` — Full Audit + Scan Pipeline
Orchestrates the Audit and Scan skills in sequence as Phase 1 and Phase 2. Each phase requires separate user consent. Produces a combined summary at the end.

**Trigger phrases:** "run audit and scan", "full 42crunch pipeline", "SQG"

---

### `code-to-oas` — Generate an OpenAPI Spec from Source Code
Analyzes your API codebase (read-only) and produces a complete `openapi.json`. Supports all major frameworks including Express, FastAPI, Flask, Django, NestJS, Spring Boot, Gin, Echo, Chi, Rails, Sinatra, and .NET. Detects routes, parameters, request/response schemas, auth middleware, data models, and server config. Performs a self-review pass before writing the file.

**Trigger phrases:** "generate OAS from code", "create OpenAPI spec", "document my API"

---

### `oas-to-arazzo` — Generate an Arazzo Workflow Spec
Reads an existing OAS file and produces an `arazzo.yaml` alongside it. Identifies logical workflows (auth flows, CRUD lifecycles, search-then-act patterns) and wires step outputs to inputs using Arazzo expressions.

**Trigger phrases:** "generate Arazzo", "create workflow spec", "OAS to Arazzo"

---

## Prerequisites

- [Claude Code](https://claude.ai/code) (CLI, desktop app, or IDE extension)
- A 42Crunch account — either a **freemium token** (Base64) or a **platform token** (`api_*` / `ide_*`)
- For the `42crunch-scan` skill: a running API server reachable at the URL in `servers[0]` of your OAS (or via the `SCAN42C_HOST` env variable)

The `42c-ast` binary is installed automatically by the `setup` skill if not already present. It is also bundled by the 42Crunch IDE extension for VS Code, IntelliJ, Eclipse, Cursor, and Windsurf.

## Configuration

Credentials are resolved in this order: environment variables → `.env` file (walked upward from the OAS file to repo root).

| Variable | Description | Default |
|---|---|---|
| `API_KEY` | Auth token. Prefix determines mode: `api_*` = Platform API, `ide_*` = Platform IDE, Base64 = Freemium | Required |
| `PLATFORM_HOST` | 42Crunch platform base URL | `https://demolabs.42crunch.cloud` |
| `SCAN42C_HOST` | Scan target base URL (overrides `servers[0]` in OAS) | — |

Credentials are never written to disk except in `~/.42crunch/conf/env` (file permissions `600` on macOS/Linux).

## Getting Started

1. **Install the plugin** — point Claude Code at this marketplace repository.
2. **Run setup** — ask Claude: *"set up 42crunch"*. Claude will download and configure the `42c-ast` binary.
3. **Audit your API** — ask Claude: *"run a 42Crunch audit on my OpenAPI spec"*.
4. **Fix issues** — Claude presents findings and asks your consent before applying any changes.
5. **Scan your API** — ask Claude: *"run a conformance scan"* against your running server.

## License

MIT — see [LICENSE](LICENSE) for details.

## Links

- [42Crunch Documentation](https://docs.42crunch.com)
- [42Crunch on GitHub](https://github.com/42Crunch)
- Support: support@42crunch.com
