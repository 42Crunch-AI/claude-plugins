# Fix Patterns Reference

## OAS Schema Fix Patterns (v3-schema-*)

These issues live in the `data` section of todo.json. The fix is always adding
the missing constraint to the correct schema in the OAS file. Use Phase 3
implementation context to choose accurate values.

The `pointer` field in issue locations tells you exactly which OAS path to fix
(via `index[pointer]`).

| Issue ID | Fix |
|---|---|
| `v3-schema-request-string-maxlength` | Add `"maxLength": <n>` to the string schema |
| `v3-schema-request-string-minlength` | Add `"minLength": <n>` to the string schema |
| `v3-schema-request-string-pattern` | Add `"pattern": "<regex>"` to the string schema |
| `v3-schema-request-numerical-max` | Add `"maximum": <n>` to the numeric schema |
| `v3-schema-request-numerical-min` | Add `"minimum": <n>` to the numeric schema |
| `v3-schema-request-numerical-format` | Add `"format": "int32"` or `"int64"` to integer schema |
| `v3-schema-request-object-additionalproperties-true` | Add `"additionalProperties": false` |
| `v3-schema-response-array-maxitems` | Add `"maxItems": <n>` to array schema |
| `v3-schema-response-string-maxlength` | Add `"maxLength": <n>` to string schema |
| `v3-schema-response-string-minlength` | Add `"minLength": <n>` to string schema |
| `v3-schema-response-string-pattern` | Add `"pattern": "<regex>"` to string schema |
| `v3-schema-response-object-additionalproperties-true` | Add `"additionalProperties": false` |
| `v3-schema-response-array-items` | Add `"items": { ... }` schema to the array |

---

## Global Security Fix Patterns (global-*)

These issues live in the `security` section of todo.json. Look them up in the KDB
at `https://platform.42crunch.com/kdb/audit-with-yaml.json` — fetch once only if
at least one `global-*` ID is present (the KDB has no `v3-schema-*` entries).

| Issue ID | Fix Pattern |
|---|---|
| `global-http-clear` | Add `https` to schemes, remove `http` |
| `global-security` | Add global `security:` block + `securitySchemes:` under components |
| `global-security-scheme` | Add `securitySchemes:` under `components:` |
| `operation-security-empty` | Add security requirement to operation, or remove empty override |
| `schema-response-body-undefined` | Add `schema:` to response content |
| `schema-request-body-undefined` | Add `schema:` to requestBody content |
| `parameter-schema-undefined` | Add `schema:` to the parameter definition |

---

## Scan Code Fix Patterns

### Issue type → code fix mapping

| Issue Type | Root Cause | Code Fix |
|---|---|---|
| `authentication-swapping-bola` | User A can access/modify User B's resource (ownership not enforced) | After fetching the resource, compare its owner field to `req.user.customerId`; return 403 if mismatch |
| `authentication-swapping-bfla` | Non-privileged user can reach a privileged operation | Add role check: `if (!req.user.isAdmin) return res.status(403).json({ error: 'Forbidden' })` |
| `partial-security-accepted` | JWT accepted without signature verification | May be intentional — check Phase 3 context. If deliberate, annotate; otherwise replace `jwt.decode()` with `jwt.verify(token, secret)` |
| `schema-type-wrong-*` / `schema-maxlength-scan` / `schema-pattern-scan` / `schema-minlength-scan` / `schema-required-scan` / `schema-additionalproperties-scan` | No server-side input validation | Create shared validators matching every OAS schema constraint; call at top of each route handler before DB access |
| `parameter-header-contenttype-wrong-scan` | Server accepts wrong/missing `Content-Type` | Add global middleware rejecting non-`application/json` with HTTP 415 |
| `security-scheme-not-enforced` | Route accessible without auth token | Add auth middleware to the route definition |
| `response-body-conformance` | Route returns undeclared fields | Return only the fields declared in the OAS response schema |
| `response-status-conformance` | Route returns undeclared status code | Use the correct status code or add it to OAS if intentional |

### Example fixes (Node.js / Express)

**BOLA ownership check:**
```js
// Authorization: only the resource owner may access this
if (order.customerId !== req.user.customerId) {
  return res.status(403).json({ error: 'Forbidden' });
}
```

**BFLA role check:**
```js
// Authorization: admin-only operation
if (!req.user.isAdmin) {
  return res.status(403).json({ error: 'Forbidden' });
}
```

**Content-Type middleware:**
```js
app.use((req, res, next) => {
  if (['POST', 'PUT', 'PATCH'].includes(req.method)) {
    const ct = req.headers['content-type'] || '';
    if (!ct.includes('application/json')) {
      return res.status(415).json({ error: 'Content-Type must be application/json' });
    }
  }
  next();
});
```

---

## Scan Config — Credential Injection Patterns

### Static token mode — credential entries

```python
import json

scanconf = json.load(open(scanconf_path))
scheme_name = list(scanconf["authenticationDetails"][0].keys())[0]
creds = scanconf["authenticationDetails"][0][scheme_name]["credentials"]
env_vars = scanconf["environments"]["default"]["variables"]
original_key = list(creds.keys())[0]

# Replace default credential with named entries
creds["user"] = {"description": "Primary user token", "credential": "{{userToken}}"}
env_vars["userToken"] = {"from": "environment", "name": "SCAN42C_SECURITY_USERTOKEN", "required": True}

if BOLA_FOUND:
    creds["user2"] = {"description": "User 2 (BOLA attacker)", "credential": "{{user2Token}}"}
    env_vars["user2Token"] = {"from": "environment", "name": "SCAN42C_SECURITY_USER2TOKEN", "required": True}

if BFLA_FOUND:
    creds["admin"] = {"description": "Admin token (BFLA)", "credential": "{{adminToken}}"}
    env_vars["adminToken"] = {"from": "environment", "name": "SCAN42C_SECURITY_ADMINTOKEN", "required": True}

if original_key not in ("user", "user2", "admin"):
    creds.pop(original_key, None)
    env_vars.pop(original_key, None)
```

### Authorization test injection

```python
auth_tests = {}
if BOLA_FOUND:
    auth_tests["bola"] = {
        "key": "authentication-swapping-bola",
        "source": [f"{scheme_name}/user"],
        "target": [f"{scheme_name}/user2"]
    }
if BFLA_FOUND:
    auth_tests["bfla"] = {
        "key": "authentication-swapping-bfla",
        "source": [f"{scheme_name}/user"],
        "target": [f"{scheme_name}/admin"]
    }
scanconf["authorizationTests"] = auth_tests

for op_id in BOLA_OPS:
    op = scanconf["operations"].setdefault(op_id, {})
    if "bola" not in op.setdefault("authorizationTests", []):
        op["authorizationTests"].append("bola")

for op_id in BFLA_OPS:
    op = scanconf["operations"].setdefault(op_id, {})
    if "bfla" not in op.setdefault("authorizationTests", []):
        op["authorizationTests"].append("bfla")

json.dump(scanconf, open(scanconf_path, "w"), indent=2)
```
