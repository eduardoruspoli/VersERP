# Desenvolvimento

Use Python 3.14, Django 6.0.8 e a venv `.venv`. Instale dependências por `python -m pip install -r requirements.txt`; o desenvolvimento usa SQLite e `VERSERP_ENV=development` por padrão.

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

## Princípios do projeto

- invariantes críticas permanecem no backend;
- operações compostas e cálculos reutilizáveis ficam em services e usam transações quando necessário;
- consultas multiempresa devem usar os mecanismos de `core.access`, filtrar objetos na view/service e testar IDs/FKs manipulados;
- prefira `select_related`, `prefetch_related` e agregações para evitar N+1;
- não altere snapshots ou revisões congeladas;
- não versione `.env`, banco local, dados reais ou arquivos gerados.

O `runserver` é destinado somente ao desenvolvimento. Configuração de produção está em [deploy.md](deploy.md).
