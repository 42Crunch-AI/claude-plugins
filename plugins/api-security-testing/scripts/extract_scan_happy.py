#!/usr/bin/env python3
"""Extract failing happy paths from a 42c-ast scan run (happy-path-only mode).

Usage:
    python3 extract_scan_happy.py [STATUS_FILE] [REPORT_FILE]

Defaults: /tmp/42c-happy-status.json /tmp/42c-happy-report.json
(the files written by `scan run --output REPORT_FILE ... > STATUS_FILE`).

Prints `scan_error: ...` if the run failed, otherwise a TOON list of failing
happy-path tests (operation, test key, HTTP status, truncated reason) or
`happy_path_failures: none`.
"""
import json
import sys

def main():
    status_file = sys.argv[1] if len(sys.argv) > 1 else "/tmp/42c-happy-status.json"
    report_file = sys.argv[2] if len(sys.argv) > 2 else "/tmp/42c-happy-report.json"

    with open(status_file) as f:
        status = json.load(f)
    if status.get("statusCode") != 0:
        print(f"scan_error: statusCode={status.get('statusCode')} {status.get('statusMessage', '')}")
        return

    # Reconstruct the combined shape from the clean status + report files
    with open(report_file) as f:
        data = {**status, "report": json.load(f)}
    results = data.get("results", data.get("scanResults", []))
    if isinstance(results, dict):
        results = [results]
    fails = [
        (r.get("operationId", r.get("path", "?")), t.get("testKey", "?"),
         t.get("httpStatus", ""), t.get("reason", ""))
        for r in results
        for t in r.get("testResults", [])
        if t.get("status") == "fail" and "happy" in t.get("testKey", "").lower()
    ]
    if fails:
        print(f"happy_path_failures[{len(fails)}]{{operation,test,status,reason}}:")
        for op, test, code, reason in fails:
            print(f"  {op},{test},{code},{reason[:60]}")
    else:
        print("happy_path_failures: none")

if __name__ == "__main__":
    main()
