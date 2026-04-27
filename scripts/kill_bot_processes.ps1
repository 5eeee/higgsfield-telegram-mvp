# Stops python.exe processes whose command line references this bot (polling conflict fix).
$ErrorActionPreference = 'SilentlyContinue'
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | ForEach-Object {
    $line = $_.CommandLine
    if (-not $line) { return }
    if ($line -match 'src\.bot' -or $line -match 'higgsfield-telegram-mvp') {
        Write-Host "Stopping PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force
    }
}
