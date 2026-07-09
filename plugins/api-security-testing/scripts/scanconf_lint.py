#!/usr/bin/env python3
"""Structural linter for a 42c-ast scan configuration.

Usage:
    python3 scanconf_lint.py <scanconf.json> [--graphql]

Catches the mechanical mistakes that otherwise cost a wasted network
`scan conf validate` round-trip or a broken/false-positive scan run, encoding
rules verified against the engine. It does NOT judge scan design (BOLA/BFLA
candidacy, creator placement, classification) — those stay with the model.

Prints findings grouped as ERROR (will break the scan or validation) and WARN
(likely wrong, review). Exit code 1 if any ERROR, else 0. `lint: clean` when
nothing is found.

Rules (see references/scanconf-templates.md "Rules at a glance"):
  ERROR  inline `request` object in a requests[] array (no operationId — the
         VS Code extension rejects it; use $ref)
  ERROR  a variable in environments.default.variables that is a raw string
         instead of an object with a source strategy
  ERROR  operation request.defaultResponse has no matching key in
         request.responses
  ERROR  "skipped": true on any operation (scanner ignores it and runs the op
         against User1 — deletes the primary user on a Class-D delete)
  WARN   generated security-scheme variable left "required": true (causes a
         runtime error when no value is provided) — auto-fixable with
         --fix-required
  WARN   "auth" nested inside request.details instead of the outer request
         object (details is the raw HTTP descriptor; auth is a scanner concern)
  WARN   laxTestingModeEnabled: true (fuzzes past failing happy paths)
  GraphQL (--graphql): ERROR when an operation carries a `before`/capture or
         variableAssignments but its Accept header is not narrowed to
         application/json — the body parser panics (SIGSEGV) otherwise.

--fix-required flips every environments.default.variables[*].required from
true to false in place (the generation-time normalization) and reports what it
changed; run the linter again afterwards.
"""
import json
import sys

def load(path):
    with open(path) as f:
        return json.load(f)

def lint(conf, graphql=False):
    errors, warns = [], []
    env_vars = ((conf.get("environments") or {}).get("default") or {}).get("variables") or {}

    # Variables must be objects with a source strategy, not raw strings.
    for name, val in env_vars.items():
        if not isinstance(val, dict):
            errors.append(f"variable '{name}' is a {type(val).__name__}, not an object "
                          f"with a source strategy (from/name/default)")
        elif val.get("required") is True:
            warns.append(f"variable '{name}' is required:true — set required:false "
                         f"(run with --fix-required) unless strict inputs are intended")

    rc = conf.get("runtimeConfiguration") or {}
    if rc.get("laxTestingModeEnabled") is True:
        warns.append("runtimeConfiguration.laxTestingModeEnabled is true — fuzzing "
                     "will run past failing happy paths and cascade false positives")

    operations = conf.get("operations") or {}
    for opid, op in operations.items():
        if op.get("skipped") is True:
            errors.append(f"operation '{opid}' has \"skipped\": true — the scanner "
                          f"ignores it and runs the op against User1")
        req = op.get("request") or {}
        # defaultResponse must have a matching responses key.
        dr = req.get("defaultResponse")
        responses = req.get("responses") or {}
        if dr is not None and str(dr) not in {str(k) for k in responses}:
            errors.append(f"operation '{opid}': defaultResponse '{dr}' has no matching "
                          f"key in responses ({', '.join(map(str, responses)) or 'none'})")
        # auth should be on the outer request object, not inside details.
        inner = req.get("request") or {}
        if isinstance(inner.get("details"), dict) and "auth" in inner["details"]:
            warns.append(f"operation '{opid}': 'auth' is inside request.details — move "
                         f"it to the outer request object")

        # GraphQL Accept-header narrowing on capture-source operations.
        if graphql:
            has_capture = bool(op.get("before")) or _has_variable_assignments(op)
            if has_capture and not _accept_is_json(inner):
                errors.append(f"operation '{opid}': feeds a capture (before/"
                              f"variableAssignments) but its Accept header is not "
                              f"narrowed to application/json — the GraphQL body parser "
                              f"panics (SIGSEGV). Set Accept: application/json;charset=utf-8")

    # Inline request objects anywhere in a requests[] array.
    for opid, op in operations.items():
        for scenario in op.get("scenarios") or []:
            for i, step in enumerate(scenario.get("requests") or []):
                if isinstance(step, dict) and "$ref" not in step and (
                        "request" in step or "details" in step):
                    errors.append(f"operation '{opid}' scenario '{scenario.get('key','?')}' "
                                  f"step {i}: inline request object — use "
                                  f"\"$ref\": \"#/operations/<id>/request\" instead")
    return errors, warns

def _has_variable_assignments(node, depth=0):
    if depth > 8:
        return False
    if isinstance(node, dict):
        if node.get("variableAssignments"):
            return True
        return any(_has_variable_assignments(v, depth + 1) for v in node.values())
    if isinstance(node, list):
        return any(_has_variable_assignments(v, depth + 1) for v in node)
    return False

def _accept_is_json(inner):
    # Headers live under request.details.headers as a list of {key, value}.
    for h in (inner.get("details") or {}).get("headers", []) or []:
        if isinstance(h, dict) and h.get("key", "").lower() == "accept":
            return ("application/json" in h.get("value", "")
                    and "graphql-response" not in h.get("value", ""))
    return False

def main():
    args = sys.argv[1:]
    graphql = "--graphql" in args
    fix_required = "--fix-required" in args
    paths = [a for a in args if not a.startswith("--")]
    if not paths:
        print("usage: scanconf_lint.py <scanconf.json> [--graphql] [--fix-required]")
        sys.exit(2)
    path = paths[0]
    conf = load(path)

    if fix_required:
        env_vars = ((conf.get("environments") or {}).get("default") or {}).get("variables") or {}
        fixed = [n for n, v in env_vars.items() if isinstance(v, dict) and v.get("required") is True]
        for n in fixed:
            env_vars[n]["required"] = False
        with open(path, "w") as f:
            json.dump(conf, f, indent=2)
        print(f"fixed_required[{len(fixed)}]: {', '.join(fixed) if fixed else '(none)'}")
        conf = load(path)

    errors, warns = lint(conf, graphql=graphql)
    for e in errors:
        print(f"ERROR: {e}")
    for w in warns:
        print(f"WARN:  {w}")
    if not errors and not warns:
        print("lint: clean")
    sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
