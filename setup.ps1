param(
    [ValidateSet('all','player','converter')][string]$Module = 'all',
    [string]$PythonPath = 'python',
    [string]$Proxy = ''
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    & $PythonPath -c "import sys; assert (3,10) <= sys.version_info[:2] < (3,14), 'Use Python 3.10-3.13 (3.12 recommended). Pass -PythonPath to its python.exe.'"
    if ($LASTEXITCODE -ne 0) { throw 'A compatible Python installation is required.' }
    & $PythonPath -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
}
$pipOptions = @()
if ($Proxy) { $pipOptions += @('--proxy', $Proxy) }
$package = if ($Module -eq 'player') { '.' } else { '.[converter]' }
& '.\.venv\Scripts\python.exe' -m pip install @pipOptions -e $package
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if ($Module -ne 'player') {
    # Basic Pitch's wheel declares TensorFlow even when using its bundled ONNX model.
    # The converter extra above explicitly installs its ONNX and audio dependencies.
    & '.\.venv\Scripts\python.exe' -m pip install @pipOptions --no-deps 'basic-pitch==0.4.0'
    if ($LASTEXITCODE -ne 0) { throw 'Basic Pitch installation failed.' }
}
Write-Host 'Ready. Launch with reed-player / reed-converter or the Chinese .cmd files.'
