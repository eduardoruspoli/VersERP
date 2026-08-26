# Preparação para deploy

Este documento registra a arquitetura alvo definida para produção. O deploy ainda não foi executado.

## Arquitetura alvo

```text
Windows Server 2019 Standard
    → IIS/HTTPS
    → Waitress/WSGI
    → VersERP/Django
    → PostgreSQL no mesmo servidor
    → armazenamento corporativo para PDFs e arquivos
    → acesso dos usuários pela rede corporativa ou VPN
```

A estimativa inicial é de até quatro usuários simultâneos. Não há necessidade prevista de cluster, balanceamento de carga ou arquitetura distribuída neste estágio. O IIS será o frontend interno e encaminhará requisições dinâmicas a um servidor WSGI; usuários acessarão pelo navegador e RDP será apenas administrativo. O PostgreSQL ficará no mesmo servidor. A implantação será executada e alinhada com o responsável de TI.

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
VERSERP_LOG_DIR=<diretório absoluto, existente e gravável>
```

Nunca versione valores reais. O projeto não carrega `.env` automaticamente; o processo de hospedagem deve fornecer as variáveis. Em produção, o diretório de logs deve ser explícito, absoluto, existente e gravável.

## Banco de produção

O desenvolvimento continua usando SQLite. Em produção, PostgreSQL é obrigatório e não existe fallback para SQLite: a inicialização falha se `DB_NAME`, `DB_USER`, `DB_PASSWORD` ou `DB_HOST` estiverem ausentes. `DB_PORT` usa 5432 quando não informado.

O banco e o usuário deverão ser criados durante a implantação, com credenciais fornecidas por meio seguro e privilégios adequados. A compatibilidade oficial da distribuição PostgreSQL com o Windows Server 2019 deve ser resolvida antes da instalação. Não registre senha no Git. Depois de configurar a conexão, execute as migrations no banco de produção durante o deploy.

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

Use o Waitress 3.0.2 fixado no projeto atrás do IIS; nunca `runserver`. O IIS deverá servir `STATIC_ROOT` e encaminhar somente requisições dinâmicas ao Waitress em loopback. O log rotativo do Django já é configurável. PDFs e exportações continuam sendo gerados para visualização/download; o usuário arquiva manualmente o arquivo na pasta corporativa apropriada. Monitoramento e backup ainda precisam ser definidos.

O procedimento operacional, as verificações de compatibilidade e os bloqueadores estão no [Runbook de Produção do VersERP — Windows Server 2019](runbook_producao_windows.md).

## Pendente de implantação com o TI

- versão definitiva do PostgreSQL no servidor;
- criação do banco, usuário e entrega segura das credenciais;
- DNS ou nome interno e HTTPS/certificado;
- servidor WSGI/ASGI e execução como serviço;
- instalação/configuração de URL Rewrite e ARR para o proxy reverso IIS;
- caminho definitivo de PDFs/documentos e permissões de filesystem;
- procedimentos de backup e restauração;
- logs e monitoramento;
- regras necessárias de firewall, rede corporativa e VPN.

Esses itens estão definidos como parte da implantação, mas ainda não estão configurados ou operacionais.
