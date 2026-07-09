#!/usr/bin/env python3
"""Surface owner-vs-attacker response bodies for every defective BOLA/BFLA
finding in a full scan report (Step 12a-0 authorization confirmation).

Usage:
    python3 compare_auth_bodies.py [REPORT_FILE]

Default: /tmp/42c-scan-report.json

For each operation with a defective authentication-swapping result, prints
whether the attacker's response body is byte-identical to the legitimate
owner's happy-path body, plus a 120-char preview of each. Interpretation is
the caller's job: for READ targets, identical bodies (or the victim's
distinguishing data in the attacker body) confirm the finding; an attacker
body reflecting only the caller's own data means an owner-scoped 2xx (not
confirmed). State-changing targets are confirmed by the 2xx alone — the body
is irrelevant.

Bodies come from response.rawPayload (base64 of the raw HTTP response): the
owner's under the operation's scenarios, the attacker's under
authorizationRequestsResults.
"""
import base64
import json
import re
import sys

def body(b64):
    if not b64:
        return None
    raw = base64.b64decode(b64).decode("utf-8", "replace")
    parts = re.split(r"\r?\n\r?\n", raw, maxsplit=1)
    m = re.search(r"\{.*\}", parts[1] if len(parts) > 1 else raw, re.S)
    return m.group() if m else None

def owner_body(op):
    for s in op.get("scenarios", []) or []:
        for r in (s.get("requests") or [s]):
            b = body((r.get("response") or {}).get("rawPayload"))
            if b:
                return b
    return None

def main():
    report_file = sys.argv[1] if len(sys.argv) > 1 else "/tmp/42c-scan-report.json"
    with open(report_file) as f:
        ops = json.load(f).get("operations", {})

    any_findings = False
    for opid, op in ops.items():
        auth = [e for e in op.get("authorizationRequestsResults", []) or []
                if "swapping" in (e.get("test") or {}).get("key", "")
                and (e.get("outcome") or {}).get("status") == "defective"]
        if not auth:
            continue
        any_findings = True
        method = (op.get("method") or "").upper()
        ob = owner_body(op)
        for e in auth:
            ab = body((e.get("response") or {}).get("rawPayload"))
            same = ab is not None and ab == ob
            print(f"{opid} [{method}] bodies_identical={same}")
            print(f"    owner:    {(ob or '(none)')[:120]}")
            print(f"    attacker: {(ab or '(none)')[:120]}")
    if not any_findings:
        print("authorization_findings: none (no defective swapping results in report)")

if __name__ == "__main__":
    main()
