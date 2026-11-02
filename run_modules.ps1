<#
.SYNOPSIS
  Runs the suite module by module. Every module gets its own timestamped HTML/PDF/JSON/CSV report,
  and reports\index.html lists them all.

.EXAMPLE
  .\run_modules.ps1                                  # all modules, one report each
  .\run_modules.ps1 -Modules registration,login      # selected modules
  .\run_modules.ps1 -Modules login -Workers 4 -Reruns 1 -ExtraArgs "--headed"
#>
param(
    [string[]]$Modules = @("registration", "login", "forgot_password", "change_password", "admin", "e2e", "api_access", "add_bank", "bank_approval"),
    [int]$Workers = 0,           # >0 runs each module in parallel with pytest-xdist
    [int]$Reruns = 0,            # >0 retries failures (pytest-rerunfailures); retries show in the report
    [string]$ExtraArgs = "",
    [switch]$NoPdf
)

$ErrorActionPreference = "Continue"
$summary = @()
$worstExit = 0

foreach ($module in $Modules) {
    $label = (Get-Culture).TextInfo.ToTitleCase($module.Replace("_", " "))
    Write-Host ""
    Write-Host "=== Module: $label ===" -ForegroundColor Cyan

    $pytestArgs = @("-m", "pytest", "-m", $module, "--report-name", $label)
    if ($Workers -gt 0) { $pytestArgs += @("-n", "$Workers") }
    if ($Reruns -gt 0) { $pytestArgs += @("--reruns", "$Reruns") }
    if ($NoPdf) { $pytestArgs += "--report-no-pdf" }
    if ($ExtraArgs) { $pytestArgs += $ExtraArgs.Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries) }

    & python @pytestArgs
    $code = $LASTEXITCODE
    # pytest exit code 5 = no tests collected for this marker; not a failure of the run
    if ($code -ne 0 -and $code -ne 5 -and $code -gt $worstExit) { $worstExit = $code }

    $latest = Join-Path $PSScriptRoot "reports\latest\json\results.json"
    if (Test-Path $latest) {
        $data = Get-Content $latest -Raw | ConvertFrom-Json
        if ($data.run.name -eq $label) {
            $summary += [pscustomobject]@{
                Module = $label; Total = $data.summary.total; Passed = $data.summary.passed
                Failed = $data.summary.failed; Blocked = $data.summary.blocked; Skipped = $data.summary.skipped
                "Pass %" = $data.summary.pass_rate; Report = "reports\runs\$($data.run.id)\html\index.html"
            }
        }
    }
}

Write-Host ""
Write-Host "=== Module summary ===" -ForegroundColor Cyan
$summary | Format-Table -AutoSize
Write-Host "All runs: $(Join-Path $PSScriptRoot 'reports\index.html')"
exit $worstExit
