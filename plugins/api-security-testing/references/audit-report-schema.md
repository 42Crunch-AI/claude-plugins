# API Contract Security Audit

 API Contract Security Audit is the assessment service of the 42Crunch Platform.

This document is canonical. If there is ambiguity between this document and the corresponding API definition or schema files, this document wins.

- [Runtime limitations](#runtime-limitations)
  * [JSON object maximum limits](#json-object-maximum-limits)
- [The JSON schema of the audit report](#the-json-schema-of-the-audit-report)
  * [Report object](#report-object)
  * [ReportError object](#reporterror-object)
    + [Errors object](#errors-object)
  * [ReportStructuralError object](#reportstructuralerror-object)
  * [ReportSemanticError object](#reportsemanticerror-object)
  * [ReportValid object](#reportvalid-object)
  * [Index object](#index-object)
  * [IssueTypeOpenApi object](#issuetypeopenapi-object)
    + [Issues object](#issues-object)
      - [Issue object](#issue-object)
  * [AssessmentSection object](#assessmentsection-object)
    + [Assessment issues object](#assessment-issues-object)
      - [Assessment issue object](#assessment-issue-object)
        
## Runtime limitations

OpenAPI definitions submitted to Security Audit are subject to the limitations detailed below. When one or more of these limits are exceeded, the
assessment fails and the reason of the failure is included in the [`errors` object](#errors-object) of the audit report.

### JSON object maximum limits

| Limit                | Size         | The `errors` field     |
| -------------------- | ------------ | ----------------       |
| Key length           | 256 chars    | `keyLength`            |
| Value length         | 8192 chars   | `valueLength`          |
| Vertical depth       | 32           | `verticalDepth`        |
| Horizontal length    | 256          | `horizontalLength`     |
| File size            | 4 MB         | `fileSize`             |
| Numerical overflow\* | 64 bit float | `overflow`             |

\* An `overflow` error is triggered if a JSON number does not fit in the range of a IEEE-754 64-bit floating-point number (fails to cast to a golang `float64`).

## The JSON schema of the audit report

This specification describes the possible structures and elements in the audit report that Security Audit returns.
 
### Report object

The `report` object is the audit report that Security Audit returns. This is the base object for all reports. The `report` object takes one of the following structures based on the enum value of the property `openapiState`:
- `fileInvalid`, see [ReportError object](#reporterror-object)
- `structureInvalid`, see [ReportStructuralError object](#reportstructuralerror-object)
- `semanticInvalid`, see [ReportSemanticError object](#reportsemanticerror-object)
- `valid`, see [ReportValid object](#reportvalid-object)

### ReportError object

This error report indicates that there are one or more errors with the API definition file. Errors prevent audit from running as long as they are present in the API definition.

|     Property         |   Type                          |      Description                                                                                                                    |
|----------------------|:---------------------------------:|-------------------------------------------------------------------------------------------------------------------------------------|
| `assessmentVersion`  | `string`                        | **REQUIRED** The version of Security Audit that ran the audit on the API definition.                                                |
| `fileId`             | `string`                        | **REQUIRED** The ID of API definition file in 42Crunch Platform.                                                                    |
| `apiId`              | `string`                        | **REQUIRED** The ID of API in 42Crunch Platform.                                                                                    |
| `openapiState`       | `string`                        | **REQUIRED** The state of the audited API definition. The enum value is `fileInvalid` to indicate there is an error with the file.  |
| `errors`             | [Errors object](#errors-object) | **REQUIRED** Indicates what is preventing Security Audit from auditing the API.                                                     |

#### Errors object

The `errors` object defines the exact reasons that prevent Security Audit from auditing the API. It comprises of `boolean` properties where `true` indicates the problem. The errors correspond the [JSON object maximum limits](#json-object-maximum-limits)

|  Property          |   Type     |      Description                                                                                                                                      |
|--------------------|:----------:|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| `fileEmpty`        | `boolean`  | **REQUIRED** The file submitted fo audit is empty.                                                                                                    |
| `fileSize`         | `boolean`  | **REQUIRED** The file is larger than the allowed 4 MB.                                                                                                |
| `json`             | `boolean`  | **REQUIRED** The file is not a proper JSON file.                                                                                                      |
| `oasVersion`       | `boolean`  | **REQUIRED** The file does not state which version of the OpenAPI Specification (OAS) it follows.                                                     |
| `keyLength`        | `boolean`  | **REQUIRED** One or more keys in the file are longer than the allowed maximum key length (256 characters).                                            |
| `valueLength`      | `boolean`  | **REQUIRED** One or more string values in the file are longer than the allowed maximum length (8192 characters).                                      |
| `verticalDepth`    | `boolean`  | **REQUIRED** One or more elements in the file are located too deep (only 32 levels allowed).                                                          |
| `horizontalLength` | `boolean`  | **REQUIRED** One or more elements in the file have too many children (only 256 objects allowed).                                                      |
| `overflow`         | `boolean`  | **REQUIRED** One or more integers or number values are greater than the allowed maximum (outside the range of IEEE-754 64-bit floating-point number). |

### ReportStructuralError object

This report indicates that Security Audit has detected *structural* issues in the OpenAPI format where the API definition does not conform to the OpenAPI Specification. 

Structural issues prevent Security Audit from auditing the security and data definition quality of the API as long as they are present in the API definition.

|     Property          |   Type                                              |      Description                                                                                                                                |
|-----------------------|:---------------------------------------------------:|-------------------------------------------------------------------------------------------------------------------------------------------------|
| `index`               | [Index object](#index-object)                       | **REQUIRED** An array of JSON pointers in `string` format to all structural issues found in the API definition.                                 |
| `assessmentVersion`   | `string`                                            | **REQUIRED** The version of Security Audit that ran the audit on the API definition.                                                            |
| `fileId`              | `string`                                            | **REQUIRED** The ID of API definition file in 42Crunch Platform.                                                                                |
| `apiId`               | `string`                                            | **REQUIRED** The ID of API in 42Crunch Platform.                                                                                                |
| `openapiState`        | `string`                                            | **REQUIRED** The state of the audited API definition. The enum value is `structureInvalid` to indicate structural errors in the API definition. |
| `score`               | `number`                                            | **REQUIRED** The audit score of the API definition. The enum value is `0`.                                                                      |
| `valid`               | `boolean`                                           | **REQUIRED** This property indicates if the API definition is a valid OpenAPI definition. The enum value is `false`.                            |
| `issueCounter`        | `integer`                                           | **REQUIRED** The total number of found issues in the audit report.                                                                              |
| `validationErrors`    | [IssueTypeOpenApi object](#issuetypeopenapi-object) | **REQUIRED** A map of structural issues in the OpenAPI format of the OpenAPI definition.                                                        |
| `minimalReport`       | `boolean`                                           | **REQUIRED** This property controls the size of the report. If set to `false`, a normal report is produced. If set to `true` and if either of the properties `maxEntriesPerIssue` and `maxImpactedPerEntry` is bigger than `-1`, the report is truncated to be more lightweight.                                                                                                  |
| `maxEntriesPerIssue`  | `integer`                                           | **REQUIRED** The maximum number of issues in the report.                                                                                        |
| `maxImpactedPerEntry` | `integer`                                           | **REQUIRED** The maximum number of JSON pointers to elements in the API definition that are affected by a particular issue.                     |   


### ReportSemanticError object

This report indicates that Security Audit has detected *semantic* issues in the OpenAPI format where the API definition does not conform to the OpenAPI Specification. 

Semantic issues do not prevent Security Audit from auditing the security and data definition quality of the API definition. The API gets an audit score to reflect these, as well as a severity level to indicate how bad the security risks are. 

|     Property          |   Type                                                |      Description                                                                                                                                |
|-----------------------|:-----------------------------------------------------:|-------------------------------------------------------------------------------------------------------------------------------------------------|
| `index`               | [Index object](#index-object)                         | **REQUIRED** An array of JSON pointers in `string` format to all structural issues found in the API definition.                                 |
| `assessmentVersion`   | `string`                                              | **REQUIRED** The version of Security Audit that ran the audit on the API definition.                                                            |
| `oasVersion`          | `string`                                              | **REQUIRED** The version of the OpenAPI Specification (OAS) that the API definition follows.                                                    |
| `apiVersion`          | `string`                                              | The version of the API as defined in the `info` object of the API definition.                                                                   | 
| `fileId`              | `string`                                              | **REQUIRED** The ID of API definition file in 42Crunch Platform.                                                                                |
| `apiId`               | `string`                                              | **REQUIRED** The ID of API in 42Crunch Platform.                                                                                                |
| `openapiState`        | `string`                                              | **REQUIRED** The state of the audited API definition. The enum value is `semanticInvalid` to indicate semantic errors in the API definition.    |
| `score`               | `number`                                              | **REQUIRED** The audit score of the API definition from `0` to `100`. The score indicates how many points security risks in the API definition *reduce* from the initial pool of `100` (the score goes down from `100`, not up).                                                                                                                                                 |
| `valid`               | `boolean`                                             | **REQUIRED** This property indicates if the API definition is a valid OpenAPI definition. The enum value is `false`.                            |
| `criticality`         | `integer`                                             | **REQUIRED** The severity of the security risks found in the API definition from `0` to `5` (critical). The value is based on the severity of all found issues and the sensitivity of all affected operations.                                                                                                                                                                     | 
| `issueCounter`        | `integer`                                             | **REQUIRED** The total number of found issues in the audit report.                                                                              |
| `semanticErrors`      | [IssueTypeOpenApi object](#issuetypeopenapi-object)   | **REQUIRED** A map of  semantic issues in the OpenAPI format of the OpenAPI definition.                                                         |
| `warnings`            | [IssueTypeOpenApi object](#issuetypeopenapi-object)   | **REQUIRED** A map of issues where the API does not follow the recommendations of the OAS.                                                      |
| `minimalReport`       | `boolean`                                             | **REQUIRED** This property controls the size of the report. If set to `false`, a normal report is produced. If set to `true` and if either of the properties `maxEntriesPerIssue` and `maxImpactedPerEntry` is bigger than `-1`, the report is truncated to be more lightweight.                                                                                                   |
| `maxEntriesPerIssue`  | `integer`                                             | **REQUIRED** The maximum number of issues in the report.                                                                                        |
| `maxImpactedPerEntry` | `integer`                                             | **REQUIRED** The maximum number of JSON pointers to elements in the API definition that are affected by a particular issue.                     |
| `security`            | [AssessmentSection object](#assessmentsection-object) | **REQUIRED** A map of issues related to the security measures in the API definition.                                                            |
| `data`                | [AssessmentSection object](#assessmentsection-object) | **REQUIRED** A map of issues related to the data definition quality in the API definition.                                                      |

### ReportValid object

This report indicates that the API definition is a valid OpenAPI definition. There are no structural or semantic issues in the API definition, although it still might not follow all the recommendations of the OpenAPI Specification. 

|     Property          |   Type                                                |      Description                                                                                                                                |
|-----------------------|:-----------------------------------------------------:|-------------------------------------------------------------------------------------------------------------------------------------------------|
| `index`               | [Index object](#index-object)                         | **REQUIRED** An array of JSON pointers in `string` format to all structural issues found in the API definition.                                 |
| `assessmentVersion`   | `string`                                              | **REQUIRED** The version of Security Audit that ran the audit on the API definition.                                                            |
| `oasVersion`          | `string`                                              | **REQUIRED** The version of the OpenAPI Specification (OAS) that the API definition follows.                                                    |
| `apiVersion`          | `string`                                              | **REQUIRED** The version of the API as defined in the `info` object of the API definition.                                                      | 
| `fileId`              | `string`                                              | **REQUIRED** The ID of API definition file in 42Crunch Platform.                                                                                |
| `apiId`               | `string`                                              | **REQUIRED** The ID of API in 42Crunch Platform.                                                                                                |
| `openapiState`        | `string`                                              | **REQUIRED** The state of the audited API definition. The enum value is `valid` to indicate the API definition is a valid OpenAPI definition.   |
| `score`               | `number`                                              | **REQUIRED** The audit score of the API definition from `0` to `100`. The score indicates how many points security risks in the API definition *reduce* from the initial pool of `100` (the score goes down from `100`, not up).                                                                                                                                                 |
| `valid`               | `boolean`                                             | **REQUIRED** This property indicates if the API definition is a valid OpenAPI definition. The enum value is `true`.                             |
| `criticality`         | `integer`                                             | **REQUIRED** The severity of the security risks found in the API definition from `0` to `5` (critical). The value is based on the severity of all found issues and the sensitivity of all affected operations.                                                                                                                                                                     | 
| `issueCounter`        | `integer`                                             | **REQUIRED** The total number of found issues in the audit report.                                                                              |
| `warnings`            | [IssueTypeOpenApi object](#issuetypeopenapi-object)   | **REQUIRED** A map of issues where the API does not follow the recommendations of the OAS.                                                      |
| `minimalReport`       | `boolean`                                             | **REQUIRED** This property controls the size of the report. If set to `false`, a normal report is produced. If set to `true` and if either of the properties `maxEntriesPerIssue` and `maxImpactedPerEntry` is bigger than `-1`, the report is truncated to be more lightweight.                                                                                                   |
| `maxEntriesPerIssue`  | `integer`                                             | **REQUIRED** The maximum number of issues in the report.                                                                                        |
| `maxImpactedPerEntry` | `integer`                                             | **REQUIRED** The maximum number of JSON pointers to elements in the API definition that are affected by a particular issue.                     |
| `security`            | [AssessmentSection object](#assessmentsection-object) | **REQUIRED** A map of issues related to the security measures in the API definition.                                                            |
| `data`                | [AssessmentSection object](#assessmentsection-object) | **REQUIRED** A map of issues related to the data definition quality in the API definition.                                                      |

### Index object

This array in the root of the [`report` object](#report-object) contains JSON pointers to all elements in the audited API definition where an issue occurs or that are affected by one. This array is used when a string value is needed for a JSON pointer.

|  Property   |   Type      |      Description                                                                      |
|-------------|:-----------:|---------------------------------------------------------------------------------------|
| `items`     | `string`    | The string values of JSON pointers of all issues found in the audited API definition. |

### IssueTypeOpenApi object

This object gathers together all issues related to the OpenAPI format of the API, where the format does not follow the OpenAPI Specification (OAS). 

Issues in this section may mean that the audited API does not in fact have a valid OpenAPI definition. This is the case if issues are found either in the structure of the API definition or its semantics.  See [ReportStructuralError object](#reportstructuralerror-object) and [ReportSemanticError object](#reportsemanticerror-object).

If the issues occur elsewhere (that is, not in the structure or semantics of the API definition), this means that the API does not follow some of the recommendations in the OAS. This may lead to misunderstandings when API consumers call your API.

|     Property     |   Type                           |      Description                                                                       |
|------------------|:--------------------------------:|----------------------------------------------------------------------------------------|
| `desciption`     | `string`                         | **REQUIRED** A generic description of what is the issue with the API definition.       |
| `issues`         | [Issues object](#issues-object)  | An array of issues objects.                                                            |
| `totalIssues`    | `integer`                        | **REQUIRED** The total number of issues.                                               |
| `tooManyError`   | `boolean`                        | **REQUIRED** This property applies to the minimal report. The value is `true` if the value of `totalIssues` is greater than the value of the property `maxEntriesPerIssue` in the [`report` object](#report-object).                                                                                                      |

#### Issues object

The `issues` array  under the `issueTypeOpenAPI` contains all issues in the OpenAPI format of the API definition. This shows how well the API definition conforms to the OAS. These issues do not directly relate to the security or data definition quality of the API (see [`assessmentSection` object](#assessmentsection-object)).

|     Property     |   Type                          | Description                                                                                                     |
|------------------|:-------------------------------:|-----------------------------------------------------------------------------------------------------------------|
| `maxItems`       | `integer`                       | The size of the array is limited by the property `maxEntriesPerIssue` in the [`report` object](#report-object). |
| `items`          | [Issue object](#issue-object)   | An array of `issue` objects.                                                                                    |

##### Issue object

This object describes what is the exact issue and where in the the API definition it is located.

|     Property          |   Type      | Description                                                                                                                                                                              |
|-----------------------|:-----------:|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `specificDescription` | `string`    | A more specific description of the issue in the API definition. This description is populated with variables to show the context where it occurs (for example, the operation or method). |
| `pointer`             | `integer`   | **REQUIRED** The index of the JSON pointer to the element where the issue occurs. To get a `string` value for the pointer, it must be fetched from the [`index` object](#index-object) in the root of the [`report` object](#report-object).                                                                                                                                                                               |

### AssessmentSection object

This object gathers together all the issues in the API definition that pose a risk to its security. An audit report can have two types of sections:

- Security: Issues in how security measures are defined in the API.
- Data validation: Issues in the data definition quality of the API.

|     Property          |   Type                                                 |      Description                                                                                                   |
|-----------------------|:------------------------------------------------------:|--------------------------------------------------------------------------------------------------------------------|
| `issueCounter`        | `integer`                                              | The total number of issues in the section.                                                                         |
| `score`               | `number`                                               | The final score of the section. The maximum score for Security is `30` points and `70` points for Data validation. |
| `criticality`         | `integer`                                              | The severity of the issues found in the issues in the section  from `0` to `5` (critical).                         |
| `issues`              | [Assessment issues object](#assessment-issues-object)  | This object gathers all errors that fall under Security or Data validation.                                        |

#### Assessment issues object

This `issues` object in the `assessmentSection` object represents all the *occurrences* of a specific issue type that Security Audit detected in the API definition that fall under Security or Data validation.

The properties of the `issues` object must match the pattern `.*`.

|     Property   |   Type                                              |      Description                                                                                                        |
|----------------|:---------------------------------------------------:|-------------------------------------------------------------------------------------------------------------------------|
| `description`  | `string`                                            | **REQUIRED** A generic description of what is the issue with the API definition.                                        |
| `issues`       | [Assessment issue object](#assessment-issue-object) | An array of `issue` objects that fall under Security or Data validation. This array gathers together all the *details* of a particular issue type in Security or Data validation sections, such as: <ul><li>Where the issue is located in the API definition</li><li>What is its impact on the audit score</li><li>How severe it is</li></ul>         |
| `issueCounter` | `integer`                                           | **REQUIRED** The total number of objects in the API definition where the issue type occurs. If the report is *not* a minimal report, the value is the length of the `issues` array.                                                                                                                                                                    |
| `score`        | `number`                                            | **REQUIRED** The sum of all scores in the `issues` array.                                                               |
| `criticality`  | `integer`                                           | **REQUIRED** The severity of the issue based on the sensitivity of all affected operations from `0` to `5` (critical).  |
| `tooManyError` | `boolean`                                           | **REQUIRED** This property applies to the minimal report. The value is `true` if the value of `totalIssues` is greater than the value of the property `maxEntriesPerIssue` in the [`report` object](#report-object).                                                                                                                                   |

##### Assessment issue object

This object describes the individual issue objects and where in the the API definition they are located.

|     Property          |   Type    | Description                                                                                                                                                                              |
|-----------------------|:---------:|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `specificDescription` | `string`  | A more specific description of the issue in the API definition. This description is populated with variables to show the context where it occurs (for example, the operation or method). |
| `sensitivity`         | `integer` | **REQUIRED** The highest sensitivity from `0` to `5` (extremely sensitive) in the operations where the issue occurs or that are affected by it, for example, through reference.          |
| `score`               | `number`  | **REQUIRED** The impact the issue has on the audit score, how many points it *takes away*.                                                                                               |
| `pointer`             | `integer` | **REQUIRED** The index of the JSON pointer to the element where the issue occurs. To get a `string` value for the pointer, it must be fetched from the [`index` object](#index-object) in the root of the [`report` object](#report-object).                                                                                                                                                                                |
| `tooManyImpacted`     | `boolean` | **REQUIRED** This property applies to the minimal report. The value is `true` if the lenght of the array `pointersAffected` is greater than the value of the property `maxImpactedPerEntry` in the [`report` object](#report-object).                                                                                                                                                                                      |
| `pointersAffected`    | `array`   | An array of all JSON pointers in `string` format to the elements in the API definition that are affected by the issue.                                                                   |
