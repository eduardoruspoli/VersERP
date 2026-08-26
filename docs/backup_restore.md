# Backup e restauração

## Desenvolvimento com SQLite

Com a aplicação parada e sem processo escrevendo no banco, faça cópia consistente de `db.sqlite3` para local protegido. Identifique data/ambiente e mantenha o arquivo fora do Git. Antes de restaurar, preserve o banco atual; restaure somente em ambiente controlado e valide:

```powershell
python manage.py check
python manage.py showmigrations
```

Uma simples cópia durante escrita pode ficar inconsistente. Nunca teste restauração sobre dados que precisam ser preservados.

## Produção

A estratégia dependerá do banco e armazenamento escolhidos. Ela deverá abranger banco, uploads persistentes quando existirem e configurações necessárias, com criptografia, retenção, cópia externa, controle de acesso e testes periódicos de restauração. RPO e RTO devem ser definidos operacionalmente.

A cópia do SQLite local não é apresentada como estratégia definitiva de produção. Nenhum backup ou restore real é executado por estes procedimentos documentais.
