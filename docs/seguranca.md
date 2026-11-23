# Segurança

A segurança combina autenticação do Django, permissões, vínculos usuário × empresa, validação backend, proteção CSRF e settings separados por ambiente.

## Controles atuais

- sessões e login do Django;
- autorização por Groups/Permissions;
- isolamento lógico por `UsuarioEmpresa`;
- querysets empresariais e middleware complementar;
- validação de FKs e POSTs manipulados;
- proteção específica de relatórios de Compras e contas da importação OFX;
- CSRF middleware nos formulários;
- revisões e históricos imutáveis quando o domínio exige;
- produção fail-closed para chave secreta, DEBUG, hosts e variáveis PostgreSQL;
- PostgreSQL obrigatório em produção, sem credenciais armazenadas no Git.

Não versione `.env`, bancos SQLite, planilhas/PDFs reais, uploads, logs, backups ou credenciais. PDFs e downloads devem partir de objetos previamente autorizados.

Esses mecanismos reduzem riscos, mas não significam que o sistema seja “100% seguro”. Produção ainda requer infraestrutura endurecida, HTTPS, controle de proxy, atualização de dependências, backups testados, monitoramento e revisão contínua de acessos.

O acesso remoto previsto para os usuários será pelo navegador através da infraestrutura/VPN corporativa. Essa arquitetura ainda será implantada com o TI; RDP permanece ferramenta administrativa e não é o meio normal de acesso ao ERP.

## Controles de infraestrutura em produção

No Windows Server 2019, o IIS atende em 80/443, termina TLS e encaminha requisições dinâmicas via ARR e URL Rewrite ao Waitress em `127.0.0.1:8000`. O serviço Windows `VersERP` executa Waitress e Django, que se conecta ao PostgreSQL. Os usuários acessam o IIS. Mantenha a porta `8000` restrita ao loopback.

Com `DJANGO_HTTPS_ENABLED=true`, o IIS deve preservar o `Host` e sobrescrever `X-Forwarded-Proto=https` nas requisições TLS encaminhadas. Habilite `DJANGO_TRUST_X_FORWARDED_PROTO=true` somente após configurar o IIS e limitar os cabeçalhos confiáveis do Waitress ao proxy em loopback. Liste o IP ou DNS real em `DJANGO_ALLOWED_HOSTS` e as origens completas com esquema em `DJANGO_CSRF_TRUSTED_ORIGINS`. Consulte os [exemplos de deploy](deploy.md#https-e-proxy).

A homologação temporária por HTTP usa `DJANGO_HTTPS_ENABLED=false`, com acesso limitado à rede de teste e somente dados e contas de teste. O modo mantém as validações de produção para banco, chave secreta, DEBUG e hosts. O go-live exige HTTPS.

Execute `VersERP` com conta dedicada de privilégios mínimos. Forneça os segredos pelo ambiente protegido do serviço. Use uma role PostgreSQL de produção sem `CREATEDB`, `CREATEROLE` ou `SUPERUSER`. A role de testes com `CREATEDB` deve ficar restrita à instância de desenvolvimento ou de testes.

No IIS, conceda à identidade do site acesso de leitura a `C:\Versatile\Financeiro\VersERP\staticfiles` para servir `/static/`. Restrinja o acesso à raiz da aplicação, configurações, logs e backups.

PDFs e exportações continuam sendo entregues por views autenticadas e autorizadas para visualização/download, sem diretório público de mídia ou arquivamento automático. O usuário decide quais arquivos salvar nas pastas corporativas. `VERSERP_LOG_DIR` recebe somente warnings/erros da aplicação por padrão; credenciais e segredos não devem ser registrados.
