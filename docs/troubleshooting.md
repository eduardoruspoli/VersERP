# Troubleshooting

- **Django não encontrado:** ative `.venv` e confirme com `python -m django --version`.
- **Falha ao criar venv/pip no Python 3.14:** use `python -m venv .venv --without-pip` e depois `.\.venv\Scripts\python.exe -m ensurepip`.
- **Migration pendente:** rode `python manage.py makemigrations --check --dry-run`; crie migration somente se houve alteração intencional de model.
- **Erro de `VERSERP_ENV`:** use apenas `development` ou `production`.
- **Produção não inicia:** configure `DJANGO_SECRET_KEY`, mantenha `DJANGO_DEBUG=false` e informe `DJANGO_ALLOWED_HOSTS` explícitos.
- **CSRF em produção:** confira esquema `https://` e origem exata em `DJANGO_CSRF_TRUSTED_ORIGINS`.
- **Loop HTTPS atrás de proxy:** com `DJANGO_HTTPS_ENABLED=true`, confira se o IIS sobrescreve `X-Forwarded-Proto=https` em TLS, se o WinSW inicia Waitress com `--trusted-proxy=127.0.0.1 --trusted-proxy-headers=x-forwarded-proto` e se `DJANGO_TRUST_X_FORWARDED_PROTO=true` está no ambiente do serviço. Em HTTP interno temporário, use ambas as variáveis em `false`.
- **Warnings no check de deploy:** execute o comando com as variáveis efetivas de produção, não com settings locais.
- **Acesso 403/404:** confira permissão funcional e vínculo `UsuarioEmpresa`.
- **XLSX indisponível:** instale `requirements-importacao.txt`.
- **IIS retorna 502:** confira `Get-Service -Name VersERP`, os logs do serviço e a escuta em `127.0.0.1:8000` no próprio servidor. Confira se ARR encaminha para esse endereço.
- **CSS ou JavaScript retorna 404 em produção:** execute `collectstatic --noinput` via `manage.py` e confira o mapeamento de `/static/` no IIS, a leitura do diretório `staticfiles` e a exclusão da rota na regra de proxy.
- **Django retorna 400 com DisallowedHost:** confira se o IIS preserva o `Host` original e se o nome de acesso consta em `DJANGO_ALLOWED_HOSTS`, sem esquema, porta ou caminho.

## `permission denied to create database` nos testes PostgreSQL

Ao executar `python manage.py test` com `VERSERP_DB=postgresql`, o Django tenta criar um banco separado. Para `DB_NAME=verserp_dev`, o nome padrão é `test_verserp_dev`. O erro indica que a role usada na sessão carece de permissão para criar bancos.

1. Confirme `VERSERP_ENV=development`, `VERSERP_DB=postgresql` e os valores de `DB_NAME` e `DB_USER`. Use uma instância de desenvolvimento ou de testes.
2. Prefira pedir ao administrador para criar previamente o banco dedicado `test_verserp_dev`, com uma role de teste autorizada a executar migrations e escrever nele. Execute `python manage.py test --keepdb --verbosity 1` para reutilizá-lo. Confirme que se trata de um banco descartável, pois a suíte modifica seus dados.
3. Se a equipe optar por criação automática, use uma role separada com `CREATEDB` em instância de desenvolvimento ou testes e acesso ao banco de manutenção `postgres`. Mantenha a role da aplicação em produção com `NOCREATEDB`. Para validar somente os settings sem criar banco, execute `python manage.py test config --verbosity 1`.

Consulte a [documentação do Django sobre o banco de testes](https://docs.djangoproject.com/en/6.0/topics/testing/overview/#the-test-database).
