# 42Crunch Report File Reference

## todo.json (audit — written alongside report.json)

Prefer `todo.json` over `report.json` — it includes `index[]` which maps integer
pointer values to human-readable OAS paths.

```
todo.json
├── score          ← float 0–100
├── issueCounter   ← total issue instances
├── index[]        ← OAS path strings; pointer integers index into this
├── security
│   └── issues
│       └── <issueId>
│           ├── description        ← short string
│           ├── criticality        ← 0=INFO 1=LOW 2=MEDIUM 3=HIGH 4=CRITICAL
│           └── issues[]
│               ├── pointer        ← integer → index[pointer] = OAS path
│               ├── criticality
│               └── specificDescription
└── data
    └── issues
        └── <issueId>
            └── (same structure)
```

### Parsing snippet

```python
import json

d = json.load(open(f"{WORK_DIR}/todo.json"))
score = d.get("score", 0)
index = d.get("index", [])
SEVERITY = {0: "INFO", 1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}

issues = []
for section in ["security", "data"]:
    for issue_id, issue_data in d.get(section, {}).get("issues", {}).items():
        crit = issue_data.get("criticality", 0)
        locations = issue_data.get("issues", [])
        pointers = [index[loc["pointer"]] for loc in locations
                    if loc.get("pointer", -1) < len(index)]
        issues.append({
            "id": issue_id, "section": section,
            "severity": crit, "label": SEVERITY.get(crit, str(crit)),
            "description": issue_data.get("description", ""),
            "count": len(locations), "pointers": pointers,
        })
issues.sort(key=lambda x: -x["severity"])
```

---

## sqg.json (audit — written alongside report.json when API_KEY + PLATFORM_HOST + --tag are provided)

```json
{
  "acceptance": "yes" | "no",
  "date": "<unix timestamp>",
  "reportType": "audit",
  "sqgs": ["<sqg-uuid>"],
  "sqgsDetail": [
    {
      "name": "<SQG name>",
      "directives": {
        "minimumAssessmentScores": { "global": 80, "dataValidation": 45, "security": 15 },
        "issueRules": ["<forbidden-issue-id>", ...]
      }
    }
  ],
  "processingDetails": [
    {
      "blockingSqgId": "<uuid>",
      "blockingRules": [
        "minimum audit score not reached: the audit sqg expects 80, got 33.17",
        "minimum data validation score not reached: the audit sqg expects 45, got 3.17",
        "forbidden issues found: v3-schema-request-string-pattern"
      ]
    }
  ]
}
```

`processingDetails` is populated only when `acceptance == "no"`.

### Parsing snippet

```python
sqg = json.load(open(f"{WORK_DIR}/sqg.json"))
sqg_passed    = sqg["acceptance"] == "yes"
sqg_name      = sqg["sqgsDetail"][0]["name"]
forbidden_ids = set(sqg["sqgsDetail"][0]["directives"].get("issueRules", []))
min_scores    = sqg["sqgsDetail"][0]["directives"].get("minimumAssessmentScores", {})
blocking_rules = [r for d in sqg.get("processingDetails", [])
                    for r in d.get("blockingRules", [])]
```

### Blocking rule formats

```
"minimum audit score not reached: the audit sqg expects 80, got 33.17"
"minimum data validation score not reached: the audit sqg expects 45, got 3.17"
"minimum security score not reached: the audit sqg expects 15, got 0.0"
"forbidden issues found: v3-schema-request-string-pattern"
```

---

## scan-report.json

```
scan-report.json
├── summary                        ← aggregate counts only, NO per-op issues here
│   ├── state                      ← "success" | "failed"
│   ├── operations                 ← counts dict (summary.operations ≠ report.operations!)
│   │   ├── success
│   │   ├── failure
│   │   ├── happyPathFailure
│   │   └── executed.total / executed.success / executed.failed
│   └── issues
│       ├── total / critical / high / medium / low / info
│       └── issueTypeCounters
│           ├── conformanceTests     ← { issueType: count, ... }
│           ├── authorizationTests   ← { issueType: count, ... }
│           └── methodNotAllowedTests
└── operations                     ← dict keyed by operationId (NOT under summary!)
    └── <operationId>
        ├── path
        ├── method
        ├── fuzzed
        ├── summary                ← per-op counts (same shape as top-level summary)
        ├── scenarios[]            ← happy-path scenario results
        ├── conformanceRequestsResults[]   ← one entry per conformance test scenario
        │   ├── test
        │   │   ├── key            ← issue type, e.g. "schema-maxlength-scan"
        │   │   ├── description
        │   │   ├── httpStatusExpected[]
        │   │   └── action         ← "fuzz" | "omit" | etc.
        │   ├── outcome
        │   │   ├── testSuccessful ← FALSE means the server misbehaved (issue found!)
        │   │   ├── status         ← "correct" | "failure" | "defective"
        │   │   ├── conformant     ← bool
        │   │   └── criticality    ← 0=INFO 1=LOW 2=MEDIUM 3=HIGH 4=CRITICAL 5=BOLA/BFLA
        │   ├── request            ← details of the test request sent
        │   └── response           ← details of the server response
        └── authorizationRequestsResults[] ← one entry per auth test
            ├── test
            │   ├── key            ← "authentication-swapping-bola" | "authentication-swapping-bfla"
            │   └── httpStatusExpected[]
            └── outcome
                ├── testSuccessful ← FALSE means vulnerability found
                ├── status
                └── criticality
```

**Critical distinction:** `report["summary"]["operations"]` = aggregate counts.
`report["operations"]` = per-operationId dict with detailed test results. These are **not the same field**.

An issue is found when `outcome["testSuccessful"] == False`.

### Parsing snippet

```python
report = json.load(open(f"{WORK_DIR}/scan-report.json"))
summary = report.get("summary", {})
# Summary counts — for display
ops_summary = summary.get("operations", {})
issues_summary = summary.get("issues", {})
issue_type_counters = issues_summary.get("issueTypeCounters", {})

# Per-operation issue detail — for fixing
ops = report.get("operations", {})   # ← top-level, NOT summary.operations

sev_labels = {0: "INFO", 1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}

auth_issues = []
conf_issues = {}

for op_id, op_data in ops.items():
    if not isinstance(op_data, dict):
        continue
    method = op_data.get("method", "?").upper()
    path = op_data.get("path", "?")

    # Conformance issues: testSuccessful=False means the server accepted bad input
    for result in op_data.get("conformanceRequestsResults", []):
        outcome = result.get("outcome", {})
        if not outcome.get("testSuccessful", True):
            test_key = result.get("test", {}).get("key", "?")
            sev = outcome.get("criticality", 0)
            if test_key not in conf_issues:
                conf_issues[test_key] = {"count": 0, "sev": sev, "ops": []}
            conf_issues[test_key]["count"] += 1
            conf_issues[test_key]["ops"].append(f"{method} {path}")

    # Authorization issues: testSuccessful=False means vulnerability found
    auth_results = op_data.get("authorizationRequestsResults", [])
    if isinstance(auth_results, dict):
        auth_results = [auth_results]  # sometimes a single object, not list
    for result in (auth_results or []):
        outcome = result.get("outcome", {})
        if not outcome.get("testSuccessful", True):
            test_key = result.get("test", {}).get("key", "?")
            sev = outcome.get("criticality", 0)
            auth_issues.append({
                "op": f"{method} {path}", "op_id": op_id,
                "test": test_key, "sev": sev_labels.get(sev, str(sev))
            })
```

---

## Scan SQG — binary stdout ONLY (NOT in scan-report.json)

The SQG result for scan is never written to a file. It is embedded in the binary's
stdout JSON only when `API_KEY + PLATFORM_HOST + --tag` are provided.

**Always capture stdout explicitly:**

```python
import subprocess, json

result = subprocess.run([ast_bin, "scan", "run", ...], capture_output=True, text=True)
cli_output = json.loads(result.stdout) if result.stdout.strip() else {}
```

### Stdout JSON structure

```json
{
  "sqgPass": true | false,
  "sqgDetails": [
    {
      "blockingSqgId": "<uuid>",
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

`sqgPass` is absent (not `false`) when no SQG is applied to the tag.

### Parsing snippet

```python
scan_sqg_passed = cli_output.get("sqgPass")   # True / False / None
scan_blocking   = [r for d in cli_output.get("sqgDetails", [])
                     for r in d.get("blockingRules", [])]
```

### Scan blocking rule formats

```
"severity_threshold"                          ← high/critical results exceed SQG severity limit
"forbidden_test:authentication-swapping-bfla" ← specific test type forbidden by SQG
"forbidden_test:authentication-swapping-bola"
```

`severity_threshold` does not indicate which category — fix all HIGH and CRITICAL issues
in `scan-report.json` to address it.
