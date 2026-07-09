# Windows / PowerShell Commands

Read this file **only when the platform is Windows**. Every command and
extraction block in the reference docs (`pre-flight.md`, `audit-workflow.md`,
`scan-workflow.md`) is written for macOS/Linux (bash + python3); this file
holds the PowerShell equivalent of each, keyed by doc and step. Read it once
when the first Windows command is needed, then use the matching section for
each subsequent block. On macOS/Linux, never read this file.

> **The report-extraction sections below are a fallback.** The bundled Python
> scripts in `../scripts/` (`extract_audit.py`, `extract_scan_happy.py`,
> `extract_scan_summary.py`, `compare_auth_bodies.py`, `oas_preview.py`,
> `scanconf_bootstrap.py`, `scanconf_lint.py`) run
> unchanged under **Windows python3** — if `python3`/`py` is on PATH, invoke
> the script (`py "${CLAUDE_PLUGIN_ROOT}\scripts\<name>.py" <args>`) exactly as
> the workflow docs describe and skip the PowerShell extraction twin. Use the
> inline PowerShell extractors here only when python3 is genuinely unavailable.
> The setup/run/classifier sections (credential loading, binary check, scan/audit
> run commands) are always needed on Windows regardless of python3.

## Windows conventions (apply to every command)

- **Credential loading** (replaces `set -a; . "$HOME/.42crunch/conf/env"; set +a`):
  ```powershell
  Get-Content "$env:APPDATA\42Crunch\conf\env" | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }
  ```
- **Token mode flag**: `--token $env:TRIAL_TOKEN` (never the literal token).
- **`SCAN42C_*` runtime overrides**: set `$env:VAR='value'` on the line before
  the `& <binary>` call (bash prefixes `VAR=value` on the same line).
- **String quoting**: when a variable is immediately followed by `:` inside a
  double-quoted string, PowerShell parses `$varName:` as a PSDrive reference
  (like `$env:TEMP`) and throws `InvalidVariableReferenceWithDrive`. Always use
  `${varName}` to delimit the name — e.g. `"${opName}: ..."` not `"$opName: ..."`.
  This applies to any inline PowerShell generated during the session, not just
  the static snippets below.
- **Paths**: binary is `%APPDATA%\42Crunch\bin\42c-ast.exe`; temp files go to
  `$env:TEMP` (the `%TEMP%` equivalents of the `/tmp/...` paths in the docs).

---

## Pre-flight — Step 1 (Binary Check)

```powershell
$BinaryPath = "$env:APPDATA\42Crunch\bin\42c-ast.exe"
$CacheFile = "$env:APPDATA\42Crunch\conf\.preflight-cache"
$Ttl = if ($env:PREFLIGHT_CACHE_TTL_SECONDS) { [int]$env:PREFLIGHT_CACHE_TTL_SECONDS } else { 86400 }
if (-not (Test-Path $BinaryPath)) { "BINARY=missing" }
else {
  $fresh = $false
  $line = Select-String -Path $CacheFile -Pattern '^CHECKED_AT=' -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($line) {
    $CheckedAt = [int]($line.Line -replace '^CHECKED_AT=', '')
    $Now = [int][double]::Parse((Get-Date -UFormat %s))
    if (($Now - $CheckedAt) -lt $Ttl) {
      & $BinaryPath --version *> $null
      if ($LASTEXITCODE -eq 0) { $fresh = $true }
    }
  }
  if ($fresh) { "BINARY=fresh" } else { "BINARY=check" }
}
```

## Pre-flight — Step 2 (Credential Check)

```powershell
$EnvFile = "$env:APPDATA\42Crunch\conf\env"
if (Select-String -Path $EnvFile -Pattern '^TRIAL_TOKEN=' -Quiet -ErrorAction SilentlyContinue) {
  # .trial-expired is the legacy sentinel name written by older plugin versions
  if ((Test-Path "$env:APPDATA\42Crunch\conf\.token-limit") -or (Test-Path "$env:APPDATA\42Crunch\conf\.trial-expired")) {
    Write-Output "MODE=token_limit"
  } else {
    Write-Output "MODE=token"
  }
} elseif (Select-String -Path $EnvFile -Pattern '^API_KEY=(api_|ide_)' -Quiet -ErrorAction SilentlyContinue) {
  Write-Output "MODE=platform"
} elseif (Select-String -Path $EnvFile -Pattern '^API_KEY=' -Quiet -ErrorAction SilentlyContinue) {
  Write-Output "MODE=badformat"
} else {
  Write-Output "MODE=none"
}
```

For `MODE=platform`, read the non-secret host with:

```powershell
Select-String -Path $EnvFile -Pattern '^PLATFORM_HOST='
```

---

## Audit — Step 1 (Output directory)

```powershell
$OUTPUT_DIR = "$env:TEMP\42c-audit"
New-Item -ItemType Directory -Force -Path $OUTPUT_DIR | Out-Null
```

The `audit run` commands themselves are identical to the bash forms — load
credentials with the convention above, call `& <binary> audit run ...` with the
same flags, and use `--token $env:TRIAL_TOKEN` in token mode.

## Audit — Step 2 (Report extraction)

```powershell
$d = Get-Content "$OUTPUT_DIR\todo.json" | ConvertFrom-Json
$state = $d.openapiState

# fileInvalid/structureInvalid reports carry no score or security/data
# sections at all — handle them before touching anything else.
if ($state -eq "fileInvalid") {
    $fileErrors = ($d.errors.PSObject.Properties | Where-Object { $_.Value } | ForEach-Object { $_.Name })
    Write-Host "openapi_state: fileInvalid"
    Write-Host "file_errors: $(if ($fileErrors) { $fileErrors -join ', ' } else { '(unspecified)' })"
    exit
}
if ($state -eq "structureInvalid") {
    Write-Host "openapi_state: structureInvalid"
    Write-Host "structural_issue_count: $($d.issueCounter)"
    exit
}

$score     = $d.score
$secScore  = $d.security.score
$dataScore = $d.data.score
Write-Host "score: $score  security: $secScore  data: $dataScore"

# "semanticErrors"/"warnings" use totalIssues, "security"/"data" use
# issueCounter — that field is the true total; .issues.Count is only what's
# shown (capped at maxEntriesPerIssue).
$issues = @()
foreach ($section in @("semanticErrors", "warnings", "security", "data")) {
    $sectionData = $d.$section
    if (-not $sectionData) { continue }
    $sectionIssues = $sectionData.issues
    foreach ($issueId in ($sectionIssues | Get-Member -MemberType NoteProperty).Name) {
        $issueData = $sectionIssues.$issueId
        $crit      = if ($null -ne $issueData.criticality) { $issueData.criticality } else { 0 }
        $desc      = $issueData.description
        $shown     = if ($issueData.issues) { $issueData.issues.Count } else { 0 }
        $total     = if ($null -ne $issueData.issueCounter) { $issueData.issueCounter } elseif ($null -ne $issueData.totalIssues) { $issueData.totalIssues } else { $shown }
        $truncated = [bool]$issueData.tooManyError
        $issues += [PSCustomObject]@{ id=$issueId; section=$section; criticality=$crit; description=$desc; shown=$shown; total=$total; truncated=$truncated }
    }
}

if ($issues.Count -gt 0) {
    Write-Host "`nissues[$($issues.Count)]{id,section,criticality,description,shown,total,truncated}:"
    foreach ($i in $issues) {
        Write-Host "  $($i.id),$($i.section),$($i.criticality),$($i.description),$($i.shown),$($i.total),$($i.truncated)"
    }
}

# sqg.json (platform mode only — file is absent in token mode)
if (Test-Path "$OUTPUT_DIR\sqg.json") {
    $sqg = Get-Content "$OUTPUT_DIR\sqg.json" | ConvertFrom-Json
    Write-Host "sqg_acceptance: $($sqg.acceptance)"
    Write-Host "sqg_name: $($sqg.sqgsDetail[0].name)"
    $blocking = $sqg.processingDetails | ForEach-Object { $_.blockingRules } | Where-Object { $_ }
    if ($blocking) {
        Write-Host "blocking_rules: $($blocking -join ', ')"
    }
}
```

---

## Scan — Step 8 (Happy-path validation run)

```powershell
# Platform mode
Get-Content "$env:APPDATA\42Crunch\conf\env" | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }
$env:SCAN42C_HAPPY_PATH_ONLY='true'; $env:SCAN42C_REPORT_GENERATE_CURL_COMMAND='false'
& <binary> scan run --enrich=false `
  --output "$env:TEMP\42c-happy-report.json" --output-format json `
  <relative-oas-path> --conf-file <CONF_FILE> > "$env:TEMP\42c-happy-status.json"

# Token mode
Get-Content "$env:APPDATA\42Crunch\conf\env" | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }
$env:SCAN42C_HAPPY_PATH_ONLY='true'; $env:SCAN42C_REPORT_GENERATE_CURL_COMMAND='false'
& <binary> scan run --enrich=false `
  --freemium-host stateless.42crunch.com:443 --token $env:TRIAL_TOKEN `
  --output "$env:TEMP\42c-happy-report.json" --output-format json `
  <relative-oas-path> --conf-file <CONF_FILE> > "$env:TEMP\42c-happy-status.json"
```

## Scan — Step 8 (Happy-path failure extraction)

```powershell
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

---

## Scan — Step 10 (Full scan run)

```powershell
# Platform mode
Get-Content "$env:APPDATA\42Crunch\conf\env" | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }
$env:SCAN42C_REPORT_GENERATE_CURL_COMMAND='false'; $env:SCAN42C_REPORT_ISSUES_ONLY='true'
& <binary> scan run --enrich=false --report-sqg `
  --output "$env:TEMP\42c-scan-report.json" --output-format json `
  <relative-oas-path> --conf-file <CONF_FILE> > "$env:TEMP\42c-scan-status.json"

# Token mode
Get-Content "$env:APPDATA\42Crunch\conf\env" | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') } }
$env:SCAN42C_REPORT_GENERATE_CURL_COMMAND='false'; $env:SCAN42C_REPORT_ISSUES_ONLY='true'
& <binary> scan run --enrich=false `
  --freemium-host stateless.42crunch.com:443 --token $env:TRIAL_TOKEN `
  --output "$env:TEMP\42c-scan-report.json" --output-format json `
  <relative-oas-path> --conf-file <CONF_FILE> > "$env:TEMP\42c-scan-status.json"
```

## Scan — Step 10 (Summary extraction)

```powershell
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
        # endpoints, so filtering on it reports them as failures. See the note
        # in scan-workflow.md Step 10.
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

---

## Scan — Step 12a-0 (Authorization body comparison)

```powershell
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
