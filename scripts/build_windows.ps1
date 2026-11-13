param(
    [string]$Python = '',
    [string]$InnoCompiler = '',
    [switch]$Installer
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Python) { $Python = Join-Path $projectRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'No se encontró Python. Crea .venv o usa -Python.' }
if ($Installer -and -not $InnoCompiler) {
    $candidates = @(
        (Join-Path $projectRoot '.runtime\inno-6.7.4\ISCC.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
    )
    $InnoCompiler = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $InnoCompiler) { throw 'No se encontró Inno Setup 6. Usa -InnoCompiler con la ruta a ISCC.exe.' }
}
function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Falló $Executable (código $LASTEXITCODE)." }
}
$previousConfig = $env:PYINSTALLER_CONFIG_DIR
$env:PYINSTALLER_CONFIG_DIR = Join-Path $projectRoot '.runtime\pyinstaller-cache'
Push-Location -LiteralPath $projectRoot
try {
    if ($env:OS -ne 'Windows_NT') { throw 'La compilación debe ejecutarse en Windows.' }
    Invoke-Checked $Python @('-B', '-c', 'import sys, struct; assert (sys.version_info[:2], struct.calcsize(chr(80))) == ((3, 11), 8)')
    Invoke-Checked $Python @('-B', '-m', 'pip', 'check')
    Invoke-Checked $Python @('-B', 'scripts/prepare_build.py')
    # PyInstaller solo reemplaza su salida generada dentro de este proyecto.
    $distPath = [IO.Path]::GetFullPath((Join-Path $projectRoot 'dist'))
    $workPath = [IO.Path]::GetFullPath((Join-Path $projectRoot 'build\pyinstaller'))
    foreach ($target in @($distPath, $workPath)) {
        if (-not $target.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Salida no permitida: $target" }
    }
    Invoke-Checked $Python @('-B', '-m', 'PyInstaller', '--noconfirm', '--distpath', $distPath, '--workpath', $workPath, 'packaging/LockIn.spec')
    $appExe = Join-Path $distPath 'LockIn\LockIn.exe'
    $smokeReport = Join-Path $projectRoot 'build\packaged-check.json'
    if (Test-Path -LiteralPath $smokeReport) { Remove-Item -LiteralPath $smokeReport }
    $smoke = Start-Process -FilePath $appExe -ArgumentList @('--self-test', '--report', ('"' + $smokeReport + '"'), '-platform', 'offscreen') -WorkingDirectory $env:WINDIR -WindowStyle Hidden -PassThru
    if (-not $smoke.WaitForExit(45000)) {
        $smoke.Kill()
        throw 'El diagnóstico del ejecutable excedió 45 segundos. No se genera el instalador.'
    }
    if ($smoke.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $smokeReport)) { throw 'Falló el diagnóstico del ejecutable. Revisa build/packaged-check.json.' }
    if (-not (Get-Content -LiteralPath $smokeReport -Raw | ConvertFrom-Json).ok) { throw 'El diagnóstico reportó errores.' }
    if ($Installer) {
        $version = (Get-Content -LiteralPath 'packaging/version.txt' -Raw).Trim()
        Invoke-Checked $InnoCompiler @('/Qp', "/DAppVersion=$version", 'packaging/installer.iss')
        $setup = Join-Path $distPath "releases\LockIn-$version-Setup-x64.exe"
        $hash = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $([IO.Path]::GetFileName($setup))" | Set-Content -LiteralPath ($setup + '.sha256') -Encoding ascii
        Write-Output "Instalador: $setup"
    }
    Write-Output ('Aplicación: ' + (Join-Path $distPath 'LockIn\LockIn.exe'))
} finally {
    Pop-Location
    $env:PYINSTALLER_CONFIG_DIR = $previousConfig
}
