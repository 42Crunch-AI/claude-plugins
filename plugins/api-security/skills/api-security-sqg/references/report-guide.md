# 42Crunch Report Field Reference

## audit run → report.json + todo.json

The binary writes two files side-by-side: `report.json` and `todo.json`. Both have the same issue structure. **Use `todo.json` for parsing** — it includes an `index[]` array that maps integer pointer values to human-readable OAS paths.

### Top-level fields (both files)

| Field | Description |
|---|---|
| `score` | Overall security score, float 0–100 |
| `issueCounter` | Total issue instances across all categories |
| `security` | Security-category issues (auth, transport, etc.) |
| `data` | Data-validation issues (schema constraints) |

### Issue structure

Issues are nested dicts, **not** flat arrays:

```
todo.json
├── index[]            ← OAS path list; pointer integers index into this
├── security
│   └── issues
│       └── <issueId>              ← e.g. "global-security"
│           ├── description        ← short description
│           ├── criticality        ← 0=info, 1=low, 2=medium, 3=high, 4=critical
│           └── issues[]           ← one entry per affected location
│               ├── pointer        ← integer → index[pointer] = OAS path string
│               ├── criticality
│               └── specificDescription
└── data
    └── issues
        └── <issueId>              ← e.g. "v3-schema-request-string-maxlength"
            └── (same structure)
```

### Parsing snippet (Python)

```python
import json

with open(f"{WORK_DIR}/todo.json") as f:
    d = json.load(f)

index = d.get("index", [])   # maps integer pointer → OAS path string
SEVERITY = {0: "INFO", 1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}

issues = []
for section in ["security", "data"]:
    for issue_id, issue_data in d.get(section, {}).get("issues", {}).items():
        crit = issue_data.get("criticality", 0)
        desc = issue_data.get("description", "")
        locations = issue_data.get("issues", [])
        pointers = [
            index[loc["pointer"]]
            for loc in locations
            if loc.get("pointer", -1) < len(index)
        ]
        issues.append({
            "id": issue_id,
            "severity": crit,
            "label": SEVERITY.get(crit, str(crit)),
            "description": desc,
            "count": len(locations),
            "pointers": pointers,
        })

issues.sort(key=lambda x: -x["severity"])
```

---

## v3-schema-* fix patterns

These issues live in the `data` section. The fix is always adding the missing constraint to the correct schema in the OAS. Use Phase 3 implementation context to choose the right value.

| Issue ID | Fix |
|---|---|
| `v3-schema-request-string-maxlength` | Add `"maxLength": <n>` to the string schema |
| `v3-schema-request-string-minlength` | Add `"minLength": <n>` to the string schema |
| `v3-schema-request-string-pattern` | Add `"pattern": "<regex>"` to the string schema |
| `v3-schema-request-numerical-max` | Add `"maximum": <n>` to the numeric schema |
| `v3-schema-request-numerical-min` | Add `"minimum": <n>` to the numeric schema |
| `v3-schema-request-numerical-format` | Add `"format": "int32"` or `"int64"` to the integer schema |
| `v3-schema-request-object-additionalproperties-true` | Add `"additionalProperties": false` to the object schema |
| `v3-schema-response-array-maxitems` | Add `"maxItems": <n>` to the array schema |
| `v3-schema-response-string-maxlength` | Add `"maxLength": <n>` to the string schema |
| `v3-schema-response-string-minlength` | Add `"minLength": <n>` to the string schema |
| `v3-schema-response-string-pattern` | Add `"pattern": "<regex>"` to the string schema |
| `v3-schema-response-object-additionalproperties-true` | Add `"additionalProperties": false` to the object schema |
| `v3-schema-response-array-items` | Add `"items": { ... }` schema to the array |

The `pointer` field in the issue locations tells you exactly which OAS path to fix (via `index[pointer]`).

---

## global-* fix patterns (KDB-backed)

These issues live in the `security` section. Look them up in the KDB at `https://platform.42crunch.com/kdb/audit-with-yaml.json` — **only fetch if at least one `global-*` issue exists**, as the KDB contains no `v3-schema-*` entries.

| Issue ID | Title | Fix Pattern |
|---|---|---|
| `global-http-clear` | API accepts HTTP | Add `https` to schemes, remove `http` |
| `global-security` | No global security | Add `security:` block + `securitySchemes:` to components |
| `global-security-scheme` | No security scheme | Add `securitySchemes:` under `components:` |
| `operation-security-empty` | Operation has empty security | Add security requirement or remove empty override |
| `schema-response-body-undefined` | Response body has no schema | Add `schema:` to response |
| `schema-request-body-undefined` | Request body has no schema | Add `schema:` to requestBody |
| `parameter-schema-undefined` | Parameter has no schema | Add `schema:` to the parameter |

---

## audit run → sqg.json (platform-authenticated runs only)

Written alongside `report.json` when `API_KEY` + `PLATFORM_HOST` + `--tag` are provided.

```json
{
  "acceptance": "yes" | "no",
  "date": "<unix timestamp string>",
  "reportType": "audit",
  "sqgs": ["<sqg-uuid>", ...],
  "processingDetails": [...],
  "sqgsDetail": [...]
}
```

### Key fields

| Field | Description |
|---|---|
| `acceptance` | `"yes"` = SQG passed; `"no"` = SQG failed |
| `processingDetails[]` | One entry per **failing** SQG (empty if all pass) |
| `processingDetails[].blockingSqgId` | UUID of the blocking SQG |
| `processingDetails[].blockingRules[]` | Human-readable strings per failing check |
| `sqgsDetail[].directives.minimumAssessmentScores` | `{ global, dataValidation, security }` thresholds |
| `sqgsDetail[].directives.issueRules[]` | Issue IDs that are forbidden (instant fail if present) |

### Blocking rule formats

```
"minimum audit score not reached: the audit sqg expects 80, got 33.17"
"minimum data validation score not reached: the audit sqg expects 45, got 3.17"
"forbidden issues found: v3-schema-request-string-pattern"
```

### Parsing `sqg.json`

```python
import json

sqg = json.load(open(f"{WORK_DIR}/sqg.json"))
sqg_passed = sqg["acceptance"] == "yes"
sqg_name = sqg["sqgsDetail"][0]["name"]
sqg_directives = sqg["sqgsDetail"][0]["directives"]

forbidden_ids = set(sqg_directives.get("issueRules", []))
min_scores = sqg_directives.get("minimumAssessmentScores", {})
# e.g. {"global": 80, "dataValidation": 45, "security": 15}

blocking_rules = []
for d in sqg.get("processingDetails", []):
    blocking_rules.extend(d.get("blockingRules", []))
```

---

## scan conf generate → scanconf.json

Scan configuration generated from the OAS. Contains:
- `version` — scan config schema version
- `authenticationDetails` — auth credentials per security scheme
- `operations` — per-operation test scenarios, expected responses, and fuzzing config

Detect auth mode by inspecting `authenticationDetails[0].<schemeName>.credentials.<firstKey>`:
- Has `"credential"` key (string `"{{varName}}"`) → **static token mode**
- Has `"requests"` key (array) → **dynamic login mode**

---

## scan run → scan-report.json

| Field | Description |
|---|---|
| `summary.state` | `"success"` or `"failed"` |
| `summary.operations` | `{ success, happyPathFailure, executed: { failed } }` counts |
| `summary.issues.total` / `.critical` / `.high` / `.medium` / `.low` | Issue counts by severity |
| `summary.issues.issueTypeCounters` | Dict: `{ conformanceTests, authorizationTests, methodNotAllowedTests }` → `{ issueType: count }` |
| `operations` | Dict keyed by operationId; each has `path`, `method`, `reason`, `authorizationRequestsResults[]` |

---

## scan run → SQG result (binary stdout ONLY)

**The SQG result is NOT written to `scan-report.json`.** It is embedded in the binary's stdout JSON when `API_KEY` + `PLATFORM_HOST` + `--tag` are provided.

```json
{
  "sqgPass": false,
  "sqgDetails": [
    {
      "blockingSqgId": "0b98cace-8440-46f5-bdc8-cbe4a2ab162d",
      "blockingRules": [
        "severity_threshold",
        "forbidden_test:authentication-swapping-bfla"
      ]
    }
  ],
  "statusCode": 0,
  "statusMessage": "success"
}
```

### Key fields

| Field | Description |
|---|---|
| `sqgPass` | `true` / `false` / absent (no SQG applied) |
| `sqgDetails[].blockingSqgId` | UUID of the blocking SQG |
| `sqgDetails[].blockingRules[]` | Reasons for failure |

### Blocking rule formats (scan)

```
"severity_threshold"                              ← high/critical issues exceed severity limit
"forbidden_test:authentication-swapping-bfla"    ← specific test key is forbidden
"forbidden_test:authentication-swapping-bola"
```

### Capturing and parsing scan SQG

```python
import json, subprocess

result = subprocess.run(
    [ast_bin, "scan", "run", ...],
    capture_output=True, text=True
)

cli_output = json.loads(result.stdout) if result.stdout.strip() else {}
scan_sqg_passed = cli_output.get("sqgPass")        # True / False / None
scan_sqg_details = cli_output.get("sqgDetails", [])

scan_blocking_rules = []
for d in scan_sqg_details:
    scan_blocking_rules.extend(d.get("blockingRules", []))
```

**Note:** `severity_threshold` is less verbose than audit blocking rules — it does not specify which category or what the threshold is. It means at least one test result has a severity that exceeds the SQG's severity limit. Fix by addressing all HIGH and CRITICAL issues in `scan-report.json`.
