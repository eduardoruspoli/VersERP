#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$SiteName,
    [Parameter(Mandatory)][uri]$PublicUrl,
    [string]$AppDir = 'C:\Versatile\Financeiro\VersERP',
    [string]$ServiceDir = 'C:\VersERP-Service',
    [string]$WinSW = (Join-Path $ServiceDir 'VersERP-Service.exe'),
    [switch]$LocalTest
)

$ErrorActionPreference = 'Stop'
$AppDir = (Resolve-Path -LiteralPath $AppDir).ProviderPath.TrimEnd('\')
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

function Get-ServiceSetting([xml.xmlelement]$Config, [string]$Name, [string]$Default) {
    $entries = @($Config.SelectNodes('env') | Where-Object { $_.GetAttribute('name') -eq $Name })
    if ($entries.Count -gt 1) {
        throw "O XML do WinSW possui mais de uma entrada para $Name."
    }
    # O XML prevalece porque o WinSW aplica esses valores ao processo do serviço.
    if ($entries.Count -eq 1) { return $entries[0].GetAttribute('value').Trim() }
    $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ($null -ne $value) { return $value.Trim() }
    return $Default
}

try {
    if (-not $SiteName) {
        if (-not $LocalTest) {
            throw 'Informe o site IIS dedicado em SiteName.'
        }
        $SiteName = 'Default Web Site'
    }
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
    if (-not $LocalTest -and (-not $registration -or
        $registration.StartName -in @('LocalSystem', 'NT AUTHORITY\SYSTEM',
            'NT AUTHORITY\LocalService', 'NT AUTHORITY\Local Service',
            'NT AUTHORITY\NetworkService', 'NT AUTHORITY\Network Service'))) {
        throw 'Configure a conta dedicada do serviço VersERP antes de iniciar a aplicação.'
    }
    if (-not $registration -or $registration.PathName.Trim('"') -ne (Resolve-Path -LiteralPath $WinSW).ProviderPath) {
        throw 'O executável registrado no serviço não corresponde ao WinSW informado.'
    }
    $serviceXml = [IO.Path]::ChangeExtension($WinSW, '.xml')
    $serviceConfig = ([xml](Get-Content -LiteralPath $serviceXml -Raw -Encoding UTF8)).DocumentElement
    if ($serviceConfig.LocalName -ne 'service' -or $serviceConfig.id -ne 'VersERP' -or
        $serviceConfig.executable -ne $Python -or $serviceConfig.workingdirectory -ne $AppDir -or
        $serviceConfig.arguments -notmatch '^-m waitress --listen=127\.0\.0\.1:8000( --trusted-proxy=127\.0\.0\.1 --trusted-proxy-headers=x-forwarded-proto)? config\.wsgi:application$') {
        throw 'Revise o XML do serviço: aplicação, diretório de trabalho e argumentos de loopback devem corresponder ao deploy.'
    }
    if ($LocalTest) {
        $environment = Get-ServiceSetting $serviceConfig 'VERSERP_ENV' 'development'
        $httpsSetting = Get-ServiceSetting $serviceConfig 'DJANGO_HTTPS_ENABLED' 'false'
        $hostsSetting = Get-ServiceSetting $serviceConfig 'DJANGO_ALLOWED_HOSTS'
        $originsSetting = Get-ServiceSetting $serviceConfig 'DJANGO_CSRF_TRUSTED_ORIGINS'
        if ($environment -ne 'development' -or
            ($null -ne $env:VERSERP_ENV -and $env:VERSERP_ENV.Trim() -ne 'development')) {
            throw 'LocalTest requer VERSERP_ENV=development no serviço e na sessão, quando definido.'
        }
        if ($httpsSetting -notin @('true', 'false')) {
            throw 'Em LocalTest, omita DJANGO_HTTPS_ENABLED ou defina true ou false.'
        }
        if ($AppDir -eq 'C:\Versatile\Financeiro\VersERP') {
            throw 'LocalTest requer um checkout local fora do diretório de produção.'
        }
    } else {
        if ($env:VERSERP_ENV -ne 'production' -or $env:DJANGO_HTTPS_ENABLED -notin @('true', 'false')) {
            throw 'Defina VERSERP_ENV=production e DJANGO_HTTPS_ENABLED=true ou false.'
        }
        $httpsSetting = $env:DJANGO_HTTPS_ENABLED
        $hostsSetting = $env:DJANGO_ALLOWED_HOSTS
        $originsSetting = $env:DJANGO_CSRF_TRUSTED_ORIGINS
        foreach ($name in @('VERSERP_ENV', 'DJANGO_HTTPS_ENABLED', 'DJANGO_ALLOWED_HOSTS',
            'DJANGO_CSRF_TRUSTED_ORIGINS', 'DJANGO_TRUST_X_FORWARDED_PROTO', 'DJANGO_DEBUG')) {
            $sessionValue = ([string][Environment]::GetEnvironmentVariable($name, 'Process')).Trim()
            if ((Get-ServiceSetting $serviceConfig $name) -cne $sessionValue) {
                throw "O XML do serviço e o ambiente da sessão divergem em $name."
            }
        }
    }
    # O Django so habilita HTTPS em production.
    $https = -not $LocalTest -and $httpsSetting -eq 'true'
    if ($https -ne ($serviceConfig.arguments -like '*--trusted-proxy=*')) {
        throw 'As opções de proxy do XML do serviço devem corresponder ao modo HTTP/HTTPS.'
    }
    $scheme = if ($https) { 'https' } else { 'http' }
    if ($https -and $env:DJANGO_TRUST_X_FORWARDED_PROTO -ne 'true') {
        throw 'HTTPS via IIS requer DJANGO_TRUST_X_FORWARDED_PROTO=true no deploy e no serviço.'
    }
    if (-not $PublicUrl.IsAbsoluteUri -or $PublicUrl.Scheme -ne $scheme -or
        -not $PublicUrl.IsDefaultPort -or $PublicUrl.AbsolutePath -ne '/' -or
        $PublicUrl.Query -or $PublicUrl.Fragment -or $PublicUrl.UserInfo) {
        throw "Informe a URL raiz do site com $scheme na porta padrão e sem credenciais."
    }
    if ($LocalTest) {
        $localAddresses = @(Get-NetIPAddress -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress)
        if ($PublicUrl.Host -ne 'localhost' -and $PublicUrl.Host -notin $localAddresses) {
            throw 'LocalTest requer localhost ou um IPv4 atribuído a este notebook em PublicUrl.'
        }
    }
    $allowedHosts = @($hostsSetting -split ',' | ForEach-Object { $_.Trim() })
    $trustedOrigins = @($originsSetting -split ',' | ForEach-Object { $_.Trim() })
    if ($PublicUrl.Host -notin $allowedHosts -or $PublicUrl.GetLeftPart([UriPartial]::Authority) -notin $trustedOrigins) {
        throw 'Inclua o host e a origem da URL informada em DJANGO_ALLOWED_HOSTS e DJANGO_CSRF_TRUSTED_ORIGINS.'
    }
    if ($LocalTest -and ('localhost' -notin $allowedHosts -or '127.0.0.1' -notin $allowedHosts)) {
        throw 'LocalTest requer localhost e 127.0.0.1 em DJANGO_ALLOWED_HOSTS.'
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
        $expectedPort = if ($https) { 443 } else { 80 }
        if (-not ($site.Bindings | Where-Object { $_.Protocol -eq $scheme -and $_.EndPoint.Port -eq $expectedPort })) {
            throw "O site não possui binding $scheme na porta $expectedPort."
        }
        $root = $site.Applications['/']
        $webRoot = [Environment]::ExpandEnvironmentVariables($root.VirtualDirectories['/'].PhysicalPath)
        $webRoot = [IO.Path]::GetFullPath($webRoot).TrimEnd('\')
        if ($webRoot -eq $AppDir -or $webRoot.StartsWith("$AppDir\", [StringComparison]::OrdinalIgnoreCase) -or
            $AppDir.StartsWith("$webRoot\", [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Use uma raiz IIS dedicada fora da árvore da aplicação.'
        }
        $proxy = $config.GetSection('system.webServer/proxy')
        if ($LocalTest -and -not $proxy.GetAttributeValue('enabled')) {
            throw 'LocalTest requer que o proxy global do ARR já esteja habilitado.'
        }
        $rules = $config.GetSection('system.webServer/rewrite/rules', $SiteName).GetCollection()
        $rule = $rules | Where-Object { $_.GetAttributeValue('name') -eq $RuleName } | Select-Object -First 1
        $existingWebRule = $false
        if (-not $rule) {
            $siteConfig = $iis.GetWebConfiguration($SiteName)
            $effectiveRule = $siteConfig.GetSection('system.webServer/rewrite/rules').GetCollection() |
                Where-Object { $_.GetAttributeValue('name') -eq $RuleName } | Select-Object -First 1
            if ($effectiveRule) {
                $effectiveMatch = $effectiveRule.GetChildElement('match')
                $effectiveConditions = $effectiveRule.GetCollection('conditions')
                $excludesStatic = $effectiveMatch.GetAttributeValue('url') -eq '^(?!static(?:/|$))(.*)$' -and
                    $effectiveConditions.Count -eq 0
                if ($effectiveMatch.GetAttributeValue('url') -eq '(.*)' -and $effectiveConditions.Count -eq 1) {
                    $condition = $effectiveConditions[0]
                    $excludesStatic = $condition.GetAttributeValue('input') -in @('{URL}', '{REQUEST_URI}') -and
                        $condition.GetAttributeValue('pattern') -eq '^/static/' -and
                        $condition.GetAttributeValue('negate')
                }
                $existingWebRule = -not $https -and
                    $effectiveRule.GetAttributeValue('enabled') -and
                    $effectiveRule.GetAttributeValue('stopProcessing') -and
                    $excludesStatic -and -not $effectiveMatch.GetAttributeValue('negate') -and
                    $effectiveRule.GetChildElement('action').GetAttributeValue('type') -in @(1, 'Rewrite') -and
                    $effectiveRule.GetChildElement('action').GetAttributeValue('url') -eq 'http://127.0.0.1:8000/{R:1}' -and
                    $effectiveRule.GetCollection('serverVariables').Count -eq 0
                if (-not $existingWebRule) {
                    throw 'O site já usa uma regra VersERP fora de applicationHost.config. Revise essa regra antes de aplicar outra.'
                }
            }
        }

        Write-Host 'Validando dependências e preparando o Django...'
        Invoke-Checked $Python @('-m', 'waitress', '--help') | Out-Null
        New-Item -ItemType Directory -Force -Path "$AppDir\logs", "$AppDir\logs\service" | Out-Null
        Invoke-Checked $Python @('-m', 'pip', 'check')
        if ($LocalTest) {
            $localSettings = @{
                VERSERP_ENV = 'development'
                DJANGO_HTTPS_ENABLED = $httpsSetting
                DJANGO_ALLOWED_HOSTS = $hostsSetting
                DJANGO_CSRF_TRUSTED_ORIGINS = $originsSetting
            }
            $previousSettings = @{}
            try {
                foreach ($name in $localSettings.Keys) {
                    $previousSettings[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
                    [Environment]::SetEnvironmentVariable($name, $localSettings[$name], 'Process')
                }
                # Django usa as credenciais já disponíveis na sessão ou no .env do checkout.
                $checkLocalSettings = @'
import os
from pathlib import Path
from django.conf import settings
from django.core.management import call_command

database = settings.DATABASES['default']
loopback = ('127.0.0.1', '::1')
if (
    database['ENGINE'] != 'django.db.backends.postgresql'
    or database['HOST'].lower() not in ('localhost', *loopback)
    or os.environ.get('PGHOSTADDR') not in (None, '', *loopback)
):
    raise SystemExit('LocalTest requer PostgreSQL local na sessão ou no .env do checkout.')
if Path(settings.STATIC_ROOT).resolve() != Path(settings.BASE_DIR).resolve() / 'staticfiles':
    raise SystemExit('STATIC_ROOT deve apontar para staticfiles no checkout.')
call_command('check')
call_command('migrate', check_unapplied=True, interactive=False)
'@
                Invoke-Checked $Python @('manage.py', 'shell', '--no-imports', '-c', $checkLocalSettings)
                Invoke-Checked $Python @('manage.py', 'collectstatic', '--noinput')
            } finally {
                foreach ($name in $previousSettings.Keys) {
                    [Environment]::SetEnvironmentVariable($name, $previousSettings[$name], 'Process')
                }
            }
        } else {
            Invoke-Checked $Python @('manage.py', 'check')
            Invoke-Checked $Python @('manage.py', 'migrate', '--noinput')
            Invoke-Checked $Python @('manage.py', 'collectstatic', '--noinput')
        }

        # SIDs fixos de IUSR e IIS_IUSRS, inclusive em servidores localizados.
        Invoke-Checked 'icacls.exe' @($StaticDir, '/grant:r', '*S-1-5-17:(OI)(CI)(RX)', '*S-1-5-32-568:(OI)(CI)(RX)')
        $static = $root.VirtualDirectories['/static']
        if ($static) {
            $static.PhysicalPath = $StaticDir
        } else {
            $null = $root.VirtualDirectories.Add('/static', $StaticDir)
        }

        if (-not $LocalTest) {
            $proxy.SetAttributeValue('enabled', $true)
            $proxy.SetAttributeValue('preserveHostHeader', $true)
        }
        if (-not $existingWebRule) {
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
    if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne '127.0.0.1') {
        throw 'Existe um listener na porta 8000 fora de 127.0.0.1. Corrija antes de liberar o acesso.'
    }

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
