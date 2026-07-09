# Bundled scripts

Deterministic helpers the skills invoke instead of inlining code in the
reference docs. Each reads 42c-ast output (or an OAS file) and prints a compact
TOON summary; the script body never enters the model's context, only its
output does. All are pure Python 3 standard library (no pip installs) except
where noted.

## Invocation path

Scripts are addressed through the plugin-root environment variable so they
resolve regardless of the user's working directory (commands run from the
project git root, not the plugin):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py" <args>
```

`CLAUDE_PLUGIN_ROOT` is set by Claude Code. The copilot and codex ports use
their host's equivalent (`${GITHUB_PLUGIN_ROOT}` / the codex plugin root); the
script bodies are identical across all three repos.

## Scripts

| Script | Reads | Prints |
|--------|-------|--------|
| `oas_preview.py <oas>` | an OpenAPI file | title/version, auth schemes, per-operation id-refs (BOLA signals), BFLA markers, sample-data flags — the scan preview, without loading the OAS into context |
| `extract_audit.py [DIR] [--locations IDS]` | `DIR/todo.json` + `sqg.json` (default `/tmp/42c-audit`) | scores, per-issue-type TOON rows, SQG verdict, before/after score delta (via `DIR/.baseline.json`); `--locations` resolves issue occurrences to OAS paths |
| `extract_scan_happy.py [STATUS] [REPORT]` | happy-path run status + report | failing happy-path tests, or `happy_path_failures: none` |
| `extract_scan_summary.py [STATUS] [REPORT]` | full-scan status + report | sqgPass, blocking rules, request/issue totals, deduplicated failure list |
| `compare_auth_bodies.py [REPORT]` | full-scan report | owner-vs-attacker body comparison for each defective BOLA/BFLA finding (Step 12a-0 confirmation) |

## Judgment stays with the model

These scripts surface **facts and mechanical transforms only**. Candidacy
decisions (which id-ref is a real BOLA target), classification (A–D), fix
generation, and every consent gate remain the model's job — `oas_preview.py`
deliberately over-surfaces BOLA/BFLA signals (recall over precision) for the
model to filter and confirm with the user.

## Dependencies / limitations

- **YAML OpenAPI files**: `oas_preview.py` needs PyYAML for YAML specs. When it
  is absent the script exits 2 with a clear message and the caller falls back
  to reading the OAS directly. JSON specs (including every generated scanconf)
  need nothing beyond the standard library.
- **Windows without python3**: the reference docs point to
  `references/windows-commands.md` for a PowerShell fallback when python3 is not
  on PATH; otherwise these scripts run identically under Windows python3.
