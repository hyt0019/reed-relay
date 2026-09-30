$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$taskRoot = $PWD.Path
New-Item -ItemType Directory -Force 'output\smoke' | Out-Null
& '.\.venv\Scripts\python.exe' -c "from pathlib import Path; from reed_relay.core.score import Score; from reed_relay.converter.audio import synthesize; synthesize(Score.load(next(Path('examples').glob('*.reedscore.json'))), 'output/smoke/calibration.wav')"
if ($LASTEXITCODE -ne 0) { throw 'Could not create the original calibration audio.' }
$savedEnvironment = @{}
foreach ($key in @('QT_QPA_PLATFORM','QT_QUICK_BACKEND','REED_RELAY_DATA_DIR','PYTHONPATH')) {
    $savedEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
}
function Invoke-SmokeApp([string]$Executable, [string[]]$Arguments) {
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(60000)) {
        Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
        throw "Smoke test timed out: $Executable"
    }
    if ($process.ExitCode -ne 0) { throw "Smoke test failed ($($process.ExitCode)): $Executable. Check output/smoke and local-data/smoke logs." }
}
try {
    $env:QT_QPA_PLATFORM='offscreen'
    $env:QT_QUICK_BACKEND='software'
    $env:REED_RELAY_DATA_DIR=Join-Path $taskRoot 'local-data\smoke'
    $env:PYTHONPATH=''
    Invoke-SmokeApp '.\dist\ReedRelay-Player\ReedRelay-Player.exe' @('--demo','--screenshot','output/smoke/player.png')
    Invoke-SmokeApp '.\dist\ReedRelay-Player\ReedRelay-Player.exe' @('--page','settings','--screenshot','output/smoke/tuning.png')
    Invoke-SmokeApp '.\dist\ReedRelay-Player\ReedRelay-Player.exe' @('--overlay-demo','--screenshot','output/smoke/calibration-overlay.png')
    Invoke-SmokeApp '.\dist\ReedRelay-Converter\ReedRelay-Converter.exe' @('--transcribe','output/smoke/calibration.wav','--output','output/smoke/score.json')
    $score = Get-Content 'output\smoke\score.json' -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($score.notes.Count -lt 8 -or $score.duration_ms -lt 6000) { throw 'Incomplete transcription in frozen converter.' }
    Invoke-SmokeApp '.\dist\ReedRelay-Converter\ReedRelay-Converter.exe' @('--score','output/smoke/score.json','--screenshot','output/smoke/converter.png')
    Invoke-SmokeApp '.\dist\ReedRelay-Converter\ReedRelay-Converter.exe' @('--overlay-demo','--screenshot','output/smoke/converter-overlay.png')
    foreach ($path in @('player.png','tuning.png','converter.png','calibration-overlay.png','converter-overlay.png')) {
        if ((Get-Item (Join-Path 'output\smoke' $path)).Length -lt 10000) { throw "Invalid screenshot: $path" }
    }
    Write-Output "Both portable applications passed. Transcription: $($score.notes.Count) notes. Captures: output/smoke."
} finally {
    foreach ($key in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($key, $savedEnvironment[$key], 'Process')
    }
}
