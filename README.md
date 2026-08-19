# VersERP

ERP web da Versatile para operação integrada de Pessoas, Comercial/Propostas, Compras, Financeiro e RH. O projeto usa Django com arquitetura MVT e regras de domínio concentradas em models e services.

## Módulos

- `core`: autenticação, dashboard, perfis, empresas autorizadas, configurações e relatórios.
- `pessoas`: clientes, fornecedores e dados cadastrais compartilhados.
- `comercial`: propostas, revisões, workflow, PDFs e previsto × realizado.
- `compras`: solicitações, cotações, pedidos, recebimentos, documentos e Financeiro.
- `financeiro`: títulos, bancos, OFX, Plano de Contas, obras, DRE e relatórios.
- `rh`: funcionários, contratos, ponto, banco de horas e pré-fechamento.

## Desenvolvimento

Requer Python 3.14 e dependências de `requirements.txt`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py sincronizar_perfis
python manage.py runserver
```

`runserver` é exclusivamente para desenvolvimento. Para importar XLSX, instale também `requirements-importacao.txt`.

## Qualidade

```powershell
python manage.py check
python manage.py test
python manage.py makemigrations --check --dry-run
git diff --check
```

## Documentação

Consulte [arquitetura](docs/arquitetura.md), [desenvolvimento](docs/desenvolvimento.md), [permissões](docs/permissoes.md), [importação](docs/importacao.md), [segurança](docs/seguranca.md) e [preparação de deploy](docs/deploy.md).
