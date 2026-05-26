# 42Crunch Claude Plugins

The official [42Crunch](https://www.42crunch.com) plugin marketplace for Claude Code — a catalog of AI-powered plugins that bring 42Crunch's API security capabilities directly into your Claude Code workflow.

42Crunch plugins give Claude the ability to audit OpenAPI specs, scan live APIs for vulnerabilities, and apply fixes to ensure APIs meet security guardrails.

## Structure

```
.claude-plugin/
  marketplace.json              # Plugin registry manifest
plugins/                        # Claude plugins developed by 42Crunch
  api-security-testing/
    .claude-plugin/
      plugin.json               # Plugin metadata
    skills/                     # Skill definitions
    references/                 # Reference definitions
    README.md                   # Documentation
    LICENSE                     # License
```

## Prerequisites

The [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code/getting-started) is required to add marketplaces and install plugins using the `claude` CLI commands below.

## Adding this Marketplace

Register the 42Crunch marketplace with Claude Code once, then install the plugin from it:

```
claude plugin marketplace add https://github.com/42Crunch-AI/claude-plugins
```

Or from an interactive Claude Code session:

```
/plugin marketplace add https://github.com/42Crunch-AI/claude-plugins
```

## Available Plugins

### [api-security-testing](./plugins/api-security-testing/)

AI-powered API security plugin backed by 42Crunch. Audit OpenAPI specs, detect OWASP API Security vulnerabilities (including BOLA/BFLA), run live conformance and authorization scans against running APIs, and apply AI-assisted fixes — all through natural language.

**Install:**
After registering the marketplace (see above), install the plugin:

```
claude plugin install api-security-testing@42crunch-marketplace
```

Or from an interactive Claude Code session:

```
/plugin install api-security-testing@42crunch-marketplace
```

See the [plugin README](./plugins/api-security-testing/README.md) for full documentation.


## Links

- [42Crunch](https://42crunch.com/)
- [42Crunch Documentation](https://docs.42crunch.com)
- [42Crunch on GitHub](https://github.com/42Crunch)
- Support: support@42crunch.com
