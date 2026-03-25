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
