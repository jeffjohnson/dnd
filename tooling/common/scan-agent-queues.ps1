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

.EXAMPLE
    .\tooling\common\scan-agent-queues.ps1

.EXAMPLE
    .\tooling\common\scan-agent-queues.ps1 -Json

.EXAMPLE
    .\tooling\common\scan-agent-queues.ps1 -Root D:\analysis\dnd -All
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Root,

    [Parameter()]
    [switch]$Json,

    [Parameter()]
    [switch]$All
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

if ($Json) {
    $arguments += "--json"
}
if ($All) {
    $arguments += "--all"
}

& $pythonCommand.Source @arguments
exit $LASTEXITCODE
