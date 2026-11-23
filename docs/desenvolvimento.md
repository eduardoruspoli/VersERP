# Desenvolvimento

Use Python 3.14.x, Django 6.0.8 e a venv `.venv`. Instale as dependências com `python -m pip install -r requirements.txt`.

O ambiente principal de desenvolvimento e homologação usa PostgreSQL 17. Na máquina local, configure `VERSERP_ENV=development`, `VERSERP_DB=postgresql` e `DB_NAME=verserp_dev` conforme [Ambiente](01-ambiente.md). Para desenvolvimento simples ou legado, selecione `VERSERP_DB=sqlite`.

## Fluxo recomendado

1. confira `git status` e preserve alterações existentes;
2. ative a venv;
3. implemente a mudança no app responsável;
4. crie migration apenas quando models mudarem;
5. execute primeiro os testes focados e depois a suíte adequada;
6. rode os checks antes do commit.

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --verbosity 1
python -m pip check
git diff --check
```

Execute a suíte contra PostgreSQL para validar o banco usado em desenvolvimento e homologação. Se o Django falhar ao criar o banco de testes, consulte [Troubleshooting](troubleshooting.md#permission-denied-to-create-database-nos-testes-postgresql).

## Princípios do projeto

- invariantes críticas permanecem no backend;
- operações compostas e cálculos reutilizáveis ficam em services e usam transações quando necessário;
- consultas multiempresa devem usar os mecanismos de `core.access`, filtrar objetos na view/service e testar IDs/FKs manipulados;
- prefira `select_related`, `prefetch_related` e agregações para evitar N+1;
- não altere snapshots ou revisões congeladas;
- não versione `.env`, banco local, dados reais ou arquivos gerados.

O `runserver` é destinado somente ao desenvolvimento. Configuração de produção está em [deploy.md](deploy.md).
