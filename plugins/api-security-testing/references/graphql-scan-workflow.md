# GraphQL Scan Workflow

Applies when pre-flight resolved `API_TYPE=graphql`. This is the GraphQL
sibling of `./scan-workflow.md` — live conformance and authorization testing of
a GraphQL endpoint against its schema. It mirrors that file's phases, consent
gates, and modes, with GraphQL-specific commands, config authoring, and result
handling.

> **Command conventions used throughout this file**
> - `<binary>` — the full path resolved during binary discovery (e.g. `~/.42crunch/bin/42c-ast`). Never call `42c-ast` by name alone unless it is confirmed to be on PATH.
> - **Never write a literal credential value into a command.** Load credentials from the conf file into the environment first, then let the command inherit them — the raw value must never appear in a command string, tool output, or chat message.
> - **Platform mode**: before every command, load credentials — macOS/Linux: `set -a; . "$HOME/.42crunch/conf/env"; set +a`; Windows: `Get-Content "$env:APPDATA\42Crunch\conf\env" | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }`. The command then inherits `API_KEY`/`PLATFORM_HOST` — no explicit prefix needed.
> - **Token mode**: load `TRIAL_TOKEN` the same way, then add `--freemium-host stateless.42crunch.com:443` and `--token "$TRIAL_TOKEN"` (macOS/Linux) or `--token $env:TRIAL_TOKEN` (Windows) to every command — never the literal token.
> - **`--graphql` on every scan command.** `scan conf generate`, `scan conf validate`, and `scan run` all require `--graphql` for a GraphQL schema. Without it the binary treats the input as OAS and fails.
> - **Schema analysis is done once, in the calling skill.** The skill's scan-preview step already counted queries and mutations and identified dependency, BOLA, and BFLA candidates. Reuse those results instead of re-reading the schema.

---

## GraphQL scan config essentials

Read this before Step 1 — these are the differences from the OAS scan config
that every later step depends on.

- **Operations** are keyed `query-<field>` / `mutation-<field>` (e.g.
  `query-book`, `mutation-addBook`). Every operation is a `POST` to `{{host}}`;
  the GraphQL document lives in `request.details.requestBody.json` as
  `{ "query": "...", "variables": { ... } }`.
- **Responses** are keyed `"default"` (the generated `defaultResponse`), not by
  HTTP status. GraphQL servers usually answer `200` even for errors — the
  scan judges each response by its GraphQL `errors`/`data`, not the status
  alone.
- **`scan conf generate --graphql` does not emit `authenticationDetails`** — a
  GraphQL schema declares no security schemes. You add them in Step 2; once
  added, they work exactly as in the OAS scan (credential substitution,
  per-user credentials, authorization tests).
- **Accept header.** The generated `Accept` header is
  `application/graphql-response+json;charset=utf-8, application/json;charset=utf-8`,
  so many servers answer with `application/graphql-response+json`. The scan's
  response capture (`variableAssignments`) accepts only `application/json` — see
  Step 6 for the narrowing rule.

---

## Step 1 — Locate or Create Scan Config

> **Token mode**: omit `--tag` and `--report-sqg` from all commands in this step.

### 1a — Resolve git root and alias

Identical to `./scan-workflow.md` Step 1a, with one change: derive the alias
from the schema. GraphQL SDL has no `info.title`, so use the **schema filename
stem** (lowercase; spaces/underscores/special chars → hyphens; collapse and
trim hyphens). Example: `Books Schema.graphql` → `books-schema`. Record the
`.42c/conf.yaml` entry against the relative schema path exactly as the OAS flow
does.

### 1b — Check for existing scan config

Resolve the config from the **filesystem only** (never VCS), same rule as the
OAS workflow. Check whether `.42c/scan/<alias>/scanconf.json` exists on disk.

**If it exists** → store `CONF_FILE=.42c/scan/<alias>/scanconf.json` and go to
Step 1c.

**If it does not exist:**

```bash
mkdir -p .42c/scan/<alias>
```

Generate a baseline config. `--graphql` and `--hosts` are **required** for
GraphQL (`--hosts` seeds the `host` variable; pass `SCAN_TARGET_URL`). The
api-reference is the **relative schema path**, not an alias.

```bash
# Platform mode
set -a; . "$HOME/.42crunch/conf/env"; set +a
<binary> scan conf generate --graphql \
  --hosts "<SCAN_TARGET_URL>" \
  --output-format json \
  --output .42c/scan/<alias>/scanconf.json \
  [--tag <category>:<tag>] \
  <relative-schema-path>

# Token mode
set -a; . "$HOME/.42crunch/conf/env"; set +a
<binary> scan conf generate --graphql \
  --freemium-host stateless.42crunch.com:443 \
  --token "$TRIAL_TOKEN" \
  --hosts "<SCAN_TARGET_URL>" \
  --output-format json \
  --output .42c/scan/<alias>/scanconf.json \
  <relative-schema-path>
```

Check the status object: `statusCode: 0` → store `CONF_FILE` and proceed;
`statusCode: 3` + `limits_reached` (token mode) → follow `./token-limit.md`;
any other non-zero → surface the error and stop.

The generated config already wires `host` to `SCAN42C_HOST` with your
`--hosts` value as the default.

**Normalization (required):** set `runtimeConfiguration.reportGenerateCurlCommand`
to `false` in the generated config. The binary generates it as `true`, which
embeds a full curl string in every test request that this workflow never reads.
```json
"reportGenerateCurlCommand": false
```

### 1c — Confirm target URL and validate

`scan conf generate --graphql --hosts` already wrote `SCAN_TARGET_URL` into
`environments.default.variables.host`. Confirm it matches the URL resolved in
the skill; if the skill resolved a different URL (e.g. from `SCAN42C_HOST`),
update the `default` field. Then run the validation checkpoint (Step 7) once
before continuing to Step 2.

---

## Step 2 — Authentication Setup

GraphQL schemas carry no security schemes, so **auth is always added by
hand** — as a standard `authenticationDetails` block, exactly the mechanism the
OAS scan uses. The scan substitutes the credential into every request and masks
it in the report.

### Collect the auth style and credentials

Determine the auth style from the user (GraphQL schemas don't declare it).
Call `AskUserQuestion` — never generate or guess values:
- **question**: `"How does your GraphQL API authenticate requests?"` — options:
  `["Bearer token from a login mutation", "Bearer token I already have", "API key in a header", "No authentication"]`

Then collect what that style needs, for **User 1** first. If the skill's
preview found BOLA candidates, also collect **User 2** (a second, non-admin
account); if it found BFLA candidates, also collect an **admin** account. Use
the same adaptive single-call collection as `./scan-workflow.md` Step 2:
- **Login mutation** → which mutation logs in (e.g. `login`), its argument
  names, the JSON field holding the token in its response, and each user's
  login values.
- **Existing bearer token** → the token per user.
- **API key** → the header name (e.g. `X-API-Key`) and the key per user.
- **No authentication** → skip the rest of Step 2. BOLA/BFLA tests need
  authenticated users, so skip them too and say so in the scan preview.

### Wire `authenticationDetails`

Declare each secret as an environment-sourced variable in
`environments.default.variables`, using the same shape and conventions as
`./scan-workflow.md` Step 1 (`"from": "environment"`, a `SCAN42C_*` name,
`"required": false`).

**API key** (one credential per user):

```json
"authenticationDetails": [
  {
    "ApiKeyAuth": {
      "type": "apiKey", "in": "header", "name": "<header-name>",
      "default": "User1",
      "credentials": {
        "User1": { "description": "user 1", "credential": "{{user1ApiKey}}" },
        "User2": { "description": "user 2", "credential": "{{user2ApiKey}}" }
      }
    }
  }
]
```

**Existing bearer token**: same shape with `"type": "bearer"` (no `in`/`name`);
each credential is `"{{user1Token}}"`, etc.

**Bearer token from a login mutation**: each credential calls the login
mutation and captures the token from its response. The pointer digs through
the GraphQL envelope — `/data/<loginField>` when the mutation returns the
token directly, `/data/<loginField>/<tokenField>` when it returns an object:

```json
"authenticationDetails": [
  {
    "BearerAuth": {
      "type": "bearer",
      "default": "User1",
      "credentials": {
        "User1": {
          "credential": "{{AccessToken}}",
          "requests": [
            {
              "$ref": "#/operations/mutation-login/request",
              "environment": { "loginUser": "<user1-username>", "loginPassword": "{{user1Password}}" },
              "responses": {
                "default": {
                  "expectations": { "httpStatus": 200 },
                  "variableAssignments": {
                    "AccessToken": {
                      "in": "body", "from": "response", "contentType": "json",
                      "path": { "type": "jsonPointer", "value": "/data/login" }
                    }
                  }
                }
              }
            }
          ]
        }
      }
    }
  }
]
```

Add `User2` / `Admin` credentials the same way, each with its own
`environment` values. For the login mutation itself:
- set its GraphQL variables to the template variables
  (`"variables": { "username": "{{loginUser}}", "password": "{{loginPassword}}" }`);
- declare `loginUser` / `loginPassword` in `environments.default.variables`
  with **User 1's** values — the login operation's own happy path needs them;
  the credential `environment` blocks override them per user;
- narrow its `Accept` header (Step 6) — its response is captured;
- give it **no** `auth` entry.

### Apply the credential to operations

Add `"auth": ["<Scheme>/User1"]` to every operation's `request` object (the
sibling of `request.request`), except the login mutation. Operations that only
an admin may call (BFLA candidates, Step 5) take `"auth": ["<Scheme>/Admin"]`
instead, so their happy path runs as the admin.

Do not proceed until User 1's credential is wired (or the user chose
"No authentication").

---

## Step 3 — Test Data

Identical in intent to `./scan-workflow.md` Step 3, adapted to GraphQL:

- The generated config fills every argument with a random value. Collect real
  values for arguments that must reference existing data (ids, accepted enum
  values) — a short `AskUserQuestion` capturing the specific values is usually
  enough, since Postman/Insomnia collections are unusual for GraphQL.
- **Check every `Int` argument.** The generator can emit `Int` values outside
  GraphQL's 32-bit range (e.g. `3073621246227064300`), which the server rejects
  with `Int cannot represent non 32-bit signed integer value` — so the happy
  path fails before anything is tested. Replace each generated `Int` value in
  `requestBody.json.variables` with a realistic in-range value.
- **Audit fixes improve test data.** When the schema constrains its scalars
  (custom scalars with `@stringValue(minLength, maxLength, pattern)` /
  `@numberValue(min, max)` from `./graphql-audit-workflow.md`), the generator
  produces values that satisfy them, including in-range integers. If the audit
  has not been run, suggest it.
- Reserve built-in variables (Step 4) for uniqueness-constrained mutation
  arguments (e.g. a title/email that must be unique per iteration).

---

## Step 4 — Built-in Variables

Built-in variables behave exactly as in `./scan-workflow.md` Step 4
(`{{$randomString}}`, `{{$randomuint}}`, `{{$uuid}}`, `{{$timestamp}}`,
`{{$timestamp3339}}`, `{{$randomFromSchema}}`) and are placed the same way — in
the **scenario request step's `environment` block**, never in
`environments.default.variables`.

For GraphQL, the value is wired into a **GraphQL variable**, so the operation's
`requestBody.json.variables.<name>` must reference the template variable and the
scenario `environment` supplies it:

```json
"operations": {
  "mutation-addBook": {
    "request": { "request": { "details": { "requestBody": { "json": {
      "query": "mutation HappyPathRequest($title: String!, ...){ addBook(title: $title, ...){ id } }",
      "variables": { "title": "{{bookTitle}}", "author": "...", "year": 2024, "genre": "Fiction" }
    }}}}},
    "scenarios": [
      { "key": "happy.path", "fuzzing": true,
        "requests": [
          { "fuzzing": true, "$ref": "#/operations/mutation-addBook/request",
            "environment": { "bookTitle": "book-{{$randomString}}" } }
        ] }
    ]
  }
}
```

**Rule — uniqueness-constrained mutation arguments**: any mutation argument
that must be unique across iterations (title, email, username, external id)
must use a built-in variable in **every** `environment` block that supplies it
(happy-path scenario, dependency-chain creator steps, and global `before`),
not just one place.

---

## Step 5 — Operation Classification

Classify every query and mutation, then show the user a table and get explicit
confirmation before writing config — same discipline as `./scan-workflow.md`
Step 5. GraphQL uses the same four classes, reinterpreted:

```
A — Standalone      Arguments are scalars satisfiable from samples/generated
                    data (e.g. query books, mutation addBook).
B — Dependency      Needs an id/value from a prior operation's response
                    (e.g. query book(id) needs a mutation addBook first).
C — Manual data     Needs a value only you can provide (an existing id the
                    server already has, a valid enum).
D — Throwaway       A mutation that destroys the authenticated principal
                    (e.g. mutation deleteMyAccount) — rare in GraphQL.
```

**Dependency detection for GraphQL:** an operation is Class-B when a
non-nullable argument is an id/reference to an object that another mutation
creates (e.g. `book(id: ID!)` depends on `addBook{ id }`). Find the creator
mutation whose selection set returns that id, and note the JSON Pointer to it
in the response — for GraphQL that is `/data/<mutationField>/<idField>` (e.g.
`/data/addBook/id`).

**BOLA candidates:** queries and mutations that take a client-supplied
reference to an existing object (an `ID`-typed argument, or an argument named
`*Id`/`*Key`/`*Ref`, including fields of an input object) and act on or return
that object — e.g. `book(id)`, `updateOrder(orderId, …)`,
`transfer(input: {fromAccountId, …})`. Exclude pure list queries and
create-new mutations. Every BOLA candidate is also Class-B: User 1 must create
the object first so User 2 has something to reach for.

**BFLA candidates:** operations meant for a more privileged role — admin or
management fields (`adminStats`, `purgeBooks`, `setUserRole`), operations on
other users' accounts, or bulk/destructive mutations. Confirm the list with
the user, as in `./scan-workflow.md`.

The table has `Operation | Class | BOLA? | BFLA? | Proposed data source / chain`.

Show the table, then call `AskUserQuestion`:
- **question**: `"Does this classification look correct, or do you need to correct any of it?"`
- **options**: `["Yes — proceed", "No — I need to correct some"]`

---

## Step 6 — Build Scenario Chains

For every Class-B operation, seed the required id before the target request
runs. Prefer the operation-level `before` block (it mirrors the OAS workflow
and is what the BOLA replay re-runs):

```json
"query-book": {
  "request": { "request": { "details": { "requestBody": { "json": {
    "query": "query HappyPathRequest($id: ID!){ book(id: $id){ id title } }",
    "variables": { "id": "{{seededBookId}}" }
  }}}}},
  "before": [
    {
      "$ref": "#/operations/mutation-addBook/request",
      "environment": { "bookTitle": "seed-{{$randomString}}" },
      "responses": {
        "default": {
          "expectations": { "httpStatus": 200 },
          "variableAssignments": {
            "seededBookId": {
              "in": "body", "from": "response", "contentType": "json",
              "path": { "type": "jsonPointer", "value": "/data/addBook/id" }
            }
          }
        }
      }
    }
  ],
  "scenarios": [
    { "key": "happy.path", "fuzzing": true,
      "requests": [ { "fuzzing": true, "$ref": "#/operations/query-book/request" } ] }
  ]
}
```

**Accept-header narrowing (mandatory for every captured response):** the
capture parser accepts only `application/json`. With the generated `Accept`
header the server may answer `application/graphql-response+json`, and the
capture fails with `only application/json content type is supported` — the
dependent operation's happy path then fails. Narrow the `Accept` header of
**every operation whose response is captured** (`before` creators, global
`before` creators, and the login mutation) in its `request.details.headers`:

```json
{ "key": "Accept", "value": "application/json;charset=utf-8" }
```

Operations whose responses are never captured can keep the generated header.

- The JSON Pointer digs through the GraphQL envelope: `/data/<field>/<idField>`.
- A **global `before` block** (top-level `before[]`) also works for values
  shared by many operations; capture with `variableAssignments` the same way
  and narrow its creator's Accept header. Never use the global `before` to
  provision users — the scan assumes accounts already exist.
- **DELETE-style mutations** that destroy the seeded object: follow the
  `./scan-workflow.md` rule — put the creator as the first request inside the
  scenario, so the BOLA replay re-seeds the object.

Show each proposed chain to the user in plain English before writing it.

### 6b — Authorization tests (BOLA/BFLA)

Wire these only for the candidates the user confirmed in Step 5, and only when
the required second credential (User 2 for BOLA, Admin for BFLA) exists in
`authenticationDetails`. Define each test once at the top level:

```json
"authorizationTests": {
  "Bola": {
    "key": "authentication-swapping-bola",
    "source": ["<Scheme>/User1"],
    "target": ["<Scheme>/User2"]
  },
  "Bfla": {
    "key": "authentication-swapping-bfla",
    "source": ["<Scheme>/Admin"],
    "target": ["<Scheme>/User1"]
  }
}
```

Then tag each candidate operation with `"authorizationTests": ["Bola"]` or
`["Bfla"]` at the operation level. The scan replays the operation's happy path
with the target credential swapped in: for BOLA, User 2 reaches for the object
User 1's `before` creator just made; for BFLA, User 1 calls the admin
operation.

---

## Step 7 — Config Validation Checkpoint

Run after Step 1c and after any edit to `CONF_FILE`, before any scan run.

```bash
# Platform mode
set -a; . "$HOME/.42crunch/conf/env"; set +a
<binary> scan conf validate --graphql <relative-schema-path> \
  --conf-file <CONF_FILE> > /tmp/42c-gql-validate.json

# Token mode
set -a; . "$HOME/.42crunch/conf/env"; set +a
<binary> scan conf validate --graphql <relative-schema-path> \
  --freemium-host stateless.42crunch.com:443 --token "$TRIAL_TOKEN" \
  --conf-file <CONF_FILE> > /tmp/42c-gql-validate.json
```

```bash
python3 -c "
import json
s = json.load(open('/tmp/42c-gql-validate.json'))
r = s.get('report') or {}
print('statusCode:', s.get('statusCode'), s.get('statusMessage', ''))
print('valid:', r.get('valid'), ' runnable:', r.get('runnable'))
for e in r.get('errors') or []:
    print('  error:', e)
"
```

- `statusCode` non-zero → surface `statusMessage` and stop (`3` +
  `limits_reached` in token mode → `./token-limit.md`).
- `valid`/`runnable` false or any `error` lines → fix the config and re-run.

`scan conf validate` catches structural errors such as an unresolved `$ref`.
It does **not** check two GraphQL specifics — confirm them yourself before
continuing:
- every `{{variable}}` used in a header, query, GraphQL variable, or credential
  is declared in `environments.default.variables` or assigned earlier in its
  chain (`variableAssignments` or an `environment` block);
- every operation whose response is captured has its `Accept` header narrowed
  (Step 6).

---

## Step 8 — Happy Path Validation Run

Set `happyPathOnly: true` in `runtimeConfiguration`, leave
`laxTestingModeEnabled: false`, then run. `--graphql` is required.

Write the report with `--output` and redirect the small stdout status object
to a separate status file. `scan run` refuses to overwrite an existing
`--output` file (`statusCode: 12`, `file_already_exists`), so each command
deletes the previous report first — keep that line when re-running.

```bash
# macOS / Linux — Platform mode
set -a; . "$HOME/.42crunch/conf/env"; set +a
rm -f /tmp/42c-gql-happy-report.json
<binary> scan run --graphql --enrich=false \
  --output /tmp/42c-gql-happy-report.json --output-format json \
  <relative-schema-path> --conf-file <CONF_FILE> > /tmp/42c-gql-happy-status.json

# macOS / Linux — Token mode
set -a; . "$HOME/.42crunch/conf/env"; set +a
rm -f /tmp/42c-gql-happy-report.json
<binary> scan run --graphql --enrich=false \
  --freemium-host stateless.42crunch.com:443 --token "$TRIAL_TOKEN" \
  --output /tmp/42c-gql-happy-report.json --output-format json \
  <relative-schema-path> --conf-file <CONF_FILE> > /tmp/42c-gql-happy-status.json
```

```powershell
# Windows — Platform mode
Get-Content "$env:APPDATA\42Crunch\conf\env" | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }
Remove-Item "$env:TEMP\42c-gql-happy-report.json" -ErrorAction SilentlyContinue
& <binary> scan run --graphql --enrich=false `
  --output "$env:TEMP\42c-gql-happy-report.json" --output-format json `
  <relative-schema-path> --conf-file <CONF_FILE> > "$env:TEMP\42c-gql-happy-status.json"

# Windows — Token mode
Get-Content "$env:APPDATA\42Crunch\conf\env" | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }
Remove-Item "$env:TEMP\42c-gql-happy-report.json" -ErrorAction SilentlyContinue
& <binary> scan run --graphql --enrich=false `
  --freemium-host stateless.42crunch.com:443 --token $env:TRIAL_TOKEN `
  --output "$env:TEMP\42c-gql-happy-report.json" --output-format json `
  <relative-schema-path> --conf-file <CONF_FILE> > "$env:TEMP\42c-gql-happy-status.json"
```

Extract only failing happy paths — never load raw output into your response.
Each operation's happy-path result is in
`report.operations["<op>"].scenarios[]`. A happy path passed only when
`outcome.testSuccessful` is `true`; do not filter on `outcome.status`, which can
read `"correct"` for a response that still failed (e.g. non-conformant). The
snippet also decodes the response body so GraphQL `errors` (returned with HTTP
200) are visible.

```bash
# macOS / Linux
python3 << 'EOF'
import json, re, base64
status = json.load(open("/tmp/42c-gql-happy-status.json"))
if status.get("statusCode") != 0:
    print(f"scan_error: statusCode={status.get('statusCode')} {status.get('statusMessage','')}")
    raise SystemExit(0)
report = json.load(open("/tmp/42c-gql-happy-report.json"))

def graphql_error(b64):
    """First GraphQL error message in a raw HTTP response, if any."""
    if not b64:
        return ""
    raw = base64.b64decode(b64).decode("utf-8", "replace")
    parts = re.split(r"\r?\n\r?\n", raw, maxsplit=1)
    try:
        errors = json.loads(parts[1] if len(parts) > 1 else raw).get("errors") or []
    except (ValueError, AttributeError):
        return ""
    return errors[0].get("message", "") if errors else ""

fails = []
for op_id, op in (report.get("operations") or {}).items():
    for s in op.get("scenarios") or []:
        o = s.get("outcome") or {}
        if o.get("testSuccessful") is True:
            continue
        resp = s.get("response") or {}
        detail = o.get("error") or graphql_error(resp.get("rawPayload"))
        if not detail and o.get("apiResponseAnalysis"):
            detail = o["apiResponseAnalysis"][0].get("responseDescription", "")
        fails.append((op_id, o.get("status", "?"), resp.get("httpStatusCode", ""),
                      str(detail).replace(",", ";")[:120]))
if fails:
    print(f"happy_path_failures[{len(fails)}]{{operation,status,http,detail}}:")
    for f in fails:
        print("  " + ",".join(str(x) for x in f))
else:
    print("happy_path_failures: none")
EOF
```

```powershell
# Windows
$status = Get-Content "$env:TEMP\42c-gql-happy-status.json" -Raw | ConvertFrom-Json
if ($status.statusCode -ne 0) { Write-Host "scan_error: statusCode=$($status.statusCode) $($status.statusMessage)"; exit }
$report = Get-Content "$env:TEMP\42c-gql-happy-report.json" -Raw | ConvertFrom-Json
function Get-GraphQLError($b64) {
    if (-not $b64) { return '' }
    $txt = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64))
    $body = ($txt -split "(?s)\r?\n\r?\n", 2)[-1]
    try { $doc = $body | ConvertFrom-Json } catch { return '' }
    if ($doc.errors) { return [string]@($doc.errors)[0].message } else { return '' }
}
$fails = @()
foreach ($p in $report.operations.PSObject.Properties) {
    foreach ($s in @($p.Value.scenarios)) {
        if (-not $s -or $s.outcome.testSuccessful -eq $true) { continue }
        $detail = if ($s.outcome.error) { [string]$s.outcome.error } else { Get-GraphQLError $s.response.rawPayload }
        if (-not $detail -and $s.outcome.apiResponseAnalysis) { $detail = [string]@($s.outcome.apiResponseAnalysis)[0].responseDescription }
        $detail = $detail -replace ',', ';'
        $detail = $detail.Substring(0, [Math]::Min(120, $detail.Length))
        $fails += "$($p.Name),$($s.outcome.status),$($s.response.httpStatusCode),$detail"
    }
}
if ($fails.Count -gt 0) {
    Write-Host "happy_path_failures[$($fails.Count)]{operation,status,http,detail}:"
    foreach ($f in $fails) { Write-Host "  $f" }
} else {
    Write-Host "happy_path_failures: none"
}
```

Root-cause table (GraphQL specifics differ from OAS):

| Symptom | Root cause | Action |
|---|---|---|
| `only application/json content type is supported` | A captured response's `Accept` header was not narrowed | Narrow that operation's `Accept` header (Step 6) |
| `Int cannot represent non 32-bit signed integer value` | Generated `Int` value out of range | Set a realistic value for that argument (Step 3) |
| `variable <name> not defined in the context` | A `{{variable}}` is not declared or assigned | Declare it in `environments.default.variables` (for the login mutation: Step 2) |
| HTTP 200 with a GraphQL error (bad argument, unknown enum, `Cannot return null for non-nullable field`) | Invalid test data, or a resolver failing | Provide valid values (Step 3); a resolver crash on valid input is a server bug to report to the user |
| HTTP 401/403 | Credential missing, wrong, or expired | Re-check the Step 2 `authenticationDetails` and the operation's `auth` entry |
| Dependency target fails: cannot extract value with the JSON pointer | Capture pointer wrong, or the creator itself failed | Check the creator's own happy path first, then the `/data/<field>/<idField>` pointer |

Iterate fix → re-run until all non-skipped happy paths pass. Then run the
**Database Reset Reminder** (identical to `./scan-workflow.md` — the happy
paths just mutated live data) and set `happyPathOnly: false`.

---

## Step 9 — Permission Gate Before Full Scan

Same as `./scan-workflow.md` Step 9. Call `AskUserQuestion`:
- **question**: `"All happy paths passed. I'm ready to run the full scan against <SCAN_TARGET_URL> — this fuzzes all <N> queries and mutations against your schema contract[, and runs authorization tests (BOLA/BFLA) on <K> operations]. Shall I proceed?"`
- **options**: `["Yes — run the full scan", "No — stop here"]`

---

## Step 10 — Full Scan

Same command as Step 8 with `happyPathOnly: false`, adding `--report-sqg` in
platform mode, and writing to the full-scan files.

```bash
# macOS / Linux — Platform mode
set -a; . "$HOME/.42crunch/conf/env"; set +a
rm -f /tmp/42c-gql-scan-report.json
<binary> scan run --graphql --enrich=false --report-sqg \
  --output /tmp/42c-gql-scan-report.json --output-format json \
  <relative-schema-path> --conf-file <CONF_FILE> > /tmp/42c-gql-scan-status.json

# macOS / Linux — Token mode
set -a; . "$HOME/.42crunch/conf/env"; set +a
rm -f /tmp/42c-gql-scan-report.json
<binary> scan run --graphql --enrich=false \
  --freemium-host stateless.42crunch.com:443 --token "$TRIAL_TOKEN" \
  --output /tmp/42c-gql-scan-report.json --output-format json \
  <relative-schema-path> --conf-file <CONF_FILE> > /tmp/42c-gql-scan-status.json
```

(Windows: the Step 8 Windows blocks with `--report-sqg` added in platform mode,
deleting and writing `$env:TEMP\42c-gql-scan-report.json` and `…-status.json`.)

Extract the summary as TOON — never include raw report content. The report
shape is identical to the OAS scan report: `sqgPass` / `sqgDetails[].blockingRules`
in the status object, and per-operation results under
`report.operations["<op>"]` (`conformanceRequestsResults[]`,
`authorizationRequestsResults[]`). Reuse the extraction snippet from
`./scan-workflow.md` Step 10 unchanged except for the two file paths
(`/tmp/42c-gql-scan-status.json` and `/tmp/42c-gql-scan-report.json`).

---

## Step 11 — Database Reset Reminder (After Full Scan)

Identical to `./scan-workflow.md` Step 11.

---

## Step 12 — Display Results and Apply Fixes

Same structure as `./scan-workflow.md` Step 12 — three tiers (🔴 Authorization,
🟠 Conformance SQG-blocking, 🟡 Conformance informational), the same fix
candidate rules, consent gate, and verification loop — with the GraphQL
differences below.

### 12a-0 — Confirm authorization findings (GraphQL)

Confirm each BOLA/BFLA finding before rendering it. The engine flags a swapped
request whose response does not look like a refusal, and GraphQL servers often
refuse with **HTTP 200 and a GraphQL error** (e.g. `FORBIDDEN`) — which the
engine reports as a finding. So the status code is not evidence: a finding is
confirmed only when the attacker's response actually carries data for the
operation's field.

```bash
# macOS / Linux
python3 << 'EOF'
import json, re, base64
report = json.load(open("/tmp/42c-gql-scan-report.json"))

def body(b64):
    """Parsed JSON body of a raw HTTP response (base64), or None."""
    if not b64:
        return None
    raw = base64.b64decode(b64).decode("utf-8", "replace")
    parts = re.split(r"\r?\n\r?\n", raw, maxsplit=1)
    try:
        return json.loads(parts[1] if len(parts) > 1 else raw)
    except ValueError:
        return None

def field_value(doc, field):
    return ((doc or {}).get("data") or {}).get(field)

rows = []
for op_id, op in (report.get("operations") or {}).items():
    findings = [e for e in op.get("authorizationRequestsResults") or []
                if "swapping" in (e.get("test") or {}).get("key", "")
                and (e.get("outcome") or {}).get("status") == "defective"]
    if not findings:
        continue
    kind, _, field = op_id.partition("-")          # query-book -> ("query", "book")
    owner = None
    for s in op.get("scenarios") or []:
        owner = field_value(body((s.get("response") or {}).get("rawPayload")), field)
        if owner is not None:
            break
    for e in findings:
        attacker_doc = body((e.get("response") or {}).get("rawPayload"))
        value = field_value(attacker_doc, field)
        errors = (attacker_doc or {}).get("errors") or []
        test = (e.get("test") or {}).get("key", "?").replace("authentication-swapping-", "")
        if value is None or value is False:
            reason = (errors[0].get("extensions", {}).get("code") or errors[0].get("message", "")) if errors else "no data"
            verdict, detail = "rejected", f"server refused ({reason})"
        elif kind == "mutation":
            verdict, detail = "confirmed", "mutation executed with the attacker's credential"
        elif value == owner:
            verdict, detail = "confirmed", "attacker received the owner's object"
        else:
            verdict, detail = "needs_review", "attacker got data, but not the owner's object (owner-scoped?)"
        rows.append((op_id, test.upper(), verdict, detail.replace(",", ";")))

if rows:
    print(f"authorization_findings[{len(rows)}]{{operation,test,verdict,detail}}:")
    for r in rows:
        print("  " + ",".join(r))
else:
    print("authorization_findings: none")
EOF
```

```powershell
# Windows
$report = Get-Content "$env:TEMP\42c-gql-scan-report.json" -Raw | ConvertFrom-Json
function Get-Body($b64) {
    if (-not $b64) { return $null }
    $txt = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64))
    $raw = ($txt -split "(?s)\r?\n\r?\n", 2)[-1]
    try { return $raw | ConvertFrom-Json } catch { return $null }
}
$rows = @()
foreach ($p in $report.operations.PSObject.Properties) {
    $op = $p.Value
    $findings = @($op.authorizationRequestsResults | Where-Object { $_.test.key -like '*swapping*' -and $_.outcome.status -eq 'defective' })
    if (-not $findings) { continue }
    $kind, $field = $p.Name -split '-', 2
    $owner = $null
    foreach ($s in @($op.scenarios)) {
        $doc = Get-Body $s.response.rawPayload
        if ($doc -and $doc.data -and $null -ne $doc.data.$field) { $owner = $doc.data.$field; break }
    }
    foreach ($e in $findings) {
        $doc = Get-Body $e.response.rawPayload
        $value = if ($doc -and $doc.data) { $doc.data.$field } else { $null }
        $test = ($e.test.key -replace 'authentication-swapping-', '').ToUpper()
        if ($null -eq $value -or $value -eq $false) {
            $reason = if ($doc -and $doc.errors) { $err = @($doc.errors)[0]; if ($err.extensions.code) { $err.extensions.code } else { $err.message } } else { 'no data' }
            $rows += "$($p.Name),$test,rejected,server refused ($reason)"
        } elseif ($kind -eq 'mutation') {
            $rows += "$($p.Name),$test,confirmed,mutation executed with the attacker's credential"
        } elseif (($value | ConvertTo-Json -Depth 20 -Compress) -eq ($owner | ConvertTo-Json -Depth 20 -Compress)) {
            $rows += "$($p.Name),$test,confirmed,attacker received the owner's object"
        } else {
            $rows += "$($p.Name),$test,needs_review,attacker got data; but not the owner's object (owner-scoped?)"
        }
    }
}
if ($rows.Count -gt 0) {
    Write-Host "authorization_findings[$($rows.Count)]{operation,test,verdict,detail}:"
    foreach ($r in $rows) { Write-Host "  $r" }
} else {
    Write-Host "authorization_findings: none"
}
```

- **confirmed** → render in the 🔴 Authorization tier; always a fix candidate.
- **rejected** → the server refused; not a finding. Do not render it in the 🔴
  tier — list it once under "Authorization tests passed" so the user sees the
  scanner's raw verdict was overruled, and why.
- **needs_review** → the attacker got data but not the owner's object (an
  owner-scoped resolver that ignores the argument, or non-deterministic data).
  Surface it for manual review; not a fix candidate.

### Rendering and fixes

**Platform mode header:** `GraphQL Scan Results  |  SQG (<sqg-name>): PASSED / FAILED`
**Token mode header:** `GraphQL Scan Results  |  SQG: N/A (Token mode — no scan SQG enforced)`

Fix candidates, consent gate (12c), schema fixes (12d), server-side resolver
fixes (12e), and verification-scan gates (12f–12h) follow `./scan-workflow.md`
with these substitutions:
- **"OAS" → "GraphQL schema (SDL)"** throughout; schema fixes tighten the
  return/argument types or add the constraint/cost directives from
  `./graphql-audit-workflow.md`.
- **Authorization fixes are server-side.** A GraphQL schema has no `security`
  section, so BOLA/BFLA are fixed in the resolvers: add an ownership check
  (the resolved object belongs to the caller, else return a `FORBIDDEN`
  error) for BOLA, and a role check for BFLA. Locate the resolver for the
  affected `Query`/`Mutation` field (search for the field name in the resolver
  map, `@Resolver` classes, or schema-first resolver objects).
- **Conformance fixes:** a "response contains fields not in the schema"
  finding maps to a resolver returning more than the schema allows — filter
  the returned object or extend the schema type per the same
  intentional/unintentional `AskUserQuestion` the OAS flow uses.
- **Token mode**: `sqgPass` absent/true; present all findings as informational
  and ask which to fix.

---

## Flags Reference

```
--graphql                enable GraphQL schema input (REQUIRED for generate, validate, and run)
--hosts <url>            host used to seed the `host` variable in scan conf generate
--conf-file <path>       explicit path to the scan config bundle
--enrich=false           skip data-dictionary enrichment (scan run)
--report-sqg             include sqgPass in the report (platform mode)
--tag <cat>:<tag>        apply platform tag for SQGs / customizations
--output-format json     output format for scan conf generate
--output <file>          write the config (generate) or report (run) to a file;
                         scan run refuses to overwrite an existing file
```
