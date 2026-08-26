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

O servidor alvo confirmado é o Windows Server 2019 Standard, com IIS como frontend e PostgreSQL local. HTTPS, configuração segura do proxy, conta de serviço, armazenamento de segredos e regras de rede ainda dependem da implantação controlada com o TI. O Waitress deverá aceitar conexões somente pelo loopback, sem exposição direta à rede corporativa.

PDFs e exportações continuam sendo entregues por views autenticadas e autorizadas para visualização/download, sem diretório público de mídia ou arquivamento automático. O usuário decide quais arquivos salvar nas pastas corporativas. `VERSERP_LOG_DIR` recebe somente warnings/erros da aplicação por padrão; credenciais e segredos não devem ser registrados.
