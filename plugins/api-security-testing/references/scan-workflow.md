# Scan Workflow

> **Command conventions used throughout this file**
> - `<binary>` — the full path resolved during binary discovery (e.g. `~/.42crunch/bin/42c-ast`). Never call `42c-ast` by name alone unless it is confirmed to be on PATH.
> - **Platform mode**: prefix every command with `API_KEY="<resolved-value>" PLATFORM_HOST="<value>"` (both values read from `~/.42crunch/conf/env` on macOS/Linux or `%APPDATA%\42Crunch\conf\env` on Windows).
> - **Freemium mode**: add `--freemium-host stateless.42crunch.com:443` and `--token <FREEMIUM_TOKEN>` to every command.

---

## Step 1 — Locate or Create Scan Config

### 1a — Resolve alias

Walk upward from the OAS file directory looking for `.42c/conf.yaml`.

**If `.42c/conf.yaml` exists and the OAS path is listed:**
- Extract the `alias` value for that path.

**If `.42c/conf.yaml` does not exist or the OAS path is not in it:**
- Derive an alias from the OAS filename: lowercase the stem, replace spaces/underscores with hyphens.
  - Example: `openAPI.json` → `openapi`, `my_banking_api.json` → `my-banking-api`
  - Or use `info.title` from the OAS file slug if more descriptive.
- Add (or create) the entry in `.42c/conf.yaml`:
  ```yaml
  apis:
    <relative-oas-path-from-git-root>:
      alias: <derived-alias>
  ```

### 1b — Check for existing scan config

Check whether `.42c/scan/<alias>/scanconf.json` exists.

**If it exists:**
- Validate it:
  ```bash
  # Platform mode
  API_KEY="<value>" PLATFORM_HOST="<value>" <binary> scan conf validate <relative-oas-path> \
    --conf-file .42c/scan/<alias>/scanconf.json

  # Freemium mode
  <binary> scan conf validate <relative-oas-path> \
    --freemium-host stateless.42crunch.com:443 \
    --token <FREEMIUM_TOKEN> \
    --conf-file .42c/scan/<alias>/scanconf.json
  ```
- If valid (`statusCode: 0`): store `CONF_FILE=.42c/scan/<alias>/scanconf.json` and proceed to Step 2.
- If invalid: treat as missing (re-generate).

**If it does not exist (or was invalid):**
- Ensure the output directory exists:
  ```bash
  mkdir -p .42c/scan/<alias>
  ```
- Generate a baseline config using the **relative OAS path** (not alias, not absolute path).
  Platform mode: include `--tag` only when a tag was resolved. Freemium mode: omit `--tag`.
  ```bash
  # Platform mode
  API_KEY="<value>" PLATFORM_HOST="<value>" <binary> scan conf generate <relative-oas-path> \
    [--tag <category>:<tag>] \
    --output-report .42c/scan/<alias>/scanconf.json

  # Freemium mode
  <binary> scan conf generate <relative-oas-path> \
    --freemium-host stateless.42crunch.com:443 \
    --token <FREEMIUM_TOKEN> \
    --output-report .42c/scan/<alias>/scanconf.json
  ```
  The `--output-report` flag writes only the config bundle (the `report` section) to the
  file — no JSON wrapper.
- Validate (use the same mode-appropriate command as above).
- If valid: store `CONF_FILE=.42c/scan/<alias>/scanconf.json` and proceed to Step 2.
- If invalid: surface the error to the user and stop.

### 1c — Write target URL to config

Write `SCAN_TARGET_URL` (confirmed in the skill's URL resolution step) into
`environments.default.variables.host` in `CONF_FILE`. No URL resolution or
user prompting is needed here — the URL was already confirmed and reachability
checked before the workflow started.

---

## Step 2 — Authentication Setup

Read the OAS `securitySchemes` and global/operation `security` definitions to
determine the auth scheme, then collect credentials using the per-scheme flows
below. Every credential field is collected via `AskUserQuestion` — never
generate, guess, or suggest credential values.

**BOLA/BFLA second-user identification (do this before collecting any credentials):**
Identify all BOLA/BFLA candidates in the OAS. Flag every operation where ALL
of the following are true:
- The path contains at least one path parameter whose name ends in `Id`, `Key`,
  or `Ref` (e.g. `{userId}`, `{orderId}`, `{documentRef}`), or is a UUID/integer
  field whose name matches a resource type — indicating a specific resource
  instance, not a collection.
- The HTTP method is GET, PUT, PATCH, or DELETE (i.e. the operation reads or
  mutates a specific resource instance, not a collection).

HTTP method does NOT gate BOLA candidacy — a PUT or PATCH on `/{resourceId}`
is just as much a BOLA candidate as a DELETE or GET on the same path.

Flag privileged operations (admin-only actions) separately as BFLA candidates
even if they have no path ID parameter. Use these heuristics to detect them
automatically; fall back to asking the user if none match:

- Path segment contains `admin`, `internal`, `management`, `staff`, `system`,
  or `superuser` (e.g. `/admin/users`, `/internal/reports`).
- Operation is in a tag group named `Admin`, `Internal`, `Management`, or similar.
- `security` requirement on the operation references a scheme whose name includes
  `admin` or `superuser`.
- Request body or parameter has a field whose enum or description restricts it to
  admin use (e.g. `role: admin`).
- If none of the above match and the OAS provides no clear signals, call
  `AskUserQuestion`: `"I couldn't automatically detect any privileged operations.
  Are there any admin-only or elevated-privilege endpoints I should test for
  BFLA?"` — options: `["Yes — I'll flag them", "No — skip BFLA testing"]`.

This determines whether a second user (User 2) is needed before credential
prompts are shown, so the user understands why they're being asked for two sets.

### Per-scheme credential collection

For each auth scheme, collect credentials using `AskUserQuestion` — never generate, guess, or suggest values. Collect in this order: User 1 first, then User 2 (BOLA only), then admin (BFLA only).

**Login endpoint** (`POST /login`, `POST /auth/token`, etc. — most common):

Announce which endpoint will be used. Then make a **single** `AskUserQuestion` call sized to the situation:

- **No BOLA found** — use 2 questions:
  - `header: "User 1"`, question: `"What is User 1's username or email?"`  → store as `{{username}}`
  - `header: "User 1"`, question: `"What is User 1's password or PIN?"`    → store as `{{password}}`

- **BOLA found** — use 4 questions (all in the same call):
  - `header: "User 1"`, question: `"What is User 1's username or email?"`                                       → store as `{{username}}`
  - `header: "User 1"`, question: `"What is User 1's password or PIN?"`                                        → store as `{{password}}`
  - `header: "User 2"`, question: `"What is User 2's username or email? (must NOT share User 1's resources)"`  → store as `{{user2Username}}`
  - `header: "User 2"`, question: `"What is User 2's password or PIN?"`                                        → store as `{{user2Password}}`

For BFLA (admin) credentials, use a separate `AskUserQuestion` call after the BOLA pair — collect `{{adminUsername}}` and `{{adminPassword}}` in 2 questions with `header: "Admin"`.

**Bearer / JWT** (no login endpoint in OAS):

- `AskUserQuestion`: `"I need a bearer token for User 1. Do you have one ready, or acquire from an endpoint?"` — options: `["I have a token — I'll paste it", "I need to acquire one — I'll specify the endpoint"]`
  - If paste → ask for the token, store as `{{user1Token}}`
  - If acquire → ask for endpoint, then collect username + password as above
- If BOLA found → repeat for User 2, store as `{{user2Token}}`

**API Key**: `AskUserQuestion` for the key value, store as `{{apiKey}}`. Header/param name from `securitySchemes[*].name` and `in`.

**Basic Auth**: use the same adaptive single-call pattern as Login endpoint — 2 questions (no BOLA) or 4 questions (BOLA). For BFLA admin, use a separate 2-question call with `header: "Admin"`.

**OAuth2**: `AskUserQuestion`: `"Do you have an access token, or use the token endpoint from the OAS?"` — options: `["I have an access token", "Use the token endpoint — I'll provide client credentials"]`. Collect accordingly.

Do not proceed until at least the primary user's credentials are confirmed.

### Writing credential acquisition flows into `authenticationDetails`

When a credential requires a request sequence (e.g. a login call) to acquire its token,
add a `requests` array to the credential object.

**Rule: always use `$ref` to reference an existing operation — never inline `request` objects.**
Inline blocks have no `operationId`, which the VS Code extension rejects with
`Unable to parse request that has no operationId set`. The `42c-ast` CLI accepts both
formats, but the extension does not — always use `$ref` regardless.

**Pattern:**
```json
"<CredentialName>": {
  "description": "<description>",
  "credential": "{{<tokenVar>}}",
  "requests": [
    {
      "$ref": "#/operations/<LoginOperationId>/request",
      "responses": {
        "200": {
          "expectations": { "httpStatus": 200 },
          "variableAssignments": {
            "<tokenVar>": {
              "in": "body", "from": "response", "contentType": "json",
              "path": { "type": "jsonPointer", "value": "/<tokenField>" }
            }
          }
        }
      }
    }
  ]
}
```

Replace `<LoginOperationId>` with the `operationId` of the operation that issues the
token (look for a `POST /login`, `POST /auth/token`, or equivalent). Replace
`<tokenField>` with the JSON Pointer path to the token value in the response body.

**Second user (BOLA):** use `environment` to override the credential variables for that
step without duplicating the operation:
```json
"<SecondCredentialName>": {
  "credential": "{{<secondTokenVar>}}",
  "requests": [
    {
      "$ref": "#/operations/<LoginOperationId>/request",
      "environment": {
        "<usernameVar>": "{{<user2UsernameVar>}}",
        "<passwordVar>": "{{<user2PasswordVar>}}"
      },
      "responses": {
        "200": {
          "expectations": { "httpStatus": 200 },
          "variableAssignments": {
            "<secondTokenVar>": {
              "in": "body", "from": "response", "contentType": "json",
              "path": { "type": "jsonPointer", "value": "/<tokenField>" }
            }
          }
        }
      }
    }
  ]
}
```

`environment` overrides apply only to that single step. The keys must match the template
variable names used in the referenced operation's `requestBody`. If the login operation
uses hardcoded values instead of `{{variables}}`, update its `requestBody` to use
template variables first — otherwise `environment` overrides have no effect.

**Multi-step credential (e.g. register then login):** add multiple entries to `requests`
in sequence. The token capture goes on the last step:
```json
"requests": [
  {
    "$ref": "#/operations/<RegisterOperationId>/request",
    "environment": { "<usernameVar>": "{{<throwawayUser>}}", ... },
    "responses": {
      "201": { "expectations": { "httpStatus": 201 } },
      "409": { "expectations": { "httpStatus": 409 } }
    }
  },
  {
    "$ref": "#/operations/<LoginOperationId>/request",
    "environment": { "<usernameVar>": "{{<throwawayUser>}}", ... },
    "responses": {
      "200": {
        "expectations": { "httpStatus": 200 },
        "variableAssignments": {
          "<tokenVar>": {
            "in": "body", "from": "response", "contentType": "json",
            "path": { "type": "jsonPointer", "value": "/<tokenField>" }
          }
        }
      }
    }
  }
]
```

---

## Step 2.5 — Test Data

Before classifying operations, establish the source of test data for the scan.

**Check the OAS for existing sample data**: scan all operation request bodies and
parameters for `example`, `examples`, or `default` values on their schemas.

Call `AskUserQuestion`:

**If OAS has sample data:**
- **question**: `"Do you have test data to use for testing, or shall I use the samples present in the OAS?"`
- **options**: `["Use OAS samples", "I have my own test data — I'll provide a Postman collection"]`

**If OAS has NO sample data:**
- **question**: `"The OAS doesn't include sample values for request bodies or parameters. Do you have test data available, or will you provide values manually as we go?"`
- **options**: `["I'll provide a Postman collection", "I'll provide values manually as needed"]`

**If the user selects a Postman collection:**
1. Call `AskUserQuestion` — **question**: `"Please share the path to your Postman collection file (v2.1 JSON format)."` — wait for the file path.
2. Parse the Postman v2.1 JSON.
3. Build a test data lookup table keyed by HTTP method + path pattern:
   ```
   { "<METHOD> <path>": { body: {...}, pathVars: {...}, queryParams: {...} } }
   ```
4. Announce: `"Loaded test data from Postman collection: <N> request(s) matched."` 
5. This table is used in Step 3 (classification) and Step 4 (scenario building) to
   auto-populate Class-C operations — no reactive import needed in Step 5.

If re-seeding is needed after a destructive scan operation (Step 3 Class D), use
the seed command captured here. If no seed command was provided and Class-D
operations exist, note to the user that they may need to manually restore test
records between scan runs if the primary user's account is deleted.

---

## Step 3 — Operation Classification

Before writing any scenario into the scan config, analyse every operation in
the OAS and classify it. Before presenting the table, give the user a brief
explanation of the four classes so they can meaningfully validate the results.

### Classification overview

Output this explanation before the table:

```
I've classified every API operation into one of four testing modes:

  A — Standalone      Runs with sample or generated data — no setup needed.
  B — Dependency      Needs a dynamic ID from a prior operation
                      (e.g. create a resource first, then fetch it by ID).
  C — Manual data     Requires values I can't generate automatically —
                      I'll use your Postman collection or ask you to provide them.
  D — Throwaway user  Destroys the currently authenticated account
                      (e.g. DELETE /account) — I'll use a temporary test user
                      to keep your primary session intact.

Here is how I've classified your operations:
```

### Classification categories

**A — Standalone**
All required inputs (path params, query params, request body) can be
satisfied from:
- OAS `example` / `examples` / `default` values on the schema
- Static literal values
- Environment variables (e.g. `{{username}}`, `{{password}}`)
- The `$randomuint` / `$randomstring` macros for uniqueness

**B — Dependency-chain required**
One or more path or query params contain a dynamic ID that can only come from
a prior operation's response body (e.g. `{orderId}`, `{userId}`, `{documentId}`).

Detection heuristic:
1. Identify path params that look like resource IDs (end in `Id`, `Key`, `Ref`,
   or are a UUID/integer field named after a resource).
2. Find the operation that creates or returns that resource (typically a `POST`
   or `GET` on the parent collection path).
3. Find the response body field in that operation's success schema that provides
   the ID value.
4. Propose the chain: `<CreatorOp> → <TargetOp>` with the JSON Pointer to
   extract the variable.

**C — User-data-required**
Inputs cannot be resolved automatically and no plausible creator operation
exists. If a Postman collection was provided in Step 2.5, use values from the
lookup table. Otherwise ask the user to provide the values directly.

**D — Throwaway-user required**
The operation destroys the currently authenticated principal's own resource
(e.g. `DELETE /account`, `DELETE /users/me`, `DELETE /profile`).

**Do NOT use `"skipped": true`** — the scanner ignores this field and will
execute the operation against User1, deleting the primary test user and
breaking all subsequent happy paths in the same run.

Instead: build a multi-step `happy.path` scenario that:
1. Registers a fresh throwaway user (accept both 201 and 409 — idempotent).
2. Logs in as the throwaway user and captures their token.
3. Executes the destructive operation using the throwaway token (override the
   primary token variable for that step via `environment`).

This leaves User1 intact while still validating the operation.

### Example classification table

```
Operation              | Class  | BOLA? | Proposed data source
-----------------------|--------|-------|----------------------------------------------
UserLogin              | A      | no    | env vars: {{username}} / {{password}}
UserRegistration       | A      | no    | $randomuint macro for username/email
CreateResource         | A      | no    | OAS body example + {{userId}} from auth
CancelResource         | B      | yes   | CreateResource → /{resourceId}
RetrieveResource       | B      | yes   | CreateResource → /{resourceId}
UpdateResource         | B      | yes   | CreateResource → /{resourceId}  ← PUT, BOLA
DeleteUser             | B      | yes   | UserRegistration → /{userId}
DeleteAccount          | D      | no    | register+login throwaway → delete throwaway
```

**`BOLA? = yes` has a direct consequence in Step 4:** every operation marked as a BOLA candidate will receive an additional BOLA test scenario (using User 2's token) alongside its happy path scenario. Every operation marked as a BFLA candidate will receive a BFLA test scenario (using User 1's low-privilege token).

Call `AskUserQuestion`:
- **question**: `"Here is the proposed operation classification (shown above). Does this look correct, or do you need to correct any misclassifications?"`
- **options**: `["Yes — proceed", "No — I need to correct some classifications"]`

---

## Step 4 — Build Scenario Chains

For every Class-B operation, inject a multi-step `happy.path` scenario into
the scan config. Show the user each proposed chain in plain English before
writing it.

### Class-B: dependency chain pattern

```json
"scenarios": [
  {
    "key": "happy.path",
    "requests": [
      {
        "$ref": "#/operations/<CreatorOperationId>/request",
        "responses": {
          "<successCode>": {
            "expectations": { "httpStatus": <successCode> },
            "variableAssignments": {
              "<varName>": {
                "in": "body",
                "from": "response",
                "contentType": "json",
                "path": { "type": "jsonPointer", "value": "/<fieldName>" }
              }
            }
          }
        }
      },
      {
        "fuzzing": true,
        "$ref": "#/operations/<TargetOperationId>/request"
      }
    ],
    "fuzzing": true
  }
]
```

The `<varName>` captured from the creator's response is then referenced as
`{{varName}}` in the target operation's `paths` or `queries` array.

### Global `before` block

If multiple operations share the same dependency variable (e.g. many operations
need `customerId` from a login call), add the creator to the global `before`
block rather than repeating it in every scenario:

```json
"before": [
  {
    "$ref": "#/operations/<AuthOp>/request",
    "responses": {
      "200": {
        "expectations": { "httpStatus": 200 },
        "variableAssignments": {
          "customerId": {
            "in": "body", "from": "response", "contentType": "json",
            "path": { "type": "jsonPointer", "value": "/user/customerId" }
          }
        }
      }
    }
  }
]
```

### Class-C: user-provided data

If a Postman collection was imported in Step 2.5, look up the operation in
the test data table and inject the extracted values as static literals in the
`paths` / `queries` / `requestBody.json` fields of the operation's `request`
block. If the operation is not in the table, ask the user to paste the values.

### Class-D: throwaway-user pattern

For operations that delete the primary user's own account, build a 3-step
throwaway chain. First, parameterise the registration operation's request body
so `email` and credential fields use template variables (e.g.
`{{throwawayEmail}}`, `{{throwawayPan}}`), with defaults set in
`environments.default.variables`. Then inject the scenario:

```json
"<DeleteSelfOperationId>": {
  "operationId": "<DeleteSelfOperationId>",
  "scenarios": [
    {
      "key": "happy.path",
      "fuzzing": true,
      "requests": [
        {
          "$ref": "#/operations/<RegisterOperationId>/request",
          "environment": {
            "<emailVar>": "throwaway@example.com",
            "<credentialVar>": "<throwawayCredential>"
          },
          "responses": {
            "201": { "expectations": { "httpStatus": 201 } },
            "409": { "expectations": { "httpStatus": 409 } }
          }
        },
        {
          "$ref": "#/operations/<LoginOperationId>/request",
          "environment": {
            "host": "{{host}}",
            "username": "throwaway@example.com",
            "password": "<throwawayCredential>"
          },
          "responses": {
            "200": {
              "expectations": { "httpStatus": 200 },
              "variableAssignments": {
                "throwawayToken": {
                  "in": "body", "from": "response", "contentType": "json",
                  "path": { "type": "jsonPointer", "value": "/<tokenField>" }
                }
              }
            }
          }
        },
        {
          "$ref": "#/operations/<DeleteSelfOperationId>/request",
          "environment": {
            "<primaryTokenVar>": "{{throwawayToken}}"
          },
          "fuzzing": true
        }
      ]
    }
  ]
}
```

The last step overrides the primary user's token variable (e.g. `user1Token`)
with `throwawayToken` so the `AccessToken/User1` credential sends the
throwaway's JWT. User1 remains untouched.

### BOLA test scenario pattern (BOLA? = yes operations)

For every operation marked `BOLA? = yes` in the Step 3 table, add a second
scenario entry alongside its `happy.path` scenario. The mechanism is identical
to Class-D: override the primary token variable via `environment` — but swap
in `{{user2Token}}` instead of a throwaway token.

**Class-B BOLA candidate** (needs a creator step to obtain a valid resource ID):

```json
{
  "key": "bola.test",
  "requests": [
    {
      "$ref": "#/operations/<CreatorOperationId>/request",
      "responses": {
        "<successCode>": {
          "expectations": { "httpStatus": <successCode> },
          "variableAssignments": {
            "<varName>": {
              "in": "body", "from": "response", "contentType": "json",
              "path": { "type": "jsonPointer", "value": "/<fieldName>" }
            }
          }
        }
      }
    },
    {
      "$ref": "#/operations/<TargetOperationId>/request",
      "environment": { "<primaryTokenVar>": "{{user2Token}}" },
      "responses": {
        "403": { "expectations": { "httpStatus": 403 } },
        "401": { "expectations": { "httpStatus": 401 } }
      }
    }
  ]
}
```

**Class-A BOLA candidate** (resource ID comes from static env vars — no
creator step needed):

```json
{
  "key": "bola.test",
  "requests": [
    {
      "$ref": "#/operations/<TargetOperationId>/request",
      "environment": { "<primaryTokenVar>": "{{user2Token}}" },
      "responses": {
        "403": { "expectations": { "httpStatus": 403 } },
        "401": { "expectations": { "httpStatus": 401 } }
      }
    }
  ]
}
```

`<primaryTokenVar>` is the template variable name used for the bearer token
in the target operation's request (e.g. `user1Token`, `accessToken`). The
`environment` override applies only to this scenario step, leaving all other
scenarios unaffected.

A 2xx response on the `bola.test` scenario is a confirmed BOLA finding. A 401
or 403 means the server enforces ownership — not a finding.

### BFLA test scenario pattern (BFLA candidates)

For every operation flagged as a BFLA candidate (privileged / admin-only),
add a BFLA test scenario that attempts the operation with User 1's
low-privilege token in place of the admin token.

```json
{
  "key": "bfla.test",
  "requests": [
    {
      "$ref": "#/operations/<PrivilegedOperationId>/request",
      "environment": { "<adminTokenVar>": "{{user1Token}}" },
      "responses": {
        "403": { "expectations": { "httpStatus": 403 } },
        "401": { "expectations": { "httpStatus": 401 } }
      }
    }
  ]
}
```

A 2xx response on the `bfla.test` scenario is a confirmed BFLA finding.

---

## Step 5 — Happy Path Validation Run

Before running the full scan, validate all happy paths in strict mode.

### Configure and run

Set `happyPathOnly: true` in `runtimeConfiguration`:

```json
"happyPathOnly": true
```

Leave `laxTestingModeEnabled` at its generated default (`false`). Never set it
to `true` before happy paths are confirmed — in lax mode, fuzzing runs even on
operations with failing happy paths, producing a cascade of false positives.

```bash
# Platform mode
API_KEY="<value>" PLATFORM_HOST="<value>" <binary> scan run --enrich=false \
  <relative-oas-path> --conf-file <CONF_FILE> > /tmp/42c-happy-out.json 2>&1

# Freemium mode
<binary> scan run --enrich=false <relative-oas-path> \
  --freemium-host stateless.42crunch.com:443 \
  --token <FREEMIUM_TOKEN> --conf-file <CONF_FILE> > /tmp/42c-happy-out.json 2>&1
```

Extract only failing happy paths — never include raw output in your response:

```bash
python3 << 'EOF'
import json, re
raw = open("/tmp/42c-happy-out.json").read()
match = re.search(r'\{[\s\S]*\}', raw)
if not match:
    print("No JSON in output"); exit(0)
data = json.loads(match.group())
results = data.get("results", data.get("scanResults", []))
if isinstance(results, dict):
    results = [results]
fails = [
    (r.get("operationId", r.get("path","?")), t.get("testKey","?"), t.get("httpStatus",""), t.get("reason",""))
    for r in results
    for t in r.get("testResults", [])
    if t.get("status") == "fail" and "happy" in t.get("testKey","").lower()
]
if fails:
    print(f"happy_path_failures[{len(fails)}]{{operation,test,status,reason}}:")
    for op, test, code, reason in fails:
        print(f"  {op},{test},{code},{reason[:60]}")
else:
    print("happy_path_failures: none")
EOF
```

### Parse results per operation

For each operation where the happy path failed, determine the root cause:

| Observed symptom | Root cause | Action |
|---|---|---|
| HTTP 400 / 422 with validation error | **Bad sample data** — request body or parameters fail server validation | Use Postman collection lookup table if available; otherwise ask the user to provide valid values |
| HTTP 2xx but conformance FAIL (undocumented fields in response) | **Excessive response data** — server returns fields not in the OAS schema (potential OWASP API3 Excessive Data Exposure) | **Block and call `AskUserQuestion`**: question: `"The response for <operation> includes fields not in your OAS schema: [list fields]. Undocumented fields in responses can expose internal data that clients shouldn't see (OWASP API3). How would you like to handle it?"` options: `["Add these fields to the OAS", "Accept as-is"]`. Do not proceed to the full scan until the user has made an explicit choice for every affected operation. |
| HTTP 2xx but wrong success code (e.g. got `200`, expected `201`) | **Status code mismatch** — `defaultResponse` in the scan config doesn't match reality | Update `defaultResponse` for that operation |
| HTTP 404 | **Unresolved path variable** — scenario chain is missing or the `variableAssignment` JSON Pointer is wrong | Inspect the chain; fix the JSON Pointer, or build a missing chain |
| HTTP 401 / 403 | **Auth failure** — token is invalid, expired, or wrong scheme applied | Re-collect credentials; verify the token is still valid |

**Group all failures by root cause before asking for any user input.** Present
the full failure table first, then resolve one root cause type at a time.

### Postman collection fallback

If an operation still fails with HTTP 400/422 after checking the already-loaded
Step 2.5 lookup table (or no collection was provided), ask the user to supply
the values manually. Do not ask for a new Postman collection — if a collection
was already imported, re-examine the existing lookup table entries for the
failing operation before requesting manual input.

### Iteration

After resolving each batch of failures, re-run using the same command as above (output to `/tmp/42c-happy-out.json`) and re-extract with the same Python snippet.

For each operation where the root cause cannot be resolved (e.g. the required
resource cannot be created in this environment), call `AskUserQuestion`:
- **question**: `"The happy path for <operationId> is still failing (<root-cause summary>). What would you like to do?"`
- **options**: `["Try a different fix", "Skip this operation — I'll come back to it later", "Abort the scan setup"]`

If **Skip** is chosen: record the operation ID and reason in a `skipped_operations` session
variable. Exclude it from all future happy-path re-runs and announce it in the final summary.

Repeat until all **non-skipped** happy paths pass.

### Restore runtime flags

Once all happy paths pass, set `happyPathOnly: false` before the full scan:

```json
"happyPathOnly": false
```

---

## Step 5.5 — Permission Gate Before Full Scan

All happy paths have passed. Before running the full security scan, ask the
user for explicit consent. Call `AskUserQuestion`:

- **question**: `"All happy paths passed successfully. I'm ready to run the full security scan against <SCAN_TARGET_URL>. This will execute authorization tests (BOLA/BFLA) and conformance fuzzing across all <N> operations. Shall I proceed?"`
- **options**: `["Yes — run the full scan", "No — stop here"]`

Only proceed to Step 6 after explicit confirmation.

---

## Step 6 — Full Scan

Run the full scan, capturing output to a temp file for extraction:

```bash
# Platform mode
API_KEY="<value>" PLATFORM_HOST="<value>" <binary> scan run --enrich=false \
  <relative-oas-path> --conf-file <CONF_FILE> > /tmp/42c-scan-out.json 2>&1

# Freemium mode
<binary> scan run --enrich=false <relative-oas-path> \
  --freemium-host stateless.42crunch.com:443 \
  --token <FREEMIUM_TOKEN> --conf-file <CONF_FILE> > /tmp/42c-scan-out.json 2>&1
```

**Immediately after the command completes**, extract the summary as TOON
(Token-Oriented Object Notation — https://github.com/toon-format/toon) —
never include raw stdout content in your response:

```bash
python3 << 'EOF'
import json, re

raw = open("/tmp/42c-scan-out.json").read()
match = re.search(r'\{[\s\S]*\}', raw)
if not match:
    print("No JSON found in scan output"); exit(0)

data = json.loads(match.group())
sqg = "PASSED" if data.get("sqgPass") else ("FAILED" if "sqgPass" in data else "N/A")
print(f"sqgPass: {sqg}")
for d in data.get("sqgDetails", []):
    rules = d.get("blockingRules", [])
    if rules:
        print(f"blockingRules[{len(rules)}]: {', '.join(rules)}")

# Failing test results (structure varies by CLI version)
results = data.get("results", data.get("scanResults", []))
if isinstance(results, dict):
    results = [results]
failures = [
    (r.get("operationId", r.get("path", "?")), t.get("testKey", "?"), t.get("severity", ""))
    for r in results
    for t in r.get("testResults", [])
    if t.get("status") == "fail"
]
if failures:
    print(f"\nfailures[{len(failures)}]{{operation,test,severity}}:")
    for op, test, sev in failures:
        print(f"  {op},{test},{sev}")
else:
    print("failures: none")
EOF
```

Use only the TOON output above when rendering Step 7. Do not load or display
the raw `/tmp/42c-scan-out.json` content.

**Freemium mode**: `sqgPass` will be absent or `true`. Present all findings
informally — no quality gate is enforced. Note to the user:
> "In freemium mode the scan shows all findings for your information — there
> is no automatic quality gate. Authorization failures (red) are real
> vulnerabilities worth fixing regardless of the gate (OWASP API1/API5).
> Conformance findings (yellow) document gaps between your OAS contract and
> your API's actual behaviour."

Then ask which (if any) findings the user wants to address.

### Blocking rule formats

| Rule | Meaning |
|---|---|
| `"severity_threshold"` | High/critical results exceed the SQG limit |
| `"forbidden_test:<test-key>"` | A specific test type is forbidden by the SQG |

---

## Step 7 — Display Results and Apply Fixes

### 7a — Render the risk-classified findings report

Before touching anything, display the full scan picture grouped into three tiers.
Use plain-English descriptions — do not surface raw test keys or scan-report field names.

**Platform mode header:**
```
Scan Results  |  SQG (<sqg-name>): PASSED / FAILED
```

**Freemium mode header:**
```
Scan Results  |  SQG: N/A (Freemium — no scan SQG enforced)
```

```
── 🔴 Authorization Failures (BOLA / BFLA) ────────────────────────────────
  (for each confirmed auth failure)
  Operation:  <HTTP method> <path>
  Test:       BOLA (accessed with user-2 token) / BFLA (accessed with low-priv token)
  Risk:       Horizontal privilege escalation — user B can read/modify user A's
              resources. / Vertical privilege escalation — unprivileged user can
              invoke admin-only operations.
  Fix:        Add / correct `security` requirement on this operation in the OAS.

── 🟠 Conformance — SQG-Blocking ──────────────────────────────────────────
  (for each conformance finding matched in sqgDetails[].blockingRules)
  Operation:  <HTTP method> <path>
  Issue:      <plain-English description of what the API returned vs what the OAS says>
  Severity:   <HIGH / CRITICAL / …>
  Risk:       <what the mismatch means: data over-exposure, broken contract, etc.>
  Fix:        <one-line OAS change to align the contract with reality>

── 🟡 Conformance — Informational (not SQG-blocking) ──────────────────────
  (for each conformance finding NOT in sqgDetails[].blockingRules)
  Operation:  <HTTP method> <path>
  Issue:      <description>
  Severity:   <MEDIUM / LOW / …>
  Note:       This finding does not block the SQG. No automatic fix will be applied.

(write "(none)" in any tier that has no findings)
```

### After rendering — Security implication narratives

If any BOLA finding was confirmed, add:
> "A confirmed BOLA vulnerability means an authenticated user can access or
> modify another user's resources by changing an ID in the URL — this is one
> of the most common and impactful API vulnerabilities (OWASP API1). The OAS
> fix I'm proposing adds or corrects the `security` requirement on the affected
> operation to document the contract correctly; you'll also want to verify your
> server-side authorisation checks the resource owner on each request."

If any BFLA finding was confirmed, add:
> "A confirmed BFLA vulnerability means a low-privilege user can invoke an
> admin-only operation (OWASP API5). The fix documents the required privilege
> level in the OAS; your backend authorisation logic is the definitive
> enforcement point."

---

### 7b — Determine fix candidates

**Platform mode:**
1. All **authorization failures** (BOLA/BFLA confirmed) → always a fix candidate.
2. **Conformance findings matched in `sqgDetails[].blockingRules`** → fix candidate
   regardless of severity.
3. Conformance findings **not** in `sqgDetails[].blockingRules` → surface only;
   do not include in the fix list.

**Freemium mode:**
1. All **authorization failures** (BOLA/BFLA confirmed) → always a fix candidate.
2. There are no SQG-blocking conformance findings — all conformance findings are
   informational. Surface them to the user and ask which (if any) they want to fix.

### 7c — Consent Gate

**Platform mode** — call `AskUserQuestion`:
- **question**: `"Here is the complete scan report (shown above). I can apply the following fixes to <filename>: 🔴 Authorization fixes: [list] 🟠 SQG-blocking conformance fixes: [list]. The 🟡 informational findings are not SQG-blocking and will not be fixed automatically — let me know if you'd like to address any of them too. What would you like to do?"`
- **options**: `["Yes — apply all fixes now", "Show me the diff first", "No — skip fixes for now"]`

**Freemium mode** — call `AskUserQuestion`:
- **question**: `"Here is the complete scan report (shown above). No SQG enforcement applies in freemium mode. 🔴 Authorization fixes I can apply: [list] 🟡 Conformance findings (informational — your call whether to fix): [list]. What would you like to do?"`
- **options**: `["Yes — apply the authorization fixes", "Show me the diff first", "No — skip fixes; summarise findings only"]`

If the user chooses **"Show me the diff first"** in either mode, display the proposed
change for each fix one at a time in unified diff format then call `AskUserQuestion`:
- **question**: `"Apply this change?"` — **options**: `["Yes", "No — skip this one"]`

Only advance to the next fix after the user confirms the current one.

Only apply fixes after explicit user confirmation.

### 7d — Apply fixes

| Finding type | Fix action |
|---|---|
| Authorization — BOLA/BFLA confirmed | Add or correct `security` requirements on the affected operations in the OAS |
| SQG-blocking conformance | Correct response schemas, required fields, or parameter definitions to align the OAS with actual API behaviour |
| Non-SQG-blocking conformance (any severity) | Surface only; ask user if they want to address them |

---

## Flags Reference

```
--conf-file <path>      explicit path to scan config bundle (preferred)
--conf-name <name>      scan config name from .42c dir (default "default")
-d, --directory <path>  working directory (default: .42c at git root)
--tag <cat>:<tag>       apply platform tag for SQGs / data dictionaries
--output-report <file>  write just the config bundle (report section) to file
```

### `scan conf generate` — important notes

- **`<api-reference>` must be a file path** (relative from git root), NOT an alias.
  Aliases are not resolved by `generate` — passing an alias causes "no such file or directory".
- **Do not use `-d` or `--conf-name`** when generating. Using those flags writes a
  fragmented multi-file format to disk instead of outputting the monolithic bundle to stdout.
- Use `--output-report .42c/scan/<alias>/scanconf.json` to save the bundle directly.

### api-reference formats accepted by `scan run` and `scan conf validate`

- Path to an OAS file (`.json` / `.yaml` / `.yml`) — use with `--conf-file`
- Alias defined in `.42c/conf.yaml` — use with `--conf-name`
- `<api-id>:<revision>` (requires valid `API_KEY` — fetched from platform)
