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
- produção fail-closed para chave secreta, DEBUG e hosts.

Não versione `.env`, bancos SQLite, planilhas/PDFs reais, uploads, logs, backups ou credenciais. PDFs e downloads devem partir de objetos previamente autorizados.

Esses mecanismos reduzem riscos, mas não significam que o sistema seja “100% seguro”. Produção ainda requer infraestrutura endurecida, HTTPS, controle de proxy, atualização de dependências, backups testados, monitoramento e revisão contínua de acessos.
