#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$Revision,
    [string]$AppDir = 'C:\Versatile\Financeiro\VersERP',
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
$AppDir = (Resolve-Path -LiteralPath $AppDir).ProviderPath
$Python = Join-Path $AppDir '.venv\Scripts\python.exe'
$Service = 'VersERP'

function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Program $($Arguments -join ' ') retornou $LASTEXITCODE."
    }
}

$previous = $null
$stopped = $false
$deploymentChanged = $false
Push-Location -LiteralPath $AppDir
try {
    if (Invoke-Checked 'git' @('--no-optional-locks', 'status', '--porcelain', '--untracked-files=all')) {
        throw 'Working tree suja. Preserve e resolva as alterações locais antes de atualizar.'
    }
    $previous = Invoke-Checked 'git' @('rev-parse', 'HEAD')
    Write-Host "Commit anterior: $previous"
    if ($ValidateOnly) {
        $target = Invoke-Checked 'git' @('rev-parse', '--verify', '--end-of-options', "$Revision^{commit}")
        if ($target -ne $previous) {
            throw 'ValidateOnly exige uma revisão que corresponda ao HEAD atual.'
        }
        Write-Host "Validação sem alteração de versão. Commit anterior: $previous. Commit atual: $target."
        return
    }
    $principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'A atualização do serviço exige PowerShell elevado.'
    }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf) -or
        -not (Test-Path -LiteralPath 'manage.py' -PathType Leaf)) {
        throw 'Valide a instalação inicial e a venv antes de atualizar.'
    }
    if ($env:VERSERP_ENV -ne 'production' -or $env:DJANGO_HTTPS_ENABLED -notin @('true', 'false')) {
        throw 'Defina VERSERP_ENV=production e DJANGO_HTTPS_ENABLED=true ou false.'
    }
    $null = Get-Command curl.exe
    if ((Get-Service -Name $Service).Status -ne 'Running') {
        throw "O serviço $Service deve estar em execução antes de atualizar."
    }
    Invoke-Checked $Python @('manage.py', 'check')
    Invoke-Checked 'git' @('fetch', 'origin', '--tags')
    $target = Invoke-Checked 'git' @('rev-parse', '--verify', '--end-of-options', "$Revision^{commit}")
    if (Invoke-Checked 'git' @('status', '--porcelain', '--untracked-files=all')) {
        throw 'A working tree mudou durante o fetch. Resolva as alterações locais antes de atualizar.'
    }
    if ((Invoke-Checked 'git' @('rev-parse', 'HEAD')) -ne $previous) {
        throw 'O HEAD mudou durante o fetch. Confirme a revisão antes de atualizar.'
    }
    Stop-Service -Name $Service
    $stopped = $true
    if ($target -ne $previous) {
        Invoke-Checked 'git' @('checkout', '--detach', '--no-overwrite-ignore', $target)
    }
    $deploymentChanged = $true

    Invoke-Checked $Python @('-m', 'pip', 'install', '-r', 'requirements.txt')
    Invoke-Checked $Python @('-m', 'pip', 'check')
    Invoke-Checked $Python @('manage.py', 'check')
    Invoke-Checked $Python @('manage.py', 'migrate', '--noinput')
    Invoke-Checked $Python @('manage.py', 'collectstatic', '--noinput')
    Invoke-Checked $Python @('manage.py', 'check')

    Start-Service -Name $Service
    $allowedHost = ($env:DJANGO_ALLOWED_HOSTS -split ',' | Select-Object -First 1).Trim()
    $options = @('--silent', '--noproxy', '*', '--max-time', '5', '--output', 'NUL', '--write-out', '%{http_code}')
    $headers = @('--header', "Host: $allowedHost")
    if ($env:DJANGO_HTTPS_ENABLED -eq 'true') {
        $headers += @('--header', 'X-Forwarded-Proto: https')
    }
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        $status = & curl.exe @options @headers 'http://127.0.0.1:8000/login/'
        if ($LASTEXITCODE -eq 0 -and $status -eq '200') { break }
        Start-Sleep -Seconds 2
    }
    if ($LASTEXITCODE -ne 0 -or $status -ne '200') {
        throw "Waitress retornou $status após a atualização. Confira os logs."
    }
    $current = Invoke-Checked 'git' @('rev-parse', 'HEAD')
    Write-Host "Atualização validada. Commit anterior: $previous. Commit atual: $current."
} catch {
    if ($stopped -and -not $deploymentChanged) {
        Start-Service -Name $Service -ErrorAction Continue
    }
    if ($deploymentChanged) {
        Stop-Service -Name $Service -ErrorAction Continue
        Write-Warning "O serviço foi mantido parado. Use o runbook para recuperar o deploy a partir de $previous e do backup."
    }
    throw "Atualização do VersERP falhou. $($_.Exception.Message)"
} finally {
    Pop-Location
}
