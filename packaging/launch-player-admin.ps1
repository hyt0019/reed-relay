$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$sourcePlayer = Join-Path $taskRoot '.venv\Scripts\pythonw.exe'
$portablePlayer = Join-Path $taskRoot 'dist\ReedRelay-Player\ReedRelay-Player.exe'
try {
    # Close the existing player first so its global hotkeys are released.
    if (Test-Path -LiteralPath $sourcePlayer) {
        Start-Process -FilePath $sourcePlayer -ArgumentList @('-m', 'reed_relay.app') -WorkingDirectory $taskRoot -Verb RunAs -WindowStyle Hidden
    } elseif (Test-Path -LiteralPath $portablePlayer) {
        Start-Process -FilePath $portablePlayer -WorkingDirectory $taskRoot -Verb RunAs -WindowStyle Hidden
    } else {
        throw 'Run setup.ps1 first, or place the portable Player under dist/ReedRelay-Player.'
    }
} catch {
    Write-Error "Could not start the administrator Player. Close the existing Player and approve the Windows prompt. $($_.Exception.Message)"
    exit 1
}
