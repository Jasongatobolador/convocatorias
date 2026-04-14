$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "No se encontro el entorno virtual en .venv\\Scripts\\python.exe"
}

Write-Host "Verificando proyecto..."
& $python manage.py check

Write-Host "Aplicando migraciones..."
& $python manage.py migrate

Write-Host "Iniciando servidor en http://127.0.0.1:8000 ..."
& $python manage.py runserver 127.0.0.1:8000
