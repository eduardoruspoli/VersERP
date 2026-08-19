# Preparação para deploy

Este documento não executa deploy. Antes de produção: usar PostgreSQL, `DEBUG=False`, `SECRET_KEY` por variável de ambiente, `ALLOWED_HOSTS`, HTTPS, cookies seguros, servidor WSGI/ASGI, coleta de estáticos, armazenamento persistente de uploads, logs, monitoramento, backup testado e usuário de banco com privilégio mínimo. Rode `check --deploy` no ambiente final.
