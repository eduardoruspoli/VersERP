# Troubleshooting

- **Django não encontrado:** ative `.venv` e confirme com `python -m django --version`.
- **Falha ao criar venv/pip no Python 3.14:** use `python -m venv .venv --without-pip` e depois `.\.venv\Scripts\python.exe -m ensurepip`.
- **Migration pendente:** rode `python manage.py makemigrations --check --dry-run`; crie migration somente se houve alteração intencional de model.
- **Erro de `VERSERP_ENV`:** use apenas `development` ou `production`.
- **Produção não inicia:** configure `DJANGO_SECRET_KEY`, mantenha `DJANGO_DEBUG=false` e informe `DJANGO_ALLOWED_HOSTS` explícitos.
- **CSRF em produção:** confira esquema `https://` e origem exata em `DJANGO_CSRF_TRUSTED_ORIGINS`.
- **Loop HTTPS atrás de proxy:** só habilite `DJANGO_TRUST_X_FORWARDED_PROTO` após validar que o proxy define o cabeçalho com confiança.
- **Warnings no check de deploy:** execute o comando com as variáveis efetivas de produção, não com settings locais.
- **Acesso 403/404:** confira permissão funcional e vínculo `UsuarioEmpresa`.
- **XLSX indisponível:** instale `requirements-importacao.txt`.
- **IIS retorna 502:** confira `Get-Service -Name VersERP`, os logs do serviço e a escuta em `127.0.0.1:8000` no próprio servidor. Confira se ARR encaminha para esse endereço.
- **CSS ou JavaScript retorna 404 em produção:** execute `collectstatic --noinput` via `manage.py` e confira o mapeamento de `/static/` no IIS, a leitura do diretório `staticfiles` e a exclusão da rota na regra de proxy.
- **Django retorna 400 com DisallowedHost:** confira se o IIS preserva o `Host` original e se o nome de acesso consta em `DJANGO_ALLOWED_HOSTS`, sem esquema, porta ou caminho.

## `permission denied to create database` nos testes PostgreSQL

Ao executar `python manage.py test` com `VERSERP_DB=postgresql`, o Django tenta criar um banco separado. Para `DB_NAME=verserp_dev`, o nome padrão é `test_verserp_dev`. O erro indica que a role usada na sessão carece de permissão para criar bancos.

1. Confirme `VERSERP_ENV=development`, `VERSERP_DB=postgresql` e os valores de `DB_NAME` e `DB_USER`. Use uma instância de desenvolvimento ou de testes.
2. Peça ao administrador que conceda `CREATEDB` à role dedicada aos testes nessa instância e confirme que ela pode conectar ao banco de manutenção `postgres`. Mantenha as roles de produção com `NOCREATEDB`.
3. Execute novamente `python manage.py test --verbosity 1`. Se usar `--keepdb`, a primeira execução ainda precisa criar o banco quando ele estiver ausente.

Consulte a [documentação do Django sobre o banco de testes](https://docs.djangoproject.com/en/6.0/topics/testing/overview/#the-test-database).
