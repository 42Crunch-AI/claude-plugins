#!/usr/bin/env python3
"""Analyze an OpenAPI file for the scan preview without loading it into
context: operation inventory, auth schemes, sample-data presence, and
BOLA/BFLA *signals*.

Usage:
    python3 oas_preview.py <oas-file>

Exit 2 with a clear message if the file is YAML and PyYAML is unavailable —
the caller should then fall back to reading the OAS directly.

This script surfaces structured FACTS; candidacy judgment stays with the
caller (recall over precision — signals are deliberately broad):

  - id_refs: parameter/body-field names ending in id/key/ref, split by
    location (path/query/body). An operation with any id_ref is a BOLA signal
    UNLESS it only creates a new resource from attributes (caller judges).
  - sec_diff: the operation declares its own `security` differing from the
    API default — a privilege-elevation (BFLA) signal.
  - admin: explicit privilege markers matched in the path, tags,
    operationId, or summary/description.
  - samples: the operation carries example/examples/default values on its
    request body or parameters.

Output is TOON: a header block, then one row per operation.
"""
import json
import re
import sys

ID_RE = re.compile(r"(id|key|ref)s?$", re.I)
ADMIN_PATH_RE = re.compile(r"/(admin|internal|management|staff|system|superuser)(/|$)", re.I)
ADMIN_WORD_RE = re.compile(
    r"\b(admin(istrator)?s?( |-)?only|admin|impersonate|promote|demote|ban|unban|"
    r"force( |_|-)?delete|refund|approve|elevated|restricted|internal use)\b", re.I)
HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "trace")

def load(path):
    text = open(path, encoding="utf-8").read()
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        import yaml
    except ImportError:
        print("error: file is not JSON and PyYAML is not installed — "
              "fall back to reading the OAS directly for the preview.")
        sys.exit(2)
    return yaml.safe_load(text)

def make_resolver(doc):
    def resolve(node, depth=0):
        if depth > 20 or not isinstance(node, dict):
            return node if isinstance(node, dict) else {}
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            target = doc
            for part in ref[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                target = target.get(part, {}) if isinstance(target, dict) else {}
            return resolve(target, depth + 1)
        return node
    return resolve

def walk_has_samples(node, resolve, seen=None, depth=0):
    if seen is None:
        seen = set()
    if depth > 12:
        return False
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            if ref in seen:
                return False
            seen.add(ref)
            return walk_has_samples(resolve(node), resolve, seen, depth + 1)
        for k, v in node.items():
            if k in ("example", "examples", "default") and v not in (None, {}, []):
                return True
            if walk_has_samples(v, resolve, seen, depth + 1):
                return True
    elif isinstance(node, list):
        return any(walk_has_samples(v, resolve, seen, depth + 1) for v in node)
    return False

def id_fields_in_schema(schema, resolve, depth=0, seen=None):
    if seen is None:
        seen = set()
    names = []
    if depth > 3 or not isinstance(schema, dict):
        return names
    ref = schema.get("$ref")
    if isinstance(ref, str):
        if ref in seen:
            return names
        seen.add(ref)
        schema = resolve(schema)
    for combiner in ("allOf", "oneOf", "anyOf"):
        for sub in schema.get(combiner, []) or []:
            names += id_fields_in_schema(sub, resolve, depth + 1, seen)
    for prop, sub in (schema.get("properties") or {}).items():
        if ID_RE.search(prop):
            names.append(prop)
        else:
            names += id_fields_in_schema(sub, resolve, depth + 1, seen)
    if isinstance(schema.get("items"), dict):
        names += id_fields_in_schema(schema["items"], resolve, depth + 1, seen)
    return names

def main():
    if len(sys.argv) != 2:
        print("usage: oas_preview.py <oas-file>")
        sys.exit(1)
    doc = load(sys.argv[1])
    resolve = make_resolver(doc)

    info = doc.get("info", {})
    is_v2 = "swagger" in doc
    spec_version = doc.get("openapi") or doc.get("swagger") or "?"
    servers = doc.get("servers") or []
    server_url = servers[0].get("url") if servers else (
        (("https" if "https" in (doc.get("schemes") or []) else "http") + "://" +
         doc.get("host", "") + doc.get("basePath", "")) if is_v2 and doc.get("host") else None)

    schemes = doc.get("components", {}).get("securitySchemes") or doc.get("securityDefinitions") or {}
    scheme_desc = []
    for name, s in schemes.items():
        s = resolve(s)
        t = s.get("type", "?")
        extra = s.get("scheme") or s.get("flow") or ("header:" + s["name"] if t == "apiKey" and s.get("name") else "")
        scheme_desc.append(f"{name}:{t}" + (f"({extra})" if extra else ""))
    # First pass: gather every operation and the de-facto security baseline.
    # An "elevated requirement" (BFLA signal) means an operation's security
    # differs from the MOST COMMON requirement across the API — not merely
    # from a (frequently absent) root default, which would flag everything.
    op_entries = []  # (path, method, op, effective_security_key)
    sec_freq = {}
    for path, path_item in (doc.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        for method in HTTP_METHODS:
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue
            eff = op.get("security", doc.get("security"))
            key = json.dumps(eff, sort_keys=True) if eff is not None else None
            if key is not None:
                sec_freq[key] = sec_freq.get(key, 0) + 1
            op_entries.append((path, method, op, key))
    baseline_key = max(sec_freq, key=sec_freq.get) if sec_freq else None

    rows = []
    counts = {"ops": 0, "bola_signal": 0, "bfla_signal": 0, "with_samples": 0}
    for path, path_item in (doc.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        path_level_params = path_item.get("parameters", [])
        for method in HTTP_METHODS:
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue
            counts["ops"] += 1
            id_refs = {"path": [], "query": [], "body": []}
            for p in list(path_level_params) + list(op.get("parameters", [])):
                p = resolve(p)
                loc, pname = p.get("in"), p.get("name", "")
                if loc in ("path", "query") and ID_RE.search(pname):
                    id_refs[loc].append(pname)
                if is_v2 and loc == "body":
                    id_refs["body"] += id_fields_in_schema(p.get("schema", {}), resolve)
            rb = resolve(op.get("requestBody", {}))
            for media in (rb.get("content") or {}).values():
                id_refs["body"] += id_fields_in_schema(media.get("schema", {}), resolve)
            id_refs = {k: sorted(set(v)) for k, v in id_refs.items()}

            # Elevated requirement: this op declares its own security AND it
            # differs from the de-facto baseline (only meaningful when a
            # baseline exists and at least one other op shares it).
            eff = op.get("security", doc.get("security"))
            key = json.dumps(eff, sort_keys=True) if eff is not None else None
            sec_diff = ("security" in op and baseline_key is not None
                        and sec_freq.get(baseline_key, 0) > 1
                        and key != baseline_key)
            markers = []
            if ADMIN_PATH_RE.search(path):
                markers.append("path")
            if any(re.search(r"admin|internal|management", t, re.I) for t in op.get("tags", []) or []):
                markers.append("tag")
            text = " ".join(str(op.get(k, "")) for k in ("operationId", "summary", "description"))
            if ADMIN_WORD_RE.search(text):
                markers.append("name")
            if sec_diff:
                markers.append("sec_diff")

            samples = walk_has_samples(
                {"parameters": op.get("parameters", []), "requestBody": op.get("requestBody", {})},
                resolve)
            has_id = any(id_refs.values())
            counts["bola_signal"] += bool(has_id)
            counts["bfla_signal"] += bool(markers)
            counts["with_samples"] += bool(samples)

            ref_str = ";".join(f"{k}:{','.join(v)}" for k, v in id_refs.items() if v) or "-"
            rows.append((method.upper(), path, op.get("operationId", "-"),
                         ref_str, "|".join(markers) or "-", "y" if samples else "n"))

    print(f"title: {info.get('title', '?')}  version: {info.get('version', '?')}  spec: {spec_version}")
    if server_url:
        print(f"server: {server_url}")
    print(f"auth_schemes[{len(scheme_desc)}]: {', '.join(scheme_desc) if scheme_desc else '(none)'}")
    print(f"operations: {counts['ops']}  bola_signal: {counts['bola_signal']}  "
          f"bfla_signal: {counts['bfla_signal']}  ops_with_samples: {counts['with_samples']}")
    print(f"\noperations[{counts['ops']}]{{method,path,operationId,id_refs,bfla_markers,samples}}:")
    for row in rows:
        print("  " + ",".join(row))

if __name__ == "__main__":
    main()
