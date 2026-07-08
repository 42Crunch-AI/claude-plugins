## Scanconf Template

**Canonical pattern library** for `scanconf.json` (version 2.0.0). Every JSON
shape used by `scan-workflow.md` Steps 2–6 (credential acquisition, operation
patterns, dependency chains, authorization tests) is defined here and only
here — the workflow file names the pattern to apply; this file is the single
source of truth for its JSON. Also use this file when building or repairing a
config manually. Replace every `<placeholder>` with the API-specific value.
Omit `authorizationTests` when no BOLA/BFLA candidates exist; omit `requests`
when no standalone utility requests are needed.

### Top-level skeleton

```json
{
  "version": "2.0.0",
  "runtimeConfiguration": { ... },    // standard defaults — copy verbatim from generated config
  "customizations": { ... },           // response-policy defaults — copy verbatim
  "environments": { ... },             // host URL + per-user credential env vars
  "operations": { ... },               // one entry per OAS operationId
  "authenticationDetails": [ ... ],    // bearer / apiKey / basic credential acquisition
  "authorizationTests": { ... },       // BOLA / BFLA test definitions (optional)
  "requests": { ... }                  // named reusable utility requests (optional)
}
```

After initial `scan conf generate`, `authenticationDetails` is initialized with
one default credential per OpenAPI `securityScheme` present in the OAS. This
includes scheme types such as bearer, oauth2, basic, and apiKey. Reuse each
scheme's generated default credential as User1 instead of creating a second
User1 credential entry.

### `runtimeConfiguration` — key flags

Copy all fields verbatim from the generated config. Two fields change during the workflow:

```json
"happyPathOnly": false,         // set true for Step 5 validation; restore to false before full scan
"laxTestingModeEnabled": false  // never set true before happy paths are confirmed
```

### `environments.default.variables` — structure

When a config is first generated, scanconf will auto-create one environment
variable per security scheme defined in the OAS and mark these entries as
`"required": true`. Normalize these
generated security-scheme entries to `"required": false` unless strict runtime
injection is intentionally required.

```json
"host": {
  "name": "SCAN42C_HOST", "from": "environment", "required": false,
  "default": "<target-base-url>"
},
"<var-name>": {
  "name": "SCAN42C_<VAR_NAME>", "from": "environment", "required": false,
  "default": "<default-value>"
}
```

Add one entry per credential variable (user1, user2, throwaway, etc.).

Credential variable example:

```json
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

---

### Operation patterns

#### Class-A — no auth (public endpoints: login, register)

```json
"<OperationId>": {
  "operationId": "<OperationId>",
  "request": {
    "operationId": "<OperationId>",
    "request": {
      "type": "42c",
      "details": {
        "operationId": "<OperationId>",
        "method": "<METHOD>",
        "url": "{{host}}<path>",
        "headers": [{ "key": "Content-Type", "value": "application/json" }],
        "requestBody": { "mode": "json", "json": { "<field>": "{{<var>}}" } }
      }
    },
    "defaultResponse": "<success-status>",
    "responses": {
      "<success-status>": { "expectations": { "httpStatus": <success-status> } },
      "default": { "expectations": { "httpStatus": "default" } }
    }
  },
  "scenarios": [
    { "key": "happy.path", "fuzzing": true,
      "requests": [{ "fuzzing": true, "$ref": "#/operations/<OperationId>/request" }] }
  ]
}
```

#### Class-A — with auth (standalone authenticated operations)

Same as above but add `"auth": ["AccessToken"]` inside the outer `request` object (alongside `operationId` and `request`). No `before` block needed.

#### Class-B — dependency chain, GET / PUT / PATCH (creator in `before` block)

Use when the operation needs an ID from a prior response and the happy path
does **not** destroy the resource. The creator lives in the operation-level
`before` block; the `happy.path` scenario is a single step. (For DELETE
targets, use the next pattern instead.)

**Required:** if the referenced creator operation contains template variables in
its request (path/query/header/body), the `before` step must resolve
those variables. Use step-level `environment` overrides unless those variables are
already resolved globally in `environments.default.variables`, global static
defaults, or a global `before` assignment.

```json
"<OperationId>": {
  "operationId": "<OperationId>",
  "request": {
    "operationId": "<OperationId>",
    "auth": ["AccessToken"],
    "request": {
      "type": "42c",
      "details": {
        "operationId": "<OperationId>",
        "method": "<METHOD>",
        "url": "{{host}}<path>/{<id-param>}",
        "paths": [{ "key": "<id-param>", "value": "{{<id-var>}}" }]
      }
    },
    "defaultResponse": "<success-status>",
    "responses": { ... }
  },
  "before": [
    {
      "$ref": "#/operations/<CreatorOperationId>/request",
      "environment": {
        "<creatorVar1>": "<value1>",
        "<creatorVar2>": "<value2>"
      },
      "responses": {
        "<success-status>": {
          "expectations": { "httpStatus": <success-status> },
          "variableAssignments": {
            "<id-var>": {
              "in": "body", "from": "response", "contentType": "json",
              "path": { "type": "jsonPointer", "value": "/<id-field>" }
            }
          }
        }
      }
    }
  ],
  "scenarios": [
    { "key": "happy.path", "fuzzing": true,
      "requests": [{ "fuzzing": true, "$ref": "#/operations/<OperationId>/request" }] }
  ]
}
```

Do not assume creator input variables provided in a different scenario step are
available here. Each `before` chain must be independently runnable unless the
variable is intentionally resolved at the global level.

To add a BOLA authorization test, append `"authorizationTests": ["<BolaTestName>"]` at the operation level.

**Object-reference location — path / query / body.** The pattern above consumes
the seeded id from a **path** parameter (`paths[]`). The object reference can
equally sit in the **query string** or the **request body** — the `before`
creator, the `variableAssignments`, and the BOLA test definition are all
identical; only the target request's `details` field that consumes
`{{<id-var>}}` changes. Swap the `paths` array in the target `request.details`
for one of these:

```json
// Query reference — e.g. GET /search?orderId=...
"queries": [{ "key": "<id-param>", "value": "{{<id-var>}}" }]
```

```json
// Body reference — e.g. POST /lookup {"orderId": "..."}  (also POST /transfer,
// /share, or any action-on-object call). One entry per referenced object.
"requestBody": { "mode": "json", "json": { "<id-field>": "{{<id-var>}}" } }
```

A body carrying **multiple** references (e.g. `{ "fromAccountId": …,
"toAccountId": … }`) is a distinct BOLA candidate on each reference; seed and
wire each id the same way. This location-agnostic behavior is verified: the
scanner seeds as User 1 and replays the target under User 2's token whether the
id is in the path, query, or body.

#### Class-B — dependency chain, DELETE (creator inside the scenario)

Use when the Class-B **target operation is DELETE** and the happy path destroys
the resource (especially when `BOLA? = yes`). Put the creator operation as the
**first request** in `scenarios[].requests[]`, immediately before the delete
`$ref` — do **not** put the creator only in the operation-level `before` block
with a single-step delete scenario.

**Why:** BOLA replays the operation's `happy.path` scenario with User 2's
credential swapped onto the delete step. If User 1's happy path already deleted
the resource — or the creator in `before` does not reliably re-seed it before
the BOLA replay — the authorization test returns **404 Not Found** instead of
the expected **401/403**, producing a false BOLA failure even when the API
correctly enforces ownership.

```json
"<DeleteOperationId>": {
  "operationId": "<DeleteOperationId>",
  "request": { ... },
  "scenarios": [
    {
      "key": "happy.path",
      "fuzzing": true,
      "requests": [
        {
          "$ref": "#/operations/<CreatorOperationId>/request",
          "environment": {
            "<creatorVar1>": "<value1>"
          }
        },
        {
          "fuzzing": true,
          "$ref": "#/operations/<DeleteOperationId>/request"
        }
      ]
    }
  ],
  "authorizationTests": ["<BolaTestName>"]
}
```

The `<varName>` captured from the creator's response (via `variableAssignments`
on the creator operation definition, or inline on the scenario step) is then
referenced as `{{varName}}` in the delete operation's `paths` or `queries`
array.

**Expected BOLA replay flow (DELETE):** creator runs as User 1 → sets
`{{resourceId}}`; delete runs as User 2 → API returns 403 if ownership is
enforced (not a finding). **Symptom of wrong placement:**
`authentication-swapping-bola` failure with HTTP 404 / "not found" on a
DELETE — restructure to this scenario-inline shape and re-test.

#### Global `before` block (shared dependencies)

If multiple operations share the same dependency variable (e.g. many operations
need `customerId` from a login call), add the creator to the top-level global
`before` block rather than repeating it in every scenario:

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

> **Do NOT use the global `before` block to register or provision test users.**
> The scan assumes all test users (User 1, User 2, Admin) already exist in
> the database before the scan starts. User provisioning is an operational
> prerequisite — it is not something the scan config manages. The global
> `before` is for creating shared resources, or extracting shared
> runtime variables that multiple operations need during the scan (e.g. a
> resource ID or session value returned by a setup call). If you need a fresh
> user per-iteration for a specific operation, use the Class-D throwaway-user
> pattern on that operation's own `before` block instead.

#### Resource-restoring `after` block (non-self-destructive deletes)

For delete operations that remove a resource owned by User1 (e.g.
`DELETE /account/products/cards/{id}`) but do NOT delete User1 themselves,
use an `after` block to recreate the resource after each test run so subsequent
fuzzing iterations find it:

```json
"<DeleteResourceOperationId>": {
  "operationId": "<DeleteResourceOperationId>",
  "request": { ... },
  "before": [
    {
      "$ref": "#/operations/<GetResourceOperationId>/request",
      "responses": {
        "200": {
          "expectations": { "httpStatus": 200 },
          "variableAssignments": {
            "<resourceId>": {
              "in": "body", "from": "response", "contentType": "json",
              "path": { "type": "jsonPointer", "value": "/<id-field>" }
            }
          }
        }
      }
    }
  ],
  "after": [
    {
      "$ref": "#/operations/<CreateResourceOperationId>/request",
      "responses": {
        "200": {
          "expectations": { "httpStatus": 200 },
          "variableAssignments": {
            "<resourceId>": {
              "in": "body", "from": "response", "contentType": "json",
              "path": { "type": "jsonPointer", "value": "/<id-field>" }
            }
          }
        }
      }
    }
  ],
  "scenarios": [
    {
      "key": "happy.path", "fuzzing": true,
      "requests": [{ "fuzzing": true, "$ref": "#/operations/<DeleteResourceOperationId>/request" }]
    }
  ]
}
```

The `before` block fetches a valid resource ID; the `after` block recreates it.
This keeps the test environment consistent across fuzzing iterations without
needing a throwaway user.

#### Class-D — throwaway user (self-destructive delete)

The operation's `auth` field pins the throwaway credential directly.
The `happy.path` scenario is a single delete step. The `before` block on the
operation re-registers the throwaway user before each iteration so the
`authenticationDetails` login step can always acquire a fresh token.

```json
"<DeleteSelfOperationId>": {
  "operationId": "<DeleteSelfOperationId>",
  "request": {
    "operationId": "<DeleteSelfOperationId>",
    "auth": ["AccessToken/<throwaway-credential-name>"],
    "request": {
      "type": "42c",
      "details": {
        "operationId": "<DeleteSelfOperationId>",
        "method": "DELETE",
        "url": "{{host}}<path>"
      }
    },
    "defaultResponse": "<success-status>",
    "responses": { ... }
  },
  "before": [
    {
      "$ref": "#/operations/<RegisterOperationId>/request",
      "environment": {
        "<emailVar>": "<throwaway@example.com>",
        "<credentialVar>": "<throwaway-value>"
      },
      "responses": {
        "201": { "expectations": { "httpStatus": 201 } },
        "409": { "expectations": { "httpStatus": 409 } }
      }
    }
  ],
  "scenarios": [
    {
      "key": "happy.path", "fuzzing": true,
      "requests": [
        {
          "fuzzing": true,
          "$ref": "#/operations/<DeleteSelfOperationId>/request"
        }
      ]
    }
  ]
}
```

The `auth` field ensures only the throwaway credential is used — User1 is never
touched. The operation's `before` block re-registers the throwaway before each
iteration so the `authenticationDetails` login flow can always acquire a fresh
token.

To add a BOLA authorization test, append `"authorizationTests": ["<BolaTestName>"]` at the operation level.

---

### `authenticationDetails` — bearer token

```json
"authenticationDetails": [
  {
    "AccessToken": {
      "type": "bearer",
      "default": "User1Token",
      "credentials": {
        "User1Token": {
          "credential": "{{AccessToken}}",
          "requests": [
            {
              "$ref": "#/operations/<LoginOperationId>/request",
              "responses": {
                "200": {
                  "expectations": { "httpStatus": 200 },
                  "variableAssignments": {
                    "AccessToken": {
                      "in": "body", "from": "response", "contentType": "json",
                      "path": { "type": "jsonPointer", "value": "/<token-field>" }
                    }
                  }
                }
              }
            }
          ]
        },
        "User2Token": {
          "credential": "{{AccessToken}}",
          "requests": [
            {
              "$ref": "#/operations/<LoginOperationId>/request",
              "environment": {
                "<credential-var>": "{{<user2-credential-var>}}",
                "<password-var>": "{{<user2-password-var>}}"
              },
              "responses": {
                "200": {
                  "expectations": { "httpStatus": 200 },
                  "variableAssignments": {
                    "AccessToken": {
                      "in": "body", "from": "response", "contentType": "json",
                      "path": { "type": "jsonPointer", "value": "/<token-field>" }
                    }
                  }
                }
              }
            }
          ]
        },
        "AdminToken": {
          "credential": "{{AccessToken}}",
          "requests": [
            {
              "$ref": "#/operations/<LoginOperationId>/request",
              "environment": {
                "<credential-var>": "{{<admin-credential-var>}}",
                "<password-var>": "{{<admin-password-var>}}"
              },
              "responses": {
                "200": {
                  "expectations": { "httpStatus": 200 },
                  "variableAssignments": {
                    "AccessToken": {
                      "in": "body", "from": "response", "contentType": "json",
                      "path": { "type": "jsonPointer", "value": "/<token-field>" }
                    }
                  }
                }
              }
            }
          ]
        },
        "<throwaway-credential-name>": {
          "credential": "{{AccessToken}}",
          "requests": [
            {
              "$ref": "#/operations/<LoginOperationId>/request",
              "environment": {
                "<credential-var>": "<throwaway@example.com>",
                "<password-var>": "<throwaway-value>"
              },
              "responses": {
                "200": {
                  "expectations": { "httpStatus": 200 },
                  "variableAssignments": {
                    "AccessToken": {
                      "in": "body", "from": "response", "contentType": "json",
                      "path": { "type": "jsonPointer", "value": "/<token-field>" }
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

- `User2Token` uses `environment` to override credential vars for the login step — no need to duplicate the login operation.
- `AdminToken` uses `environment` overrides for admin credentials and is required for privileged (BFLA-candidate) operations.
- `<throwaway-credential-name>` acquires its token via the login step at session start. The register step is placed in the operation's `before` block so the throwaway user exists before each scenario iteration; it accepts both 201 and 409 for idempotency. The operation that uses this credential sets `"auth": ["AccessToken/<throwaway-credential-name>"]` directly on its `request` definition — not as a scenario-step override.

---

### `authorizationTests` — BOLA and BFLA

```json
"authorizationTests": {
  "<BolaTestName>": {
    "key": "authentication-swapping-bola",
    "source": ["AccessToken/User1Token"],
    "target": ["AccessToken/User2Token"]
  },
  "<BflaTestName>": {
    "key": "authentication-swapping-bfla",
    "source": ["AccessToken/AdminToken"],
    "target": ["AccessToken/User1Token"]
  }
}
```

Define each test **once** at the top level, then tag every candidate operation
by appending the test name to its operation-level `authorizationTests` array:

```json
"<TargetOperationId>": {
  "operationId": "<TargetOperationId>",
  "authorizationTests": ["<BolaTestName>"],
  ...
}
```

For each privileged operation included in the BFLA test, additionally pin the
operation's auth to the admin credential in the operation request definition
(mandatory — the baseline happy path must run as admin so the BFLA test is a
true admin→low-privilege swap):

```json
"<PrivilegedOperationId>": {
  "operationId": "<PrivilegedOperationId>",
  "request": {
    "operationId": "<PrivilegedOperationId>",
    "auth": ["AccessToken/AdminToken"],
    "request": { ... }
  },
  "authorizationTests": ["<BflaTestName>"]
}
```

No additional scenario block is needed for either test — the scanner replays
the operation's `happy.path` scenario (including its `before` blocks and all
`scenarios[].requests[]` steps) with the swapped credential.

**Result semantics:** the engine's verdict is **status-only** — a 2xx on the
swapped request is reported as a finding; 401/403 means the server enforces
authorization (not a finding). A 2xx is a true finding for **state-changing**
targets (PUT / PATCH / DELETE, or a POST that mutates) — the attacker operated
on the victim's resource. For **read** targets (GET, or a lookup/search that
returns the object) a 2xx can be a false positive: an owner-scoped endpoint that
returns the *caller's own* data also answers 2xx. Confirm read findings by
comparing the attacker's response body to the owner's — see `scan-workflow.md`
Step 12a's authorization-confirmation pass. (A 404 on a DELETE usually means the
creator step is misplaced — see the Class-B DELETE pattern above.)

---

### `requests` — named utility request

Use for reusable calls that are not OAS operations. Referenced in `before` blocks or `authenticationDetails`. Common use cases:

- **Utility / cleanup requests** — e.g. a DELETE to remove a throwaway user before re-registering, where no matching OAS operation exists.
- **OAuth token endpoints** — e.g. `POST /oauth/token` or an external authorization server endpoint that issues access tokens but is not part of the API's own OAS file. Define it here and reference it via `$ref` in `authenticationDetails[*].credentials.<name>.requests` so the scanner can acquire tokens without an inline request block.

```json
"requests": {
  "<UtilityRequestName>": {
    "request": {
      "type": "42c",
      "details": {
        "method": "<METHOD>",
        "url": "{{host}}<path>",
        "headers": [{ "key": "Authorization", "value": "Bearer {{AccessToken}}" }],
        "requestBody": { "mode": "urlencoded", "urlencoded": { "<key>": { "value": "{{<value>}}" } } }
      }
    },
    "defaultResponse": "<success-status>",
    "responses": {
      "<success-status>": { "expectations": { "httpStatus": <success-status> } }
    }
  }
}
```

#### Referencing a `requests` entry from `authenticationDetails`

When the token endpoint is defined in `requests` (e.g. an OAuth server not in the OAS), reference it with `"$ref": "#/requests/<RequestName>"` inside the credential's `requests` array. Use `environment` to inject per-credential variables:

```json
"authenticationDetails": [
  {
    "<SchemeName>": {
      "type": "bearer",
      "default": "User1Token",
      "credentials": {
        "User1Token": {
          "credential": "{{AccessToken}}",
          "requests": [
            {
              "$ref": "#/requests/<TokenRequestName>",
              "environment": {
                "<usernameVar>": "{{<user1UsernameVar>}}",
                "<passwordVar>": "{{<user1PasswordVar>}}"
              },
              "responses": {
                "200": {
                  "expectations": { "httpStatus": 200 },
                  "variableAssignments": {
                    "AccessToken": {
                      "from": "response", "in": "body", "contentType": "json",
                      "path": { "type": "jsonPointer", "value": "/<tokenField>" }
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

The key difference from an OAS-operation reference (`"$ref": "#/operations/<OperationId>/request"`) is the path prefix: `#/requests/<RequestName>` targets the top-level `requests` map, while `#/operations/<OperationId>/request` targets the `operations` map. Both support `environment` overrides and `variableAssignments` on responses.

---

### Rules at a glance

| Rule | Reason |
|---|---|
| Always use `$ref` in `requests` arrays — never inline `request` objects | Inline requests have no `operationId`; the VS Code extension rejects them |
| `auth: ["AccessToken"]` goes in the outer `request` object, not inside `details` | `details` is the raw HTTP descriptor; auth injection is a scanner concern |
| After first `scan conf generate`, set generated security-scheme env vars to `"required": false` | Generated security variables are often `"required": true`; leaving them required causes runtime scan errors when values are not provided |
| After initial generation, reuse the default credential created for each security scheme as User1 | `scan conf generate` initializes one default credential per scheme; duplicating User1 credentials creates ambiguity and miswiring |
| BFLA-candidate privileged operations must set operation-level auth to `"<SchemeName>/AdminToken"` (for example `"AccessToken/AdminToken"`) | Ensures happy path runs with admin privileges and BFLA swapping tests demote to low-privilege users |
| `environment` overrides in a step apply only to that step | Safe credential/variable swap without duplicating the operation |
| For Class-B/Class-D creator calls, use step-level `environment` overrides unless variables are already resolved globally (`environments.default.variables`, global static defaults, or global `before` assignments) | Prevents unresolved template variables while allowing intentional global wiring |
| Class-B DELETE: creator goes scenario-inline (first request in `happy.path`), never `before`-only | BOLA replay must seed a live resource; a `before`-only creator causes false 404 BOLA failures |
| BOLA candidacy covers object references in the path, query, AND request body — not the path alone | Object references in `?id=` and in body fields (lookup, transfer, share) are equally exploitable (OWASP API1); the swap is credential-level, so it works identically in all three locations |
| Never use `"skipped": true` on Class-D operations | The scanner ignores it and deletes the primary user, breaking subsequent tests |
| Never override the token variable via `environment` to swap credentials on a Class-D operation | `authenticationDetails` tokens are cached at session start; environment overrides do not change which cached token is injected |
| Class-D operations: set `"auth": ["AccessToken/<throwaway>"]` on the operation definition, not as a scenario-step override | The credential must be pinned at the operation level so the scanner uses the throwaway for ALL execution paths — happy path, fuzzing, and authorization tests |
| Class-D scenarios: delete only — do NOT re-register in the scenario | The operation's `before` block already re-registers the throwaway before each iteration; adding a re-register step in the scenario is redundant and incorrect |
| Non-self-destructive deletes: use `after` block to recreate the resource | Keeps the test environment consistent across fuzzing iterations without a throwaway user |
