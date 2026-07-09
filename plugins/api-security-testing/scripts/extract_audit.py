#!/usr/bin/env python3
"""Extract a compact TOON summary from 42c-ast audit output.

Usage:
    python3 extract_audit.py [OUTPUT_DIR]
    python3 extract_audit.py [OUTPUT_DIR] --locations ISSUE_ID[,ISSUE_ID...]

OUTPUT_DIR defaults to /tmp/42c-audit and must contain todo.json (or
report.json as fallback) and, in platform mode, sqg.json.

Default mode prints: openapi state, scores, per-issue-type TOON rows, and SQG
acceptance. On the first run for a given OAS the scores are saved as the
baseline in OUTPUT_DIR/.baseline.json; subsequent runs also print a
score_change line (before -> after) against that baseline.

--locations prints every occurrence of the given issue IDs with its pointer
resolved to a human-readable OAS path via todo.json's index[], plus
specificDescription when present. Use it in the fix loop to locate what to
change.

Field notes (from the report schema):
  - "semanticErrors"/"warnings" use totalIssues; "security"/"data" use
    issueCounter — that field is the true total; len(issues) is only what is
    shown (capped at maxEntriesPerIssue, tooManyError=True when truncated).
  - criticality: 4=CRITICAL 3=HIGH 2=MEDIUM 1=LOW 0=INFO.
  - specificDescription is frequently absent or "" — fall back to the issue
    type's description.
  - sqg.json: acceptance "yes"/"no"; blocking issue rules live in
    sqgsDetail[0].directives.issueRules; per-run blocking rules in
    processingDetails[].blockingRules.
"""
import json
import os
import sys

def load(output_dir):
    for name in ("todo.json", "report.json"):
        path = os.path.join(output_dir, name)
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f), name
    print(f"error: no todo.json or report.json in {output_dir}")
    sys.exit(1)

def main():
    args = [a for a in sys.argv[1:]]
    loc_ids = None
    if "--locations" in args:
        i = args.index("--locations")
        loc_ids = set(args[i + 1].split(","))
        del args[i:i + 2]
    output_dir = args[0] if args else "/tmp/42c-audit"

    d, source = load(output_dir)
    state = d.get("openapiState")

    # fileInvalid/structureInvalid reports carry no score or security/data
    # sections at all — handle them before touching anything else.
    if state == "fileInvalid":
        errors = [k for k, v in d.get("errors", {}).items() if v]
        print("openapi_state: fileInvalid")
        print(f"file_errors: {', '.join(errors) if errors else '(unspecified)'}")
        return
    if state == "structureInvalid":
        print("openapi_state: structureInvalid")
        print(f"structural_issue_count: {d['issueCounter']}")
        return

    if loc_ids is not None:
        index = d.get("index", [])
        found = False
        for section in ("security", "data", "semanticErrors", "warnings"):
            for issue_id, issue_data in (d.get(section) or {}).get("issues", {}).items():
                if issue_id not in loc_ids:
                    continue
                found = True
                occs = issue_data.get("issues", [])
                print(f"{issue_id} ({section}) [{len(occs)} shown of "
                      f"{issue_data.get('issueCounter', issue_data.get('totalIssues', len(occs)))}]:")
                for loc in occs:
                    ptr = loc.get("pointer")
                    path = index[ptr] if isinstance(ptr, int) and ptr < len(index) else f"pointer:{ptr}"
                    path = path.replace("~1", "/").replace("~0", "~")
                    detail = loc.get("specificDescription") or issue_data.get("description", "")
                    print(f"  {path} — {detail}")
        if not found:
            print(f"locations: no issues matched {','.join(sorted(loc_ids))}")
        return

    # GraphQL audit reports carry a single score (no security/data split) —
    # print the sub-scores only when the sections exist.
    score = d["score"]
    sec_score = (d.get("security") or {}).get("score")
    data_score = (d.get("data") or {}).get("score")
    line = f"score: {score}"
    if sec_score is not None:
        line += f"  security: {sec_score}"
    if data_score is not None:
        line += f"  data: {data_score}"
    print(line)

    issues = []
    for section in ("semanticErrors", "warnings", "security", "data"):
        section_data = d.get(section)
        if not section_data:
            continue
        for issue_id, issue_data in section_data["issues"].items():
            crit = issue_data.get("criticality", 0)
            desc = issue_data["description"]
            shown = len(issue_data.get("issues", []))
            total = issue_data.get("issueCounter", issue_data.get("totalIssues", shown))
            truncated = issue_data.get("tooManyError", False)
            issues.append((issue_id, section, crit, desc, shown, total, truncated))
    if issues:
        print(f"\nissues[{len(issues)}]{{id,section,criticality,description,shown,total,truncated}}:")
        for row in issues:
            print("  " + ",".join(str(v) for v in row))

    sqg_path = os.path.join(output_dir, "sqg.json")
    if os.path.exists(sqg_path):
        with open(sqg_path) as f:
            sqg = json.load(f)
        print(f"sqg_acceptance: {sqg['acceptance']}")
        print(f"sqg_name: {sqg['sqgsDetail'][0]['name']}")
        blocking = [r for pd in sqg.get("processingDetails", [])
                    for r in pd.get("blockingRules", [])]
        if blocking:
            print(f"blocking_rules: {', '.join(blocking)}")
        if sqg.get("acceptance") != "yes":
            rules = sqg["sqgsDetail"][0].get("directives", {}).get("issueRules", [])
            if rules:
                print(f"sqg_blocking_issue_ids: {', '.join(rules)}")

    # Baseline for before/after score comparison across fix cycles.
    baseline_path = os.path.join(output_dir, ".baseline.json")
    if os.path.exists(baseline_path):
        with open(baseline_path) as f:
            base = json.load(f)
        def fmt(delta):
            delta = round(delta, 1)
            return f"+{delta}" if delta > 0 else (f"-{abs(delta)}" if delta < 0 else "±0")
        line = f"score_change: {base['score']} → {score} ({fmt(score - base['score'])})"
        if data_score is not None and base.get("data") is not None:
            line += f"  |  Data: {base['data']} → {data_score} ({fmt(data_score - base['data'])})"
        if (sec_score is not None and base.get("security") is not None
                and round(sec_score - base["security"], 1) != 0):
            line += f"  |  Security: {base['security']} → {sec_score} ({fmt(sec_score - base['security'])})"
        print(line)
    else:
        with open(baseline_path, "w") as f:
            json.dump({"score": score, "security": sec_score, "data": data_score}, f)

if __name__ == "__main__":
    main()
