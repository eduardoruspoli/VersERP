# VersERP

ERP web modular da Versatile para operação integrada de cadastros, propostas comerciais, compras, financeiro e RH. O sistema é desenvolvido em Django, com regras de domínio em models e services e isolamento lógico por empresa.

## Stack e módulos

- Python 3.14.6 e Django 6.0.8;
- Django MVT, HTML, CSS e JavaScript;
- SQLite no desenvolvimento local;
- `core`: autenticação, dashboard, perfis, empresas autorizadas, configurações e central de relatórios;
- `pessoas`: clientes e fornecedores;
- `comercial`: propostas, revisões, formação de preço, documento comercial e acompanhamento;
- `compras`: solicitações, cotações, pedidos, recebimentos e documentos de compra;
- `financeiro`: pagar/receber, bancos, OFX, Plano de Contas, obras, DRE e relatórios;
- `rh`: funcionários, contratos, jornadas, ponto, banco de horas e conferência.

## Instalação local no Windows

Requer Python 3.14.

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

O desenvolvimento funciona com os padrões locais. As variáveis disponíveis estão em `.env.example`; o projeto não carrega `.env` automaticamente, portanto elas devem ser definidas no processo ou pela infraestrutura. Em produção, use `VERSERP_ENV=production` e configure chave secreta, hosts, origens CSRF e opções HTTPS conforme [Deploy](docs/deploy.md).

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
- [Deploy](docs/deploy.md), [backup e restauração](docs/backup_restore.md)
- [Comercial](docs/comercial.md), [Compras](docs/compras.md), [Financeiro](docs/financeiro.md) e [RH](docs/rh.md)
- [Importação histórica](docs/importacao.md), [roadmap](docs/03-roadmap.md) e [troubleshooting](docs/troubleshooting.md)
