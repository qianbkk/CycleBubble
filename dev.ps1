# ============================================================================
#   CycleBubble 本地一键启停 — PowerShell 核心
#   File encoding: UTF-8 with BOM (so PowerShell reads CJK correctly
#                   even when called from a cmd that hasn't done chcp 65001)
#   Platform:  Windows 10/11 + PowerShell 5.1+
#   Companion: dev.bat — thin wrapper that launches this file.
#
#   Known small issue: PID file writes occasionally fail on Windows when
#   python's redirected stdout/stderr is still releasing handles to the same
#   directory.  symptom = status reads 'foreign' immediately after start,
#   but the actual processes are listening and stop() still works (it uses
#   port lookup, not the pid file).  work-around if bothersome: re-run
#   `dev.bat stop` then `dev.bat start` again.
# ============================================================================

$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# --- Config --------------------------------------------------------------
$ScriptDir         = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot       = $ScriptDir
$BackendDir        = Join-Path $ProjectRoot 'backend'
$FrontendDir       = $ProjectRoot
$BackendHost       = '127.0.0.1'
$BackendPort       = 8765
$FrontendHost      = '127.0.0.1'
$FrontendPort      = 8766
$LogDir            = Join-Path $ProjectRoot '.runlogs'
$BackendPidFile    = Join-Path $LogDir 'backend.pid'
$FrontendPidFile   = Join-Path $LogDir 'frontend.pid'
$BackendOutFile    = Join-Path $LogDir 'backend.out.log'
$BackendErrFile    = Join-Path $LogDir 'backend.err.log'
$FrontendOutFile   = Join-Path $LogDir 'frontend.out.log'
$FrontendErrFile   = Join-Path $LogDir 'frontend.err.log'
$CbJwtSecret       = 'dev-local-secret-not-for-prod'
$CbCorsOrigins     = "http://localhost:$FrontendPort,http://127.0.0.1:$FrontendPort"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# --- ANSI color helpers --------------------------------------------------
function Write-Banner {
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host '   CycleBubble 本地开发'                                   -ForegroundColor Cyan
    Write-Host '============================================================' -ForegroundColor Cyan
    Write-Host ("   Backend  : http://{0}:{1}  (uvicorn)"   -f $BackendHost,  $BackendPort)
    Write-Host ("   Frontend : http://{0}:{1}  (python -m http.server)" -f $FrontendHost, $FrontendPort)
    Write-Host ("   API docs : http://{0}:{1}/docs"           -f $BackendHost,  $BackendPort)
    Write-Host ("   Logs dir : {0}"                            -f $LogDir)
    Write-Host '------------------------------------------------------------' -ForegroundColor Cyan
}

# Return @([int[]] $pids) of anything LISTENING on $port (IPv4 + IPv6).
function Get-PidsOnPort {
    param([int]$Port)
    $listeners = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    $pids = @()
    if ($listeners) {
        $pids = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
    }
    return ,$pids
}

function Read-PidFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return @() }
    $pids = @()
    foreach ($line in (Get-Content $Path)) {
        $line = $line.Trim()
        if ($line -match '^\d+$') { $pids += [int]$line }
    }
    return $pids
}

function Write-PidFile {
    param([int]$ProcessId, [string]$Path)
    $dir = Split-Path -Parent $Path
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    # Try Set-Content first; fall back to direct .NET write if PowerShell's
    # stream layer swallows the IO.  Either way, never throw — stop() uses
    # port lookup so a missing pid file is non-fatal (state just reads 'foreign').
    try {
        Set-Content -Path $Path -Value "$ProcessId" -Encoding ascii -Force
        return $true
    } catch {
        try {
            [System.IO.File]::WriteAllText($Path, "$ProcessId`n", [System.Text.Encoding]::ASCII)
            return $true
        } catch {
            return $false
        }
    }
}

function Remove-PidFile {
    param([string]$Path)
    if (Test-Path $Path) { Remove-Item -Path $Path -Force }
}

function Kill-Pid {
    param([int]$Pid)
    $proc = Get-Process -Id $Pid -ErrorAction SilentlyContinue
    if ($proc) {
        try { Stop-Process -Id $Pid -Force -ErrorAction Stop } catch { }
    }
}

# Compute state: 'running' (our PID on port) | 'foreign' (port busy but not by us) | 'stopped'
function Get-ServiceState {
    param([int]$Port, [string]$PidFile, [string]$Label)
    $portPids  = Get-PidsOnPort -Port $Port
    $ownPids   = Read-PidFile -Path $PidFile
    if ($ownPids.Count -eq 0) {
        if ($portPids.Count -gt 0) {
            return @{ State='foreign'; Pids=$portPids }
        } else {
            return @{ State='stopped'; Pids=@() }
        }
    }
    foreach ($op in $ownPids) {
        if ($portPids -contains $op) {
            return @{ State='running'; Pids=$portPids }
        }
    }
    # our recorded PIDs do not match anyone on the port — PID file stale
    Remove-PidFile -Path $PidFile
    if ($portPids.Count -gt 0) {
        return @{ State='foreign'; Pids=$portPids }
    } else {
        return @{ State='stopped'; Pids=@() }
    }
}

function Print-State {
    param([string]$Label, [hashtable]$S)
    $color = switch ($S.State) {
        'running' { 'Green'  }
        'foreign' { 'Yellow' }
        'stopped' { 'Gray'   }
    }
    $pidsStr = ''
    if ($S.State -eq 'running') { $pidsStr = ($S.Pids -join ' ') }
    elseif ($S.State -eq 'foreign') { $pidsStr = (($S.Pids -join ' ') + '  (not started by dev.bat)') }
    $port = if ($Label -eq 'backend') { $BackendPort } else { $FrontendPort }
    Write-Host ("   {0,-9}: {1}    " -f $Label, $port) -NoNewline
    Write-Host ("{0,-8}" -f $S.State) -ForegroundColor $color -NoNewline
    Write-Host (" PIDs: {0}" -f $pidsStr)
}

function Http-Probe {
    param([string]$Label, [string]$Url)
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        $code = $resp.StatusCode
        $ok   = ($code -lt 400)
    } catch {
        $resp = $_.Exception.Response
        if ($resp -and $resp.StatusCode) {
            $code = [int]$resp.StatusCode
        } else {
            $code = 'err'
        }
        $ok = $false
    }
    if ($ok) {
        Write-Host ("   {0,-22}" -f $Label) -NoNewline
        Write-Host 'UP    ' -ForegroundColor Green -NoNewline
        Write-Host ("http {0}" -f $code)
    } else {
        Write-Host ("   {0,-22}" -f $Label) -NoNewline
        Write-Host 'DOWN  ' -ForegroundColor Gray -NoNewline
        Write-Host ("http {0}" -f $code)
    }
}

function Show-Status {
    Write-Banner
    $be = Get-ServiceState -Port $BackendPort  -PidFile $BackendPidFile  -Label 'backend'
    Print-State 'backend'  $be
    $fe = Get-ServiceState -Port $FrontendPort -PidFile $FrontendPidFile -Label 'frontend'
    Print-State 'frontend' $fe
    Write-Host '------------------------------------------------------------' -ForegroundColor Gray
    Write-Host '[HTTP probe]'                                            -ForegroundColor Cyan
    Http-Probe 'backend /health   ' ("http://{0}:{1}/health" -f $BackendHost,  $BackendPort)
    Http-Probe 'backend /docs     ' ("http://{0}:{1}/docs"   -f $BackendHost,  $BackendPort)
    Http-Probe 'frontend /        ' ("http://{0}:{1}/"       -f $FrontendHost, $FrontendPort)
    Write-Host '------------------------------------------------------------' -ForegroundColor Gray
    Write-Host ''
}

function Start-One {
    param(
        [string]$Label,
        [string]$WorkingDir,
        [string[]]$CommandArgs,
        [string]$PidFile,
        [string]$OutFile,
        [string]$ErrFile,
        [hashtable]$ExtraEnv
    )
    $portPids = Get-PidsOnPort -Port ($ExtraEnv.Port)
    if ($portPids.Count -gt 0) {
        Write-Host ("{0} :{1} 端口已被占用,PID: {2}" -f $Label, $ExtraEnv.Port, ($portPids -join ' ')) -ForegroundColor Yellow
        Write-Host '   跳过启动。如需重启请先 stop 或手动 taskkill。'
        return
    }
    Write-Host ("[start] {0}  ...  > {1}, 2> {2}" -f $Label, $OutFile, $ErrFile) -ForegroundColor Cyan
    try {
        # Start-Process with -PassThru returns a Process object whose .Id is the
        # child PID we can later kill.  WorkingDirectory + redirects make the
        # child fully detached from this shell.
        $proc = Start-Process -FilePath 'python.exe' `
                              -ArgumentList $CommandArgs `
                              -WorkingDirectory $WorkingDir `
                              -RedirectStandardOutput $OutFile `
                              -RedirectStandardError  $ErrFile `
                              -WindowStyle Hidden `
                              -PassThru
        Write-Host ("   {0}  spawned PID {1}" -f $Label, $proc.Id) -ForegroundColor Gray
    } catch {
        Write-Host ("  {0}  Start-Process FAILED: {1}" -f $Label, $_.Exception.Message) -ForegroundColor Red
        return
    }

    # Best-effort: push env vars onto the child process.  Not strictly needed
    # because they're inherited from parent shell, but useful if user has
    # different values in scope.
    foreach ($k in $ExtraEnv.Keys) {
        if ($k -eq 'Port') { continue }
        try { [Environment]::SetEnvironmentVariable($k, $ExtraEnv[$k], 'Process') } catch { }
    }

    # Write pid file LAST so a half-started service never has a stale pid entry.
    # Note: param is $ProcessId because $PID/$Pid is reserved in PowerShell.
    # If the write fails (rare, depends on PowerShell stream state), status()
    # will report 'foreign' instead of 'running' — stop() uses port lookup so
    # the script still works.
    $pidWritten = Write-PidFile -ProcessId $proc.Id -Path $PidFile
    if ($pidWritten) {
        Write-Host ("{0}  started, PID {1}" -f $Label, $proc.Id) -ForegroundColor Green
    } else {
        Write-Host ("{0}  started, PID {1}  (pid file not written; status will show 'foreign')" -f $Label, $proc.Id) -ForegroundColor Yellow
    }
}

function Stop-One {
    param([string]$Label, [int]$Port, [string]$PidFile)
    # Always kill whatever is listening on $Port.  PID file is a hint we read
    # FIRST, but if it's missing or stale we still recover via the port lookup,
    # which is the durable source of truth.
    $ownPids = Read-PidFile -Path $PidFile
    $portPids = Get-PidsOnPort -Port $Port
    $targets = @($portPids | Sort-Object -Unique)
    if ($targets.Count -eq 0 -and $ownPids.Count -eq 0) {
        Write-Host ("{0}  :{1} already stopped" -f $Label, $Port) -ForegroundColor Gray
        return
    }
    foreach ($p in $targets) {
        try { Stop-Process -Id $p -Force -ErrorAction Stop } catch { }
    }
    # Also kill any stale PIDs from the file (process may have died but file
    # remained).  Don't fail if they're already gone.
    foreach ($p in $ownPids) {
        if ($targets -notcontains $p) {
            try { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } catch { }
        }
    }
    Remove-PidFile -Path $PidFile
    Write-Host ("{0}  stopped (port {1}, killed {2} process(es))" -f $Label, $Port, $targets.Count) -ForegroundColor Green
}

# --- Actions -------------------------------------------------------------
function Action-Start {
    Start-One -Label 'backend'  -WorkingDir $BackendDir  -CommandArgs @('-m','uvicorn','main:app','--host',$BackendHost,'--port',[string]$BackendPort) `
              -PidFile $BackendPidFile  -OutFile $BackendOutFile  -ErrFile $BackendErrFile `
              -ExtraEnv @{ Port=$BackendPort; CB_JWT_SECRET=$CbJwtSecret; CB_CORS_ORIGINS=$CbCorsOrigins }
    Start-One -Label 'frontend' -WorkingDir $FrontendDir -CommandArgs @('-m','http.server',[string]$FrontendPort,'--bind',$FrontendHost) `
              -PidFile $FrontendPidFile -OutFile $FrontendOutFile -ErrFile $FrontendErrFile `
              -ExtraEnv @{ Port=$FrontendPort }
    Write-Host ''
    Show-Status
}

function Action-Stop {
    Stop-One 'backend'  -Port $BackendPort  -PidFile $BackendPidFile
    Stop-One 'frontend' -Port $FrontendPort -PidFile $FrontendPidFile
    Write-Host ''
    Show-Status
}

function Action-Restart {
    Action-Stop
    Write-Host ''
    Write-Host 'wait 1.5s before restart ...' -ForegroundColor Cyan
    Start-Sleep -Seconds 1.5
    Action-Start
}

# --- Dispatch ------------------------------------------------------------
$action = if ($args.Count -gt 0) { $args[0] } else { '' }
switch -Regex ($action) {
    '^start$'   { Action-Start;   return }
    '^stop$'    { Action-Stop;    return }
    '^restart$' { Action-Restart; return }
    '^status$'  { Show-Status;    return }
    '^help$'    {
        Write-Host ''
        Write-Host 'Usage: dev.bat [start|stop|restart|status|help]'
        Write-Host '   no arg     interactive menu (start/stop/restart/status/exit)'
        Write-Host '   start      后端 + 前端一起拉起'
        Write-Host '   stop       一起关停'
        Write-Host '   restart    stop 后再 start'
        Write-Host '   status     端口 + PID + HTTP 健康'
        Write-Host ''
        return
    }
    '^$' {
        # interactive menu
        while ($true) {
            Write-Banner
            Write-Host ''
            Write-Host 'Choose action:' -ForegroundColor Yellow
            Write-Host '   1) start BOTH'
            Write-Host '   2) stop BOTH'
            Write-Host '   3) restart BOTH'
            Write-Host '   0) status'
            Write-Host '   9) exit'
            Write-Host ''
            $choice = Read-Host '  Your choice [0-3, 9]'
            switch ($choice) {
                '1' { Action-Start;   pause; continue }
                '2' { Action-Stop;    pause; continue }
                '3' { Action-Restart; pause; continue }
                '0' { Show-Status;    pause; continue }
                '9' { return }
                default { Write-Host ("unknown choice '{0}'" -f $choice) -ForegroundColor Red }
            }
        }
    }
    default {
        Write-Host ("unknown subcommand: {0}" -f $action) -ForegroundColor Red
        Write-Host 'try: dev.bat help'
    }
}
