$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$taskRoot = $PWD.Path
New-Item -ItemType Directory -Force 'output\smoke' | Out-Null
& '.\.venv\Scripts\python.exe' -c "from pathlib import Path; from reed_relay.core.score import Score; from reed_relay.converter.audio import synthesize; synthesize(Score.load(next(Path('examples').glob('*.reedscore.json'))), 'output/smoke/calibration.wav')"
if ($LASTEXITCODE -ne 0) { throw 'Could not create the original calibration audio.' }
& '.\.venv\Scripts\python.exe' -c "from reed_relay.core.score import Score,Note; ns=[Note(0,200,60),Note(200,12,84),Note(225,200,62)]; Score('Repair test',ns,6600,original_notes=ns).save('output/smoke/fragmented.json')"
if ($LASTEXITCODE -ne 0) { throw 'Could not create fragment test score.' }
& '.\.venv\Scripts\python.exe' -c "from reed_relay.core.score import Score,Note; ns=[Note(0,800,36),Note(0,400,60,cents=100/3),Note(400,400,62)]; meta={'engine':'Spotify Basic Pitch 0.4.0 / ONNX','pitch_bends_third_semitone':{ns[1].id:[1,1]}}; Score('Melody test',[ns[0]],800,original_notes=ns,metadata=meta).save('output/smoke/melody.json')"
if ($LASTEXITCODE -ne 0) { throw 'Could not create melody test score.' }
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
    Invoke-SmokeApp '.\dist\ReedRelay-Player\ReedRelay-Player.exe' @('--page','settings','--screenshot','output/smoke/settings.png')
    Invoke-SmokeApp '.\dist\ReedRelay-Player\ReedRelay-Player.exe' @('--page','storage','--screenshot','output/smoke/storage.png')
    Invoke-SmokeApp '.\dist\ReedRelay-Player\ReedRelay-Player.exe' @('--demo','--page','audition','--screenshot','output/smoke/audition.png')
    Invoke-SmokeApp '.\dist\ReedRelay-Player\ReedRelay-Player.exe' @('--page','settings','--binding-demo','--screenshot','output/smoke/binding.png')
    Invoke-SmokeApp '.\dist\ReedRelay-Converter\ReedRelay-Converter.exe' @('--transcribe','output/smoke/calibration.wav','--output','output/smoke/score.json')
    $score = Get-Content 'output\smoke\score.json' -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($score.notes.Count -lt 8 -or $score.duration_ms -lt 6000) { throw 'Incomplete transcription in frozen converter.' }
    Invoke-SmokeApp '.\dist\ReedRelay-Converter\ReedRelay-Converter.exe' @('--score','output/smoke/score.json','--screenshot','output/smoke/converter.png')
    Invoke-SmokeApp '.\dist\ReedRelay-Converter\ReedRelay-Converter.exe' @('--score','output/smoke/score.json','--page','audition','--screenshot','output/smoke/converter-audition.png')
    Invoke-SmokeApp '.\dist\ReedRelay-Player\ReedRelay-Player.exe' @('--demo','--page','audition','--audition-demo','--screenshot','output/smoke/player-transport.png')
    Invoke-SmokeApp '.\dist\ReedRelay-Converter\ReedRelay-Converter.exe' @('--demo','--page','audition','--audition-demo','--screenshot','output/smoke/converter-transport.png')
    Invoke-SmokeApp '.\dist\ReedRelay-Player\ReedRelay-Player.exe' @('--render-audition','output/smoke/score.json','--output','output/smoke/player-harmonica.wav','--audition-speed','1.25')
    Invoke-SmokeApp '.\dist\ReedRelay-Converter\ReedRelay-Converter.exe' @('--render-audition','output/smoke/score.json','--output','output/smoke/converter-harmonica.wav','--audition-mode','game')
    Invoke-SmokeApp '.\dist\ReedRelay-Player\ReedRelay-Player.exe' @('--repair-score','output/smoke/fragmented.json','--output','output/smoke/player-repaired.json')
    Invoke-SmokeApp '.\dist\ReedRelay-Converter\ReedRelay-Converter.exe' @('--repair-score','output/smoke/fragmented.json','--output','output/smoke/converter-repaired.json')
    Invoke-SmokeApp '.\dist\ReedRelay-Player\ReedRelay-Player.exe' @('--extract-score','output/smoke/melody.json','--minimum-pitch','60','--maximum-pitch','72','--output','output/smoke/player-melody.json')
    Invoke-SmokeApp '.\dist\ReedRelay-Converter\ReedRelay-Converter.exe' @('--extract-score','output/smoke/melody.json','--minimum-pitch','60','--maximum-pitch','72','--output','output/smoke/converter-melody.json')
    foreach ($melodyPath in @('player-melody.json','converter-melody.json')) {
        $melody = Get-Content (Join-Path 'output\smoke' $melodyPath) -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($melody.notes.Count -ne 2 -or $melody.notes[0].midi_pitch -ne 60 -or $melody.notes[1].midi_pitch -ne 62 -or $melody.notes[0].cents -ne 0 -or $melody.original_notes.Count -ne 3 -or $melody.original_notes[1].cents -lt 33 -or $melody.duration_ms -ne 800) { throw "Invalid melody extraction: $melodyPath" }
    }
    foreach ($repairedPath in @('player-repaired.json','converter-repaired.json')) {
        $repaired = Get-Content (Join-Path 'output\smoke' $repairedPath) -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($repaired.notes.Count -ne 2 -or $repaired.original_notes.Count -ne 3 -or $repaired.duration_ms -ne 6600 -or $repaired.notes[1].start_ms -ne 225) { throw "Invalid fragment repair: $repairedPath" }
    }
    foreach ($path in @('player.png','settings.png','storage.png','audition.png','binding.png','converter.png','converter-audition.png','player-transport.png','converter-transport.png')) {
        if ((Get-Item (Join-Path 'output\smoke' $path)).Length -lt 10000) { throw "Invalid screenshot: $path" }
    }
    & '.\.venv\Scripts\python.exe' -c "import wave,numpy as np; from pathlib import Path; files=[Path('output/smoke/player-harmonica.wav'),Path('output/smoke/converter-harmonica.wav')]; [None for p in files if p.stat().st_size>10000]; readers=[wave.open(str(p)) for p in files]; lengths=[r.getnframes()/r.getframerate() for r in readers]; samples=[np.frombuffer(r.readframes(r.getnframes()),dtype='<i2') for r in readers]; assert abs(lengths[0]*1.25-lengths[1])<.01; assert all(np.max(np.abs(x.astype(float)))>100 for x in samples); [r.close() for r in readers]; print('Frozen audition WAVs: valid duration and non-silent samples')"
    if ($LASTEXITCODE -ne 0) { throw 'Frozen harmonica audition verification failed.' }
    Write-Output "Both portable applications passed. Transcription: $($score.notes.Count) notes. Captures: output/smoke."
} finally {
    foreach ($key in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($key, $savedEnvironment[$key], 'Process')
    }
}
