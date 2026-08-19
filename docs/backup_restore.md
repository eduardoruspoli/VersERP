# Backup e restauração

Defina política por ambiente e banco. Backup deve incluir banco e uploads, ser criptografado, ter retenção e cópia fora do servidor. Teste restauração periodicamente em ambiente isolado, registre RPO/RTO e nunca valide restauração sobre produção. SQLite local não é estratégia de produção.
