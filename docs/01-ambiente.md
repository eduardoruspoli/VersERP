# Ambiente de desenvolvimento

O ambiente validado utiliza Windows, Python 3.14.6, Django 6.0.8 e SQLite. A venv local fica em `.venv/` e não é versionada.

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

SQLite é o banco configurado para desenvolvimento. `db.sqlite3` é local e ignorado pelo Git. Nenhuma variável PostgreSQL é necessária no ambiente local.

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py sincronizar_perfis
python manage.py runserver
```

O acesso local padrão é `http://127.0.0.1:8000/`; o Admin fica em `/admin/`. O `runserver` não é servidor de produção.

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

Novas alterações de model devem gerar migration versionada. Não edite migrations já aplicadas nem o banco SQLite manualmente.

## Ambiente alvo de produção

O servidor alvo confirmado é o Microsoft Windows Server 2019 Standard, versão 1809, build 17763.9020, com IIS como frontend, servidor WSGI executado como serviço Windows e PostgreSQL no mesmo servidor. A aplicação ainda não foi implantada nesse ambiente.

PostgreSQL será configurado por `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` e, opcionalmente, `DB_PORT` (padrão 5432). Banco e usuário serão criados durante a implantação; credenciais reais não devem entrar no Git. A compatibilidade da distribuição PostgreSQL com o Windows Server 2019 deve ser resolvida com o TI antes da instalação, conforme o runbook. As migrations deverão ser aplicadas ao PostgreSQL no processo de deploy.
