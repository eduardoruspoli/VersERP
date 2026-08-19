# Segurança

Não versione `.env`, bancos, planilhas, PDFs reais, uploads, logs ou backups. Segredos devem vir do ambiente em produção. Views devem validar permissão e empresa no backend; esconder botão não autoriza ação. Downloads/PDFs devem partir de objetos já filtrados por empresa. Audite alterações de acesso e preserve históricos específicos de domínio.
