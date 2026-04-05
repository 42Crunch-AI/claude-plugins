[//]: # (Canonical copy lives in 42crunch-scan/references/scan-workflow.md — keep in sync.)

# Scan Workflow

> **Command conventions used throughout this file**
> - `<binary>` — the full path resolved during binary discovery (e.g. `~/.42crunch/bin/42c-ast`). Never call `42c-ast` by name alone unless it is confirmed to be on PATH.
> - **Platform mode**: prefix every command with `API_KEY="<resolved-value>" PLATFORM_HOST="<value>"` (omit `PLATFORM_HOST` to use the value from your environment or `.env` file).
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

### 1c — Set target URL

Use `SCAN42C_HOST` environment variable if set, otherwise `servers[0].url` from the OAS file.
Write it into `environments.default.variables.host` in `CONF_FILE`.

---

## Step 2 — Authentication Setup

Read the OAS `securitySchemes` and global/operation `security` definitions.

| Scheme type | What to collect |
|---|---|
| Bearer / JWT | Token for a primary test user |
| API Key | Key value; confirm header or query param name |
| Basic Auth | Username and password |
| OAuth2 | Token endpoint from OAS; ask for client credentials or access token |
| Login endpoint detected (`POST /login`, `POST /auth/token`, `POST /auth/login`, etc.) | Offer to acquire a token dynamically via the login flow; ask for credentials to supply to the login request |

**BOLA/BFLA second-user identification (do this now, not later):**
Before asking for any credentials, first identify all BOLA/BFLA candidates in
the OAS. Flag every operation where ALL of the following are true:
- The path contains at least one `{…Id}`, `{…Key}`, `{…Ref}`, or equivalent
  resource-ID placeholder.
- The HTTP method is GET, PUT, PATCH, or DELETE (i.e. the operation reads or
  mutates a specific resource instance, not a collection).

HTTP method does NOT gate BOLA candidacy — a PUT or PATCH on `/{resourceId}`
is just as much a BOLA candidate as a DELETE or GET on the same path.

Flag privileged operations (admin-only actions) separately as BFLA candidates
even if they have no path ID parameter.

Name all candidates in the credential collection prompt so the user knows why
two users are needed. Call `AskUserQuestion`:
- **question**: `"I found DELETE /{resource}/{id}, GET /{resource}/{id}, and PATCH /{resource}/{id} as BOLA candidates. I'll need credentials for a second user who should NOT have access to the first user's resources. Can you provide a token or login details for this second user?"`

If elevated privileges are also needed (BFLA), call a separate `AskUserQuestion`
with a clear label (e.g. "admin user").

Do not proceed until at least one valid credential set is confirmed.

### Test data / seed check

Call `AskUserQuestion` before building the scan config:
- **question**: `"Does the API need pre-seeded database records (accounts, users, reference data) to exist before scanning? If the server is freshly started or the database was wiped, happy paths will fail with 404 / 401 even with correct credentials."`
- **options**: `["Yes — I'll seed first", "No — it's ready as-is"]`

If yes — call `AskUserQuestion` — **question**: `"Please share the seed command or procedure so I can record it for re-use after destructive scan operations:"` — confirm it is run before proceeding. Record the seed command so it can be re-run if destructive
operations (see Step 3 Class D) delete test data during a scan run.

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

## Step 3 — Operation Classification

Before writing any scenario into the scan config, analyse every operation in
the OAS and classify it. Present the full table to the user and wait for
confirmation before proceeding.

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
exists. Ask the user to either:
- Provide the values directly (paste into chat)
- Point to a Postman collection or JSON fixtures file (see Postman import below)

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

If the user provides raw values, inject them as static literals in the
`paths` / `queries` / `requestBody.json` fields of the operation's `request`
block. If the user provides a Postman collection, see the Postman import
procedure in Step 5.

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

If re-seeding is needed after a scan run, use the seed command captured in Step 2.

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
API_KEY="<value>" PLATFORM_HOST="<value>" <binary> scan run <relative-oas-path> --conf-file <CONF_FILE>

# Freemium mode
<binary> scan run <relative-oas-path> \
  --freemium-host stateless.42crunch.com:443 \
  --token <FREEMIUM_TOKEN> --conf-file <CONF_FILE>
```

### Parse results per operation

For each operation where the happy path failed, determine the root cause:

| Observed symptom | Root cause | Action |
|---|---|---|
| HTTP 400 / 422 with validation error | **Bad sample data** — request body or parameters fail server validation | Ask the user: provide valid values, or supply a Postman collection |
| HTTP 2xx but conformance FAIL (undocumented fields in response) | **Excessive response data** — server returns fields not in the OAS schema (potential OWASP API3 Excessive Data Exposure) | **Block and call `AskUserQuestion`**: question: `"The response for <operation> includes fields not in your OAS schema: [list fields]. Undocumented fields in responses can expose internal data that clients shouldn't see (OWASP API3). How would you like to handle it?"` options: `["Add these fields to the OAS", "Accept as-is"]`. Do not proceed to the full scan until the user has made an explicit choice for every affected operation. |
| HTTP 2xx but wrong success code (e.g. got `200`, expected `201`) | **Status code mismatch** — `defaultResponse` in the scan config doesn't match reality | Update `defaultResponse` for that operation |
| HTTP 404 | **Unresolved path variable** — scenario chain is missing or the `variableAssignment` JSON Pointer is wrong | Inspect the chain; fix the JSON Pointer, or build a missing chain |
| HTTP 401 / 403 | **Auth failure** — token is invalid, expired, or wrong scheme applied | Re-collect credentials; verify the token is still valid |

**Group all failures by root cause before asking for any user input.** Present
the full failure table first, then resolve one root cause type at a time.

### Postman collection import

If the user provides a Postman collection to fix bad sample data:

1. Parse the collection JSON (v2.1 format).
2. Match each failing operation by HTTP method + URL path pattern to a Postman item.
3. Extract:
   - `body.raw` (JSON) → inject into scan config `requestBody.json`
   - URL path variable values → inject into `paths` array
   - URL query variable values → inject into `queries` array
4. Write the extracted values back into the scan config for those operations.
5. Re-run happy paths for the affected operations only.

### Iteration

After resolving each batch of failures, re-run (using the same mode-appropriate command from above):

```bash
# Platform mode
API_KEY="<value>" PLATFORM_HOST="<value>" <binary> scan run <relative-oas-path> --conf-file <CONF_FILE>

# Freemium mode
<binary> scan run <relative-oas-path> \
  --freemium-host stateless.42crunch.com:443 \
  --token <FREEMIUM_TOKEN> --conf-file <CONF_FILE>
```

Repeat until all reachable happy paths pass, or the user explicitly marks an
operation as skipped (record it with the reason).

### Restore runtime flags

Once all happy paths pass, set `happyPathOnly: false` before the full scan:

```json
"happyPathOnly": false
```

---

## Step 6 — Full Scan

Run the full scan:

```bash
# Platform mode
API_KEY="<value>" PLATFORM_HOST="<value>" <binary> scan run <relative-oas-path> --conf-file <CONF_FILE>

# Freemium mode
<binary> scan run <relative-oas-path> \
  --freemium-host stateless.42crunch.com:443 \
  --token <FREEMIUM_TOKEN> --conf-file <CONF_FILE>
```

**Freemium mode note**: No SQG is enforced by the platform for freemium scan. The
`sqgPass` field in stdout will be absent or `true`. When presenting results in
freemium mode, include this note for the user:

> "In freemium mode, the scan shows all findings for your information — there
> is no automatic quality gate. This means no finding will block your workflow,
> but the authorization failures shown in red are real vulnerabilities worth
> fixing regardless of the gate (OWASP API1/API5). The conformance findings in
> yellow document gaps between your OAS contract and your API's actual behaviour."

Then ask which (if any) findings the user wants to address.

**The SQG result is only in stdout, not in `scan-report.json`.** Parse it from
the JSON output of the command.

### Stdout JSON structure

```json
{
  "sqgPass": true,
  "sqgDetails": [
    {
      "blockingSqgId": "<uuid>",
      "blockingRules": [
        "severity_threshold",
        "forbidden_test:<test-key>"
      ]
    }
  ],
  "statusCode": 0,
  "statusMessage": "success"
}
```

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
