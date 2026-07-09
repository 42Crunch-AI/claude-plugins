#!/usr/bin/env python3
"""Deterministic Step-1 scan-config bootstrap helpers.

Usage:
    python3 scanconf_bootstrap.py alias <oas-file>
    python3 scanconf_bootstrap.py set-host <scanconf.json> <SCAN_TARGET_URL>

`alias` derives the 42Crunch alias from the OAS `info.title` (falling back to
the filename stem) using the canonical transform — lowercase; spaces,
underscores and non-alphanumerics to hyphens; collapse repeats; strip
leading/trailing hyphens. It reads only `info.title`, so a large OAS never
enters context just to name the config. For JSON specs no dependency is
needed; YAML specs need PyYAML (exit 2 with a fallback message otherwise).

`set-host` writes SCAN_TARGET_URL into environments.default.variables.host as a
proper object with the SCAN42C_HOST env-var source strategy (creating the
variables map if absent), in place. It prints the host block it wrote.

Judgment stays with the model: this does not choose the URL, wire auth, or
classify operations — it performs the two mechanical transforms Step 1
otherwise does by hand-editing.
"""
import json
import re
import sys

def derive_alias(oas_path):
    title = None
    text = open(oas_path, encoding="utf-8").read()
    try:
        doc = json.loads(text)
        title = (doc.get("info") or {}).get("title")
    except ValueError:
        try:
            import yaml
        except ImportError:
            print("error: YAML OAS and PyYAML is not installed — derive the alias "
                  "by reading info.title directly.")
            sys.exit(2)
        doc = yaml.safe_load(text)
        title = (doc.get("info") or {}).get("title") if isinstance(doc, dict) else None

    if not title:
        # Fall back to the filename stem.
        base = oas_path.rsplit("/", 1)[-1]
        title = base.rsplit(".", 1)[0] if "." in base else base

    alias = title.lower()
    alias = re.sub(r"[^a-z0-9]+", "-", alias)
    alias = re.sub(r"-+", "-", alias).strip("-")
    return alias or "api"

def set_host(conf_path, url):
    with open(conf_path) as f:
        conf = json.load(f)
    envs = conf.setdefault("environments", {}).setdefault("default", {})
    variables = envs.setdefault("variables", {})
    variables["host"] = {
        "name": "SCAN42C_HOST",
        "from": "environment",
        "required": False,
        "default": url,
    }
    with open(conf_path, "w") as f:
        json.dump(conf, f, indent=2)
    print("host: " + json.dumps(variables["host"]))

def main():
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "alias":
        print(derive_alias(args[1]))
        return
    if len(args) >= 3 and args[0] == "set-host":
        set_host(args[1], args[2])
        return
    print("usage: scanconf_bootstrap.py alias <oas-file> | "
          "set-host <scanconf.json> <SCAN_TARGET_URL>")
    sys.exit(2)

if __name__ == "__main__":
    main()
