#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SiteName,
    [Parameter(Mandatory)][uri]$PublicUrl,
    [string]$WinSW = 'C:\VersERP-Service\VersERP-Service.exe'
)

$ErrorActionPreference = 'Stop'
$AppDir = 'C:\Versatile\Financeiro\VersERP'
$Python = Join-Path $AppDir '.venv\Scripts\python.exe'
$StaticDir = Join-Path $AppDir 'staticfiles'
$IisDir = Join-Path $env:windir 'System32\inetsrv'
$RuleName = 'VersERP Reverse Proxy'

function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Program $($Arguments -join ' ') retornou $LASTEXITCODE."
    }
}

function Get-HttpStatus([string]$Url, [string[]]$Headers = @()) {
    $options = @('--silent', '--noproxy', '*', '--max-time', '5', '--output', 'NUL', '--write-out', '%{http_code}')
    $status = & curl.exe @options @Headers $Url
    if ($LASTEXITCODE -ne 0) { return '000' }
    return $status
}

try {
    Set-Location -LiteralPath $AppDir
    foreach ($file in @('manage.py', $Python)) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
            throw "Arquivo obrigatório ausente: $file."
        }
    }
    if (-not (Test-Path -LiteralPath $WinSW -PathType Leaf)) {
        throw "WinSW ausente em $WinSW. Obtenha o executável aprovado pelo TI e siga o runbook."
    }
    $service = Get-Service -Name VersERP -ErrorAction SilentlyContinue
    if (-not $service) {
        throw "Registre o serviço VersERP com $WinSW e configure a conta e o ambiente conforme o runbook."
    }
    $registration = Get-CimInstance Win32_Service -Filter "Name='VersERP'"
    if (-not $registration -or $registration.StartName -in @('LocalSystem', 'NT AUTHORITY\SYSTEM')) {
        throw 'Configure a conta dedicada do serviço VersERP antes de iniciar a aplicação.'
    }
    if ($env:VERSERP_ENV -ne 'production' -or $env:DJANGO_HTTPS_ENABLED -notin @('true', 'false')) {
        throw 'Defina VERSERP_ENV=production e DJANGO_HTTPS_ENABLED=true ou false.'
    }
    $https = $env:DJANGO_HTTPS_ENABLED -eq 'true'
    $scheme = if ($https) { 'https' } else { 'http' }
    if ($https -and $env:DJANGO_TRUST_X_FORWARDED_PROTO -ne 'true') {
        throw 'HTTPS via IIS requer DJANGO_TRUST_X_FORWARDED_PROTO=true no deploy e no serviço.'
    }
    if (-not $PublicUrl.IsAbsoluteUri -or $PublicUrl.Scheme -ne $scheme -or
        -not $PublicUrl.IsDefaultPort -or $PublicUrl.AbsolutePath -ne '/' -or
        $PublicUrl.Query -or $PublicUrl.Fragment -or $PublicUrl.UserInfo) {
        throw "Informe a URL raiz do site com $scheme na porta padrão e sem credenciais."
    }
    $null = Get-Command curl.exe

    if (-not (Test-Path -LiteralPath "$IisDir\Microsoft.Web.Administration.dll") -or
        -not (Get-Service -Name W3SVC -ErrorAction SilentlyContinue)) {
        throw 'Instale IIS com as ferramentas de gerenciamento e conteúdo estático.'
    }
    Add-Type -Path "$IisDir\Microsoft.Web.Administration.dll"
    $iis = New-Object Microsoft.Web.Administration.ServerManager
    try {
        $config = $iis.GetApplicationHostConfiguration()
        $modules = @($config.GetSection('system.webServer/globalModules').GetCollection() |
            ForEach-Object { $_.GetAttributeValue('name') })
        foreach ($module in @('RewriteModule', 'ApplicationRequestRouting', 'StaticFileModule')) {
            if ($module -notin $modules) {
                throw "Módulo IIS ausente: $module. Valide URL Rewrite, ARR e conteúdo estático."
            }
        }
        $site = $iis.Sites[$SiteName]
        if (-not $site -or $site.State -ne 'Started') {
            throw "Inicie o site dedicado '$SiteName' e configure seus bindings primeiro."
        }
        $root = $site.Applications['/']
        $webRoot = [Environment]::ExpandEnvironmentVariables($root.VirtualDirectories['/'].PhysicalPath)
        $webRoot = [IO.Path]::GetFullPath($webRoot).TrimEnd('\')
        if ($webRoot -eq $AppDir -or $webRoot.StartsWith("$AppDir\", [StringComparison]::OrdinalIgnoreCase) -or
            $AppDir.StartsWith("$webRoot\", [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Use uma raiz IIS dedicada fora da árvore da aplicação.'
        }
        $proxy = $config.GetSection('system.webServer/proxy')
        $rules = $config.GetSection('system.webServer/rewrite/rules', $SiteName).GetCollection()
        $rule = $rules | Where-Object { $_.GetAttributeValue('name') -eq $RuleName } | Select-Object -First 1

        Write-Host 'Validando dependências e preparando o Django...'
        Invoke-Checked $Python @('-m', 'waitress', '--help') | Out-Null
        New-Item -ItemType Directory -Force -Path "$AppDir\logs", "$AppDir\logs\service" | Out-Null
        Invoke-Checked $Python @('-m', 'pip', 'check')
        Invoke-Checked $Python @('manage.py', 'check')
        Invoke-Checked $Python @('manage.py', 'migrate', '--noinput')
        Invoke-Checked $Python @('manage.py', 'collectstatic', '--noinput')

        # SIDs fixos de IUSR e IIS_IUSRS, inclusive em servidores localizados.
        Invoke-Checked 'icacls.exe' @($StaticDir, '/grant:r', '*S-1-5-17:(OI)(CI)(RX)', '*S-1-5-32-568:(OI)(CI)(RX)')
        $static = $root.VirtualDirectories['/static']
        if ($static) {
            $static.PhysicalPath = $StaticDir
        } else {
            $null = $root.VirtualDirectories.Add('/static', $StaticDir)
        }

        $proxy.SetAttributeValue('enabled', $true)
        $proxy.SetAttributeValue('preserveHostHeader', $true)
        $newRule = -not $rule
        if ($newRule) {
            $rule = $rules.CreateElement('rule')
            $rule.SetAttributeValue('name', $RuleName)
        }
        $rule.SetAttributeValue('enabled', $true)
        $rule.SetAttributeValue('stopProcessing', $true)
        $rule.SetAttributeValue('patternSyntax', 'ECMAScript')
        $match = $rule.GetChildElement('match')
        $match.SetAttributeValue('url', '^(?!static(?:/|$))(.*)$')
        $match.SetAttributeValue('ignoreCase', $true)
        $match.SetAttributeValue('negate', $false)
        $action = $rule.GetChildElement('action')
        $action.SetAttributeValue('type', 'Rewrite')
        $action.SetAttributeValue('url', 'http://127.0.0.1:8000/{R:1}')
        $action.SetAttributeValue('appendQueryString', $true)

        $conditions = $rule.GetCollection('conditions')
        $headers = $rule.GetCollection('serverVariables')
        foreach ($item in @($conditions)) { $conditions.Remove($item) }
        foreach ($item in @($headers)) { $headers.Remove($item) }
        if ($https) {
            $allowed = $config.GetSection('system.webServer/rewrite/allowedServerVariables', $SiteName).GetCollection()
            if (-not ($allowed | Where-Object { $_.GetAttributeValue('name') -eq 'HTTP_X_FORWARDED_PROTO' })) {
                $entry = $allowed.CreateElement('add')
                $entry.SetAttributeValue('name', 'HTTP_X_FORWARDED_PROTO')
                $allowed.Add($entry)
            }
            $condition = $conditions.CreateElement('add')
            $condition.SetAttributeValue('input', '{HTTPS}')
            $condition.SetAttributeValue('pattern', '^ON$')
            $conditions.Add($condition)
            $header = $headers.CreateElement('set')
            $header.SetAttributeValue('name', 'HTTP_X_FORWARDED_PROTO')
            $header.SetAttributeValue('value', 'https')
            $header.SetAttributeValue('replace', $true)
            $headers.Add($header)
        }
        if ($newRule) {
            $rules.Add($rule)
        }
        $iis.CommitChanges()
    } finally {
        $iis.Dispose()
    }

    if ($service.Status -eq 'Running') {
        Restart-Service -Name VersERP
    } else {
        Start-Service -Name VersERP
    }

    $hostHeader = @('--header', "Host: $($PublicUrl.Host)")
    $loopbackHeaders = $hostHeader
    if ($https) {
        $loopbackHeaders += @('--header', 'X-Forwarded-Proto: https')
    }
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        $backend = Get-HttpStatus 'http://127.0.0.1:8000/login/' $loopbackHeaders
        if ($backend -eq '200') { break }
        Start-Sleep -Seconds 2
    }
    if ($backend -ne '200') {
        throw "Waitress em 127.0.0.1:8000 retornou $backend. Confira os logs do serviço."
    }
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8000)
    if ($listeners.LocalAddress | Where-Object { $_ -ne '127.0.0.1' }) {
        throw 'Existe um listener na porta 8000 fora de 127.0.0.1. Corrija antes de liberar o acesso.'
    }

    $localStatic = Get-HttpStatus 'http://localhost/static/css/style.css' $hostHeader
    Write-Host "Checagem do IIS em localhost: HTTP $localStatic."
    $publicStatic = Get-HttpStatus ([uri]::new($PublicUrl, '/static/css/style.css').AbsoluteUri)
    $frontendHeaders = @()
    if ($https) {
        # A requisição TLS deve funcionar mesmo se o cliente enviar seu próprio cabeçalho.
        $frontendHeaders = @('--header', 'X-Forwarded-Proto: http')
    }
    $frontend = Get-HttpStatus ([uri]::new($PublicUrl, '/login/').AbsoluteUri) $frontendHeaders
    if ($publicStatic -ne '200' -or $frontend -ne '200') {
        throw "IIS em $PublicUrl retornou $publicStatic para CSS e $frontend para login. Confira bindings, certificado e regras."
    }
    if ($https) {
        $http = "http://$($PublicUrl.Authority)/static/css/style.css"
        $redirect = Get-HttpStatus $http
        if ($redirect -notin @('301', '302', '307', '308')) {
            throw "O IIS deve redirecionar HTTP para HTTPS. Resposta atual na porta 80: $redirect."
        }
    }
    Write-Host 'VersERP validado: serviço em loopback, login e arquivos estáticos pelo IIS.'
} catch {
    throw "Instalação do VersERP falhou. $($_.Exception.Message)"
}
