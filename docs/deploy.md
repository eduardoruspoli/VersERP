# Preparação para deploy

Este documento descreve configuração; não escolhe provedor, domínio, servidor ou banco definitivo.

## Ambientes

- `VERSERP_ENV=development`: padrão local, `DEBUG=True`, hosts locais e sem redirecionamento HTTPS/HSTS.
- `VERSERP_ENV=production`: modo fail-closed; exige chave segura, `DEBUG=False` e hosts explícitos.

Variáveis implementadas:

```text
VERSERP_ENV=production
DJANGO_SECRET_KEY=<segredo forte fornecido pela infraestrutura>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=<hosts separados por vírgula>
DJANGO_CSRF_TRUSTED_ORIGINS=<origens https separadas por vírgula>
DJANGO_SECURE_HSTS_SECONDS=31536000
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=false
DJANGO_SECURE_HSTS_PRELOAD=false
DJANGO_TRUST_X_FORWARDED_PROTO=false
DB_NAME=<nome do banco>
DB_USER=<usuário do banco>
DB_PASSWORD=<senha fornecida com segurança>
DB_HOST=<host do PostgreSQL>
DB_PORT=5432
```

Nunca versione valores reais. O projeto não carrega `.env` automaticamente; o processo de hospedagem deve fornecer as variáveis.

## Banco de produção

O desenvolvimento continua usando SQLite. Em produção, PostgreSQL é obrigatório e não existe fallback para SQLite: a inicialização falha se `DB_NAME`, `DB_USER`, `DB_PASSWORD` ou `DB_HOST` estiverem ausentes. `DB_PORT` usa 5432 quando não informado.

O banco e o usuário deverão ser criados no Windows Server durante a implantação, com credenciais fornecidas por meio seguro e privilégios adequados. Não registre senha no Git. Depois de configurar a conexão, execute as migrations no banco de produção durante o deploy.

## HTTPS e proxy

Em produção, redirecionamento HTTPS e cookies seguros de sessão/CSRF são ativados. HSTS usa o período configurado; inclusão de subdomínios e preload só devem ser habilitados após confirmar HTTPS definitivo para todo o domínio.

`DJANGO_TRUST_X_FORWARDED_PROTO=true` define `SECURE_PROXY_SSL_HEADER`. Use somente quando um proxy confiável remover cabeçalhos enviados pelo cliente e definir `X-Forwarded-Proto` corretamente.

## Validação

No ambiente final, execute:

```powershell
python manage.py check
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
```

Use servidor WSGI/ASGI adequado; nunca `runserver`. Defina persistência de arquivos no servidor da empresa, logs, monitoramento e backup. A configuração de SSL da conexão PostgreSQL permanece dependente da topologia definida pelo TI.
