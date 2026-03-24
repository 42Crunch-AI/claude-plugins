---
description: Generate an Arazzo Specification from an existing OpenAPI Specification file. Analyzes the OAS operations, identifies logical API workflows and step sequences, and produces a valid arazzo.yaml file.
---

# Generate Arazzo Specification from OpenAPI Specification

## Overview

The Arazzo Specification (by the OpenAPI Initiative) describes sequences of API calls — workflows — that together accomplish a business goal. Each workflow chains one or more steps, where each step references an operation defined in an OpenAPI Specification. Steps can pass outputs from one call as inputs to the next, model success/failure criteria, and define reusable actions.

This skill reads an existing OpenAPI Specification file, reasons about how its operations relate to each other, and produces a valid `arazzo.yaml` file alongside the OAS.

## Arazzo Document Structure

```yaml
arazzo: "1.0.1"
info:
  title: <human-readable title>
  summary: <one-line summary>
  version: "1.0.0"

sourceDescriptions:
  - name: <short alias used in $sourceDescriptions references>
    url: <relative or absolute path to the OAS file>
    type: openapi

workflows:
  - workflowId: <camelCase or kebab-case unique id>
    summary: <one-line summary>
    description: <detailed description>
    inputs:           # optional — JSON Schema for workflow-level inputs
      type: object
      properties: {}
    steps:
      - stepId: <camelCase or kebab-case unique id>
        operationId: <sourceDescriptions alias>.<operationId from OAS>
        parameters:   # optional overrides
          - name: <paramName>
            in: <path|query|header|cookie>
            value: <literal or $inputs / $steps expression>
        requestBody:  # optional
          contentType: application/json
          payload: <literal object or expression>
        successCriteria:
          - condition: $statusCode == 200
        outputs:      # extract values from the response for later steps
          <outputKey>: $response.body#/<jsonPointer>
        onSuccess:    # optional
          - name: <actionName>
            type: goto | end
            stepId: <target stepId>     # only for goto
        onFailure:    # optional
          - name: <actionName>
            type: retry | goto | end
            retryAfter: 1               # seconds, only for retry
            retryLimit: 3               # only for retry
    outputs:          # promote step outputs to workflow outputs
      <workflowOutputKey>: $steps.<stepId>.outputs.<outputKey>
```

## Expression Reference

| Expression | Meaning |
|---|---|
| `$inputs.<name>` | Workflow-level input value |
| `$steps.<stepId>.outputs.<key>` | Output captured in a previous step |
| `$steps.<stepId>.request.body` | Full request body of a previous step |
| `$steps.<stepId>.response.body` | Full response body of a previous step |
| `$statusCode` | HTTP status code of the current step's response |
| `$response.body#/<pointer>` | JSON Pointer into the response body |
| `$response.header.<name>` | Response header value |
| `$url` | Resolved URL of the current step |

## Step-by-Step Instructions

### Step 1 — Read and understand the OpenAPI Specification

Read the provided OAS file in full. Note:
- The `info.title` and `info.description` — they inform the Arazzo `info` block.
- Every `operationId` — these are the atoms Arazzo steps reference.
- Security schemes and which operations require authentication.
- Operations that create resources (POST returning a new `id`), and downstream operations that consume that `id` (GET / PUT / DELETE `/{id}`). These are natural workflow chains.
- Any operations that must be called before others (e.g., login → obtain token → call protected endpoint).

### Step 2 — Identify workflows

Group operations into cohesive business workflows. Common patterns:

| Pattern | Example steps |
|---|---|
| Auth + protected call | `POST /login` → `GET /resource` |
| CRUD lifecycle | `POST /items` → `GET /items/{id}` → `PUT /items/{id}` → `DELETE /items/{id}` |
| Search then act | `GET /search` → `POST /order` |
| Pagination | `GET /items?page=1` → loop via `onSuccess goto` |

Aim for 1–5 meaningful workflows that cover the most important use cases. Do not create a separate workflow for every single operation — only model sequences that have real dependencies or that tell a coherent story.

### Step 3 — Map operation references

For each step, the `operationId` field must be written as:

```
<sourceDescriptions[].name>.<OAS operationId>
```

Example: if the source alias is `petstore` and the OAS operation is `listPets`, write `petstore.listPets`.

If the OAS operation lacks an `operationId`, use the `operationPath` field instead:

```yaml
operationPath: '{$sourceDescriptions.petstore.url}#/paths/~1pets/get'
```

### Step 4 — Wire outputs to inputs

When a later step needs a value produced by an earlier step, capture it in `outputs` and reference it with `$steps.<stepId>.outputs.<key>`:

```yaml
steps:
  - stepId: createUser
    operationId: myApi.createUser
    requestBody:
      payload:
        username: $inputs.username
        password: $inputs.password
    successCriteria:
      - condition: $statusCode == 201
    outputs:
      userId: $response.body#/id
      authToken: $response.body#/token

  - stepId: getUser
    operationId: myApi.getUserById
    parameters:
      - name: userId
        in: path
        value: $steps.createUser.outputs.userId
    successCriteria:
      - condition: $statusCode == 200
```

### Step 5 — Add success and failure criteria

Every step should have at least one `successCriteria` condition using `$statusCode`:

```yaml
successCriteria:
  - condition: $statusCode == 200
```

For steps where multiple status codes are acceptable:

```yaml
successCriteria:
  - condition: $statusCode >= 200
  - condition: $statusCode < 300
```

Add `onFailure` actions for steps where retrying or branching makes sense (e.g., rate-limited calls, token refresh flows).

### Step 6 — Write the arazzo.yaml file

Place the output file next to the OAS file, naming it `arazzo.yaml` (or `<api-name>.arazzo.yaml` if multiple specs share a directory).

Validate the output mentally:
- Every `operationId` reference resolves to an actual operation in the OAS.
- Every `$steps.<id>.outputs.<key>` reference points to a key declared in that step's `outputs` block.
- Every `workflowId` and `stepId` is unique within its scope.
- The `sourceDescriptions[].url` correctly points to the OAS file (relative path from the Arazzo file location).

### Step 7 — Report to the user

After writing the file, summarise:
1. The file path written.
2. The number of workflows created and their `workflowId` values.
3. A one-sentence description of what each workflow accomplishes.
4. Any OAS operations that were intentionally excluded and why (e.g., standalone utility endpoints with no natural sequence).
5. Any assumptions made about operation ordering or data flow that the user should verify.
