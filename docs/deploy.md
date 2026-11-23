# Preparação para deploy

Este documento registra a arquitetura alvo definida para produção. A aplicação deve ficar em `C:\Versatile\Financeiro\VersERP`.

## Arquitetura alvo

```text
Windows Server 2019 Standard
    Navegador → IIS (80/443, ARR + URL Rewrite)
                  ├─ /static/ → C:\Versatile\Financeiro\VersERP\staticfiles (IIS)
                  └─ rotas dinâmicas → Waitress (127.0.0.1:8000)
                                        → Django → PostgreSQL
```

A estimativa inicial é de até quatro usuários simultâneos. Não há necessidade prevista de cluster, balanceamento de carga ou arquitetura distribuída neste estágio. O IIS será o frontend interno e encaminhará requisições dinâmicas ao Waitress, executado pelo serviço Windows `VersERP`; usuários acessarão pelo navegador exclusivamente pelo IIS, sem acesso direto à porta `8000` e RDP será apenas administrativo. O PostgreSQL ficará no mesmo servidor. A implantação será executada e alinhada com o responsável de TI.

## Ambientes

- `VERSERP_ENV=development`: padrão local, `DEBUG=True`, hosts locais e sem redirecionamento HTTPS/HSTS.
- `VERSERP_ENV=production`: modo fail-closed; exige chave segura, `DEBUG=False` e hosts explícitos.

Variáveis implementadas:

```text
VERSERP_ENV=production
DJANGO_SECRET_KEY=<segredo forte fornecido pela infraestrutura>
DJANGO_DEBUG=false
DJANGO_HTTPS_ENABLED=false
DJANGO_ALLOWED_HOSTS=<hosts separados por vírgula>
DJANGO_CSRF_TRUSTED_ORIGINS=<origens completas separadas por vírgula>
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

Forneça as variáveis ao processo de deploy e ao serviço Windows pelo mecanismo aprovado pelo TI. Produção não carrega `.env` automaticamente. Em produção, o diretório de logs deve ser explícito, absoluto, existente e gravável.

## Banco de produção

Desenvolvimento e homologação usam PostgreSQL 17, com `verserp_dev` como banco local principal. SQLite é opcional em desenvolvimento com `VERSERP_DB=sqlite`. Em produção, PostgreSQL é obrigatório e não existe fallback para SQLite: a inicialização falha se `DB_NAME`, `DB_USER`, `DB_PASSWORD` ou `DB_HOST` estiverem ausentes. `DB_PORT` usa 5432 quando não informado.

O banco e o usuário deverão ser criados durante a implantação, com credenciais fornecidas por meio seguro e privilégios adequados. A compatibilidade oficial da distribuição PostgreSQL com o Windows Server 2019 deve ser resolvida antes da instalação. Não registre senha no Git. Depois de configurar a conexão, execute as migrations no banco de produção durante o deploy.

## HTTPS e proxy

`DJANGO_ALLOWED_HOSTS` define `ALLOWED_HOSTS`. Informe o IP ou DNS real pelo qual o usuário acessa o IIS, sem esquema, porta ou caminho. `DJANGO_CSRF_TRUSTED_ORIGINS` define `CSRF_TRUSTED_ORIGINS`. Informe as origens que precisam enviar requisições protegidas por CSRF, com `http://` na homologação interna ou `https://` em HTTPS definitivo, com esquema e host, sem caminho. Ambos aceitam listas separadas por vírgula e usam valores explícitos em produção. Exemplo ilustrativo para um único nome:

```text
DJANGO_ALLOWED_HOSTS=verserp.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://verserp.example.com
```

- **HTTP interno temporário** — use `DJANGO_HTTPS_ENABLED=false` e `DJANGO_TRUST_X_FORWARDED_PROTO=false`. O Django desliga redirecionamento SSL, flags de cookies seguros e HSTS. Restrinja o acesso à rede de homologação e use dados e contas de teste. As validações de produção continuam ativas.
- **HTTPS definitivo** — use `DJANGO_HTTPS_ENABLED=true`. O Django ativa redirecionamento SSL, cookies seguros e o HSTS configurado. O IIS termina TLS na porta 443, redireciona a porta 80 para HTTPS e preserva o `Host`. Habilite `DJANGO_TRUST_X_FORWARDED_PROTO=true` depois que o IIS estiver configurado para sobrescrever o cabeçalho `X-Forwarded-Proto` com `https` nas requisições TLS. Ative subdomínios e preload somente após validar todo o domínio.

Se `DJANGO_HTTPS_ENABLED` estiver ausente, produção mantém HTTPS ativo. Waitress escuta exclusivamente em `127.0.0.1:8000`. O acesso dos usuários usa o IP ou DNS do IIS na porta do protocolo.

## Instalação e atualização

O diretório `deploy/windows/` contém o modelo WinSW, o exemplo de URL Rewrite e os scripts `install.ps1` e `update.ps1`. Prepare o site IIS dedicado, registre o serviço `VersERP` e forneça as variáveis pela infraestrutura antes de executar a instalação como administrador. O instalador valida os módulos, executa migrations e coleta os estáticos, configura o IIS e verifica o serviço. Para atualizar, use `update.ps1 -Revision <referência aprovada>` em uma janela de manutenção com backup verificado.

## Validação

No ambiente final, execute:

```powershell
python manage.py check
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
```

Execute a aplicação pelo serviço Windows `VersERP` com `Waitress==3.0.2`. O serviço opera sem VS Code ou `manage.py runserver`. O `collectstatic` reúne os arquivos em `C:\Versatile\Financeiro\VersERP\staticfiles`. Mapeie `/static/` para esse diretório no IIS e exclua essa rota da regra de proxy. O log rotativo do Django já é configurável. PDFs e exportações continuam sendo gerados para visualização/download; o usuário arquiva manualmente o arquivo na pasta corporativa apropriada. Monitoramento e backup ainda precisam ser definidos.

O procedimento operacional, as verificações de compatibilidade e os bloqueadores estão no [Runbook de Produção do VersERP — Windows Server 2019](runbook_producao_windows.md).

## Pendente de implantação com o TI

- versão definitiva do PostgreSQL no servidor;
- criação do banco, usuário e entrega segura das credenciais;
- DNS ou nome interno e HTTPS/certificado;
- configuração operacional do serviço Windows `VersERP` com Waitress;
- instalação/configuração de URL Rewrite e ARR para o proxy reverso IIS;
- caminho definitivo de PDFs/documentos e permissões de filesystem;
- procedimentos de backup e restauração;
- logs e monitoramento;
- regras necessárias de firewall, rede corporativa e VPN.

Esses itens estão definidos como parte da implantação, mas ainda não estão configurados ou operacionais.
