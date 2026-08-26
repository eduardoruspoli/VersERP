# Convenções do projeto

## Código e domínio

- classes e models usam `PascalCase`;
- funções, métodos, variáveis, arquivos Python e templates usam `snake_case`;
- apps representam domínios claros; não use `core` como depósito de models;
- termos de negócio podem permanecer em português; APIs do framework seguem convenções Django;
- cada app possui namespace próprio de URLs.

Models protegem invariantes. Forms validam entrada; JavaScript melhora a experiência, mas nunca é a única validação. Operações transacionais e cálculos reutilizáveis devem ser centralizados em services quando isso já for o padrão do domínio.

## Interface

Templates específicos usam diretório/namespace do app. CSS deve preferir classes reutilizáveis, variáveis do design system e separação entre base, componentes, layout e páginas. Evite estilos inline quando houver alternativa no projeto.

## Dados e migrations

- alterações de model exigem migration correspondente;
- não edite migrations aplicadas apenas para esconder divergências;
- preserve snapshots, históricos e objetos congelados;
- cadastros referenciados preferem inativação quando a exclusão comprometer histórico;
- validações de empresa e integridade referencial ficam no backend.

## Git

Antes de editar, confira `git status`. Adicione explicitamente somente arquivos do escopo quando houver itens adicionais no working tree. Commits devem ser pequenos, coerentes e usar a mensagem definida para o checkpoint.

Nunca versione:

- `.pyc` e `__pycache__/`;
- `.env`, credenciais ou secrets;
- `db.sqlite3` ou outros bancos locais;
- planilhas, PDFs, uploads ou dados reais;
- logs, backups, arquivos temporários e diretórios gerados como `staticfiles/`.

Antes do commit, execute conforme o risco:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --verbosity 1
python -m pip check
git diff --check
```

Revise `git status`, `git diff` e o diff staged. Não inclua arquivos gerados automaticamente.
