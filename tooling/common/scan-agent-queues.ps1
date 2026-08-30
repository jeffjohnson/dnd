<#
.SYNOPSIS
    Reports logical agent work queues from repository artifact lineage.

.DESCRIPTION
    This is a PowerShell entry point for scan_agent_queues.py. The Python
    implementation follows contracts/WORK_QUEUES.md and groups artifact
    components into logical jobs, including both GUP lineage roots: packet
    updates, which consume a GUR, and decision migrations, which consume
    approved Architect Decisions and have none.

    WORK_QUEUES 1.2 requires the two scanners to return equivalent jobs,
    diagnostics, components and exit codes. That holds here by construction
    rather than by duplication: this script forwards its arguments and returns
    the Python exit code unchanged, so there is only one implementation of the
    lineage rules to keep correct. A parity test in
    tooling/common/tests/test_scan_agent_queues.py runs both and compares.

.PARAMETER Root
    Repository root. Defaults to the repository containing this script.

.PARAMETER Json
    Emits machine-readable JSON.

.PARAMETER All
    Also prints active, blocked, and informational items in console mode.

.PARAMETER Verbose
    Displays the Diagnostics section. Defaults to true. Use `-Verbose false`
    or `-v false` to suppress it.

.EXAMPLE
    .\tooling\common\scan-agent-queues.ps1

.EXAMPLE
    .\tooling\common\scan-agent-queues.ps1 -Json

.EXAMPLE
    .\tooling\common\scan-agent-queues.ps1 -Root D:\analysis\dnd -All

.EXAMPLE
    .\tooling\common\scan-agent-queues.ps1 -Verbose false
#>

param(
    [string]$Root,

    [switch]$Json,

    [switch]$All,

    [Alias("v")]
    [string]$Verbose = "true"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptPath = Join-Path $PSScriptRoot "scan_agent_queues.py"

if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    throw "Queue scanner implementation is missing: $scriptPath"
}

if ([string]::IsNullOrWhiteSpace($Root)) {
    $Root = [System.IO.Path]::GetFullPath(
        (Join-Path $PSScriptRoot "..\..")
    )
}

$pythonCommand = Get-Command "python" -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    $pythonCommand = Get-Command "py" -ErrorAction SilentlyContinue
}
if (-not $pythonCommand) {
    throw "Python 3 is required. Neither 'python' nor 'py' was found on PATH."
}

$arguments = @(
    $scriptPath
    "--root"
    ([System.IO.Path]::GetFullPath($Root))
)

$showDiagnostics = switch ($Verbose.Trim().ToLowerInvariant()) {
    { $_ -in "1", "true", "yes", "on" } { $true; break }
    { $_ -in "0", "false", "no", "off" } { $false; break }
    default {
        throw (
            "Verbose must be one of: true, false, yes, no, 1, 0, on, off. " +
            "Received: $Verbose"
        )
    }
}

if ($Json) {
    $arguments += "--json"
}
if ($All) {
    $arguments += "--all"
}
if (-not $showDiagnostics) {
    $arguments += @("--verbose", "false")
}

& $pythonCommand.Source @arguments
exit $LASTEXITCODE
