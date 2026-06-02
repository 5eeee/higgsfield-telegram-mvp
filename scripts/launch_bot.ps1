#Requires -Version 5.1
<#
  One-click: read Windows proxy (WinHTTP / IE), set HTTPS_PROXY for child, ensure venv + deps, run bot.
  Double-click Start-Bot.bat in repo root, or: powershell -File scripts\launch_bot.ps1
#>
param()

$ErrorActionPreference = 'Stop'
$RepoRoot = (Get-Item $PSScriptRoot).Parent.FullName
Set-Location -LiteralPath $RepoRoot

function Write-LaunchInfo([string]$Message) {
    Write-Host "[EarthZoomBot] $Message" -ForegroundColor Cyan
}

function Write-LaunchWarn([string]$Message) {
    Write-Host "[EarthZoomBot] $Message" -ForegroundColor Yellow
}

function Write-LaunchErr([string]$Message) {
    Write-Host "[EarthZoomBot] $Message" -ForegroundColor Red
}

function Apply-WindowsProxyEnv {
    if ($env:HTTPS_PROXY -or $env:HTTP_PROXY -or $env:TELEGRAM_PROXY) {
        Write-LaunchInfo 'Proxy already set in environment (HTTPS_PROXY / ...); not overwriting.'
        return
    }

    $applied = $false
    $winhttpLines = @(netsh winhttp show proxy 2>$null)
    foreach ($line in $winhttpLines) {
        if ($line -match 'Proxy Server\(s\)\s*:\s*(.+)') {
            $srv = $matches[1].Trim()
            if ($srv -and $srv -notmatch 'no proxy|direct') {
                $sl = $srv.ToLowerInvariant()
                if (-not ($sl.StartsWith('http://') -or $sl.StartsWith('https://') -or $sl.StartsWith('socks5://'))) {
                    $srv = 'http://' + $srv
                }
                $env:HTTPS_PROXY = $srv
                $env:HTTP_PROXY = $srv
                Write-LaunchInfo ('WinHTTP -> HTTPS_PROXY=' + $srv)
                $applied = $true
                break
            }
        }
    }
    if ($applied) { return }

    try {
        $p = Get-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction Stop
        if ($p.ProxyEnable -eq 1 -and $p.ProxyServer) {
            $s = [string]$p.ProxyServer.Trim()
            $srv = $null
            foreach ($part in ($s -split ';')) {
                $part = $part.Trim()
                $low = $part.ToLowerInvariant()
                if ($low.StartsWith('https=')) {
                    $srv = 'http://' + $part.Substring(6).Trim()
                    break
                }
                if ($low.StartsWith('http=')) {
                    $srv = 'http://' + $part.Substring(5).Trim()
                    break
                }
                if ($low.StartsWith('socks=')) {
                    $srv = 'socks5://' + $part.Substring(6).Trim()
                    break
                }
            }
            if (-not $srv -and $s.Contains(':') -and -not $s.Contains('=')) {
                $t = $s.Trim()
                $tl = $t.ToLowerInvariant()
                if ($tl.StartsWith('http://') -or $tl.StartsWith('https://') -or $tl.StartsWith('socks5://')) {
                    $srv = $t
                }
                else {
                    $srv = 'http://' + $t
                }
            }
            if ($srv) {
                while ($srv.ToLowerInvariant().StartsWith('http://http://')) {
                    $srv = $srv.Substring(7)
                }
                $env:HTTPS_PROXY = $srv
                $env:HTTP_PROXY = $srv
                Write-LaunchInfo ('IE/LAN -> HTTPS_PROXY=' + $srv)
            }
        }
    }
    catch {
    }

    if (-not ($env:HTTPS_PROXY -or $env:HTTP_PROXY)) {
        Write-LaunchInfo 'No Windows system proxy found; bot will try direct HTTPS + local port autodetect.'
    }
}

function Test-ProxyUrlTcpOpen {
    param([Parameter(Mandatory)][string]$ProxyUrl)
    try {
        $uri = [System.Uri]$ProxyUrl
    }
    catch {
        return $false
    }
    $h = $uri.Host
    $port = $uri.Port
    if ($port -lt 1) {
        if ($uri.Scheme -eq 'socks5' -or $uri.Scheme -eq 'socks') { $port = 1080 }
        else { $port = 80 }
    }
    $c = $null
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $a = $c.BeginConnect($h, $port, $null, $null)
        if (-not $a.AsyncWaitHandle.WaitOne(2000)) {
            $c.Close()
            return $false
        }
        $c.EndConnect($a)
        $c.Close()
        return $true
    }
    catch {
        if ($null -ne $c) { try { $c.Close() } catch { } }
        return $false
    }
}

function Clear-DeadLocalProxyForSession {
    $url = $env:HTTPS_PROXY
    if (-not $url) { $url = $env:HTTP_PROXY }
    if (-not $url) { return }
    try {
        $u = [System.Uri]$url
    }
    catch { return }
    $hn = $u.Host.ToLowerInvariant()
    if ($hn -ne '127.0.0.1' -and $hn -ne 'localhost' -and $hn -ne '[::1]') { return }
    if (Test-ProxyUrlTcpOpen -ProxyUrl $url) { return }
    Write-LaunchWarn ('Local proxy in env is not listening (dropped or offline): ' + $url)
    Write-LaunchWarn 'Cleared HTTPS_PROXY/HTTP_PROXY for this run. Bot will use direct HTTPS + in-code autodetect (or set TELEGRAM_PROXY in .env).'
    Remove-Item env:HTTPS_PROXY -ErrorAction SilentlyContinue
    Remove-Item env:HTTP_PROXY -ErrorAction SilentlyContinue
    Remove-Item env:ALL_PROXY -ErrorAction SilentlyContinue
}

function Ensure-DotEnv {
    $envFile = Join-Path $RepoRoot '.env'
    $example = Join-Path $RepoRoot '.env.example'
    if (-not (Test-Path -LiteralPath $envFile)) {
        if (Test-Path -LiteralPath $example) {
            Copy-Item -LiteralPath $example -Destination $envFile
            Write-LaunchWarn 'Created .env from .env.example — fill TELEGRAM_BOT_TOKEN and Higgsfield keys, save, run Start-Bot.bat again.'
            Read-Host 'Press Enter to open .env in Notepad'
            notepad $envFile
            exit 1
        }
        Write-LaunchErr 'Missing .env and .env.example'
        Read-Host 'Press Enter'
        exit 1
    }
}

function Install-RequirementsWithProxyFallback {
    param(
        [Parameter(Mandatory)][string]$PipExe,
        [Parameter(Mandatory)][string]$ReqPath
    )
    & $PipExe install -r $ReqPath
    if ($LASTEXITCODE -ne 0) {
        Write-LaunchWarn 'pip failed with current proxy; retrying without HTTPS_PROXY/HTTP_PROXY.'
        Remove-Item env:HTTPS_PROXY -ErrorAction SilentlyContinue
        Remove-Item env:HTTP_PROXY -ErrorAction SilentlyContinue
        Remove-Item env:ALL_PROXY -ErrorAction SilentlyContinue
        & $PipExe install -r $ReqPath
    }
    return [int]$LASTEXITCODE
}

Apply-WindowsProxyEnv
Clear-DeadLocalProxyForSession
Ensure-DotEnv

$venvPy = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPy)) {
    Write-LaunchWarn 'First run: creating .venv and installing requirements...'
    $venvParent = Join-Path $RepoRoot '.venv'
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $venvParent 2>&1 | Out-Null
    }
    elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv $venvParent 2>&1 | Out-Null
    }
    else {
        Write-LaunchErr 'Need python or py on PATH to create .venv'
        Read-Host 'Press Enter'
        exit 1
    }
    if (-not (Test-Path -LiteralPath $venvPy)) {
        Write-LaunchErr 'Failed to create .venv'
        Read-Host 'Press Enter'
        exit 1
    }
    $pip = Join-Path $RepoRoot '.venv\Scripts\pip.exe'
    $req = Join-Path $RepoRoot 'requirements.txt'
    $pipExit = Install-RequirementsWithProxyFallback -PipExe $pip -ReqPath $req
    if ($pipExit -ne 0) {
        Write-LaunchErr 'pip install failed'
        Read-Host 'Press Enter'
        exit 1
    }
}

if (-not (Test-Path -LiteralPath $venvPy)) {
    Write-LaunchErr 'Missing .venv\Scripts\python.exe'
    Read-Host 'Press Enter'
    exit 1
}

$pythonExe = $venvPy
$pip = Join-Path $RepoRoot '.venv\Scripts\pip.exe'
$req = Join-Path $RepoRoot 'requirements.txt'

& $pythonExe -c 'import aiohttp, aiogram, imageio; from PIL import Image' 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-LaunchWarn 'Python packages missing or incomplete; pip install -r requirements.txt ...'
    $pipExit = Install-RequirementsWithProxyFallback -PipExe $pip -ReqPath $req
    if ($pipExit -ne 0) {
        Write-LaunchErr 'pip install failed — check network, then run Start-Bot.bat again.'
        Read-Host 'Press Enter'
        exit 1
    }
}

Write-LaunchInfo ('Repo: ' + $RepoRoot)
Write-LaunchInfo ('Python: ' + $pythonExe)
Write-LaunchInfo 'Starting: python -m src.bot'
Write-Host ''

& $pythonExe -m src.bot

$code = $LASTEXITCODE
if ($code -ne 0) {
    Write-LaunchErr ('Process exited with code ' + $code)
    Read-Host 'Press Enter'
}
exit $code
