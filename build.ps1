param([ValidateSet('all','player','converter')][string]$Module='all')
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$workspaceRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$distRoot = [IO.Path]::GetFullPath((Join-Path $workspaceRoot 'dist'))
$buildRoot = [IO.Path]::GetFullPath((Join-Path $workspaceRoot 'build'))
if (-not $distRoot.StartsWith($workspaceRoot + [IO.Path]::DirectorySeparatorChar) -or -not $buildRoot.StartsWith($workspaceRoot + [IO.Path]::DirectorySeparatorChar)) {
    throw 'Build outputs must remain inside this workspace.'
}
if (-not (Test-Path -LiteralPath '.venv\Scripts\pyinstaller.exe')) {
    throw 'Run .venv\Scripts\python.exe -m pip install -e ".[dev,converter]" first.'
}
$targets = if ($Module -eq 'all') { @('player','converter') } else { @($Module) }
foreach ($target in $targets) {
    $env:REED_BUILD_TARGET=$target
    & '.\.venv\Scripts\python.exe' -m PyInstaller --noconfirm --distpath $distRoot --workpath $buildRoot 'packaging\windows.spec'
    if ($LASTEXITCODE -ne 0) { throw "Build failed: $target" }
}
Remove-Item Env:REED_BUILD_TARGET -ErrorAction SilentlyContinue
Write-Host 'Portable applications are in dist. Keep each executable with its _internal directory.'
