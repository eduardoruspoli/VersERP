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
