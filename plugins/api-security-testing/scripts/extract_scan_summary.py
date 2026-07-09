#!/usr/bin/env python3
"""Extract a compact TOON summary from a full 42c-ast scan run.

Usage:
    python3 extract_scan_summary.py [STATUS_FILE] [REPORT_FILE]

Defaults: /tmp/42c-scan-status.json /tmp/42c-scan-report.json
(the files written by `scan run --output REPORT_FILE ... > STATUS_FILE`).

Prints: sqgPass verdict, blocking rules, request/issue totals, and the
deduplicated failure list (operation, test key, severity).

Verdict rule (non-obvious): the engine's verdict is outcome.status —
"correct" means the API behaved correctly (e.g. enforced 401/403 on an
authorization swap, or accepted a partial-security scenario).
outcome.testSuccessful is NOT a reliable discriminator — it is false even for
correctly-enforced endpoints, so filtering on it alone reports secured
endpoints as failures. Any entry marked "correct" is skipped.

SQG field location (common mistake): sqgPass is a boolean at the ROOT of the
status object — not nested inside the report, and not under an "sqg" key.
"""
import json
import sys

SEVERITY = {5: "critical", 4: "high", 3: "medium", 2: "low", 1: "info", 0: "info"}

def main():
    status_file = sys.argv[1] if len(sys.argv) > 1 else "/tmp/42c-scan-status.json"
    report_file = sys.argv[2] if len(sys.argv) > 2 else "/tmp/42c-scan-report.json"

    with open(status_file) as f:
        status = json.load(f)
    if status.get("statusCode") != 0:
        print(f"scan_error: statusCode={status.get('statusCode')} {status.get('statusMessage', '')}")
        return

    # Reconstruct the combined shape from the clean status + report files
    with open(report_file) as f:
        data = {**status, "report": json.load(f)}
    report = data.get("report", {})
    summary = report.get("summary", {})

    sqg = "PASSED" if data.get("sqgPass") else ("FAILED" if "sqgPass" in data else "N/A")
    print(f"sqgPass: {sqg}")
    for d in data.get("sqgDetails", []):
        rules = d.get("blockingRules", [])
        if rules:
            print(f"blockingRules[{len(rules)}]: {', '.join(rules)}")

    auth_total = (((summary.get("authorizationTestRequests") or {}).get("executed") or {}).get("total"))
    issue_total = (summary.get("issues") or {}).get("total")
    if auth_total is not None:
        print(f"authorizationRequests: {auth_total}")
    if issue_total is not None:
        print(f"issuesTotal: {issue_total}")

    failures = []
    operations = report.get("operations") or {}
    if isinstance(operations, dict):
        for operation_id, operation in operations.items():
            for section in ("authorizationRequestsResults", "conformanceRequestsResults",
                            "customRequestsResults"):
                for entry in operation.get(section, []) or []:
                    outcome = entry.get("outcome") or {}
                    if outcome.get("testSuccessful") is True or outcome.get("status") == "correct":
                        continue
                    test = entry.get("test") or {}
                    failures.append((operation_id, test.get("key", "?"),
                                     SEVERITY.get(outcome.get("criticality"), "")))

    if not failures:
        # Legacy report shape fallback
        legacy = data.get("results", data.get("scanResults", []))
        if isinstance(legacy, dict):
            legacy = [legacy]
        for result in legacy:
            for t in result.get("testResults", []):
                if t.get("status") == "fail":
                    failures.append((result.get("operationId", result.get("path", "?")),
                                     t.get("testKey", "?"), t.get("severity", "")))

    unique, seen = [], set()
    for f_ in failures:
        if f_ not in seen:
            seen.add(f_)
            unique.append(f_)
    if unique:
        print(f"\nfailures[{len(unique)}]{{operation,test,severity}}:")
        for op, test, sev in unique:
            print(f"  {op},{test},{sev}")
    else:
        print("failures: none")

if __name__ == "__main__":
    main()
