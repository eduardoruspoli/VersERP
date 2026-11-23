# Ambiente de desenvolvimento

O ambiente validado utiliza Windows, Python 3.14.x, Django 6.0.8 e PostgreSQL 17 em desenvolvimento e homologação. O banco local principal é verserp_dev. As dependências fixadas incluem psycopg[binary]==3.3.4 e Waitress==3.0.2. A venv local fica em `.venv/` e não é versionada.

## Preparação

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Se o Python 3.14 não instalar o pip durante a criação:

```powershell
python -m venv .venv --without-pip
.\.venv\Scripts\python.exe -m ensurepip
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Não instale Django isoladamente: `requirements.txt` é a referência das dependências do projeto. Importações XLSX exigem também `requirements-importacao.txt`.

## Banco e inicialização

Crie `verserp_dev` no PostgreSQL 17 e dê a uma role de desenvolvimento acesso ao banco e permissões de criação de objetos para as migrations. Em homologação, use o banco e a role próprios do ambiente. Configure a sessão PowerShell antes de rodar os comandos de Django.

```powershell
$env:VERSERP_ENV = 'development'
$env:VERSERP_DB = 'postgresql'
$env:DB_NAME = 'verserp_dev'
$env:DB_HOST = '127.0.0.1'
$env:DB_PORT = '5432'
$verserpDbCredential = Get-Credential -Message 'Informe a role e a senha do PostgreSQL de desenvolvimento'
$env:DB_USER = $verserpDbCredential.UserName
$env:DB_PASSWORD = $verserpDbCredential.GetNetworkCredential().Password
Remove-Variable verserpDbCredential
```

Depois, na mesma sessão:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py sincronizar_perfis
python manage.py runserver
```

O acesso local padrão é `http://127.0.0.1:8000/`; o Admin fica em `/admin/`. O `runserver` não é servidor de produção.

## SQLite opcional

Para desenvolvimento simples ou legado, use `VERSERP_ENV=development` e `VERSERP_DB=sqlite`. As migrations serão aplicadas ao arquivo local `db.sqlite3`, ignorado pelo Git. O código ainda seleciona SQLite quando `VERSERP_DB` está ausente, por isso configure `postgresql` explicitamente para usar o ambiente principal.

## Ambiente local

Sem variáveis, o projeto assume `VERSERP_ENV=development`, `DEBUG=True` e hosts locais. `.env.example` lista as opções, mas o Django não lê arquivos `.env` sozinho: exporte as variáveis no processo quando necessário.

## Comandos úteis

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --verbosity 1
python -m pip check
git diff --check
```

Novas alterações de model devem gerar migration versionada. Não edite migrations já aplicadas nem altere o schema do banco manualmente.

## Ambiente alvo de produção

O servidor alvo confirmado é o Microsoft Windows Server 2019 Standard, versão 1809, build 17763.9020, com a aplicação em C:\Versatile\Financeiro\VersERP. O IIS atende em 80/443 e usa ARR e URL Rewrite para encaminhar requisições ao Waitress em 127.0.0.1:8000. O serviço Windows VersERP executa o Django via Waitress, com PostgreSQL no mesmo servidor. Consulte o [runbook](runbook_producao_windows.md).

PostgreSQL será configurado por `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` e, opcionalmente, `DB_PORT` (padrão 5432). Banco e usuário serão criados durante a implantação; credenciais reais não devem entrar no Git. A compatibilidade da distribuição PostgreSQL com o Windows Server 2019 deve ser resolvida com o TI antes da instalação, conforme o runbook. As migrations deverão ser aplicadas ao PostgreSQL no processo de deploy.
