#Requires -Version 7.0
<#
.SYNOPSIS
    Deliver exactly one worker-selected handoff to exactly one verified agent.

.DESCRIPTION
    Implements the relay DEC-2026-0082 assigns to Builder, under
    `contracts/HERDR_HANDOFFS.md` 1.0, corrected for findings F1-F5 of
    REV-IMP-DEC-2026-0082-r01-r01.

    The problem this solves is narrow. Herdr will happily prompt an agent that
    is still working, and it does not correlate a wait to a particular turn, so
    "send the prompt as my last tool call" is not serialization -- the sender is
    by definition still running when it sends. The relay therefore runs outside
    the sender's turn: scheduling returns immediately, the sender ends its turn,
    and a detached process waits for the sender to settle before submitting.

    Five properties the first revision got wrong, each now load-bearing:

    1. A request is complete and typed or it does not schedule. Every input and
       prerequisite carries a path *and* a checksum; scope identifiers are
       either explicitly null or well-formed; the endpoint is verified against
       the inherited one. Containment is decided on resolved paths with a
       separator boundary, because `StartsWith` alone admits a sibling
       directory whose name merely begins with the root's.

    2. Both parties are resolved by unique role alias and then cross-checked on
       provider, pane, repository root and native session. The first matching
       pane is never good enough: an alias reassigned to another agent, or two
       agents answering to one alias, must fail closed rather than pick one.

    3. Delivery acknowledgment is not settlement. A response of `submitted` or
       `blocked` means the message left, not that the turn finished, so the
       relay re-resolves the recipient and requires it to be idle or done
       before it calls the job settled and releases the lock.

    4. Identity is claimed atomically under the lock at every entry point, and
       evidence of a possible send is never overwritten. A killed relay leaves
       `submitting` behind; a later attempt must refuse without erasing it.

    5. Every child endpoint call is supervised against one monotonic deadline
       and killed when it expires. A hung client cannot be trusted to honour
       its own `--timeout`, and nothing may be sent after the window closes.

    What the relay is not: it chooses nothing. It does not rank work, consume an
    artifact, approve anything, or decide who runs next. The worker picked the
    recipient and wrote the prompt; this transports that one message and refuses
    when it cannot do so safely.

.PARAMETER RequestPath
    A local JSON request. `Test-HandoffRequest` documents the required shape.

.PARAMETER TimeoutMs
    Explicit bounded budget for the whole deferred phase, child calls included.
    Required; an unbounded relay can hang forever holding the global lock.

.PARAMETER ValidateOnly
    Validate and exit. Launches nothing, writes nothing, takes no lock.

.PARAMETER ExecuteRequest
    Internal. Run the deferred phase in the foreground. The scheduler spawns
    this; the test suites drive it directly so the races stay deterministic.

.OUTPUTS
    A JSON object on stdout. Exit codes:
      0  queued (scheduling), or delivered and settled (execution)
      1  not delivered for a stated, expected reason (a peer is not idle)
      2  invalid request or fail-closed refusal; nothing was sent
      3  uncertain; a human must reconcile before any resend
#>

[CmdletBinding(DefaultParameterSetName = 'Schedule')]
param(
    [Parameter(Mandatory = $true)]
    [string] $RequestPath,

    [Parameter(Mandatory = $true)]
    [ValidateRange(1000, 3600000)]
    [int] $TimeoutMs,

    [Parameter(ParameterSetName = 'Validate')]
    [switch] $ValidateOnly,

    [Parameter(ParameterSetName = 'Execute')]
    [switch] $ExecuteRequest
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = 'Stop'

$script:ActiveRoles = @('architect', 'analyst', 'builder', 'reviewer', 'integrator')
$script:RetiredRoles = @{ dispatcher = 'DEC-2026-0082' }

# Provider bindings from HERDR_HANDOFFS.md. A role alias attached to the wrong
# provider means the pane is not the agent the worker believes it addressed.
$script:RoleProviders = @{
    architect = 'codex'; analyst = 'claude'; builder = 'claude'
    reviewer  = 'codex'; integrator = 'claude'
}

# A terminal state releases the queue. `uncertain` is deliberately absent: an
# unresolved possible-delivery blocks every later request until a human clears it.
$script:TerminalStates = @('settled', 'failed', 'refused')

# States recording that a send may already have happened. Never overwritten by
# a competing attempt.
$script:ProtectedStates = @('submitting', 'acknowledged', 'uncertain')

# A response status meaning the recipient's turn finished. `submitted` and
# `blocked` are deliberately absent: the first says the message left, the
# second says a human is needed, and neither is settlement (F3).
$script:SettledResponseStatuses = @('done', 'idle', 'completed', 'settled', 'finished')

$script:ExitOk = 0; $script:ExitNotReady = 1; $script:ExitInvalid = 2; $script:ExitUncertain = 3

# One monotonic budget for the whole deferred phase, started in Invoke-Execute.
$script:DeadlineStopwatch = $null
$script:BudgetMs = 0

# --------------------------------------------------------------------------
# Result plumbing
# --------------------------------------------------------------------------

function Write-Result {
    param([hashtable] $Result, [int] $Code)
    $Result | ConvertTo-Json -Depth 12 | Write-Output
    exit $Code
}

function New-Failure {
    param([string] $RequestId, [string] $Stage, [string[]] $Problems, [int] $Code)
    Write-Result -Code $Code -Result @{
        request_id = $RequestId; stage = $Stage; status = 'refused'
        delivered  = $false; problems = @($Problems)
    }
}

function Get-RemainingMs {
    if (-not $script:DeadlineStopwatch) { return $script:BudgetMs }
    return [int]($script:BudgetMs - $script:DeadlineStopwatch.ElapsedMilliseconds)
}

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

function Resolve-InsideRoot {
    <#
        The resolved path, or $null when it does not exist or escapes the root.

        Containment is decided on the resolved path with a trailing separator
        appended to the root. Without that boundary a sibling directory named
        like the root plus a suffix -- `repo-backup` beside `repo` -- passes a
        bare StartsWith, and a request can name a file outside the repository.
    #>
    param([string] $Root, [string] $Relative)

    if ([string]::IsNullOrWhiteSpace($Relative)) { return $null }
    $combined = if ([System.IO.Path]::IsPathRooted($Relative)) { $Relative }
                else { Join-Path $Root $Relative }
    try { $resolved = (Resolve-Path -LiteralPath $combined -ErrorAction Stop).Path }
    catch { return $null }

    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd([System.IO.Path]::DirectorySeparatorChar)
    $boundary = $rootFull + [System.IO.Path]::DirectorySeparatorChar
    $target = [System.IO.Path]::GetFullPath($resolved)
    if ($target -eq $rootFull) { return $resolved }
    if (-not $target.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase)) { return $null }

    # Fail closed on any reparse point between the root and the target. The
    # root's own ancestry is deliberately not inspected: a repository that
    # happens to live under a junction is not the attack, and rejecting it
    # would make the relay unusable on ordinary Windows layouts.
    $current = $target
    while ($current -and $current.Length -gt $rootFull.Length) {
        try { $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop }
        catch { return $null }
        if ($item.Attributes.HasFlag([System.IO.FileAttributes]::ReparsePoint)) { return $null }
        $current = [System.IO.Path]::GetDirectoryName($current)
    }
    return $resolved
}

function Get-Sha256 {
    param([string] $Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLower()
}

# --------------------------------------------------------------------------
# Supervised endpoint calls (F5)
# --------------------------------------------------------------------------

function Invoke-Herdr {
    <#
        One herdr call, supervised against the remaining budget and killed when
        it expires.

        A hung client cannot be trusted to honour its own `--timeout`, so the
        bound is enforced by the parent. A non-zero exit, unparseable output, or
        an expired deadline is an uncertainty rather than an empty result: "no
        agents" and "could not ask" must never look alike to the caller.
    #>
    param([string] $HerdrBin, [string[]] $Arguments, [switch] $AllowErrorEnvelope)

    $remaining = Get-RemainingMs
    if ($remaining -le 0) {
        throw "the request deadline expired before 'herdr $($Arguments -join ' ')' could run"
    }

    $info = [System.Diagnostics.ProcessStartInfo]::new()
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.UseShellExecute = $false
    $info.WorkingDirectory = (Get-Location).Path

    # A native client is executed directly; only a PowerShell script double
    # needs a host. ArgumentList is used rather than a joined string so a path
    # or prompt containing spaces is passed through intact.
    if ([System.IO.Path]::GetExtension($HerdrBin) -eq '.ps1') {
        $info.FileName = (Get-Process -Id $PID).Path
        foreach ($argument in @('-NoLogo', '-NonInteractive', '-NoProfile', '-File', $HerdrBin)) {
            $info.ArgumentList.Add([string]$argument)
        }
    } else {
        $info.FileName = $HerdrBin
    }
    foreach ($argument in $Arguments) { $info.ArgumentList.Add([string]$argument) }

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $info
    [void]$process.Start()
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()

    if (-not $process.WaitForExit($remaining)) {
        try { $process.Kill($true) } catch { }
        throw "herdr '$($Arguments -join ' ')' exceeded the ${remaining}ms deadline and was stopped"
    }
    $text = ($stdout.GetAwaiter().GetResult() + $stderr.GetAwaiter().GetResult()).Trim()
    if ($process.ExitCode -ne 0) {
        # herdr reports a refused or unobserved submission as a nonzero exit
        # carrying a structured error envelope. Throwing that away made
        # `agent_blocked` -- which sends nothing -- indistinguishable from
        # `agent_prompt_stalled` -- which may well have delivered. Both were
        # filed `uncertain`, so every one left a record a human had to clear.
        # Only the caller that knows how to classify the codes asks for it.
        if ($AllowErrorEnvelope) {
            $envelope = $null
            try { $envelope = $text | ConvertFrom-Json } catch { $envelope = $null }
            if ($envelope -and ($envelope.PSObject.Properties.Name -contains 'error')) {
                return $envelope
            }
        }
        throw "herdr '$($Arguments -join ' ')' exited $($process.ExitCode): $text"
    }
    try { return $text | ConvertFrom-Json }
    catch { throw "herdr '$($Arguments -join ' ')' returned unparseable output: $text" }
}

function Get-AgentField {
    <#
        One field of a JSON object, or the default.

        `$object.PSObject.Properties.Name` throws under StrictMode when the
        object has no properties at all, which a herdr error envelope of `{}`
        does. That turned a malformed response into an unhandled crash after the
        request was already recorded `submitting`, leaving the worst possible
        record: a send that may have happened, with no classification.
    #>
    param([object] $Agent, [string] $Name, [string] $Default = '')

    if ($null -eq $Agent) { return $Default }
    $names = @()
    try { $names = @($Agent.PSObject.Properties | ForEach-Object { $_.Name }) }
    catch { return $Default }
    if ($names -notcontains $Name) { return $Default }
    if ($null -eq $Agent.$Name) { return $Default }
    return [string]$Agent.$Name
}

function Get-AgentSession {
    param([object] $Agent)
    if ($Agent.PSObject.Properties.Name -contains 'agent_session' -and $Agent.agent_session) {
        if ($Agent.agent_session.PSObject.Properties.Name -contains 'value') {
            return [string]$Agent.agent_session.value
        }
    }
    return ''
}

function Get-BoundAgents {
    <#
        Every agent herdr reports for this exact repository root, re-resolved on
        each call. Aliases are reassigned when an agent exits and pane IDs move
        when panes move, so a cached binding is a guess.
    #>
    param([string] $HerdrBin, [string] $Root)

    $response = Invoke-Herdr -HerdrBin $HerdrBin -Arguments @('agent', 'list')
    $rootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd([System.IO.Path]::DirectorySeparatorChar)
    $agents = @()
    if ($response.PSObject.Properties.Name -notcontains 'result') { return , $agents }
    foreach ($agent in @($response.result.agents)) {
        if (-not $agent) { continue }
        $cwd = Get-AgentField $agent 'cwd'
        if ([string]::IsNullOrWhiteSpace($cwd)) { continue }
        try { $cwdFull = [System.IO.Path]::GetFullPath($cwd).TrimEnd([System.IO.Path]::DirectorySeparatorChar) }
        catch { continue }
        if ($cwdFull -ne $rootFull) { continue }
        $agents += $agent
    }
    return , $agents
}

function Resolve-Party {
    <#
        Resolve one party by its unique role alias, then cross-check everything
        the request asserted about it (F2).

        Resolution is by alias rather than by pane because a pane is a location
        and an alias is an identity. Two agents answering to one alias is an
        ambiguity that must fail closed: picking the first is how a review
        assignment reaches the wrong agent.

        Returns @{ ok; problems; agent; identity }.
    #>
    param([object] $Party, [string] $Label, [object[]] $Agents)

    $problems = [System.Collections.Generic.List[string]]::new()
    $role = [string]$Party.role
    $declaredName = [string]$Party.name

    if ($declaredName -ne $role) {
        $problems.Add("$Label declares alias '$declaredName' for role '$role'; the herdr alias is the role name")
        return @{ ok = $false; problems = $problems.ToArray() }
    }

    $found = @($Agents | Where-Object { (Get-AgentField $_ 'name') -eq $declaredName })
    if ($found.Count -eq 0) {
        $problems.Add("$Label alias '$declaredName' is not bound to this repository")
        return @{ ok = $false; problems = $problems.ToArray() }
    }
    if ($found.Count -gt 1) {
        $panes = ($found | ForEach-Object { Get-AgentField $_ 'pane_id' }) -join ', '
        $problems.Add("$Label alias '$declaredName' is ambiguous across panes $panes; refusing to choose one")
        return @{ ok = $false; problems = $problems.ToArray() }
    }

    $agent = $found[0]
    $identity = @{
        name = Get-AgentField $agent 'name'
        provider = Get-AgentField $agent 'agent'
        pane_id = Get-AgentField $agent 'pane_id'
        status = Get-AgentField $agent 'agent_status'
        session_id = Get-AgentSession $agent
        state_change_seq = Get-AgentField $agent 'state_change_seq'
    }

    $expectedProvider = $script:RoleProviders[$role]
    if ($identity.provider -ne $expectedProvider) {
        $problems.Add("$Label provider is '$($identity.provider)', expected '$expectedProvider' for role '$role'")
    }
    if ($identity.pane_id -ne [string]$Party.pane_id) {
        $problems.Add("$Label alias '$declaredName' is on pane '$($identity.pane_id)', request names '$($Party.pane_id)'")
    }
    if ($identity.session_id -ne [string]$Party.session_id) {
        $problems.Add("$Label native session is '$($identity.session_id)', request names '$($Party.session_id)'")
    }

    return @{
        ok = ($problems.Count -eq 0); problems = $problems.ToArray()
        agent = $agent; identity = $identity
    }
}

function Get-ResponseAgentStatus {
    <#
        The recipient's status as the prompt response actually reports it.

        herdr returns {id, result:{agent:{... agent_status ...}, type}}. There is
        no `result.status`: reading one meant every real delivery reported 'the
        response carried no status' and was filed `uncertain`, which blocks the
        next handoff until a human clears it. Three consecutive confirmed
        deliveries were misfiled that way before anyone compared the relay's
        assumption against the installed binary.

        The flat spellings are still accepted first so an older or future
        envelope that does carry one keeps working; the nested agent is the
        shape 0.8.2 emits.
    #>
    param([object] $Response)

    if (-not $Response) { return '' }
    if (-not ($Response.PSObject.Properties.Name -contains 'result')) { return '' }
    $result = $Response.result
    if (-not $result) { return '' }

    foreach ($name in @('status', 'agent_status')) {
        $value = Get-AgentField $result $name
        if ($value) { return $value }
    }
    if (($result.PSObject.Properties.Name -contains 'agent') -and $result.agent) {
        return Get-AgentField $result.agent 'agent_status'
    }
    return ''
}

function Test-ObservationAdvanced {
    <#
        Whether the recipient's state-change counter moved past the value read
        immediately before submission.

        This is the positive evidence that a turn actually started, independent
        of the response envelope's shape. An unreadable counter on either side
        is not advancement: this must fail closed.
    #>
    param([string] $Before, [string] $After)

    # Deliberately not Int64.TryParse: PowerShell does not reliably bind a
    # [ref] to that out-parameter overload, and the failure mode is silent --
    # it simply reports no advancement, which reads as a delivery that never
    # ran. Matching the digits first keeps the cast total.
    if ($Before -notmatch '^\s*-?\d+\s*$') { return $false }
    if ($After -notmatch '^\s*-?\d+\s*$') { return $false }
    return ([int64]$After.Trim()) -gt ([int64]$Before.Trim())
}

function Test-AgentSettled {
    param([string] $Status)
    return @('idle', 'done') -contains $Status
}

# --------------------------------------------------------------------------
# Request validation (F1)
# --------------------------------------------------------------------------

function Test-HandoffRequest {
    <#
        A complete, typed, bounded request, or nothing happens.

        Validation is total rather than early-exit: a worker fixing one field
        per run is the slowest possible way to learn that four are wrong.

        Required shape:
          request_id          safe filename token
          repository_root     an existing directory
          endpoint            { herdr_bin }, matching the inherited endpoint
          authority           non-empty
          scope               { ruleset_id, book_id }, each null or well formed
          sender, recipient   { role, name, pane_id, session_id }
          inputs              [ { id, path, checksum } ], each inside the root
          prerequisites       [ { id, path, checksum } ], each inside the root
          action              non-empty
          ordered_next_steps  [ { priority, role, action, readiness, reason } ]
          prompt              non-empty
    #>
    param([object] $Request, [string] $RequestFile)

    $problems = [System.Collections.Generic.List[string]]::new()
    function Has { param($Object, $Name)
        return ($null -ne $Object) -and ($Object.PSObject.Properties.Name -contains $Name)
    }

    $required = @('request_id', 'repository_root', 'endpoint', 'authority', 'scope',
                  'sender', 'recipient', 'inputs', 'prerequisites', 'action',
                  'ordered_next_steps', 'prompt')
    foreach ($field in $required) {
        if (-not (Has $Request $field)) { $problems.Add("missing required field '$field'") }
    }
    if ($problems.Count -gt 0) { return $problems.ToArray() }

    foreach ($collection in @('inputs', 'prerequisites', 'ordered_next_steps')) {
        $value = $Request.$collection
        if ($null -eq $value) {
            $problems.Add("$collection must be an array; null is not an empty collection")
        } elseif (($value -is [string]) -or -not ($value -is [System.Collections.IEnumerable])) {
            $problems.Add("$collection must be an array")
        }
    }

    if ([string]$Request.request_id -notmatch '^[A-Za-z0-9._-]{1,128}$') {
        # The ID becomes a filename under .local/herdr/. A separator or a
        # traversal segment there would let a request write outside its store.
        $problems.Add("request_id '$($Request.request_id)' must match ^[A-Za-z0-9._-]{1,128}$")
    }
    foreach ($field in @('authority', 'action', 'prompt')) {
        if ([string]::IsNullOrWhiteSpace([string]$Request.$field)) {
            $problems.Add("$field is empty")
        }
    }

    $root = $null
    try { $root = (Resolve-Path -LiteralPath ([string]$Request.repository_root)).Path }
    catch { $problems.Add("repository_root '$($Request.repository_root)' does not exist") }

    if ($root) {
        if (-not (Resolve-InsideRoot -Root $root -Relative $RequestFile)) {
            $problems.Add('the request file is outside repository_root')
        }
        foreach ($group in @(@{ Key = 'inputs'; Label = 'input' },
                             @{ Key = 'prerequisites'; Label = 'prerequisite' })) {
            foreach ($entry in @($Request.($group.Key))) {
                if ($null -eq $entry) { continue }
                if ($entry -is [string]) {
                    $problems.Add("$($group.Label) '$entry' must be an object with id, path and checksum")
                    continue
                }
                foreach ($field in @('id', 'path', 'checksum')) {
                    if (-not (Has $entry $field) -or [string]::IsNullOrWhiteSpace([string]$entry.$field)) {
                        $problems.Add("$($group.Label) entry is missing '$field'")
                    }
                }
                if (-not (Has $entry 'path')) { continue }
                $relative = [string]$entry.path
                $resolved = Resolve-InsideRoot -Root $root -Relative $relative
                if (-not $resolved) {
                    $problems.Add("$($group.Label) path '$relative' does not exist inside repository_root")
                    continue
                }
                if ((Has $entry 'checksum') -and $entry.checksum) {
                    $declared = (([string]$entry.checksum) -replace '^sha256:', '').ToLower()
                    $actual = Get-Sha256 -Path $resolved
                    if ($actual -ne $declared) {
                        # A stale checksum means the worker measured a different
                        # file than the recipient would open.
                        $problems.Add("$($group.Label) '$relative' checksum is stale: request says $declared, file is $actual")
                    }
                }
            }
        }
    }

    # Endpoint identity. A relay pointed at a different endpoint than the caller
    # inherited is addressing a different herdr server.
    if (-not (Has $Request.endpoint 'herdr_bin') -or
        [string]::IsNullOrWhiteSpace([string]$Request.endpoint.herdr_bin)) {
        $problems.Add('endpoint.herdr_bin is missing')
    } else {
        $declaredBin = [string]$Request.endpoint.herdr_bin
        if (-not (Test-Path -LiteralPath $declaredBin)) {
            $problems.Add("endpoint.herdr_bin '$declaredBin' does not exist")
        } elseif ($env:HERDR_BIN_PATH -and (Test-Path -LiteralPath $env:HERDR_BIN_PATH)) {
            $declaredFull = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $declaredBin).Path)
            $inheritedFull = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $env:HERDR_BIN_PATH).Path)
            if ($declaredFull -ne $inheritedFull) {
                $problems.Add("endpoint.herdr_bin '$declaredBin' is not the inherited endpoint '$($env:HERDR_BIN_PATH)'")
            }
        }
    }

    # The socket identifies the server; the binary only identifies the client.
    # A request may omit it, but one that names a different socket than the
    # inherited endpoint is addressing a different herdr.
    if ((Has $Request.endpoint 'socket_path') -and $Request.endpoint.socket_path) {
        $declaredSocket = [string]$Request.endpoint.socket_path
        if ($env:HERDR_SOCKET_PATH -and ($declaredSocket -ne $env:HERDR_SOCKET_PATH)) {
            $problems.Add("endpoint.socket_path '$declaredSocket' is not the inherited socket '$($env:HERDR_SOCKET_PATH)'")
        }
    }

    # Scope. An identifier is either explicitly unassigned (null) or a
    # well-formed ID; it is never invented and never a path fragment.
    foreach ($field in @('ruleset_id', 'book_id')) {
        if (-not (Has $Request.scope $field)) {
            $problems.Add("scope.$field is missing; record it as null when unassigned")
            continue
        }
        $value = $Request.scope.$field
        if ($null -eq $value) { continue }
        if ([string]$value -cnotmatch '^[a-z0-9][a-z0-9-]{0,63}$') {
            $problems.Add("scope.$field '$value' is not a well-formed identifier")
        }
    }

    foreach ($side in @('sender', 'recipient')) {
        $party = $Request.$side
        foreach ($field in @('role', 'name', 'pane_id', 'session_id')) {
            if (-not (Has $party $field) -or [string]::IsNullOrWhiteSpace([string]$party.$field)) {
                $problems.Add("$side.$field is missing")
            }
        }
        if (-not (Has $party 'role')) { continue }
        $role = [string]$party.role
        if ($script:RetiredRoles.ContainsKey($role)) {
            $problems.Add("$side role '$role' was retired by $($script:RetiredRoles[$role]); it cannot be addressed")
        } elseif ($script:ActiveRoles -notcontains $role) {
            $problems.Add("$side role '$role' is not one of: $($script:ActiveRoles -join ', ')")
        }
    }
    if ((Has $Request.sender 'role') -and (Has $Request.recipient 'role') -and
        ([string]$Request.sender.role -eq [string]$Request.recipient.role)) {
        $problems.Add('sender and recipient are the same role; a handoff goes to another agent')
    }

    foreach ($step in @($Request.ordered_next_steps)) {
        if ($null -eq $step) { continue }
        foreach ($field in @('priority', 'role', 'action', 'readiness', 'reason')) {
            if (-not (Has $step $field)) { $problems.Add("an ordered_next_steps entry is missing '$field'") }
        }
        if ((Has $step 'role') -and ($script:ActiveRoles -notcontains [string]$step.role)) {
            $problems.Add("ordered_next_steps names role '$($step.role)', which is not active")
        }
        if ((Has $step 'readiness') -and (@('ready', 'blocked') -notcontains [string]$step.readiness)) {
            $problems.Add("ordered_next_steps readiness '$($step.readiness)' must be ready or blocked")
        }
    }

    return $problems.ToArray()
}

# --------------------------------------------------------------------------
# Durable request state (F4)
# --------------------------------------------------------------------------

function Get-StateDirectory {
    param([string] $Root)
    $directory = Join-Path $Root '.local/herdr/requests'
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    return $directory
}

function Get-StatePath {
    param([string] $Root, [string] $RequestId)
    return Join-Path (Get-StateDirectory -Root $Root) "$RequestId.state.json"
}

function Get-State {
    param([string] $Root, [string] $RequestId)
    $path = Get-StatePath -Root $Root -RequestId $RequestId
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    try { return Get-Content -LiteralPath $path -Raw | ConvertFrom-Json }
    catch { return [pscustomobject]@{ request_id = $RequestId; state = 'unreadable' } }
}

function Write-State {
    <#
        Crash-visible progress. `submitting` is written before the prompt so a
        process that dies mid-send leaves evidence that a send may have landed;
        losing that ordering is what turns a crash into a duplicate assignment.

        A protected state is never overwritten except by this relay's own
        forward progress (-Force). A competitor recording `refused` over another
        execution's `submitting` would erase the only evidence that something
        may already be in flight (F4).
    #>
    param(
        [string] $Root, [string] $RequestId, [string] $State,
        [hashtable] $Extra = @{}, [switch] $Force
    )

    if (-not $Force) {
        $existing = Get-State -Root $Root -RequestId $RequestId
        if ($existing -and ($script:ProtectedStates -contains [string]$existing.state)) {
            return $existing
        }
    }
    $record = @{
        request_id = $RequestId
        state = $State
        updated_utc = (Get-Date).ToUniversalTime().ToString('o')
        pid = $PID
    }
    foreach ($key in $Extra.Keys) { $record[$key] = $Extra[$key] }
    $record | ConvertTo-Json -Depth 12 |
        Set-Content -LiteralPath (Get-StatePath -Root $Root -RequestId $RequestId) -Encoding utf8
    return $record
}

function Get-OutstandingRequests {
    <#
        One outstanding delivery across all five roles. A worker may stage its
        own request while another is in flight; it may not submit one.
        `uncertain` counts as outstanding until a human clears it.
    #>
    param([string] $Root, [string] $ExceptRequestId)

    $outstanding = @()
    foreach ($file in Get-ChildItem -LiteralPath (Get-StateDirectory -Root $Root) `
                     -Filter '*.state.json' -ErrorAction SilentlyContinue) {
        try { $record = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json }
        catch {
            $outstanding += @{ request_id = $file.BaseName; state = 'unreadable'; recipient_pane = '' }
            continue
        }
        if ([string]$record.request_id -eq $ExceptRequestId) { continue }
        if ($script:TerminalStates -contains [string]$record.state) { continue }
        $pane = ''
        if ($record.PSObject.Properties.Name -contains 'recipient_pane') {
            $pane = [string]$record.recipient_pane
        } elseif (($record.PSObject.Properties.Name -contains 'recipient') -and $record.recipient) {
            if ($record.recipient.PSObject.Properties.Name -contains 'pane_id') {
                $pane = [string]$record.recipient.pane_id
            }
        }
        $outstanding += @{
            request_id = [string]$record.request_id
            state = [string]$record.state
            recipient_pane = $pane
        }
    }
    return , $outstanding
}


function Get-DeliveryBlockers {
    <#
        Outstanding work that forbids a *delivery*, as opposed to work that
        merely forbids staging.

        The contract's serial continuation depends on this distinction. A
        recipient finishing its turn must be able to queue the next assignment
        while its own parent relay still holds the delivery lock through
        settlement; refusing that leaves the chain unusable. A request whose
        parent named this sender as its recipient is that continuation. Anything
        else -- an independent competitor, or an unresolved uncertainty -- still
        blocks.
    #>
    param([object[]] $Outstanding, [string] $SenderPane, [switch] $AllowContinuation)

    $blockers = @()
    foreach ($entry in $Outstanding) {
        if ($entry.state -eq 'uncertain') {
            $blockers += "$($entry.request_id)=uncertain (unresolved; a human must reconcile it)"
            continue
        }
        if ($AllowContinuation -and $SenderPane -and ($entry.recipient_pane -eq $SenderPane)) {
            continue
        }
        $blockers += "$($entry.request_id)=$($entry.state)"
    }
    return , $blockers
}


function New-StateReservation {
    <#
        Atomically claim a request ID by creating its state file exclusively.

        Check-then-write is not a reservation: two schedulers can both observe
        an absent record and both proceed. CreateNew makes the claim itself the
        test, so exactly one wins (R4).
    #>
    param([string] $Root, [string] $RequestId, [hashtable] $Record)

    $path = Get-StatePath -Root $Root -RequestId $RequestId
    try {
        $stream = [System.IO.File]::Open(
            $path, [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
    } catch [System.IO.IOException] {
        return $false
    }
    try {
        $writer = [System.IO.StreamWriter]::new($stream)
        $writer.Write(($Record | ConvertTo-Json -Depth 12))
        $writer.Flush()
        $writer.Dispose()
    } finally {
        $stream.Dispose()
    }
    return $true
}

# --------------------------------------------------------------------------
# The repository-wide lock
# --------------------------------------------------------------------------

function Open-HandoffLock {
    <#
        Exclusive create. Never stolen by age: a stale-looking lock may belong
        to a live process whose recipient is mid-turn, and the cost of guessing
        wrong is two agents working at once.
    #>
    param([string] $Root, [string] $RequestId)

    $path = Join-Path $Root '.local/herdr/handoff.lock'
    $parent = Split-Path -Parent $path
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    try {
        $stream = [System.IO.File]::Open(
            $path, [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
    } catch [System.IO.IOException] {
        return $null
    }
    $writer = [System.IO.StreamWriter]::new($stream)
    $writer.WriteLine((@{
        request_id = $RequestId; pid = $PID
        acquired_utc = (Get-Date).ToUniversalTime().ToString('o')
    } | ConvertTo-Json -Compress))
    $writer.Flush()
    return @{ Path = $path; Stream = $stream; Writer = $writer }
}

function Close-HandoffLock {
    param([object] $Lock)
    if (-not $Lock) { return }
    try { $Lock.Writer.Dispose() } catch { }
    try { $Lock.Stream.Dispose() } catch { }
    try { Remove-Item -LiteralPath $Lock.Path -Force -ErrorAction Stop } catch { }
}

# --------------------------------------------------------------------------
# Phases
# --------------------------------------------------------------------------

function Invoke-Schedule {
    param([object] $Request, [string] $RequestFile, [string] $Root, [int] $TimeoutMs)

    $requestId = [string]$Request.request_id

    $existing = Get-State -Root $Root -RequestId $requestId
    if ($existing) {
        New-Failure -RequestId $requestId -Stage 'schedule' -Code $script:ExitInvalid -Problems @(
            "request '$requestId' already exists in state '$($existing.state)'; a duplicate ID cannot resubmit"
        )
    }

    # Staging is permitted while this sender's own parent is still settling;
    # delivery is not. Anything else outstanding still refuses.
    $outstanding = Get-OutstandingRequests -Root $Root -ExceptRequestId $requestId
    $blockers = Get-DeliveryBlockers -Outstanding $outstanding `
        -SenderPane ([string]$Request.sender.pane_id) -AllowContinuation
    if ($blockers.Count -gt 0) {
        New-Failure -RequestId $requestId -Stage 'schedule' -Code $script:ExitNotReady -Problems @(
            "another request is outstanding ($($blockers -join ', ')); only one handoff may be in flight"
        )
    }

    # The queued payload is bound by checksum so it cannot change between
    # scheduling and delivery, and the claim is atomic rather than
    # check-then-write.
    $reserved = New-StateReservation -Root $Root -RequestId $requestId -Record @{
        request_id = $requestId
        state = 'queued'
        updated_utc = (Get-Date).ToUniversalTime().ToString('o')
        pid = $PID
        request_path = $RequestFile
        request_checksum = "sha256:$(Get-Sha256 -Path $RequestFile)"
        endpoint = @{
            herdr_bin = [string]$Request.endpoint.herdr_bin
            socket_path = [string]$env:HERDR_SOCKET_PATH
        }
        sender = @{ role = [string]$Request.sender.role; pane_id = [string]$Request.sender.pane_id }
        recipient = @{ role = [string]$Request.recipient.role; pane_id = [string]$Request.recipient.pane_id }
        recipient_pane = [string]$Request.recipient.pane_id
        timeout_ms = $TimeoutMs
    }
    if (-not $reserved) {
        New-Failure -RequestId $requestId -Stage 'schedule' -Code $script:ExitInvalid -Problems @(
            "request '$requestId' was reserved concurrently; a duplicate ID cannot resubmit"
        )
    }

    $arguments = @(
        '-NoLogo', '-NonInteractive', '-NoProfile', '-File', $PSCommandPath,
        '-RequestPath', $RequestFile, '-TimeoutMs', $TimeoutMs, '-ExecuteRequest'
    )
    $process = Start-Process -FilePath (Get-Process -Id $PID).Path `
        -ArgumentList $arguments -WindowStyle Hidden -PassThru

    Write-Result -Code $script:ExitOk -Result @{
        request_id = $requestId; stage = 'schedule'; status = 'queued'
        delivered = $false; relay_pid = $process.Id
        note = 'The sender must now end its turn. Delivery happens only after it settles.'
    }
}

function Invoke-Execute {
    param([object] $Request, [string] $RequestFile, [string] $Root, [int] $TimeoutMs)

    $requestId = [string]$Request.request_id
    $herdr = [string]$Request.endpoint.herdr_bin

    $script:BudgetMs = $TimeoutMs
    $script:DeadlineStopwatch = [System.Diagnostics.Stopwatch]::StartNew()

    # The lock is taken before anything is claimed or inspected, so identity
    # reservation and the outstanding check happen under mutual exclusion (F4).
    $lock = Open-HandoffLock -Root $Root -RequestId $requestId
    if (-not $lock) {
        # Deliberately no state write: a competitor must not record `refused`
        # over another execution's `submitting` evidence.
        New-Failure -RequestId $requestId -Stage 'lock' -Code $script:ExitNotReady -Problems @(
            'another relay holds the repository handoff lock; not stealing it'
        )
    }

    try {
        # -- claim the identity ------------------------------------------
        $existing = Get-State -Root $Root -RequestId $requestId
        if (-not $existing) {
            # Authorization is never created merely because no record exists.
            New-Failure -RequestId $requestId -Stage 'claim' -Code $script:ExitInvalid -Problems @(
                "request '$requestId' has no queued reservation; delivery requires an unconsumed scheduled request"
            )
        }
        if ([string]$existing.state -ne 'queued') {
            New-Failure -RequestId $requestId -Stage 'claim' -Code $script:ExitInvalid -Problems @(
                "request '$requestId' is already in state '$($existing.state)'; it is consumed and cannot be replayed"
            )
        }
        $currentChecksum = "sha256:$(Get-Sha256 -Path $RequestFile)"
        if ($existing.PSObject.Properties.Name -contains 'request_checksum') {
            if ([string]$existing.request_checksum -ne $currentChecksum) {
                New-Failure -RequestId $requestId -Stage 'claim' -Code $script:ExitInvalid -Problems @(
                    "the request payload changed after it was queued: queued $($existing.request_checksum), now $currentChecksum"
                )
            }
        }
        # Delivery, unlike staging, tolerates no outstanding predecessor at all.
        $outstanding = Get-OutstandingRequests -Root $Root -ExceptRequestId $requestId
        $blockers = Get-DeliveryBlockers -Outstanding $outstanding -SenderPane ''
        if ($blockers.Count -gt 0) {
            New-Failure -RequestId $requestId -Stage 'claim' -Code $script:ExitNotReady -Problems @(
                "another request is outstanding ($($blockers -join ', ')); refusing to deliver a second"
            )
        }
        Write-State -Root $Root -RequestId $requestId -State 'claimed' -Extra @{
            request_path = $RequestFile; request_checksum = $currentChecksum
        } | Out-Null

        # -- wait for the sender's own turn to finish --------------------
        $senderSettled = $false
        $senderWaitError = ''
        $agents = @()
        while ((Get-RemainingMs) -gt 0) {
            try { $agents = Get-BoundAgents -HerdrBin $herdr -Root $Root }
            catch {
                # The budget ran out inside the call, or the endpoint failed.
                # Nothing has been sent, so this is an ordinary refusal.
                $senderWaitError = "$_"
                break
            }
            $sender = Resolve-Party -Party $Request.sender -Label 'sender' -Agents $agents
            if (-not $sender.ok) {
                Write-State -Root $Root -RequestId $requestId -State 'failed' -Extra @{
                    reason = 'sender identity'; problems = $sender.problems
                } | Out-Null
                New-Failure -RequestId $requestId -Stage 'verify-sender' -Code $script:ExitInvalid -Problems $sender.problems
            }
            $senderStatus = $sender.identity.status
            if (Test-AgentSettled -Status $senderStatus) { $senderSettled = $true; break }
            if ($senderStatus -ne 'working') {
                # Blocked or unknown is not "not finished yet". A later idle
                # observation must not implicitly resume a request that met an
                # unresolved blocker, so this stops for reconciliation.
                Write-State -Root $Root -RequestId $requestId -State 'failed' -Extra @{
                    reason = 'sender in an unresolved state'; sender_status = $senderStatus
                } | Out-Null
                New-Failure -RequestId $requestId -Stage 'wait-sender' -Code $script:ExitInvalid -Problems @(
                    "the sender is '$senderStatus', which is neither settled nor working; stopping for reconciliation rather than waiting it out"
                )
            }
            Start-Sleep -Milliseconds 300
        }
        if (-not $senderSettled) {
            Write-State -Root $Root -RequestId $requestId -State 'refused' -Extra @{
                reason = 'sender still working at the deadline'
            } | Out-Null
            New-Failure -RequestId $requestId -Stage 'wait-sender' -Code $script:ExitNotReady -Problems @(
                "the sender had not settled within $TimeoutMs ms; nothing was sent" +
                $(if ($senderWaitError) { " ($senderWaitError)" } else { '' })
            )
        }

        # -- every bound repository agent must be settled ----------------
        $busy = @()
        foreach ($agent in $agents) {
            if (-not (Test-AgentSettled -Status (Get-AgentField $agent 'agent_status'))) {
                $busy += "$(Get-AgentField $agent 'pane_id')/$(Get-AgentField $agent 'name')=$(Get-AgentField $agent 'agent_status')"
            }
        }
        if ($busy.Count -gt 0) {
            Write-State -Root $Root -RequestId $requestId -State 'refused' -Extra @{
                reason = 'another repository agent is active'; busy = $busy
            } | Out-Null
            New-Failure -RequestId $requestId -Stage 'verify-peers' -Code $script:ExitNotReady -Problems @(
                "another repository agent is not idle: $($busy -join ', ')"
            )
        }

        # -- re-resolve the recipient immediately before delivery --------
        $recipient = Resolve-Party -Party $Request.recipient -Label 'recipient' -Agents $agents
        if (-not $recipient.ok) {
            Write-State -Root $Root -RequestId $requestId -State 'failed' -Extra @{
                reason = 'recipient identity'; problems = $recipient.problems
            } | Out-Null
            New-Failure -RequestId $requestId -Stage 'verify-recipient' -Code $script:ExitInvalid -Problems $recipient.problems
        }
        $recipientPane = $recipient.identity.pane_id
        # Read before anything is sent, so a later advance is attributable.
        $observationBefore = $recipient.identity.state_change_seq

        if ((Get-RemainingMs) -le 0) {
            Write-State -Root $Root -RequestId $requestId -State 'refused' -Extra @{
                reason = 'deadline expired before submission'
            } | Out-Null
            New-Failure -RequestId $requestId -Stage 'submit' -Code $script:ExitNotReady -Problems @(
                'the deadline expired before the prompt could be sent; nothing was sent'
            )
        }

        # -- submit ------------------------------------------------------
        Write-State -Root $Root -RequestId $requestId -State 'submitting' -Extra @{
            recipient_pane = $recipientPane; recipient_session = $recipient.identity.session_id
        } -Force | Out-Null

        try {
            $response = Invoke-Herdr -HerdrBin $herdr -AllowErrorEnvelope -Arguments @(
                'agent', 'prompt', $recipientPane, [string]$Request.prompt,
                '--wait', '--timeout', "$(Get-RemainingMs)"
            )
        } catch {
            # The call failed or was stopped at the deadline. That is not the
            # same as a failed delivery: `--wait` holds this budget for the
            # recipient's entire turn, so a recipient that simply works for
            # longer than the budget lands its prompt and then has the waiting
            # call killed out from under it. Filing that as an unexplained
            # 'submission outcome unknown' is what produced records a human had
            # to reconcile after deliveries that plainly succeeded.
            #
            # The recipient's own counter settles it. Advancing past the value
            # read before submission means a turn started, which only the
            # delivered prompt could have caused.
            $failure = "$_"
            $observedStatus = ''
            $observedSeq = ''
            try {
                $afterFailure = Get-BoundAgents -HerdrBin $herdr -Root $Root
                $observed = Resolve-Party -Party $Request.recipient -Label 'recipient' -Agents $afterFailure
                if ($observed.ok) {
                    $observedStatus = $observed.identity.status
                    $observedSeq = $observed.identity.state_change_seq
                }
            } catch { }

            $landed = Test-ObservationAdvanced -Before $observationBefore -After $observedSeq
            $problem = if ($landed) {
                "the prompt was delivered and the recipient began a turn (state_change_seq " +
                "'$observationBefore' -> '$observedSeq', now '$observedStatus'), but this relay's " +
                "budget expired before that turn finished: $failure"
            } else {
                "the prompt may or may not have been delivered: $failure"
            }

            Write-State -Root $Root -RequestId $requestId -State 'uncertain' -Extra @{
                reason = if ($landed) { 'delivered; recipient turn outlasted the relay budget' }
                         else { 'submission outcome unknown' }
                detail = $failure
                delivery_observed = $landed
                observation_before = $observationBefore; observation_after = $observedSeq
                recipient_status = $observedStatus
            } -Force | Out-Null
            Write-Result -Code $script:ExitUncertain -Result @{
                request_id = $requestId; stage = 'submit'; status = 'uncertain'
                delivered = $landed
                problems = @($problem)
                note = if ($landed) {
                    'Delivery is evidenced; only completion is unconfirmed. Do not resend: a resend would duplicate a prompt the recipient already has.'
                } else {
                    'Reconcile published outputs and herdr state before any resend. Do not retry automatically.'
                }
            }
        }

        # -- acknowledgment is not settlement (F3) -----------------------
        #
        # Two herdr outcomes are not the same and must not be filed the same way.
        # `agent_blocked` is rejected *before any input is sent*, so nothing was
        # delivered and there is nothing to reconcile. `agent_prompt_stalled`
        # means the submission was accepted but herdr did not observe a state
        # change inside its own 5000ms window, so the prompt may well have
        # landed; that is decided below from the recipient's own state, not from
        # the error code.
        $doubts = @()
        $herdrError = ''
        if (($response.PSObject.Properties.Name -contains 'error') -and $response.error) {
            $herdrError = Get-AgentField $response.error 'code'
            if (-not $herdrError) { $herdrError = ($response.error | ConvertTo-Json -Compress) }

            if ($herdrError -eq 'agent_blocked') {
                Write-State -Root $Root -RequestId $requestId -State 'refused' -Extra @{
                    reason = 'recipient blocked; herdr sent nothing'; detail = $herdrError
                } -Force | Out-Null
                New-Failure -RequestId $requestId -Stage 'submit' -Code $script:ExitNotReady -Problems @(
                    'the recipient is blocked, so herdr rejected the submission before sending any input; a human must clear the recipient. Nothing was delivered and nothing needs reconciling'
                )
            }
            # `timeout` is herdr's own wording for the same situation as
            # agent_prompt_stalled when --timeout is shorter than its 5000ms
            # observation window: the submission was accepted, the state change
            # was not seen. Both are decided below from the recipient's state.
            if (@('agent_prompt_stalled', 'timeout') -notcontains $herdrError) {
                $doubts += "herdr reported an error: $herdrError"
            }
        }

        $responseStatus = Get-ResponseAgentStatus -Response $response
        $envelopePresent = ($response.PSObject.Properties.Name -contains 'result') -and $response.result
        if (-not $envelopePresent -and -not $herdrError) {
            $doubts += 'the response carried no result envelope'
        }
        if ($responseStatus -and ($script:SettledResponseStatuses -notcontains $responseStatus)) {
            $doubts += "the response status '$responseStatus' acknowledges delivery but does not confirm the turn finished"
        }

        Write-State -Root $Root -RequestId $requestId -State 'acknowledged' -Extra @{
            recipient_pane = $recipientPane; response_status = $responseStatus
            herdr_error = $herdrError
        } -Force | Out-Null

        # The lock is still held: serialization runs through settlement, not
        # through submission. The recipient's own state is the authority here --
        # an envelope this relay cannot parse is a reason to look, not a verdict.
        $observationAfter = ''
        if ($doubts.Count -eq 0) {
            try {
                $after = Get-BoundAgents -HerdrBin $herdr -Root $Root
                $settled = Resolve-Party -Party $Request.recipient -Label 'recipient' -Agents $after
                if (-not $settled.ok) {
                    $doubts += "the recipient's identity changed after delivery: $($settled.problems -join '; ')"
                } else {
                    $observationAfter = $settled.identity.state_change_seq
                    if (-not (Test-AgentSettled -Status $settled.identity.status)) {
                        $doubts += "the recipient is '$($settled.identity.status)' after delivery, not idle or done"
                    } elseif (-not $responseStatus -and
                              -not (Test-ObservationAdvanced -Before $observationBefore -After $observationAfter)) {
                        # Settled, but nothing was observed to happen and the
                        # envelope confirmed nothing either. With
                        # agent_prompt_stalled that is exactly the case where the
                        # prompt may still be sitting unread.
                        $doubts += ("the recipient is '$($settled.identity.status)' but its state_change_seq " +
                                    "did not advance past '$observationBefore', so no turn was observed to run")
                    }
                }
            } catch {
                $doubts += "the recipient's state after delivery could not be confirmed: $_"
            }
        }

        if ($doubts.Count -gt 0) {
            Write-State -Root $Root -RequestId $requestId -State 'uncertain' -Extra @{
                reason = 'delivered but not confirmed settled'; problems = $doubts
                response_status = $responseStatus; herdr_error = $herdrError
                observation_before = $observationBefore; observation_after = $observationAfter
            } -Force | Out-Null
            Write-Result -Code $script:ExitUncertain -Result @{
                request_id = $requestId; stage = 'settle'; status = 'uncertain'; delivered = $false
                problems = $doubts
                note = 'The message may have been delivered. Reconcile before any resend; do not retry automatically.'
            }
        }

        Write-State -Root $Root -RequestId $requestId -State 'settled' -Extra @{
            recipient_pane = $recipientPane; recipient_session = $recipient.identity.session_id
            response_status = $responseStatus
            observation_before = $observationBefore; observation_after = $observationAfter
        } -Force | Out-Null

        Write-Result -Code $script:ExitOk -Result @{
            request_id = $requestId; stage = 'settle'; status = 'settled'
            delivered = $true; recipient_pane = $recipientPane
            recipient_role = [string]$Request.recipient.role
        }
    }
    finally {
        Close-HandoffLock -Lock $lock
    }
}

# --------------------------------------------------------------------------
# Entry
# --------------------------------------------------------------------------

if (-not (Test-Path -LiteralPath $RequestPath)) {
    New-Failure -RequestId '' -Stage 'load' -Code $script:ExitInvalid -Problems @(
        "request file '$RequestPath' does not exist"
    )
}
try { $request = Get-Content -LiteralPath $RequestPath -Raw | ConvertFrom-Json }
catch {
    New-Failure -RequestId '' -Stage 'load' -Code $script:ExitInvalid -Problems @(
        "request file '$RequestPath' is not readable JSON: $_"
    )
}

$problems = @(Test-HandoffRequest -Request $request -RequestFile $RequestPath)
$requestId = if ($request.PSObject.Properties.Name -contains 'request_id') {
    [string]$request.request_id
} else { '' }
if ($problems.Count -gt 0) {
    New-Failure -RequestId $requestId -Stage 'validate' -Code $script:ExitInvalid -Problems $problems
}

$repositoryRoot = (Resolve-Path -LiteralPath ([string]$request.repository_root)).Path
$resolvedRequest = (Resolve-Path -LiteralPath $RequestPath).Path

if ($ValidateOnly) {
    # Nothing is scheduled, locked, written, or sent.
    Write-Result -Code $script:ExitOk -Result @{
        request_id = $requestId; stage = 'validate'; status = 'valid'; delivered = $false
        recipient_role = [string]$request.recipient.role
        note = 'ValidateOnly: no relay was launched and no state was written.'
    }
}
if ($ExecuteRequest) {
    Invoke-Execute -Request $request -RequestFile $resolvedRequest -Root $repositoryRoot -TimeoutMs $TimeoutMs
}
Invoke-Schedule -Request $request -RequestFile $resolvedRequest -Root $repositoryRoot -TimeoutMs $TimeoutMs
