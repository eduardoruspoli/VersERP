# VersERP

ERP web modular da Versatile para operação integrada de cadastros, propostas comerciais, compras, financeiro e RH. O sistema é desenvolvido em Django, com regras de domínio em models e services e isolamento lógico por empresa.

## Stack e módulos

- Python 3.14.x e Django 6.0.8;
- Django MVT, HTML, CSS e JavaScript;
- PostgreSQL 17 em desenvolvimento e homologação, com banco local `verserp_dev`;
- PostgreSQL em produção;
- `psycopg[binary]==3.3.4` e `Waitress==3.0.2`;
- `core`: autenticação, dashboard, perfis, empresas autorizadas, configurações e central de relatórios;
- `pessoas`: clientes e fornecedores;
- `comercial`: propostas, revisões, formação de preço, documento comercial e acompanhamento;
- `compras`: solicitações, cotações, pedidos, recebimentos e documentos de compra;
- `financeiro`: pagar/receber, bancos, OFX, Plano de Contas, obras, DRE e relatórios;
- `rh`: funcionários, contratos, jornadas, ponto, banco de horas e conferência.

## Instalação local no Windows

Requer Python 3.14.x e PostgreSQL 17. Antes de executar as migrations, crie o banco `verserp_dev` e configure as variáveis da sessão conforme [Ambiente](docs/01-ambiente.md).x e PostgreSQL 17. Antes de executar as migrations, crie o banco `verserp_dev` e configure as variáveis da sessão conforme [Ambiente](docs/01-ambiente.md).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py sincronizar_perfis
python manage.py runserver
```

Se a criação da venv não instalar o pip, consulte [Ambiente](docs/01-ambiente.md). Para importação XLSX, instale separadamente `requirements-importacao.txt`.

`python manage.py runserver` é exclusivamente um servidor de desenvolvimento e não deve ser usado em produção.

## Configuração

Use `VERSERP_DB=postgresql` no ambiente principal. SQLite continua disponível como opção simples ou legada em desenvolvimento com `VERSERP_DB=sqlite`. As variáveis disponíveis estão em `.env.example`; o projeto não carrega `.env` automaticamente, portanto elas devem ser definidas no processo ou pela infraestrutura. Em produção, o alvo é Windows Server 2019, com a aplicação em `C:\Versatile\Financeiro\VersERP`. O IIS atende nas portas 80/443, serve `/static/` diretamente e encaminha as demais requisições via ARR e URL Rewrite para Waitress em `127.0.0.1:8000`. O serviço Windows `VersERP` executa Waitress, que carrega o Django conectado ao PostgreSQL. Os usuários acessam somente o IIS. VS Code e `manage.py runserver` são ferramentas de desenvolvimento. Consulte [Deploy](docs/deploy.md) para os detalhes de implantação.

## Qualidade

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --verbosity 1
python -m pip check
git diff --check
```

## Documentação

- [Ambiente](docs/01-ambiente.md) e [desenvolvimento](docs/desenvolvimento.md)
- [Arquitetura detalhada](docs/02-arquitetura.md)
- [Permissões](docs/permissoes.md) e [segurança](docs/seguranca.md)
- [Deploy](docs/deploy.md), [runbook de produção no Windows Server 2019](docs/runbook_producao_windows.md), [backup e restauração](docs/backup_restore.md)
- [Comercial](docs/comercial.md), [Compras](docs/compras.md), [Financeiro](docs/financeiro.md) e [RH](docs/rh.md)
- [Importação histórica](docs/importacao.md), [roadmap](docs/03-roadmap.md) e [troubleshooting](docs/troubleshooting.md)
