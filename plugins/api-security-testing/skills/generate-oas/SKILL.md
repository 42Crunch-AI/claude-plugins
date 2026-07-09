---
name: generate-oas
description: >
  Generate a complete OpenAPI 3.0 (OAS) specification from an API codebase, a
  Postman or Insomnia collection, or both together. Use this skill whenever
  the user wants to generate, create, or derive an OpenAPI spec,
  reverse-engineer an API definition, document an existing API, or convert a
  Postman/Insomnia collection to OpenAPI — when there is no existing OAS file
  yet. Triggers on phrases like "generate OAS", "create an OpenAPI spec",
  "generate openapi.json", "document my API", "reverse-engineer spec",
  "convert postman to openapi", "convert insomnia to openapi", "postman
  collection to OAS", "insomnia collection to OAS", or any request to produce
  an OAS file from source material rather than from an existing spec.
---

# Generate an OpenAPI Specification

Produces a complete, valid **OpenAPI 3.0.x** specification file (`openapi.json`)
from one or two source materials:

- an **API codebase** (any language/framework), and/or
- an **API client collection** — either a **Postman collection** (v2.0 or
  v2.1, with an optional environment file) or an **Insomnia collection**
  (v4 JSON export, or v5 JSON/YAML export, with an optional separate
  environment export)

No existing OAS file is required. When both a codebase and a collection are
available, the codebase is treated as the primary source of truth for
structure — routes, validation, security — and the collection is used to
enrich the result with concrete, real-world examples and to surface any
endpoint the codebase analysis missed.

---

## Entry Point

Ask about sources **one at a time**, codebase first, in this order.

### 1. Codebase

**Call `AskUserQuestion`:**
- question: "Do you have the API codebase available to generate the spec from?"
- options: `["Yes — I'll point you to it", "No"]`

If yes, **call `AskUserQuestion`** to ask for the root directory:
- question: "What is the root directory of the API codebase?"
- options: `["Current working directory", "A specific subdirectory (type custom path in other)"]`

The user can always type a custom path via the "Other" option.

### 2. API client collection

**Call `AskUserQuestion`:**
- question: "Do you have a Postman or Insomnia collection for this API?"
- options: `["Postman", "Insomnia", "No"]`

If **Postman**, **call `AskUserQuestion` twice, as two separate calls**:
1. First call — ask for the Postman collection file path (JSON, v2.0 or
   v2.1 — required).
2. Second call — ask for the Postman environment file path (optional —
   skip if none).

If **Insomnia**, **call `AskUserQuestion` twice, as two separate calls**:
1. First call — ask for the Insomnia export file path (required) — JSON
   for v4, JSON or YAML for v5. Detect the version automatically once read
   (see [Insomnia Collection](#insomnia-collection) below); don't ask the
   user to specify it.
2. Second call — ask for a separate Insomnia environment export file path
   (optional — skip if the main export already contains the environment(s),
   which is the common case for a full workspace export).

### 3. Resolve the mode

- **Neither** source provided → stop. Tell the user a codebase, a
  Postman/Insomnia collection, or both are required to generate an OAS file,
  and offer to restart once one is available.
- **Codebase only** → run [Codebase Analysis](#codebase-analysis), then
  [Synthesize the Specification](#synthesize-the-specification).
- **Collection only** → run [Postman Collection](#postman-collection) or
  [Insomnia Collection](#insomnia-collection) (whichever was provided), then
  [Synthesize the Specification](#synthesize-the-specification).
- **Both** → run [Codebase Analysis](#codebase-analysis) and the applicable
  collection section (independently, each producing its own normalized
  model), then [Merge Codebase and Collection Models](#merge-codebase-and-collection-models),
  then [Synthesize the Specification](#synthesize-the-specification).

### 4. Output path

**Call `AskUserQuestion`** to confirm the output file path, defaulting to:
- `openapi.json` at the codebase root (if a codebase was provided), else
- `openapi.json` next to the collection file

**Announce the plan**, e.g.:
> "I'll analyze the codebase as a `<framework>` API [and enrich it with the
> Postman/Insomnia collection] and generate `<output path>`. This may take a
> moment."

Never overwrite an existing OAS file without first reading it and confirming
intent with the user (unless it is clearly a scaffold or stub).

---

## Codebase Analysis

Skip this section entirely if no codebase was provided. Produce a normalized
in-memory model (routes, params, bodies, responses, security, schemas,
server config, info) — do not write any file yet.

### C1 — Detect the language and framework

Scan for indicators before opening implementation files, and only open files
needed to confirm the framework:
- `package.json` → Node.js. Check `dependencies` for `express`, `fastify`,
  `koa`, `hapi`, `nestjs`, `@nestjs/core`.
- `requirements.txt` / `pyproject.toml` / `setup.py` → Python. Check for
  `fastapi`, `flask`, `django`, `starlette`, `tornado`.
- `pom.xml` / `build.gradle` → Java/Kotlin. Check for `spring-boot`,
  `quarkus`, `micronaut`.
- `go.mod` → Go. Check for `gin`, `echo`, `chi`, `gorilla/mux`, `fiber`.
- `Gemfile` → Ruby. Check for `rails`, `sinatra`, `grape`.
- `*.csproj` / `*.sln` → C#/.NET. Check for `AspNetCore`, `WebApi`.
- Any existing partial OAS file (e.g. `openapi.yaml`, `swagger.json`) — read
  it and use it as a starting scaffold, then extend/correct it.

### C2 — Discover route / controller files

Locate the files that define HTTP routes or controllers, matched to the
detected framework:

| Framework | Look for |
|---|---|
| **Express** | Files importing `express.Router()`, `app.get/post/put/delete/patch` |
| **FastAPI** | Files with `@app.get`, `@router.get`, `APIRouter()` |
| **Flask** | Files with `@app.route`, `@blueprint.route` |
| **Django** | `urls.py` files, `path()` / `re_path()` / `url()` calls |
| **NestJS** | Files with `@Controller`, `@Get`, `@Post`, `@Put`, `@Delete`, `@Patch` |
| **Spring** | Files with `@RestController`, `@RequestMapping`, `@GetMapping`, etc. |
| **Gin/Echo/Chi** | Files calling `r.GET`, `r.POST`, `e.GET`, `r.Route`, `chi.NewRouter()` |
| **Rails** | `config/routes.rb` |
| **Sinatra/Grape** | Files with `get '/'`, `post '/'`, `resource :name` |

Read only the discovered route files needed to enumerate endpoints. For each
route, record: HTTP method, path string (convert framework syntax to OAS
syntax: `:param` → `{param}`, `<param>` → `{param}`, `{param:int}` →
`{param}`), handler function name (seed for `operationId`), and applied
middleware.

### C3 — Extract operation details from handlers

For each route handler, read only the sections needed to extract the
contract:

- **Path parameters** — any `{id}`-style segment; `in: path`, `required: true`.
- **Query parameters** — Express: `req.query.foo`; FastAPI: function args
  without `Body()` and not in the path; Flask: `request.args.get('foo')`;
  Django: `request.GET.get('foo')`; Spring: `@RequestParam`; Go:
  `c.Query("foo")`, `r.URL.Query().Get("foo")`.
- **Request body** — Express: `req.body`; FastAPI: `Body()`/Pydantic params;
  Flask: `request.json`/`request.get_json()`; Django: `request.data`,
  `request.POST`; Spring: `@RequestBody`; Go: `c.ShouldBindJSON()`,
  `json.NewDecoder(r.Body)`.
- **Response structure** — `res.json({...})` (Express); `return {...}` with
  type annotations (FastAPI); `jsonify({...})` (Flask); `Response(data, ...)`
  (Django REST); `ResponseEntity<>` (Spring); `c.JSON(200, ...)` (Gin). Note
  every distinct status code and response body shape.
- **Auth headers** — `req.headers['authorization']`, `Authorization: Bearer`
  checks, custom headers like `x-api-key`, `x-user-id`.

### C4 — Identify authentication / middleware

Read middleware files. Map patterns to security schemes:
- JWT verification → `http` / `bearer` / `bearerFormat: JWT`
- API key header check → `apiKey`, `in: header`
- API key query param check → `apiKey`, `in: query`
- Basic auth → `http` / `basic`
- OAuth2 / OIDC → `oauth2` / `openIdConnect`
- Session / cookie auth → `apiKey`, `in: cookie`

For each route, determine whether auth is applied at the router/group level,
per-route, or excluded via an allowlist (e.g. `/login`, `/register` public).
Map each route to **authenticated** (scheme) or **public**.

### C5 — Discover data models / schemas

Locate model/schema/DTO definitions:

| Framework | Source |
|---|---|
| **Express + Mongoose** | `mongoose.Schema({...})` |
| **Express + Sequelize** | `sequelize.define(...)` or class models |
| **Express + TypeORM** | `@Entity` classes |
| **FastAPI** | Pydantic `BaseModel` subclasses |
| **Flask + SQLAlchemy** | `db.Model` subclasses |
| **Django** | `models.Model`, `serializers.Serializer` subclasses |
| **Spring** | `@Entity`, `@Document`, DTO/POJO classes |
| **Go** | `type Foo struct { ... }` with JSON tags |
| **Rails** | ActiveRecord model files, serializer files |

For each model, extract fields with types, required vs optional, validation
constraints (`minLength`, `maxLength`, `minimum`, `maximum`, `pattern`,
`enum`), and relationships (for reference only). Map framework types to OAS:

| Framework type | OAS `type` + `format` |
|---|---|
| `String` / `str` / `string` | `type: string` |
| `Number` / `float` / `Float` | `type: number, format: float` |
| `Int` / `int` / `Integer` / `Long` | `type: integer, format: int64` |
| `Boolean` / `bool` | `type: boolean` |
| `Date` / `DateTime` / `datetime` | `type: string, format: date-time` |
| `Buffer` / `bytes` / `BinaryField` | `type: string, format: binary` |
| `Array` / `List` / `[]Type` | `type: array, items: <schema>` |
| `Object` / `Dict` / `Map` | `type: object` |
| `ObjectId` / `UUID` / `uuid` | `type: string, format: uuid` |
| `Email` / `EmailStr` | `type: string, format: email` |
| Enum | `type: string, enum: [...]` |

### C6 — Discover server configuration and supporting files

Find the base URL/port (`app.listen(PORT)`, `uvicorn.run(...)`,
`server.port`, `http.ListenAndServe(":PORT", ...)`, `docker-compose.yml`,
`.env`, `Dockerfile`) and any URL prefix (`app.use('/api/v1', router)`,
`app.include_router(router, prefix=...)`, `@RequestMapping('/api/v1')`).

Read `README.md`, any existing partial OAS, `CHANGELOG.md`, `.env.example`,
and the `version` field in `package.json`/`pyproject.toml` to populate
`info.title`, `info.description`, `info.version`, `info.contact`,
`info.license`.

This produces the **codebase model**: routes with params/bodies/responses/
security, schemas, servers, and info — ready for merging or synthesis.

---

## Postman Collection

Skip this section entirely if no Postman collection was provided. Produce a
normalized in-memory model with the same shape as the codebase model plus
concrete examples — do not write any file yet.

### P1 — Read and parse the collection

Confirm valid Postman format via `info.schema` containing
`postman-collection`. Identify schema version (`v2.1.0` vs `v2.0.0` — handled
identically thereafter). Extract `info.name` → `info.title` candidate,
`info.description`, `info.version` (fall back `"1.0.0"`), and `variable[]`.

If an environment file was provided, parse its `values[]` into a flat map.
Environment values take precedence over collection-level variables when
resolving `{{variableName}}` placeholders, and are a preferred source of
concrete examples (e.g. `userId`, `token`, `baseUrl`).

Build a merged variable map: start with collection `variable[]`, overlay
environment `values[]` (environment wins on key collision).

### P2 — Flatten the collection into a request list

Recursively walk the `item` tree: entries with an `item` array are folders
(recurse, track breadcrumb for tagging); entries with a `request` property
are leaf requests (extract).

For each leaf request, extract:
- **URL** — resolve `{{variableName}}` via the merged variable map; split into
  protocol/host/port/path segments.
- **Method** — normalized uppercase.
- **Path variables** — `url.variable[]` → concrete values for path params;
  convert all path-param syntaxes to OAS `{paramName}`.
- **Query parameters** — `url.query[]`, excluding `disabled: true`, resolving
  variables.
- **Request headers** — `header[]`, excluding `disabled: true`, excluding
  `Content-Type`/`Accept`; retain `Authorization` only to infer security
  schemes (never emit as a header parameter).
- **Request body** — `mode: raw` + `json` → parse as JSON (fallback: raw
  string schema); `xml`/`text`/`html` → record content type only;
  `formdata` → `{key, value, type}` pairs; `urlencoded` → `{key, value}`
  pairs; `graphql` → `application/json` with `query`/`variables`; `file` →
  `multipart/form-data` binary field; no body/`mode: none` → omit
  `requestBody`.
- **Responses** — `item.response[]`: `status`, `name`, `header[]`, `body`
  (parse as JSON if possible), `_postman_previewlanguage`.

**Skip attack-oriented requests** entirely (do not add to the model):
- Bodies containing SQL keywords (`SELECT`, `UNION`, `DROP`, `--`), NoSQL
  operators (`$ne`, `$gt`, `$where`, `$regex`), XML injection
  (`<!DOCTYPE`, `ENTITY`), path traversal (`../`), or script tags in JSON
  string values.
- Requests under folders named like `Attacks`, `Security Tests`, `Exploits`,
  `Abuse`, `Negative Tests`, or with names indicating exploit scenarios
  (`SQL Injection`, `XSS`, `XXE`, `Log4Shell`, `Privilege Escalation`,
  `BOLA`, `BFLA`, `Un-authenticated Access`, `HTTP Verb Tampering`).

When in doubt, exclude and note it in the final summary.

### P3 — Infer authentication schemes

Walk each request's `auth` block and `Authorization` header:
- `type: bearer` → `http`/`bearer`/`JWT`
- `type: basic` → `http`/`basic`
- `type: apikey` → `apiKey`, check `in`: `header`/`query`/`cookie`
- `type: oauth2` → `oauth2`; extract `authUrl`, `accessTokenUrl`, `scope`
- `type: noauth` → explicitly public
- Collection-level `auth` applies as default unless overridden per-request
- Header value patterns: `Bearer ...` → bearer; `Basic ...` → basic;
  `ApiKey ...` → API key in header

Deduplicate into canonical scheme names: `BearerAuth`, `BasicAuth`,
`ApiKeyAuth`, `ApiKeyQuery`, `OAuth2`. Track which requests use which scheme;
`type: noauth` requests get `"security": []`.

### P4 — Derive base URL(s) and servers

Collect all unique `protocol://host:port` combinations from resolved URLs.
One unique base → `servers[0].url`. Multiple → list all with descriptions
(`"Local development"`, `"Production"`, etc.). A `{{baseUrl}}`-style base →
emit a server variable with the resolved default. No determinable base →
fall back to `http://localhost`. Strip the base URL from each request's path.

### P5 — Synthesize schemas from bodies

For each unique request/response body (grouped by path + method), infer a
JSON Schema: objects → `type: object` with `properties`; strings → `type:
string` (ISO date pattern → `format: date-time`); integer vs decimal
numbers → `integer`/`number`; booleans → `boolean`; `null` → `nullable:
true`; arrays → `type: array` with `items` inferred from the first element;
nested objects recurse. Mark a property `required` when non-null/non-empty
in the example. Set `example` from the Postman value (prefer resolved
environment values).

Form/urlencoded bodies → `properties` of `type: string` (file fields →
`type: string, format: binary`).

After inference, deduplicate structurally identical schemas across
operations and name them after the resource in the path (`/users/{userId}`
→ `User`; `/auth/login` request → `LoginRequest`, response → `LoginResponse`).
PascalCase throughout; use `$ref` for reused schemas.

### P6 — Build path and parameter entries

For each unique (normalized path, method): merge multiple saved
requests/responses into one operation, picking the most representative body
example. Path parameters get `in: path, required: true` with an example and
inferred type (digits-only → `integer`; UUID pattern → `format: uuid`).
Query parameters get `in: query`, `required: true` only if present with a
non-empty value in every saved variant. Only non-auth, non-standard headers
become `in: header` parameters (omit `Content-Type`, `Accept`,
`Authorization`, `Host`, `User-Agent`, `Content-Length`, `Connection`).
Response headers follow the same omission list.

This produces the **collection model**: operations with params/bodies/
responses/security/examples, schemas, servers, and info — ready for merging
or synthesis.

---

## Insomnia Collection

Skip this section entirely if no Insomnia collection was provided. Produce a
normalized in-memory model with the **same shape** as the Postman model
above (params, bodies, security, schemas, servers, info) — do not write any
file yet. One structural gap vs. Postman: standard Insomnia exports do not
include saved example responses, so response status codes and bodies
generally cannot be inferred from an Insomnia collection alone (see I6).

### I0 — Detect the export format and version

Read the file and branch on its shape:
- **v4 (JSON only)** — top-level `_type: "export"` and `__export_format: 4`,
  with a flat `resources[]` array.
- **v5 (JSON or YAML)** — top-level `type: "collection.insomnia.rest/5.0"`
  (parse as YAML if the file isn't valid JSON, or if its extension is `.yaml`/
  `.yml`), with a nested `collection[]` tree.
- If a separate environment export was provided, detect its format the same
  way: v4 environment resources have `_type: "environment"`; a standalone v5
  environment export has top-level `type: "environment.insomnia.rest/5.0"`.

### I1 — Read and parse the collection, build the variable map

**v4:** Walk `resources[]`. Entries with `_type: "workspace"` are the root;
entries with `_type: "environment"` hold `data: {key: value}` — there is
typically a base environment (`parentId` = workspace id) and zero or more
sub-environments (`parentId` = base environment id). Merge order: base
environment → overlay each sub-environment in order → overlay the separate
environment export, if one was provided.

**v5:** Read the top-level `environments` object: `data` on the root entry is
the base environment; `subEnvironments[]` overlay it in order. Same merge
order and precedence as v4. `meta.name`/`name`/description-equivalent fields
seed `info.title`/`info.description` if not already set from a codebase.

Both versions use Nunjucks templating (`{{ variableName }}`, or
`{{ _.variableName }}` to explicitly scope to environment data, plus
`{% tagName %}` function tags like `{% uuid %}`, `{% timestamp %}`,
`{% prompt %}`, `{% response %}`). Build a merged variable map from the
resolved environment data. Resolve `{{ ... }}` / `{{ _.* }}` references
against this map wherever they appear in URLs, headers, parameters, and
bodies. Leave `{% ... %}` function tags unresolved — they are computed at
send-time, not static values — and record the tag name as a placeholder
`example` (e.g. `<generated-uuid>` for `{% uuid %}`).

### I2 — Flatten the collection into a request list

**v4:** Entries with `_type: "request_group"` are folders; entries with
`_type: "request"` are leaf requests. Build the tree via `parentId`
(child → parent id), tracking folder-name breadcrumbs from workspace down to
each request for tag assignment, same as Postman folder breadcrumbs.

**v5:** Walk the nested `collection[]` tree directly: an entry with a
`children[]` array is a folder (recurse, track breadcrumb); an entry with a
`url`/`method` is a leaf request.

For each leaf request, extract (field names are identical across v4/v5
unless noted):
- **URL** — resolve template variables via the merged map; split into
  protocol/host/port/path segments. A path segment that is *entirely* a
  template tag (e.g. `{{ _.userId }}`) is a path parameter — use the
  variable name (stripped of any `_.` prefix) as the OAS parameter name and
  convert the segment to `{paramName}`.
- **Method** — normalized uppercase.
- **Query parameters** — `parameters[]`: `{name, value, disabled}`; exclude
  `disabled: true`; resolve template variables.
- **Request headers** — `headers[]`: `{name, value, disabled}`; exclude
  `disabled: true`; exclude `Content-Type`/`Accept`; retain `Authorization`
  only to infer security schemes (never emit as a header parameter).
- **Request body** (`body.mimeType`) — `application/json` → parse `body.text`
  as JSON (fallback: raw string schema); `application/xml`/`text/plain`/
  `text/html` → record content type only; `multipart/form-data` → `body.params[]`
  as `{name, value, type}` pairs (`type: "file"` → binary field);
  `application/x-www-form-urlencoded` → `body.params[]` as `{name, value}`
  pairs; `application/graphql` → `application/json` with a `query`/
  `variables` shape; no `body` or empty `mimeType` → omit `requestBody`.
- **Responses** — none (see I6).

Apply the **same attack-request exclusion rules** as Postman P2 (SQL/NoSQL/
XML-injection/path-traversal payloads in bodies; folders or request names
indicating exploit scenarios). When in doubt, exclude and note it in the
summary.

### I3 — Infer authentication schemes

Walk each request's `authentication` object (falls back to a parent
folder's/workspace's `authentication` if the request doesn't set its own —
same inheritance model as Postman's per-request vs. collection-level `auth`):
- `type: "bearer"` → `http`/`bearer`/`JWT` (`bearerFormat` from
  `authentication.token` shape if discernible, else default `JWT`)
- `type: "basic"` → `http`/`basic`
- `type: "apikey"` → `apiKey`; `addTo: "header"` → `in: header`;
  `addTo: "queryParams"` → `in: query`
- `type: "oauth2"` → `oauth2`; extract `authorizationUrl`, `accessTokenUrl`,
  `scope` where present
- `type: "none"` or no `authentication` object → explicitly public
- `Authorization` header value patterns (when no structured `authentication`
  object is set): `Bearer ...` → bearer; `Basic ...` → basic

Deduplicate into the same canonical scheme names used for Postman:
`BearerAuth`, `BasicAuth`, `ApiKeyAuth`, `ApiKeyQuery`, `OAuth2`. A request
with `type: "none"` gets `"security": []`.

### I4 — Derive base URL(s) and servers

Same approach as Postman P4: collect unique `protocol://host:port`
combinations from resolved URLs; one unique base → `servers[0].url`;
multiple → list all with descriptions; a templated base
(e.g. `{{ _.base_url }}`) → emit a server variable using the resolved
environment value as the default; no determinable base → fall back to
`http://localhost`. Strip the base URL from each request's path.

### I5 — Synthesize schemas from request bodies

Apply the same JSON-to-schema inference as Postman P5, but from request
bodies only (there are no saved response bodies to draw from — see I6). Mark
properties `required` when non-null/non-empty in the example; set `example`
from the Insomnia value (prefer resolved environment values over literal
placeholder text); deduplicate structurally identical schemas and name them
after the resource in the path, same conventions as Postman (`PascalCase`,
`$ref` for reuse).

### I6 — Build path/parameter entries and handle the missing-responses gap

Build `parameters` and `requestBody` exactly as in Postman P6 (path params
`required: true` with inferred type; query params `required: true` only if
present with a non-empty value on every variant of that operation; only
non-auth, non-standard headers become `in: header` parameters).

Because Insomnia exports carry no saved responses, every operation gets a
placeholder response set instead of observed ones:
- `200` (or `201` for `POST` if the path suggests creation, e.g. no trailing
  path parameter) with `description: "Success"` and a response schema built
  **only from fields with direct evidence in the collection** — never a
  copy of the request body schema and never an invented field. Two sources
  count as direct evidence:
  - A `properties`/test/`afterResponse` script that reads a named field off
    the parsed response (e.g. `insomnia.response.json().id`,
    `jsonData.token`) — this confirms that field's name (and, loosely, its
    type from how it's used) exists in the response. Include only the
    field(s) actually referenced this way.
  - Explicit prose in the request/folder `description` that names a
    concrete field (e.g. "returns a JSON web token" → a `token` field).
  If no such evidence exists for a given operation, do not include any
  `properties` at all — emit `type: object` with `additionalProperties:
  true` and nothing else. Do not pad a partially-evidenced schema with
  request-body fields "for completeness"; a schema with only the one or two
  confirmed fields is correct, an inflated one is not.
- The same `400`/`401`/`403`/`404`/`500` additions as the general response
  rules in [Synthesize the Specification](#synthesize-the-specification).

Flag this limitation clearly in the final report (see
[Report to the User](#report-to-the-user)) so the user knows which response
fields are directly evidenced vs. which operations got the bare
`additionalProperties: true` placeholder — this gap narrows as more
evidence surfaces and disappears when a codebase is also provided and
merged in.

This produces the **collection model**: operations with params/bodies/
responses/security/examples, schemas, servers, and info — ready for merging
or synthesis.

---

## Merge Codebase and Collection Models

Only when both a codebase and a collection (Postman or Insomnia) were
provided. The codebase model is the structural source of truth; the
collection model supplies real examples and coverage checks.

1. **Match operations.** Pair codebase and collection operations by HTTP
   method and path shape (same literal segments and segment count; parameter
   names may differ — e.g. `/users/{id}` matches `/users/{userId}`). Use the
   codebase's parameter name in the merged result.

2. **For matched operations:**
   - Keep the codebase's parameter list, request/response schema structure,
     `required` flags, and validation constraints — code-derived types are
     more reliable than inferred-from-example types.
   - Overlay collection-derived `example` values onto matching parameters and
     schema properties by name (path/query/header params, request body
     fields, response body fields).
   - Union the response status codes: keep every status the codebase
     produces, and add any additional status the collection captured that
     the codebase analysis didn't surface (e.g. a `404` only seen in a saved
     Postman response). If the collection is Insomnia, it contributes no
     observed statuses (see I6) — the codebase's statuses stand as-is, and
     the placeholder-response gap is resolved by the codebase's real ones.
   - Union security: keep the codebase-detected scheme; if the collection's
     recorded auth implies a scheme the codebase missed, add it and note
     the discrepancy for the report.

3. **Operations only in the collection** (no codebase route matched — e.g. a
   dynamically-registered route, or a call the static analysis missed):
   add them to the merged model as-is, using the collection-inferred schema
   (and, for Insomnia, the placeholder responses from I6). Flag each in the
   final report as "found only in the [Postman/Insomnia] collection — verify
   against the codebase."

4. **Operations only in the codebase** (no matching saved request in the
   collection): keep them as-is; they simply have no `example` enrichment.
   Flag as "no example data available" in the report.

5. **`info` and `servers`:** prefer codebase-derived `info` (README,
   `package.json`/`pyproject.toml`) when present, falling back to the
   collection's `info` for any missing field. Union `servers` from both
   sources, deduplicating identical URLs.

6. **Schemas:** prefer the codebase-derived schema for a given resource
   name; if the collection model has an equivalent schema with additional
   fields the codebase missed (e.g. a computed/joined field only visible in
   a live response), add those fields as additional properties and note it.

The result of this step is a single merged model with the same shape as
either individual model, ready for synthesis.

---

## Synthesize the Specification

Build the complete OAS 3.0 document in memory before writing, from
whichever model applies (codebase-only, collection-only, or merged).

### `openapi` and `info`

```json
"openapi": "3.0.3",
"info": {
  "title": "<API name>",
  "description": "<description; CommonMark supported>",
  "version": "<version>",
  "contact": { "name": "...", "email": "..." },
  "license": { "name": "...", "url": "..." }
}
```

Omit `contact`/`license` if not found in any source.

### `servers`

```json
"servers": [
  { "url": "http://localhost:<PORT>", "description": "Local development server" }
]
```

Add staging/production servers found in either source's config.

### `tags`

One tag per resource noun (codebase: `/vehicles/*` → `Vehicles`) or per
top-level collection folder when only a Postman/Insomnia collection is
available. List all tags at the root `tags` field with short descriptions.

### `components.securitySchemes`

One entry per distinct scheme found across whichever sources were used.
Descriptive names: `BearerAuth`, `ApiKeyAuth`, `BasicAuth`, `OAuth2`.

### `components.schemas`

One schema per model/resource, PascalCase, deduplicated, referenced via
`$ref` everywhere reused. For request schemas, exclude `readOnly` fields
(`id`, `createdAt`, `updatedAt`) from what's required to submit; mark them
`"readOnly": true` on the base schema instead of creating parallel
`CreateFoo`/`Foo` schemas unless the shapes genuinely differ.

### `paths`

For each operation:

```json
"/path/{param}": {
  "<method>": {
    "operationId": "<camelCase unique id>",
    "summary": "<short description>",
    "description": "<longer description if needed>",
    "tags": ["<resource tag>"],
    "parameters": [
      { "name": "param", "in": "path", "required": true, "schema": { "type": "string" } }
    ],
    "requestBody": {
      "required": true,
      "content": { "application/json": { "schema": { "$ref": "#/components/schemas/FooRequest" } } }
    },
    "responses": {
      "200": { "description": "Success", "content": { "application/json": { "schema": { "$ref": "#/components/schemas/Foo" } } } },
      "400": { "description": "Bad request — invalid input" },
      "401": { "description": "Unauthorized — missing or invalid credentials" },
      "404": { "description": "Not found" },
      "500": { "description": "Internal server error" }
    },
    "security": [{ "BearerAuth": [] }]
  }
}
```

Omit `requestBody` for `GET`/`DELETE`/`HEAD`. Omit `security` on public
routes, or set `[]` to override a global default.

**`operationId` rules:** globally unique, camelCase. Prefer the codebase
handler name when available (`getVehicleById`); otherwise derive from the
collection request name (`"Get User By ID"` → `getUserById`); otherwise fall
back to `<method><Resource>`. On collision, append a numeric suffix
(`getUser`, `getUser2`).

**Response rules:**
- Include every status code explicitly observed in either source.
- Always add `401` to authenticated routes, `404` to routes with path
  parameters that fetch a resource, `400` to routes accepting a request
  body, `403` if authorization checks are present, and `500` always.
- If an operation came from Postman with no saved responses at all, emit a
  single `default: { "description": "Unexpected error" }` instead.
- If an operation came from an Insomnia collection with no codebase to
  supply real responses, use the placeholder response built in I6 rather
  than a bare `default` entry — it at least carries a best-effort schema.

**Apply global security:** if the majority of operations share one scheme,
set it at the document root and override public routes with
`"security": []`. If auth is mixed or inconsistent, apply `security`
per-operation only.

---

## Write the File and Self-Review

**Output location:** the path confirmed in the Entry Point step. Never
overwrite an existing file without reading it and confirming intent first.

**Format:** JSON, 2-space indentation. Root key order: `openapi`, `info`,
`servers`, `tags`, `paths`, `components`.

Before writing, run the self-review checklist and fix any violations found:
- Every `$ref` resolves to a defined component
- Every `{param}` in a path has a matching `in: path` parameter with
  `required: true`
- Every `operationId` is unique
- Every response has a `description`
- No path is missing a leading `/`
- No duplicate (path, method) combinations
- `requestBody` never appears on `GET`, `DELETE`, or `HEAD` operations
- Uses `nullable: true` (OAS 3.0 style), never `type: ["string", "null"]`
  (OAS 3.1 style)

---

## Report to the User

After writing the file, output a summary:

```
OpenAPI Specification Generated
  File:       <relative path to openapi.json>
  OAS version: 3.0.3
  Sources:    <"Codebase (<framework>)" | "Postman collection" | "Insomnia collection (v4|v5)" | "Codebase (<framework>) + Postman collection" | "Codebase (<framework>) + Insomnia collection (v4|v5)">
  Servers:    <N server URLs>
  Paths:      <N> endpoints
  Tags:       <list of tags>
  Schemas:    <N> component schemas
  Security:   <scheme names, or "None detected">

Coverage notes:
  - <endpoints found only in the codebase — no example data available, if applicable>
  - <endpoints found only in the collection — verify against the codebase, if applicable>
  - <requests skipped as attack payloads / attack-demo folders, if a collection was used>
  - <schemas with only partial field evidence — list which field(s) are
    confirmed (and how, e.g. "id — referenced in an afterResponse script")
    vs. left as additionalProperties: true, if Insomnia was used without a
    codebase>
  - <any response bodies or schemas that could not be inferred at all —
    emitted as bare additionalProperties: true>
  - <any assumptions made that the user should verify>
```

---

## Framework-Specific Notes (codebase source)

### Express (Node.js)
- Route files often export a `Router` mounted in a central `app.js`/
  `server.js` — read the entry point to find all mounts and prefixes.
- Middleware like `authenticate`/`verifyToken` applied with `.use()` before
  a route group protects the whole group.
- `req.params`, `req.query`, `req.body` map to path/query/requestBody.

### FastAPI (Python)
- Type annotations on route function parameters are the source of truth for
  schemas.
- `response_model=Foo` gives the response schema; `status_code=201` overrides
  the default `200`.
- Pydantic `BaseModel` subclasses become `components.schemas` directly.

### Flask (Python)
- Blueprint `url_prefix` combines with `@blueprint.route` path.
- Flask-RESTX/Flask-RESTful `Resource` classes map methods to HTTP verbs.
- Marshmallow schemas, if present, are the source of truth for
  serialization/deserialization shapes.

### Django REST Framework
- `ViewSet` routers generate CRUD routes automatically — infer from
  `router.register()` calls.
- `serializers.py` defines schema shapes; `permission_classes` defines auth
  requirements.

### NestJS (TypeScript)
- DTOs annotated with `class-validator` decorators become request schemas.
- `@ApiProperty()` decorators (Swagger module) carry schema metadata —
  prioritize these.
- `@UseGuards(JwtAuthGuard)` marks routes as authenticated.

### Spring Boot (Java/Kotlin)
- `@RequestBody`, `@PathVariable`, `@RequestParam` map directly to OAS
  concepts.
- Controller method return type (including `ResponseEntity<Foo>`) defines
  the response schema.
- `@Valid`/`@Validated` implies validation constraints live on the DTO
  class fields.

### Go (Gin / Echo / Chi)
- Struct tags (`json:"field_name" binding:"required"`) define field names
  and required constraints.
- `c.ShouldBindJSON(&dto)`/`c.BindJSON(&dto)` identifies the request body
  type.
- `r.Use(AuthMiddleware)` before route groups marks those routes as
  authenticated.

---

## Collection Edge Cases

### Postman

- **`{{variableName}}` placeholders** — resolve using the merged variable
  map before any processing; propagate resolved values into `example`
  fields; leave unresolvable placeholders as-is and note them in the
  summary; `{{baseUrl}}` is stripped from the path and becomes a server
  variable or resolved server URL.
- **Pre-request scripts and tests** — ignore entirely; not part of the API
  contract.
- **Security demo folders mixed with functional endpoints** — exclude
  attack/demo requests; keep legitimate operations even if they share an
  endpoint with a skipped attack variant.
- **Collection/folder-level variables** — folder variables apply only within
  that folder. Merge order: environment file > collection variables >
  folder variables > request variables.
- **Auth inheritance** — a folder's `auth` block applies to its requests
  unless a request overrides it with its own `auth` block.
- **Duplicate request names** — append a numeric suffix to the
  `operationId` (`getUser`, `getUser2`).
- **Requests with no URL** — skip silently, note in the summary.
- **GraphQL requests** — emit as a single `POST /graphql` operation with a
  `query`/`variables` body; note the limitation if multiple GraphQL requests
  exist.
- **Multiple content types** — if an operation appears with both JSON and
  form bodies across saved requests, emit both under `requestBody.content`.

### Insomnia

- **No saved responses** — the single biggest gap vs. Postman. Response
  status codes and bodies are best-effort placeholders (see I6) unless a
  codebase is also provided and merged in. Always call this out in the
  final report.
- **`{{ variableName }}` / `{{ _.variableName }}` placeholders** — resolve
  using the merged environment map before any processing (see I1); the
  `_.` prefix explicitly scopes to environment data but is otherwise
  equivalent to a bare `{{ variableName }}` reference for resolution
  purposes.
- **`{% tagName %}` function tags** (`{% uuid %}`, `{% timestamp %}`,
  `{% prompt %}`, `{% response %}`, etc.) — these are computed at send-time,
  not static values. Leave them unresolved in the URL/body structure and
  record a descriptive placeholder as the `example` (e.g. `<generated-uuid>`).
  Never treat a `{% response %}` chained-request tag as a literal value.
- **v4 vs. v5 structural differences** — v4 is a flat `resources[]` array
  linked by `parentId`; v5 is a nested `collection[]`/`children[]` tree
  (JSON or YAML). Detect the version once in I0 and use the matching
  traversal; the extracted per-request fields (I2–I6) are handled
  identically once flattened.
- **Environments and sub-environments** — a v4/v5 collection can define a
  base environment plus multiple named sub-environments (e.g.
  "Development", "Production"). If the user didn't specify which one to
  use and more than one sub-environment exists, ask which to use as the
  default source of example values, or use the base environment alone if
  none is specified and note the ambiguity in the summary.
- **Cookie jar** — ignore `cookieJar`/`_type: "cookie_jar"` entries; not
  part of the API contract.
- **Unit test suites and mock routes** (`unit-test-suite.insomnia.rest/*`,
  `mock-server.insomnia.rest/*` resources/types) — ignore entirely; only
  `request`/`request_group` (v4) or `collection[]` request entries (v5) are
  in scope.
- **Duplicate request names** — same handling as Postman: append a numeric
  suffix to the `operationId`.
- **Requests with no URL** — skip silently, note in the summary.

---

## General Constraints

- **Do not fabricate** routes, schemas, or responses unsupported by the
  source material. If a response body is unclear, use `type: object` with
  `additionalProperties: true` and note the ambiguity.
- **Never guess a field into existence.** Every property in every schema
  must trace back to something actually present in the codebase, the
  Postman/Insomnia collection, or an explicit inference rule this skill
  defines (e.g. P5/I5/C5 body-to-schema inference, or the script/description
  evidence rule in I6). It is never acceptable to fill a gap by copying
  another operation's request body onto a response, inventing a plausible
  field name, or padding a schema to "look complete." If the available
  evidence only supports one field, emit a schema with exactly that one
  field (plus `additionalProperties: true` if the shape is otherwise
  unknown) — a thin, honest schema is always preferred over a fuller,
  invented one. When there is no evidence at all for a schema's shape, emit
  `type: object` with `additionalProperties: true` and nothing else, and
  say so plainly in the coverage notes rather than presenting a guess as if
  it were observed.
- **Do not modify** any source code, Postman/Insomnia collection, or
  environment file. This skill is read-only with respect to its inputs.
- **Prefer `$ref`** over inline schemas for any object used more than once.
- **Use OAS 3.0.x** (e.g. `"3.0.3"`), not 2.0 (Swagger) or 3.1, unless the
  user explicitly requests otherwise.
- **Always include `operationId`** — required for downstream tooling such
  as 42Crunch audit and scan.
- **Use `nullable: true`** (OAS 3.0 style) for nullable fields, not
  `type: ["string", "null"]` (OAS 3.1 style).
- Keep schema names in **PascalCase**, `operationId` values in **camelCase**,
  and tag names in **Title Case**.
- Use `format` where applicable: `date-time`, `date`, `uuid`, `email`, `uri`,
  `binary`, `byte`, `int32`, `int64`, `float`, `double`, `password`.
