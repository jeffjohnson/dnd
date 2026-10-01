<#
.SYNOPSIS
Sends a timestamped direct Herdr notification to one repository role.

.EXAMPLE
.\tooling\common\Send-HerdrPrompt.ps1 -Role Builder -Message `
  'Ready work: rulesets/shadowdark/escalations/decisions/DEC-2026-0095.yaml. Run your bounded queue check.'

.EXAMPLE
.\tooling\common\Send-HerdrPrompt.ps1 -List

.DESCRIPTION
This wrapper implements the direct-notification checks in HERDR_HANDOFFS 2.1.
It verifies the unique live role, expected provider, and repository before
calling `herdr agent prompt`. It sends a notification; it never executes a
shell command in another pane.
#>
[CmdletBinding(DefaultParameterSetName = 'Send')]
param(
    [Parameter(Mandatory, ParameterSetName = 'Send')]
    [ValidateSet('Analyst', 'Builder', 'Integrator', 'Reviewer', 'Architect')]
    [string]$Role,

    [Parameter(Mandatory, Position = 0, ParameterSetName = 'Send')]
    [ValidateNotNullOrEmpty()]
    [string]$Message,

    [Parameter(ParameterSetName = 'List')]
    [switch]$List,

    [string]$Repository = 'D:\analysis\dnd'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ExpectedProvider = @{
    analyst = 'claude'
    builder = 'claude'
    integrator = 'claude'
    reviewer = 'codex'
    architect = 'codex'
}

function Invoke-HerdrJson {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $output = & $script:Herdr @Arguments 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        throw "Herdr failed (`$LASTEXITCODE): $output"
    }

    try {
        return $output | ConvertFrom-Json -Depth 32
    }
    catch {
        throw "Herdr returned non-JSON output: $output"
    }
}

if ([string]::IsNullOrWhiteSpace($env:HERDR_BIN_PATH)) {
    throw 'HERDR_BIN_PATH is not set. Run this script from the Herdr-hosted PowerShell session.'
}

$script:Herdr = $env:HERDR_BIN_PATH
$repositoryPath = (Resolve-Path -LiteralPath $Repository).Path.TrimEnd('\', '/')
$agentList = Invoke-HerdrJson -Arguments @('agent', 'list')
$agents = @($agentList.result.agents)
$unidentifiedAgents = @($agents | Where-Object {
        $null -eq $_.PSObject.Properties['name']
    })

if ($List) {
    foreach ($name in $ExpectedProvider.Keys | Sort-Object) {
        $matches = @($agents | Where-Object {
                $null -ne $_.PSObject.Properties['name'] -and $_.name -ieq $name
            })
        if ($matches.Count -eq 1) {
            $agent = $matches[0]
            [pscustomobject]@{
                Role             = $name
                Provider         = $agent.agent
                ExpectedProvider = $ExpectedProvider[$name]
                Status           = $agent.agent_status
                Pane             = $agent.pane_id
                Repository       = $agent.cwd
                ValidTarget      = ($agent.agent -eq $ExpectedProvider[$name] -and
                                    $agent.cwd.TrimEnd('\', '/') -ieq $repositoryPath)
            }
        }
        else {
            [pscustomobject]@{
                Role             = $name
                Provider         = if ($matches.Count) {
                    'ambiguous'
                }
                elseif ($unidentifiedAgents.Count) {
                    'unidentified'
                }
                else {
                    'absent'
                }
                ExpectedProvider = $ExpectedProvider[$name]
                Status           = ''
                Pane             = ''
                Repository       = ''
                ValidTarget      = $false
            }
        }
    }
    return
}

$roleKey = $Role.ToLowerInvariant()
$matches = @($agents | Where-Object {
        $null -ne $_.PSObject.Properties['name'] -and $_.name -ieq $roleKey
    })
if ($matches.Count -eq 0) {
    if ($unidentifiedAgents.Count) {
        throw "Herdr exposes $($unidentifiedAgents.Count) unnamed agent record(s), including a possible '$Role' pane; no prompt was sent because identity cannot be verified."
    }
    throw "Herdr role '$Role' is absent; no prompt was sent. Run with -List to inspect live agents."
}
if ($matches.Count -ne 1) {
    throw "Herdr role '$Role' is ambiguous ($($matches.Count) matches); no prompt was sent."
}

$target = $matches[0]
if ($target.agent -ne $ExpectedProvider[$roleKey]) {
    throw "Herdr role '$Role' uses provider '$($target.agent)', expected '$($ExpectedProvider[$roleKey])'; no prompt was sent."
}
if ($target.cwd.TrimEnd('\', '/') -ine $repositoryPath) {
    throw "Herdr role '$Role' is attached to '$($target.cwd)', not '$repositoryPath'; no prompt was sent."
}

$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss K'
$notification = "Local time: $timestamp; Repository $repositoryPath. $Message"
$result = Invoke-HerdrJson -Arguments @('agent', 'prompt', $roleKey, $notification)

[pscustomobject]@{
    Role         = $roleKey
    Pane         = $target.pane_id
    Status       = $target.agent_status
    Notification = $notification
    Result       = $result.result.type
}
