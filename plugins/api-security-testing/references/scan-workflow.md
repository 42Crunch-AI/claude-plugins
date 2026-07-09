# Scan Workflow

> **Command conventions used throughout this file**
> - `<binary>` — the full path resolved during binary discovery (e.g. `~/.42crunch/bin/42c-ast`). Never call `42c-ast` by name alone unless it is confirmed to be on PATH.
> - **Never write a literal credential value into a command.** Load credentials from the conf file into the environment first, then let the command inherit them — the raw value must never appear in a command string, tool output, or chat message.
> - **Platform mode**: before every command, load credentials — macOS/Linux: `set -a; . "$HOME/.42crunch/conf/env"; set +a`; Windows: `Get-Content "$env:APPDATA\42Crunch\conf\env" | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }`. The command then inherits `API_KEY`/`PLATFORM_HOST` — no explicit prefix needed.
> - **Token mode**: load `TRIAL_TOKEN` the same way, then add `--freemium-host stateless.42crunch.com:443` and `--token "$TRIAL_TOKEN"` (macOS/Linux) or `--token $env:TRIAL_TOKEN` (Windows) to every command — never the literal token.
> - **OAS analysis is done once, in the calling skill.** The skill's scan-preview step already extracted the operation count, auth scheme types, BOLA/BFLA candidates, and sample-data presence. Reuse those results throughout Steps 2–5 — do not re-read the OAS to re-derive facts already established this conversation. Open the OAS only to look up detail not yet extracted (e.g. a specific operation's schema or examples).
> - **PowerShell string quoting**: when a variable is immediately followed by `:` inside a double-quoted string, PowerShell parses `$varName:` as a PSDrive reference (like `$env:TEMP`) and throws `InvalidVariableReferenceWithDrive`. Always use `${varName}` to delimit the name — e.g. `"${opName}: ..."` not `"$opName: ..."`. This applies to any inline PowerShell generated during the session, not just the static snippets below.

---

## Step 1 — Locate or Create Scan Config

> **Token mode**: omit `--tag` and `--report-sqg` from all commands in this step.
> These flags require platform access and must not be used in token mode.

### 1a — Resolve git root and alias

**Resolve the git root first.** Run from the OAS file's directory:

```bash
git -C "<oas-file-directory>" rev-parse --show-toplevel 2>/dev/null || echo "NOT_GIT"
```

- **Git root found** → store as `GIT_ROOT`. All relative paths (OAS path in
  `conf.yaml`, `--conf-file`, `scan run` / `scan conf validate` arguments) are
  relative to this directory. All `42c-ast` commands must be run from `GIT_ROOT`
  (use `cd "$GIT_ROOT" &&` or equivalent).
- **NOT_GIT** → use the agent's working directory as the project root and note to
  the user that there is no git repository.

Walk upward from `GIT_ROOT` looking for `.42c/conf.yaml`.

**If `.42c/conf.yaml` exists and the OAS path is listed:**
- Extract the `alias` value for that path.

**If `.42c/conf.yaml` does not exist or the OAS path is not in it:**
- Derive an alias from `info.title` in the OAS file: lowercase, replace spaces/underscores/special characters with hyphens, collapse consecutive hyphens, strip leading/trailing hyphens.
  - Example: `info.title: "My Banking API"` → `my-banking-api`, `info.title: "Vulnerable API v2"` → `vulnerable-api-v2`
  - If `info.title` is absent or empty, fall back to the OAS filename stem using the same transformation rules.
- Add (or create) the entry in `$GIT_ROOT/.42c/conf.yaml`:
  ```yaml
  apis:
    <relative-oas-path-from-git-root>:
      alias: <derived-alias>
  ```

### 1b — Check for existing scan config

> **Scan config source — mandatory**
>
> Resolve scan config from the **filesystem only**. Never use git (or any VCS)
> to locate, restore, or reconstruct a config:
> - Do **not** run `git show`, `git log`, `git checkout`, or similar to read
>   `.42c/scan/<alias>/scanconf.json` from history.
> - If the on-disk file is **missing**, always run `scan conf generate` (Step 1b
>   below). Never backfill from version control.

Check whether `.42c/scan/<alias>/scanconf.json` exists **on disk**.

**If it exists:**
- Store `CONF_FILE=.42c/scan/<alias>/scanconf.json` and proceed directly to
  Step 1c. Do **not** validate it here — Step 1c writes the target URL first
  and then runs a single validation checkpoint that covers both the existing
  content and the URL write. Validating twice (before and after the URL write)
  is a wasted network call.

**If it does not exist (or Step 1c's checkpoint found an existing config invalid):**
- Ensure the output directory exists:
  ```bash
  mkdir -p .42c/scan/<alias>
  ```
- Generate a baseline config using the **relative OAS path** (not alias, not absolute path).
  Platform mode: include `--tag` only when a tag was resolved. Token mode: omit `--tag`.
  ```bash
  # Platform mode
  set -a; . "$HOME/.42crunch/conf/env"; set +a
  <binary> scan conf generate \
    --output-format json \
    --output .42c/scan/<alias>/scanconf.json \
    [--tag <category>:<tag>] \
    <relative-oas-path>

  # Token mode
  set -a; . "$HOME/.42crunch/conf/env"; set +a
  <binary> scan conf generate \
    --freemium-host stateless.42crunch.com:443 \
    --token "$TRIAL_TOKEN" \
    --output-format json \
    --output .42c/scan/<alias>/scanconf.json \
    <relative-oas-path>
  ```
- Check the generate result — this may be the first `42c-ast` call this run
  makes:
  - **`statusCode: 3` and `statusMessage: limits_reached`** (Token mode
    only) → follow `./token-limit.md` now. Do not proceed.
  - **Any other non-zero** → surface the error to the user and stop.
  - **`statusCode: 0`** → store `CONF_FILE=.42c/scan/<alias>/scanconf.json`,
    apply the normalization below, then proceed to Step 1c. Do **not** run a
    standalone validate here — the config is edited again in Step 1c
    (normalization + target URL) and validated there once; validating the raw
    generated output first is a wasted network call.

**Scan Configuration Normalization after first generation (required):**
- On first `scan conf generate`, the generated `environments.default.variables`
  includes one variable per OpenAPI security scheme (for example bearer auth,
  oauth2, apiKey, or basic auth variables) typically with `"required": true`.
  - Normalize these generated security-related variables to `"required": false`
    before proceeding, unless the user explicitly wants strict required inputs.
- The generated `authenticationDetails` is also initialized with one default credential
  per OpenAPI security scheme defined in the OAS (for example bearer, oauth2, basic, or apiKey).
  - Use this generated default credential as the User 1 credential for that
    scheme. Update/wire that default entry as needed; do not create an additional
    User 1 credential unless the user explicitly asks for multiple primary
    identities.
- Set `runtimeConfiguration.reportGenerateCurlCommand` to `false`. The binary
  generates it as `true`, which embeds a full curl string in every test
  request — roughly 9% of the report's bytes — that this workflow never reads
  (body-aware authorization confirmation in Step 12a-0 uses `response.rawPayload`,
  not the curl field). Turning it off shrinks the report file and speeds parsing
  at no cost to any step.
  ```json
  "reportGenerateCurlCommand": false
  ```

### 1c — Write target URL to config

Write `SCAN_TARGET_URL` (confirmed in the skill's URL resolution step) into
`environments.default.variables.host` in `CONF_FILE`. No URL resolution or
user prompting is needed here — the URL was already confirmed and reachability
checked before the workflow started.

Important schema rule for `environments.default.variables`:
- Variable entries must be objects with a source strategy, not raw string literals.
- Keep generated security-scheme variables optional for scan execution — set `"required": false`
  for each generated security-scheme variable in `environments.default.variables`.
- For values used by operation templates (for example `{{username}}`, `{{password}}`),
  add entries under `environments.default.variables` using `"from": "environment"`
  with both `"name"` and `"required": false`.
- Use this shape for scan variables:
  ```json
  "host": {
    "name": "SCAN42C_HOST",
    "from": "environment",
    "required": false,
    "default": "<SCAN_TARGET_URL>"
  },
  "username": {
    "name": "SCAN42C_USERNAME",
    "from": "environment",
    "required": false,
    "default": "<user1-username>"
  },
  "password": {
    "name": "SCAN42C_PASSWORD",
    "from": "environment",
    "required": false,
    "default": "<user1-password>"
  }
  ```

After writing `SCAN_TARGET_URL` (and any other Step 1 edits — normalization,
etc.), run the **single Step 1 validation checkpoint**:

```bash
# Platform mode
set -a; . "$HOME/.42crunch/conf/env"; set +a
<binary> scan conf validate <relative-oas-path> \
  --conf-file <CONF_FILE>

# Token mode
set -a; . "$HOME/.42crunch/conf/env"; set +a
<binary> scan conf validate <relative-oas-path> \
  --freemium-host stateless.42crunch.com:443 \
  --token "$TRIAL_TOKEN" \
  --conf-file <CONF_FILE>
```

Check the status object — this may be the first `42c-ast` call this run makes,
so check for a token-plan limit rather than assuming a failure means an invalid
config:

- **`statusCode: 0`** → proceed to Step 2.
- **`statusCode: 3` and `statusMessage: limits_reached`** (Token mode
  only) → the token plan has hit its usage limit. Follow `./token-limit.md` now.
  Do not treat this as an invalid config, do not attempt to regenerate.
- **Any other non-zero:**
  - If `CONF_FILE` was an **existing** config found in Step 1b → treat it as
    invalid: regenerate via Step 1b's generate branch, then repeat Step 1c
    (write the URL, validate once).
  - If it was **freshly generated** this run → surface the error to the user
    and stop.

---

## Step 2 — Authentication Setup

Use the auth scheme types already identified in the skill's preview analysis
(read `securitySchemes` from the OAS only if the preview result is not in
context), then collect credentials using the per-scheme flows below. Every
credential field is collected via `AskUserQuestion` — never generate, guess,
or suggest credential values.

**BOLA/BFLA second-user identification (do this before collecting any credentials):**
Reuse the BOLA/BFLA candidate list from the skill's preview analysis if it is
in context. Otherwise flag every operation that acts on a **specific existing
resource instance named by a client-supplied object reference** — an id / key /
ref to a resource that some *other* request created. The reference can sit in
any of three locations; check all of them, not just the path:

- **Path parameter** — name ends in `Id`, `Key`, or `Ref`, or is a UUID/integer
  named after a resource (`GET /orders/{orderId}`, `DELETE /users/{userId}`).
- **Query parameter** — the same shape carried in the query string
  (`GET /search?orderId=…`, `GET /documents?ref=…`).
- **Request-body field** — a field that references an existing object rather
  than populating a new one (`POST /lookup {orderId}`, `POST /transfer
  {fromAccountId, toAccountId}`, `POST /orders/{id}/share {targetUserId}`). A
  body carrying **multiple** references (e.g. a transfer) is a BOLA candidate on
  **each** reference.

HTTP method does NOT gate candidacy: a `POST` whose body names an existing
resource (a lookup, transfer, share, or action-on-object call) is as much a
BOLA candidate as a `GET` / `PUT` / `PATCH` / `DELETE` on `/{resourceId}`. What
*excludes* an operation is the absence of any reference to an existing instance
— a pure collection `GET /orders` (list), or a `POST /orders` that only creates
a new resource from attributes it is given (`{item}`, `{name}`) without
referencing another object. This location-agnostic swap has been verified
end-to-end: the scanner seeds the resource as User 1 and replays the operation
under User 2's token regardless of whether the id sits in the path, query, or
body.

Flag privileged operations (admin-only or elevated-privilege actions) separately
as BFLA candidates, even if they have no path ID parameter. **Recall matters
more than precision here:** a missed candidate means BFLA is silently never
tested for that operation, while an over-flagged one costs only one extra
confirmation and admin-credential prompt. So flag on *any* of the signals below
— and the most dangerous real-world BFLA is an admin-only action on a
**normal-looking path with no explicit marker** (e.g. `DELETE /users/{id}`,
`POST /orders/{id}/refund`), so do not rely on the name-based signals alone.

**Explicit markers** (name/tag/scheme):
- Path segment contains `admin`, `internal`, `management`, `staff`, `system`,
  or `superuser` (e.g. `/admin/users`, `/internal/reports`).
- Operation is in a tag group named `Admin`, `Internal`, `Management`, or similar.
- `operationId` or `summary`/`description` implies privilege — e.g. `banUser`,
  `promoteUser`, `impersonate`, `forceDelete`, `refund`, `approve`, or prose like
  "admin only", "administrators", "elevated", "restricted", "internal use".

**Structural signals** (catch the unmarked cases):
- **Elevated security requirement** — the operation's `security` requires a
  scheme, OAuth2 scope, or role the *baseline* operations don't (e.g. most
  operations need scope `read`/`write` but this one needs `admin`/`manage`, or
  an extra scheme). A per-operation `security` that differs from the API default
  is a strong privilege signal.
- **Cross-subject management** — a state-changing operation (POST/PUT/PATCH/DELETE)
  that acts on an **arbitrary** user/tenant/resource identified in the path
  (`/users/{id}`, `/accounts/{id}/status`) rather than the caller's own
  (`/users/me`, `/profile`). Managing *another* subject's record is typically an
  admin function.
- **Sensitive action shape** — role/permission changes, account enable/disable/ban,
  refunds/adjustments, config/settings/feature-flag writes, bulk or system
  operations, or a request field constrained to privileged values (e.g.
  `role: admin`, `isAdmin: true`).

Compile the candidate list from all signals, then **confirm it with the user**
rather than only asking when nothing matched — call `AskUserQuestion`:
`"These operations look like they may require elevated privilege, so I'll test
them for BFLA (function-level authorization): <list>. Should I test all of them,
and are there any privileged operations I missed?"` — options: `["Test these —
list looks right", "Let me add or remove some", "None of these are privileged —
skip BFLA"]`. If the list is empty, still ask: `"I couldn't identify privileged
operations automatically. Are there any admin-only or elevated-privilege
endpoints I should test for BFLA?"` — options: `["Yes — I'll flag them", "No —
skip BFLA testing"]`.

Any confirmed BFLA candidate means an **admin / elevated-privilege credential is
required** — a distinct identity from the BOLA User 2. Collect it in the
credential step below (`{{adminUsername}}` / `{{adminPassword}}` or an admin
token), pin each candidate's happy path to the admin credential, and wire the
BFLA test (see Step 6). If the user skips BFLA, collect no admin credential and
wire no BFLA test. Detecting BOLA and BFLA candidates up front is what
determines how many identities the user is asked for (User 1 always; User 2 for
BOLA; an admin for BFLA), so the credential prompts don't come as a surprise.

### Per-scheme credential collection

> **Prerequisite:** The accounts you collect credentials for must already exist
> in the database before the scan runs. The scan does not create these users —
> ensure User 1, User 2 (if needed for BOLA), and Admin (if needed for BFLA)
> are pre-registered before proceeding. If any account is missing, credential
> acquisition will fail and all operations that depend on that credential will
> be skipped.

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

**Read `./scanconf-templates.md` now if it is not already in context** — it is
the canonical library for every scanconf JSON shape used in Steps 2–6
(credential acquisition, operation patterns, dependency chains, authorization
tests). Never re-read it once loaded, and never invent a shape it already
defines.

When a credential requires a request sequence (e.g. a login call) to acquire
its token, add a `requests` array to the credential object using the
**`authenticationDetails` — bearer token** pattern from the templates file.
`<LoginOperationId>` is the `operationId` of the operation that issues the
token (look for a `POST /login`, `POST /auth/token`, or equivalent);
`<tokenField>` is the JSON Pointer path to the token value in the response
body.

**Rule: always use `$ref` to reference an existing operation — never inline `request` objects.**
Inline blocks have no `operationId`, which the VS Code extension rejects with
`Unable to parse request that has no operationId set`. The `42c-ast` CLI accepts both
formats, but the extension does not — always use `$ref` regardless.

**Variable scoping — credential context only:**
`variableAssignments` in a credential acquisition step are scoped to the credential
context. Only the token variable `<tokenVar>` (the one referenced by `"credential"`) is reliably
available in the operation context at scan time. Any extra variables captured here are NOT in the operation context during full fuzzing scans.

**Rule:** capture only the credential (for example Bearer token, API key, or Basic Auth) 
in `authenticationDetails`. For any other data needed from the login response, 
add an explicit `before` block on each operation that needs it and capture the value
there instead (see Step 6 and the Class-B patterns in `./scanconf-templates.md`).
  - If many operations share the same variable, use the global 
    before block (see Step 6 — Global `before` block). Do not rely on
    variableAssignments in `authenticationDetails` for anything beyond the
    credential token itself.

**Rule:** use existing generated default credential for User 1.
After initial scan config generation, treat the scheme's default generated
credential in `authenticationDetails` as User 1. Populate or adjust that
credential's `credential`, `requests`, and `variableAssignments` fields as
needed instead of creating a second User 1 credential entry.

**Second user (BOLA) / Admin (BFLA):** use a step-level `environment` override
on the same login `$ref` to swap credential variables without duplicating the
operation — the `User2Token` / `AdminToken` entries in the templates'
`authenticationDetails` pattern show the exact shape.

`environment` overrides apply only to that single step. The keys must match the template
variable names used in the referenced operation's `requestBody`. If the login operation
uses hardcoded values instead of `{{variables}}`, update its `requestBody` to use
template variables first — otherwise `environment` overrides have no effect.

---

## Step 3 — Test Data

Before classifying operations, establish the source of test data for the scan.

**Sample-data presence was already determined in the skill's preview analysis**
— reuse that result. Only re-scan the OAS (request bodies and parameters for
`example` / `examples` / `default` values) if the preview result is not in
context.

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
5. This table is used in Step 5 (classification) and Step 6 (scenario building) to
   auto-populate Class-C operations — no reactive import needed in Step 8.

If re-seeding is needed after a destructive scan operation (Step 5 Class-D), use
the seed command captured here. If no seed command was provided and Class-D
operations exist, note to the user that they may need to manually restore test
records between scan runs if the primary user's account is deleted.

---

## Step 4 — Built-in Variables

The scan config supports a set of built-in variables that generate dynamic values at scan runtime. These can be used in place of or concatenated with static string values for parameters and request body properties.

| Variable | Description |
|---|---|
| `{{$randomString}}` | Random alphanumeric string of 20 characters |
| `{{$randomuint}}` | Random uint32 integer |
| `{{$uuid}}` | Unique UUID |
| `{{$timestamp}}` | Current time in UNIX format |
| `{{$timestamp3339}}` | Current date and time in RFC 3339 format |
| `{{$randomFromSchema}}` | Value generated from the schema defined in the OAS |

**When to use them:** built-in variables are most useful for operations that require unique values across iterations. For example, when testing a user registration endpoint, using a static email address causes the second and subsequent iterations to fail with `409 Conflict`. Instead, compose the value with a built-in variable to guarantee uniqueness each time:

```json
"email": "user{{$randomuint}}@email.com"
```

Built-in variables can be concatenated with any static string prefix or suffix. They are evaluated fresh on every request — each iteration gets a different value.

**Where to place them — scenario-level `environment`, not global variables:**

Do **not** put built-in variable expressions in `environments.default.variables`. Global variables must be static strings (or environment-variable overrides). Instead, pass built-in variable expressions in the `environment` block of the scenario request step that needs them:

```json
"scenarios": [
  {
    "key": "happy.path",
    "fuzzing": true,
    "requests": [
      {
        "fuzzing": true,
        "$ref": "#/operations/UserRegistration/request",
        "environment": {
          "reg_username": "user{{$randomuint}}",
          "reg_email": "user{{$randomuint}}@example.com",
          "reg_password": "password"
        }
      }
    ]
  }
]
```

This keeps the operation reusable: a `before` block that calls `UserRegistration` can supply its own `environment` override, while the happy-path scenario independently supplies its own values — neither one interferes with the other.

**Rule — uniqueness-constrained fields:** if a creator operation contains fields that must be unique across iterations (e.g. VIN, email, account number, username — fields where a duplicate causes a 409 Conflict or 400 Bad Request on the second run), use a built-in variable expression (`{{$randomFromSchema}}`, `{{$randomuint}}`, etc.) in **every** `environment` block that supplies those fields — including `before` blocks and dependency-chain creator steps, not just the happy-path scenario. Reserve static values for fields that are not uniqueness-constrained (e.g. passwords, boolean flags, fixed categorical values).

**Common patterns:**

```json
"username": "testuser_{{$randomString}}",
"email": "user{{$randomuint}}@example.com",
"referenceId": "{{$uuid}}",
"createdAt": "{{$timestamp3339}}"
```

Keep these available when classifying operations in Step 5 — Class-A operations that create uniquely-keyed resources (users, accounts, orders) should use built-in variables rather than static literals to avoid collision failures across scan iterations.

---

## Step 5 — Operation Classification

Before writing any scenario into the scan config, analyse every operation in
the OAS and classify it. The `BOLA?` column reuses the candidate list already
established in Step 2 (which itself came from the skill's preview analysis) —
do not re-derive it here. Before presenting the table, give the user a brief
explanation of the four classes so they can meaningfully validate the results.

This step is mandatory and visible: do not treat the classification as an
internal inference. Show a complete operation-by-operation table, including the
proposed data source or dependency chain for every operation, and wait for an
explicit user confirmation before writing any scan config changes.

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
- The `{{$randomuint}}` / `{{$randomstring}}` macros for uniqueness

**B — Dependency-chain required**
One or more inputs contain a dynamic ID that can only come from a prior
operation's response body (e.g. `{orderId}`, `{userId}`, `{documentId}`). The ID
can be consumed from a **path** parameter, a **query** parameter, or a
**request-body field** — all three are dependency-chain inputs.

Detection heuristic:
1. Identify resource-ID inputs in any location — path params, query params, or
   body fields that reference an existing object (end in `Id`, `Key`, `Ref`, or
   are a UUID/integer named after a resource).
2. Find the operation that creates or returns that resource (typically a `POST`
   or `GET` on the parent collection path).
3. Find the response body field in that operation's success schema that provides
   the ID value.
4. Propose the chain: `<CreatorOp> → <TargetOp>`, noting where the ID is consumed
   (path / query / body) and the JSON Pointer to extract it.

**C — User-data-required**
Inputs cannot be resolved automatically and no plausible creator operation
exists. If a Postman collection was provided in Step 3, use values from the
lookup table. Otherwise ask the user to provide the values directly.

**D — Throwaway-user required**
The operation destroys the currently authenticated principal's own resource
(e.g. `DELETE /account`, `DELETE /users/me`, `DELETE /profile`).

**Class-D requires the absence of a resource-identifying path parameter.** If the
operation has a path parameter that names the target (e.g. `DELETE /users/{username}`,
`DELETE /accounts/{accountId}`), it is NOT Class-D — the caller is naming an explicit
target, not implicitly deleting themselves. Classify it as B or A instead, with a
`before` block to seed the target resource if needed. Class-D applies only when the
operation's sole implicit target is the authenticated user (no path parameter identifies
a different resource).

**Do NOT use `"skipped": true`** — the scanner ignores this field and will
execute the operation against User1, deleting the primary test user and
breaking all subsequent happy paths in the same run.

**Do NOT use `environment` overrides on the token variable** — the
`authenticationDetails` credential tokens are acquired and cached at session
start. Overriding the variable at step level does not change which cached
credential is injected; the operation will still run as User1.

Instead:
1. Add a named throwaway credential to `authenticationDetails` with only
   the login acquisition step.
2. Set `"auth": ["AccessToken/<throwaway-credential-name>"]` **directly on
   the operation's `request` definition** — using `Scheme/CredentialName`
   notation. Do not use the default credential.
3. Build a `happy.path` scenario with a `before` block:
   - Before block: register the throwaway user (with environment overrides for
     the throwaway credentials) by adding the register step to the operation's `before` block.
   - Happy Path: run the destructive operation (it authenticates as the throwaway
     via the operation's `auth` setting).

This leaves User1 intact while still validating the operation across
multiple fuzzing iterations.

### Example classification table

```
Operation              | Class  | BOLA? | Proposed data source
-----------------------|--------|-------|----------------------------------------------
UserLogin              | A      | no    | env vars: {{username}} / {{password}}
UserRegistration       | A      | no    | {{$randomuint}} macro for username/email
CreateResource         | A      | no    | OAS body example + {{userId}} from auth
RetrieveResource       | B      | yes   | CreateResource → /{resourceId} in path (`before` block)
UpdateResource         | B      | yes   | CreateResource → /{resourceId} in path (`before` block)
LookupResource         | B      | yes   | CreateResource → resourceId in body (`before` block)
SearchResource         | B      | yes   | CreateResource → ?resourceId= in query (`before` block)
DeleteResource         | B      | yes   | CreateResource → /{resourceId} (creator in scenario, not `before`)
DeleteUser             | B      | yes   | UserRegistration → /{userId} (`before` block)
DeleteAccount          | D      | no    | register+login throwaway → delete throwaway
```

**`BOLA? = yes` has a direct consequence in Step 6:** every operation marked as a BOLA candidate will receive an additional BOLA test scenario (using User 2's token) alongside its happy path scenario. Every operation marked as a BFLA candidate must run its happy path as admin (`auth: ["<SchemeName>/AdminToken"]`) and will receive a BFLA test scenario that replays the same request with User 1's low-privilege token.

Output the classification explanation and table above as a chat message, then call `AskUserQuestion`:
- **question**: `"Does this classification look correct, or do you need to correct any misclassifications?"`
- **options**: `["Yes — proceed", "No — I need to correct some classifications"]`

---

## Step 6 — Build Scenario Chains

All JSON shapes for this step live in `./scanconf-templates.md` (the canonical
pattern library) — read it now if it is not already in context. This step
decides *which* pattern applies *where*; the templates file defines the exact
JSON for each named pattern.

For every Class-B operation, wire a creator step that seeds the resource ID
before the target request runs. Show the user each proposed chain in plain
English before writing it.

**Where the creator step goes depends on whether the happy path consumes the
seeded resource:**

| Target operation | Creator placement | Pattern in `scanconf-templates.md` |
|------------------|-------------------|-------------------------------------|
| Non-destructive (GET, PUT, PATCH, or a body/query reader such as `POST /lookup`) | Operation-level `before` block + single-step `happy.path` scenario | **Class-B — dependency chain, GET / PUT / PATCH** |
| Destructive (DELETE, or any operation whose happy path removes/consumes the seeded resource) | First request inside `happy.path` `requests[]`, **not** in `before` | **Class-B — dependency chain, DELETE** |

**Why destructive targets differ:** BOLA replays `happy.path` with User 2's
credential on the target step; a creator that lives only in `before` may not
re-seed the resource before the replay, so the test returns 404 instead of
401/403 — a false BOLA failure. The full rationale, replay flow, and
symptom-to-watch-for are documented with the DELETE pattern in the templates
file. (Non-destructive targets are safe in `before` because the seeded resource
survives to the replay — verified: the User 2 replay reads a resource seeded on
an earlier User 1 run.)

**Where the seeded ID is wired into the target request depends on the reference
location** (from the Step 5 classification):

| Reference location | Wire the `{{resourceId}}` variable into |
|--------------------|------------------------------------------|
| Path parameter  | the target request's `paths[]` array |
| Query parameter | the target request's `queries[]` array |
| Request-body field | the target request's `requestBody.json` (or matching body mode) |

The creator/`before` wiring and the BOLA test definition are identical across
all three — only the target request field that consumes the id changes.

Do not consider a Class-B operation fully configured unless the creator step
reliably seeds the resource and extracts the required identifier (`variableAssignments`
on the creator's success response, or on the creator operation definition that
the `$ref` inherits). A BOLA authorization test alone is not a substitute for a
dependency chain, and a static placeholder path value is not sufficient when a
resource must be created or resolved first. If no existing operation can
reliably create or return the needed resource ID, stop and ask the user for
the missing seed data or an alternate creator operation.

#### `before` block rules:
1. Always prefer to reference existing OAS operations in `before` blocks — avoid creating
a utility request as a substitute. If an operation already exists in the spec
(e.g. `UserRegistration`, `UserLogin`), use `"$ref": "#/operations/<OperationId>/request"`
with `environment` overrides to supply different inputs. Only add an entry to
the top-level `requests` section when no OAS operation covers the call.

2. Mandatory variable wiring rule — if the referenced creator operation uses any
template variables in `paths`, `queries`, `headers`, or `requestBody`, every
`before` step that references it MUST resolve those variables. Use
a step-level `environment` block unless the variables are already resolved
globally via `environments.default.variables`, global static defaults, or a
global `before` assignment. Do not rely on values supplied only in another
scenario.

Apply the matching Class-B pattern from `./scanconf-templates.md` to every
Class-B operation.

Before running Step 8, verify each Class-B chain is self-contained:
- **GET/PUT/PATCH:** every `before` step resolves creator input variables in its
  `environment` or globally; no creator input depends only on another scenario's
  `environment` block.
- **DELETE:** creator is the first step in `happy.path` `requests[]`; `variableAssignments`
  on the creator's success response (on the creator operation definition or inline
  on the scenario step) populate the ID used by the delete step.

### Global `before` block

If multiple operations share the same dependency variable (e.g. many operations
need `customerId` from a login call), use the **Global `before` block** pattern
from `./scanconf-templates.md` rather than repeating the creator in every
scenario. **Never use the global `before` to register or provision test
users** — the scan assumes User 1, User 2, and Admin already exist before it
starts; see the warning attached to that pattern.

### Class-C: user-provided data

If a Postman collection was imported in Step 3, look up the operation in
the test data table and inject the extracted values as static literals in the
`paths` / `queries` / `requestBody.json` fields of the operation's `request`
block. If the operation is not in the table, ask the user to paste the values.

### Class-D: throwaway-user pattern

For operations that delete the primary user's own account, apply the
**Class-D — throwaway user** pattern from `./scanconf-templates.md` in full.
Four elements are all mandatory:

1. **Register step in the operation's `before` block** — so the throwaway user
   exists before each scenario iteration; accept both 201 (created) and 409
   (already exists — idempotent).
2. **Named throwaway credential in `authenticationDetails`** — login
   acquisition step only (see the `<throwaway-credential-name>` entry in the
   templates' `authenticationDetails` pattern).
3. **`auth` pinned on the operation definition itself** —
   `"auth": ["AccessToken/<throwaway-credential-name>"]` on the operation's
   `request` block, never as a scenario-step override. This guarantees User1
   is never touched.
4. **Delete-only 1-step scenario** — do NOT re-register in the scenario; the
   `before` block already re-registers before every iteration.

If the register operation rejects existing accounts (no 409 tolerance), add an
idempotent pre-cleanup utility request per the templates' **`requests` — named
utility request** section: login as the throwaway → delete any pre-existing
account → the register step always finds a clean slate.

### BOLA / BFLA authorization test patterns

Apply the **`authorizationTests` — BOLA and BFLA** section of
`./scanconf-templates.md`:

- **BOLA** — for every operation marked `BOLA? = yes` in the Step 5 table:
  define the `authentication-swapping-bola` test once at the top level
  (source `User1Token` → target `User2Token`), then tag each candidate
  operation's `authorizationTests` array.
- **BFLA** — for every operation flagged as a BFLA candidate (privileged /
  admin-only): define the `authentication-swapping-bfla` test once (source
  `AdminToken` → target `User1Token`), tag each candidate, **and pin the
  operation's `auth` to the admin credential on its request definition**
  (mandatory — the baseline happy path must run as admin so the test is a
  true admin→low-privilege swap).

No additional scenario block is needed for either test — the scanner replays
the operation's `happy.path` scenario (including its `before` blocks and all
`scenarios[].requests[]` steps) with the swapped credential.

**Result semantics:** the engine's authorization verdict is **status-only** —
any 2xx on the swapped request is reported as a finding; 401/403 means the
server enforces authorization (not a finding). This is correct for
**state-changing** targets (PUT / PATCH / DELETE, or a POST that mutates the
resource): a 2xx means the attacker's credential successfully operated on the
victim's resource. For **read** targets (GET, or a lookup/search that returns
the object) it can **false-positive** — an owner-scoped endpoint that ignores
the client-supplied id and returns the *caller's own* data also answers 2xx
without leaking anything. Confirm read findings by comparing response bodies
(Step 12a's authorization-confirmation pass) before presenting them. For DELETE,
also ensure the creator is scenario-inline per the placement table above — a
creator-only `before` block commonly causes false BOLA failures (404 instead of
403).

## Step 7 — Scan Config Validation Checkpoint

After all Step 2 to Step 6 edits are complete (credentials, operation
classification, scenario chains, and authorization test wiring), validate
`CONF_FILE` again before running happy-path validation.

**Skip condition:** if Steps 2–6 made **no changes** to `CONF_FILE` since the
Step 1c checkpoint passed (rare — no auth schemes, no Class-B/C/D operations,
no authorization tests), skip this checkpoint and go straight to Step 8 —
re-validating an unchanged file is a wasted network call.

```bash
# Platform mode
set -a; . "$HOME/.42crunch/conf/env"; set +a
<binary> scan conf validate <relative-oas-path> \
  --conf-file <CONF_FILE>

# Token mode
set -a; . "$HOME/.42crunch/conf/env"; set +a
<binary> scan conf validate <relative-oas-path> \
  --freemium-host stateless.42crunch.com:443 \
  --token "$TRIAL_TOKEN" \
  --conf-file <CONF_FILE>
```

Validation result handling:
- `statusCode: 0` → continue to Step 8.
- Any non-zero status or schema errors (for example `unknown env from` paths)
  → fix config shape and re-run this checkpoint.
- Do not run Step 8 until this checkpoint passes.

---

## Step 8 — Happy Path Validation Run

Before running the full scan, validate all happy paths in strict mode.

### Configure and run

Set `happyPathOnly: true` in `runtimeConfiguration`:

```json
"happyPathOnly": true
```

Leave `laxTestingModeEnabled` at its generated default (`false`). Never set it
to `true` before happy paths are confirmed — in lax mode, fuzzing runs even on
operations with failing happy paths, producing a cascade of false positives.

Write the report to a file with `--output` (clean, directly parseable JSON);
the small status object — `statusCode`, `statusMessage`, `sqgPass`,
`sqgDetails` — prints to stdout, so redirect it to a separate status file. Do
**not** use `2>&1`: the binary emits its logs inside the stdout JSON object
(`logs[]`), not to stderr, so the status file stays pure JSON. This replaces
the old single-stream capture that required regex-extracting JSON from a
1.6MB+ log-contaminated blob.

```bash
# macOS / Linux — Platform mode
set -a; . "$HOME/.42crunch/conf/env"; set +a
<binary> scan run --enrich=false \
  --output /tmp/42c-happy-report.json --output-format json \
  <relative-oas-path> --conf-file <CONF_FILE> > /tmp/42c-happy-status.json

# macOS / Linux — Token mode
set -a; . "$HOME/.42crunch/conf/env"; set +a
<binary> scan run --enrich=false \
  --freemium-host stateless.42crunch.com:443 --token "$TRIAL_TOKEN" \
  --output /tmp/42c-happy-report.json --output-format json \
  <relative-oas-path> --conf-file <CONF_FILE> > /tmp/42c-happy-status.json
```

```powershell
# Windows — Platform mode
Get-Content "$env:APPDATA\42Crunch\conf\env" | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }
& <binary> scan run --enrich=false `
  --output "$env:TEMP\42c-happy-report.json" --output-format json `
  <relative-oas-path> --conf-file <CONF_FILE> > "$env:TEMP\42c-happy-status.json"

# Windows — Token mode
Get-Content "$env:APPDATA\42Crunch\conf\env" | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }
& <binary> scan run --enrich=false `
  --freemium-host stateless.42crunch.com:443 --token $env:TRIAL_TOKEN `
  --output "$env:TEMP\42c-happy-report.json" --output-format json `
  <relative-oas-path> --conf-file <CONF_FILE> > "$env:TEMP\42c-happy-status.json"
```

Extract only failing happy paths — never include raw output in your response.

> **Platform note**: macOS/Linux use the Python snippet below. Windows users
> should use the PowerShell equivalent that follows.

```bash
# macOS / Linux
python3 << 'EOF'
import json
status = json.load(open("/tmp/42c-happy-status.json"))
if status.get("statusCode") != 0:
    print(f"scan_error: statusCode={status.get('statusCode')} {status.get('statusMessage','')}")
    raise SystemExit(0)
# Reconstruct the combined shape from the clean status + report files
data = {**status, "report": json.load(open("/tmp/42c-happy-report.json"))}
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

```powershell
# Windows
$status = Get-Content "$env:TEMP\42c-happy-status.json" -Raw | ConvertFrom-Json
if ($status.statusCode -ne 0) { Write-Host "scan_error: statusCode=$($status.statusCode) $($status.statusMessage)"; exit }
# Reconstruct the combined shape from the clean status + report files
$report = Get-Content "$env:TEMP\42c-happy-report.json" -Raw | ConvertFrom-Json
$data = $status | Select-Object *; $data | Add-Member -NotePropertyName report -NotePropertyValue $report -Force
$results = if ($data.results) { $data.results } elseif ($data.scanResults) { $data.scanResults } else { @() }
if ($results -is [PSCustomObject]) { $results = @($results) }
$fails = @()
foreach ($r in $results) {
    foreach ($t in $r.testResults) {
        if ($t.status -eq 'fail' -and $t.testKey -match 'happy') {
            $op     = if ($r.operationId) { $r.operationId } elseif ($r.path) { $r.path } else { '?' }
            $test   = if ($t.testKey) { $t.testKey } else { '?' }
            $code   = if ($t.httpStatus) { $t.httpStatus } else { '' }
            $reason = if ($t.reason) { $t.reason.Substring(0, [Math]::Min(60, $t.reason.Length)) } else { '' }
            $fails += "$op,$test,$code,$reason"
        }
    }
}
if ($fails.Count -gt 0) {
    Write-Host "happy_path_failures[$($fails.Count)]{operation,test,status,reason}:"
    foreach ($f in $fails) { Write-Host "  $f" }
} else {
    Write-Host "happy_path_failures: none"
}
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
Step 3 lookup table (or no collection was provided), ask the user to supply
the values manually. Do not ask for a new Postman collection — if a collection
was already imported, re-examine the existing lookup table entries for the
failing operation before requesting manual input.

### Iteration

After resolving each batch of failures, re-run using the same command as above (report to `/tmp/42c-happy-report.json` + status to `/tmp/42c-happy-status.json` on macOS/Linux, the `%TEMP%` equivalents on Windows) and re-extract with the same extraction snippet above.

For each operation where the root cause cannot be resolved (e.g. the required
resource cannot be created in this environment), call `AskUserQuestion`:
- **question**: `"The happy path for <operationId> is still failing (<root-cause summary>). What would you like to do?"`
- **options**: `["Try a different fix", "Skip this operation — I'll come back to it later", "Abort the scan setup"]`

If **Skip** is chosen: record the operation ID and reason in a `skipped_operations` session
variable. Exclude it from all future happy-path re-runs and announce it in the final summary.

Repeat until all **non-skipped** happy paths pass.

### Database Reset Reminder (After Happy Path)

The happy path scenarios have now executed against your live API and may have
created, modified, or deleted records in your database. Before the full scan
runs, the database should be restored to a clean state so that conformance
fuzzing and authorization tests start from known data.

Call `AskUserQuestion`:
- **question**: `"The happy path scenarios have finished running and may have modified your database (created, updated, or deleted records). Please reset your database to a clean state before the full scan starts. Have you reset the database?"`
- **options**: `["Yes — database is reset, ready to proceed", "No — continue without resetting (results may be affected)"]`

Proceed regardless of the answer. If the user selects **No**, surface a one-line
warning before continuing:
> ⚠️ Proceeding without a database reset — scan results may be affected by
> residual state from happy path runs.

### Restore runtime flags

Once all happy paths pass, set `happyPathOnly: false` before the full scan:

```json
"happyPathOnly": false
```

---

## Step 9 — Permission Gate Before Full Scan

All happy paths have passed. Before running the full security scan, ask the
user for explicit consent. Call `AskUserQuestion`:

- **question**: `"All happy paths passed successfully. I'm ready to run the full security scan against <SCAN_TARGET_URL>. This will execute authorization tests (BOLA/BFLA) and conformance fuzzing across all <N> operations. Shall I proceed?"`
- **options**: `["Yes — run the full scan", "No — stop here"]`

Only proceed to Step 10 after explicit confirmation.

---

## Step 10 — Full Scan

Run the full scan. As in Step 8, write the report to a file with `--output`
(clean JSON) and redirect the small stdout status object to a separate status
file — no `2>&1`. The status object carries `statusCode`, `statusMessage`,
`sqgPass`, and `sqgDetails`, so the pass/fail verdict and blocking rules are
read from a <1KB file; the multi-MB report file is only opened to render
findings.

```bash
# macOS / Linux — Platform mode
set -a; . "$HOME/.42crunch/conf/env"; set +a
<binary> scan run --enrich=false --report-sqg \
  --output /tmp/42c-scan-report.json --output-format json \
  <relative-oas-path> --conf-file <CONF_FILE> > /tmp/42c-scan-status.json

# macOS / Linux — Token mode
set -a; . "$HOME/.42crunch/conf/env"; set +a
<binary> scan run --enrich=false \
  --freemium-host stateless.42crunch.com:443 --token "$TRIAL_TOKEN" \
  --output /tmp/42c-scan-report.json --output-format json \
  <relative-oas-path> --conf-file <CONF_FILE> > /tmp/42c-scan-status.json
```

```powershell
# Windows — Platform mode
Get-Content "$env:APPDATA\42Crunch\conf\env" | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }
& <binary> scan run --enrich=false --report-sqg `
  --output "$env:TEMP\42c-scan-report.json" --output-format json `
  <relative-oas-path> --conf-file <CONF_FILE> > "$env:TEMP\42c-scan-status.json"

# Windows — Token mode
Get-Content "$env:APPDATA\42Crunch\conf\env" | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }
& <binary> scan run --enrich=false `
  --freemium-host stateless.42crunch.com:443 --token $env:TRIAL_TOKEN `
  --output "$env:TEMP\42c-scan-report.json" --output-format json `
  <relative-oas-path> --conf-file <CONF_FILE> > "$env:TEMP\42c-scan-status.json"
```

**Immediately after the command completes**, extract the summary as TOON
(Token-Oriented Object Notation — https://github.com/toon-format/toon) —
never include raw report content in your response.

> **SQG field location — common mistake to avoid:**
> The SQG verdict is `sqgPass` (a boolean) at the **root of the status object**
> (`/tmp/42c-scan-status.json`) — NOT nested inside the report, and not under a
> `sqg` key. The extraction snippet reconstructs `data = {**status, "report":
> <report>}`, so `data.get("sqgPass")` and `data.get("sqgDetails")` read from
> the status object exactly as before. Always use the prescribed extraction snippet
> below rather than writing a custom parser, to avoid reading the wrong field.

> **Platform note**: macOS/Linux use the Python snippet below. Windows users
> should use the PowerShell equivalent that follows.

```bash
# macOS / Linux
python3 << 'EOF'
import json

status = json.load(open("/tmp/42c-scan-status.json"))
if status.get("statusCode") != 0:
  print(f"scan_error: statusCode={status.get('statusCode')} {status.get('statusMessage','')}")
  raise SystemExit(0)

# Reconstruct the combined shape from the clean status + report files
data = {**status, "report": json.load(open("/tmp/42c-scan-report.json"))}
report = data.get("report", {})
summary = report.get("summary", {})

sqg = "PASSED" if data.get("sqgPass") else ("FAILED" if "sqgPass" in data else "N/A")
print(f"sqgPass: {sqg}")
for d in data.get("sqgDetails", []):
    rules = d.get("blockingRules", [])
    if rules:
        print(f"blockingRules[{len(rules)}]: {', '.join(rules)}")

auth_summary = (((summary.get("authorizationTestRequests") or {}).get("executed") or {}).get("total"))
issue_summary = (((summary.get("issues") or {}).get("total")))
if auth_summary is not None:
  print(f"authorizationRequests: {auth_summary}")
if issue_summary is not None:
  print(f"issuesTotal: {issue_summary}")

def severity_from_criticality(value):
  mapping = {
    5: "critical",
    4: "high",
    3: "medium",
    2: "low",
    1: "info",
    0: "info",
  }
  return mapping.get(value, "")

failures = []
operations = report.get("operations") or {}
if isinstance(operations, dict):
  for operation_id, operation in operations.items():
    for section_name in ("authorizationRequestsResults", "conformanceRequestsResults", "customRequestsResults"):
      for entry in operation.get(section_name, []) or []:
        outcome = entry.get("outcome") or {}
        # The engine's verdict is outcome.status: "correct" = the API behaved
        # correctly (e.g. enforced 401/403 on an authorization swap, or accepted
        # a partial-security scenario). testSuccessful is NOT a reliable
        # discriminator — it is false even for correctly-enforced endpoints, so
        # filtering on it alone reports secured endpoints as failures. Skip any
        # entry the engine marked "correct".
        if outcome.get("testSuccessful") is True or outcome.get("status") == "correct":
          continue
        test = entry.get("test") or {}
        severity = severity_from_criticality(outcome.get("criticality"))
        failures.append((
          operation_id,
          test.get("key", "?"),
          severity,
        ))

if not failures:
  legacy_results = data.get("results", data.get("scanResults", []))
  if isinstance(legacy_results, dict):
    legacy_results = [legacy_results]
  for result in legacy_results:
    for test_result in result.get("testResults", []):
      if test_result.get("status") == "fail":
        failures.append((
          result.get("operationId", result.get("path", "?")),
          test_result.get("testKey", "?"),
          test_result.get("severity", ""),
        ))

if failures:
  unique_failures = []
  seen = set()
  for failure in failures:
    if failure in seen:
      continue
    seen.add(failure)
    unique_failures.append(failure)
  print(f"\nfailures[{len(unique_failures)}]{{operation,test,severity}}:")
  for op, test, sev in unique_failures:
        print(f"  {op},{test},{sev}")
else:
    print("failures: none")
EOF
```

```powershell
# Windows
$status = Get-Content "$env:TEMP\42c-scan-status.json" -Raw | ConvertFrom-Json
if ($status.statusCode -ne 0) { Write-Host "scan_error: statusCode=$($status.statusCode) $($status.statusMessage)"; exit }
# Reconstruct the combined shape from the clean status + report files
$reportContent = Get-Content "$env:TEMP\42c-scan-report.json" -Raw | ConvertFrom-Json
$data = $status | Select-Object *; $data | Add-Member -NotePropertyName report -NotePropertyValue $reportContent -Force
$report = if ($data.report) { $data.report } else { $null }
$summary = if ($report -and $report.summary) { $report.summary } else { $null }
$sqg = if ($null -ne $data.sqgPass) { if ($data.sqgPass) { 'PASSED' } else { 'FAILED' } } else { 'N/A' }
Write-Host "sqgPass: $sqg"
foreach ($d in $data.sqgDetails) {
    if ($d.blockingRules -and $d.blockingRules.Count -gt 0) {
        Write-Host "blockingRules[$($d.blockingRules.Count)]: $($d.blockingRules -join ', ')"
    }
}
if ($summary -and $summary.authorizationTestRequests -and $summary.authorizationTestRequests.executed) {
  Write-Host "authorizationRequests: $($summary.authorizationTestRequests.executed.total)"
}
if ($summary -and $summary.issues) {
  Write-Host "issuesTotal: $($summary.issues.total)"
}

function Get-SeverityFromCriticality {
  param([int]$criticality)
  switch ($criticality) {
    5 { 'critical' }
    4 { 'high' }
    3 { 'medium' }
    2 { 'low' }
    default { 'info' }
  }
}

$failures = @()
if ($report -and $report.operations) {
  $report.operations.PSObject.Properties | ForEach-Object {
    $opName = $_.Name
    $op = $_.Value
    foreach ($sectionName in @('authorizationRequestsResults', 'conformanceRequestsResults', 'customRequestsResults')) {
      $entries = $op.$sectionName
      if (-not $entries) { continue }
      foreach ($entry in $entries) {
        # Skip entries the engine marked "correct" (e.g. enforced 401/403 on an
        # authorization swap). testSuccessful alone is false even for secured
        # endpoints, so filtering on it reports them as failures. See the Python
        # note above.
        if ($entry.outcome -and ($entry.outcome.testSuccessful -eq $true -or $entry.outcome.status -eq 'correct')) { continue }
        $testKey = if ($entry.test -and $entry.test.key) { $entry.test.key } else { '?' }
        $severity = if ($entry.outcome) { Get-SeverityFromCriticality([int]$entry.outcome.criticality) } else { '' }
        $failures += "$opName,$testKey,$severity"
      }
    }
  }
}

if ($failures.Count -eq 0) {
$results = if ($data.results) { $data.results } elseif ($data.scanResults) { $data.scanResults } else { @() }
if ($results -is [PSCustomObject]) { $results = @($results) }
foreach ($r in $results) {
    foreach ($t in $r.testResults) {
        if ($t.status -eq 'fail') {
            $op  = if ($r.operationId) { $r.operationId } elseif ($r.path) { $r.path } else { '?' }
            $test = if ($t.testKey) { $t.testKey } else { '?' }
            $sev  = if ($t.severity) { $t.severity } else { '' }
            $failures += "$op,$test,$sev"
        }
    }
}
}

$failures = $failures | Select-Object -Unique
if ($failures.Count -gt 0) {
    Write-Host "`nfailures[$($failures.Count)]{operation,test,severity}:"
    foreach ($f in $failures) { Write-Host "  $f" }
} else {
    Write-Host "failures: none"
}
```

Use only the TOON output above when rendering Step 12. Do not load or display
the raw scan output file content.

## Step 11 — Database Reset Reminder (After Full Scan)

The full scan (conformance fuzzing and authorization tests) has now completed.
It may have made malformed requests, cross-user resource accesses (BOLA/BFLA),
and repeated operations that further mutated your database state.

Call `AskUserQuestion`:
- **question**: `"The full security scan has finished. Conformance fuzzing and authorization tests (BOLA/BFLA) may have further modified your database. Would you like to reset your database before reviewing results and applying fixes?"`
- **options**: `["Yes — I'll reset the database now", "No — continue to results"]`

If the user selects **Yes**: display the message `"Please reset your database
and confirm when ready."`, then call a second `AskUserQuestion`:
- **question**: `"Database reset complete?"`
- **options**: `["Yes — ready to review results"]`

Then proceed to Step 12.

---

**Token mode**: `sqgPass` will be absent or `true`. Present all findings
informally — no quality gate is enforced. Note to the user:
> "In token mode the scan shows all findings for your information — there
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

## Step 12 — Display Results and Apply Fixes

### 12a-0 — Confirm authorization findings (body-aware)

Confirm each BOLA/BFLA finding the scan reported **before** rendering it. The
engine's authorization verdict is **status-only** — it flags every 2xx on the
swapped request — so read endpoints can false-positive: an owner-scoped endpoint
that ignores the client-supplied id and returns the *caller's own* data also
answers 2xx without leaking anything. Route each finding by the operation's
read/write nature **from your Step 5 classification** (not HTTP method alone — a
`POST` may be a lookup that returns an object, or a mutation):

- **State-changing target** (PUT / PATCH / DELETE, or a POST/other you classified
  as mutating): a 2xx is **confirmed** — the attacker's credential operated on
  the victim's resource. The body is irrelevant; skip the comparison.
- **Read target** (GET, or a POST/other you classified as returning the
  referenced object): confirm only if the attacker received the **victim's**
  data. Compare the attacker's response body against the legitimate owner's
  (User 1 happy-path) body for the same operation — both are in the scan output
  under `response.rawPayload` (base64 of the raw HTTP response): the owner's
  under the operation's `scenarios`, the attacker's under
  `authorizationRequestsResults`.

Surface the evidence for every authorization finding:

```bash
# macOS / Linux
python3 << 'EOF'
import json, re, base64
d = {"report": json.load(open("/tmp/42c-scan-report.json"))}
ops = d.get("report", {}).get("operations", {})

def body(b64):
    if not b64: return None
    raw = base64.b64decode(b64).decode("utf-8", "replace")
    parts = re.split(r'\r?\n\r?\n', raw, maxsplit=1)
    m = re.search(r'\{.*\}', parts[1] if len(parts) > 1 else raw, re.S)
    return m.group() if m else None

def owner_body(op):
    for s in op.get("scenarios", []) or []:
        for r in (s.get("requests") or [s]):
            b = body((r.get("response") or {}).get("rawPayload"))
            if b: return b
    return None

for opid, op in ops.items():
    auth = [e for e in op.get("authorizationRequestsResults", []) or []
            if "swapping" in (e.get("test") or {}).get("key", "")
            and (e.get("outcome") or {}).get("status") == "defective"]
    if not auth: continue
    method = (op.get("method") or "").upper()
    ob = owner_body(op)
    for e in auth:
        ab = body((e.get("response") or {}).get("rawPayload"))
        same = ab is not None and ab == ob
        print(f"{opid} [{method}] bodies_identical={same}")
        print(f"    owner:    {(ob or '(none)')[:120]}")
        print(f"    attacker: {(ab or '(none)')[:120]}")
EOF
```

```powershell
# Windows
$reportContent = Get-Content "$env:TEMP\42c-scan-report.json" -Raw | ConvertFrom-Json
$d = [PSCustomObject]@{ report = $reportContent }
function Get-JsonBody($b64) {
  if (-not $b64) { return $null }
  $txt = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64))
  $body = ($txt -split "(?s)\r?\n\r?\n", 2)[1]
  $m = [regex]::Match([string]$body, '(?s)\{.*\}')
  if ($m.Success) { $m.Value } else { $null }
}
foreach ($p in $d.report.operations.PSObject.Properties) {
  $op = $p.Value
  $auth = @($op.authorizationRequestsResults | Where-Object { $_.test.key -like '*swapping*' -and $_.outcome.status -eq 'defective' })
  if (-not $auth) { continue }
  $ob = $null
  foreach ($s in $op.scenarios) {
    $steps = @($s.requests); if (-not $steps) { $steps = @($s) }
    foreach ($r in $steps) { $b = Get-JsonBody $r.response.rawPayload; if ($b) { $ob = $b; break } }
    if ($ob) { break }
  }
  foreach ($e in $auth) {
    $ab = Get-JsonBody $e.response.rawPayload
    $same = ($ab -and $ab -eq $ob)
    Write-Host "$($p.Name) [$($op.method.ToUpper())] bodies_identical=$same"
    Write-Host "    owner:    $ob"
    Write-Host "    attacker: $ab"
  }
}
```

Classify each **read** finding from the output:
- `bodies_identical=True`, or the attacker body otherwise carries the victim's
  distinguishing data → **confirmed** BOLA/BFLA; render in the 🔴 tier.
- attacker body reflects only the **caller's own** data, or is empty/redacted →
  **not confirmed** (owner-scoped 2xx). Do not render it as 🔴; list it under a
  one-line note: *"Authorization — needs manual review: 2xx on the swap but no
  cross-user data returned (likely owner-scoped)."*

Byte-identical bodies are the strong positive signal. When bodies differ only in
non-deterministic fields (timestamps, echoed request ids), judge by whether the
attacker's body contains the victim's distinguishing values, not strict equality.
State-changing findings from the routing above are confirmed without this check.

### 12a — Render the risk-classified findings report

Before touching anything, display the full scan picture grouped into three tiers.
Use plain-English descriptions — do not surface raw test keys or scan-report field names.

Mandatory behavior:
- The next user-visible output after Step 10 / 11 MUST be the full Step 12a report in the three-tier structure below.
- A short prose summary, condensed recap, or partial listing does NOT satisfy 12a.
- Render all three tiers every time, even when one or more tiers are `(none)`.

**Platform mode header:**
```
Scan Results  |  SQG (<sqg-name>): PASSED / FAILED
```

**Token mode header:**
```
Scan Results  |  SQG: N/A (Token mode — no scan SQG enforced)
```

```
── 🔴 Authorization Failures (BOLA / BFLA) ────────────────────────────────
  (for each finding confirmed in 12a-0 — owner-scoped 2xx go to "needs review", not here)
  Operation:  <HTTP method> <path>
  Test:       BOLA (accessed with user-2 token) / BFLA (accessed with low-priv token)
  Risk:       Horizontal privilege escalation — user B can read/modify user A's
              resources. / Vertical privilege escalation — unprivileged user can
              invoke admin-only operations.
  Fix:        Add / correct `security` requirement on this operation in the OAS, and add server-side ownership / privilege check in the route handler.

── 🟠 Conformance — SQG-Blocking ──────────────────────────────────────────
  (for each conformance finding matched in sqgDetails[].blockingRules)
  Operation:  <HTTP method> <path>
  Issue:      <plain-English description of what the API returned vs what the OAS says>
  Severity:   <HIGH / CRITICAL / …>
  Risk:       <what the mismatch means: data over-exposure, broken contract, etc.>
  Fix:        <one-line OAS change to align the contract with reality>, and corresponding server-side code fix in the route handler or serializer.

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

### 12b — Determine fix candidates

Mandatory behavior:
- Derive fix candidates only from the fully rendered Step 12a report and the blocking rules in `sqgDetails`.
- Before calling 12c, explicitly assemble the candidate lists that will be referenced in the consent prompt:
  - `authorization_fix_candidates`
  - `sqg_blocking_conformance_fix_candidates` (platform mode only)
  - `informational_conformance_findings`
- If a tier is empty, say so explicitly; do not silently omit it.

**Platform mode:**
1. All **authorization failures confirmed in 12a-0** (BOLA/BFLA) → always a fix candidate. "Needs review" owner-scoped 2xx are **not** fix candidates — they are surfaced for manual review only.
2. **Conformance findings matched in `sqgDetails[].blockingRules`** → fix candidate
   regardless of severity.
3. Conformance findings **not** in `sqgDetails[].blockingRules` → surface only;
   do not include in the fix list.

**Token mode:**
1. All **authorization failures confirmed in 12a-0** (BOLA/BFLA) → always a fix candidate. "Needs review" owner-scoped 2xx are **not** fix candidates — they are surfaced for manual review only.
2. There are no SQG-blocking conformance findings — all conformance findings are
   informational. Surface them to the user and ask which (if any) they want to fix.

### 12c — Consent Gate

Mandatory behavior:
- The very next action after completing 12b MUST be the `AskUserQuestion` call defined in this section for the active mode.
- Do not apply fixes, show diffs, or ask for approval on any individual fix before this gate returns.
- If the user chooses `Show me the diff first`, stay in Step 12c until each proposed change is shown and individually approved or skipped.
- If the user chooses `No`, stop remediation and proceed only with summary/reporting.

**Platform mode** — call `AskUserQuestion`:
- **question**: `"Here is the complete scan report (shown above). I can apply the following fixes to <filename>: 🔴 Authorization fixes: [list] 🟠 SQG-blocking conformance fixes: [list]. The 🟡 informational findings are not SQG-blocking and will not be fixed automatically — let me know if you'd like to address any of them too. What would you like to do?"`
- **options**: `["Yes — apply all fixes now", "Show me the diff first", "No — skip fixes for now"]`

**Token mode** — call `AskUserQuestion`:
- **question**: `"Here is the complete scan report (shown above). No SQG enforcement applies in token mode. 🔴 Authorization fixes I can apply: [list] 🟡 Conformance findings (informational — your call whether to fix): [list]. What would you like to do?"`
- **options**: `["Yes — apply the authorization fixes", "Show me the diff first", "No — skip fixes; summarise findings only"]`

If the user chooses **"Show me the diff first"** in either mode, display the proposed
change for each fix one at a time in unified diff format then call `AskUserQuestion`:
- **question**: `"Apply this change?"` — **options**: `["Yes", "No — skip this one"]`

Only advance to the next fix after the user confirms the current one.

Only apply fixes after explicit user confirmation.

### 12d — Apply fixes

| Finding type | Fix action |
|---|---|
| Authorization — BOLA/BFLA confirmed | Add or correct `security` requirements on the affected operations in the OAS |
| SQG-blocking conformance | Correct response schemas, required fields, or parameter definitions to align the OAS with actual API behaviour |
| Non-SQG-blocking conformance (any severity) | Surface only; ask user if they want to address them |

### 12e — Server-side / Implementation Fixes

OAS fixes document the contract but do not secure the API. Every SQG-blocking finding has a root cause in the server-side code. After 12d, continue to 12e to locate and fix the implementation.

#### 12e-1 — Gate

Trigger 12e for every confirmed finding that is SQG-blocking:
- 🔴 Authorization failures (BOLA / BFLA confirmed)
- 🟠 Conformance findings matched in `sqgDetails[].blockingRules`

Skip 12e entirely only when the scan has zero SQG-blocking findings.

#### 12e-2 — Consent gate for code fixes

Call `AskUserQuestion`:
- **question**: `"The OAS has been updated. The following SQG-blocking issues also require server-side code fixes — the API implementation is the root cause. Should I locate and fix the code? <list all SQG-blocking findings by operation>"`
- **options**: `["Yes — find and fix the code", "Show me the relevant code first", "No — skip code fixes"]`

If **"Show me the relevant code first"** is chosen, locate each handler (step 12e-3) and display the relevant code block without making any changes, then call `AskUserQuestion` again with the same options to proceed.

#### 12e-3 — Locate route handlers

For each SQG-blocking finding:

1. Search the codebase for files that register or handle the affected HTTP method + path. Use grep for the path fragment and common framework patterns: `router.get/post/put/delete/patch`, `@app.route`, `@GetMapping`, `@PostMapping`, `@RestController`, `app.get(`, `Route::get(`, etc.
2. If not found by path, widen the search to the operation ID or a handler name derived from the path.
3. Read the identified handler file and any middleware it calls (auth middleware, serializers, validators, permission decorators).
4. Report: `"Found handler for <METHOD> <path> in <file>:<line>."`
5. If no handler is found after the widened search, report it as not found and skip the fix for that operation — do not block the remaining fixes.

#### 12e-4 — Apply fix by finding type

| Finding type | Root cause to look for in the code | Server-side fix |
|---|---|---|
| **BOLA** (OWASP API1) | Handler fetches a resource by a path/query ID without verifying that it belongs to the authenticated user | Add an ownership check after the resource is fetched: compare `resource.owner_id` (or equivalent field) to the authenticated user's ID; return `403 Forbidden` if they do not match |
| **BFLA** (OWASP API5) | Handler for a privileged/admin operation does not check the caller's role, scope, or group membership before executing | Add a role/scope/permission check at the top of the handler; return `403 Forbidden` if the caller lacks the required privilege |
| **Conformance — undocumented response fields** | Response serializer or ORM query returns fields not present in the OAS schema | Call `AskUserQuestion`: _"The response for `<METHOD> <path>` includes fields not declared in the OAS: `<field list>`. Are these intentional?"_ — **options**: `["Add them to the OAS (field is intentional)", "Remove them from the code (field should not be returned)"]`. Apply the chosen fix: extend the OAS schema, or filter/exclude the fields in the serializer/handler |
| **Conformance — missing required response fields** | Handler response omits a field marked `required` in the OAS schema | Add the missing field to the response payload or serializer |
| **Conformance — wrong response status code** | Handler returns a status code that differs from what the OAS declares as the success code | Update the handler to return the status code declared in the OAS |
| **Conformance — wrong or missing Content-Type / headers** | Handler does not set the `Content-Type` or other response headers required by the OAS | Add the required headers to the response |
| **Conformance — schema type/format mismatch** | Handler returns a field with a different type or format than declared (e.g., returns a string where the OAS declares integer) | Coerce or cast the field to the declared type/format in the serializer or handler |

#### 12e-5 — Diff and confirm before writing

For each proposed code change, display it in unified diff format and call `AskUserQuestion`:
- **question**: `"Apply this fix to <file>?"` — **options**: `["Yes", "No — skip this one"]`

Only write the change after explicit confirmation. Advance to the next finding only after the current one is confirmed or skipped.

#### 12e-6 — Summary

After all code fixes are applied or skipped, append to the final output:

```
── Server-side Fixes ────────────────────────────────────────────────────
  Fixed:   <n> issue(s) across <m> file(s)
  Skipped: <k> issue(s) (user declined or handler not found)
─────────────────────────────────────────────────────────────────────────
```

### 12f — Permission Gate Before Verification Scan

After Step 12e is complete (all server-side fixes applied or skipped), ask the
user whether they want to run the final verification scan before the final
scan summary is presented.

Call `AskUserQuestion`:
- **question**: `"Would you like me to run a final verification scan after the code fixes?"`
- **options**: `["Yes — run the verification scan", "No — skip it and continue to the final scan summary"]`

If the user selects **No**:
- Continue directly to the final scan summary output.

If the user selects **Yes**:
- Continue to Step 12g.

### 12g — Optional API Restart Before Verification Scan

Ask whether the API needs to be restarted for the code fixes to take effect.

Call `AskUserQuestion`:
- **question**: `"Do you need to restart the API for the code fixes to take effect?"`
- **options**: `["No — run the scan now", "Yes — I need to restart it first"]`

If the user selects **No**:
- Run the verification scan using the Step 10 command for the active mode, then continue to Step 12h.

If the user selects **Yes**:
- Ask a follow-up question:
  - **question**: `"Have you restarted the API?"`
  - **options**: `["Yes — run the scan now", "No — not yet"]`
- If the user selects **Yes**:
  - Run the verification scan using the Step 10 command for the active mode, then continue to Step 12h.
- If the user selects **No**:
  - Wait for the API to be restarted, then ask the same question again.

### 12h — Post-Verification Checkpoint

After the verification scan completes, check `sqgPass` from the scan output.

**If `sqgPass: true` (SQG passed):**
- Proceed directly to the final scan summary output.

**If `sqgPass: false` (SQG still failing):**

Display the updated findings report (same three-tier structure from Step 12a) reflecting the verification scan results.

Then call `AskUserQuestion`:
- **question**: `"The SQG is still failing after applying fixes. Would you like me to address more issues, or finish here and review the final summary?"`
- **options**: `["Yes — fix more issues", "No — present the final scan summary"]`

If the user selects **Yes — fix more issues**:
- Re-enter the fix loop starting at Step 12b (determine new fix candidates from the verification scan results), then 12c → 12d → 12e → 12f → 12g → 12h.
- Continue this loop until either `sqgPass: true` or the user selects **No** at this checkpoint.

If the user selects **No — present the final scan summary**:
- Proceed to the final scan summary output.

**Token mode**: `sqgPass` is always `true` or absent — Step 12h is a no-op; proceed directly to the final scan summary output.

---

## Flags Reference

```
--conf-file <path>      explicit path to scan config bundle (preferred)
--conf-name <name>      scan config name from .42c dir (default "default")
-d, --directory <path>  working directory (default: .42c at git root)
--tag <cat>:<tag>       apply platform tag for SQGs / data dictionaries
--output-report <file>  write just the config bundle (report section) to file
--report-sqg            include sqg_pass in the report
```

### `scan conf generate` — important notes

- **`<api-reference>` must be a file path** (relative from git root), NOT an alias.
  Aliases are not resolved by `generate` — passing an alias causes "no such file or directory".
- **Do not use `-d` or `--conf-name`** when generating. Using those flags writes a
  fragmented multi-file format to disk instead of outputting the monolithic bundle to stdout.
- Use `--output-format json --output .42c/scan/<alias>/scanconf.json` to write the config directly.

### api-reference formats accepted by `scan run` and `scan conf validate`

- Path to an OAS file (`.json` / `.yaml` / `.yml`) — use with `--conf-file`
- Alias defined in `.42c/conf.yaml` — use with `--conf-name`
- `<api-id>:<revision>` (requires valid `API_KEY` — fetched from platform)


---

## Scanconf Template

When building or repairing a config manually (config is missing, invalid, or
has structural gaps), read `./scanconf-templates.md` for the complete JSON
patterns and the rules-at-a-glance table.
