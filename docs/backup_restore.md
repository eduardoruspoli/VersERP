# Backup e restauração

## Desenvolvimento e homologação com PostgreSQL 17

Para o banco local principal `verserp_dev`, use as ferramentas cliente do PostgreSQL 17. Em homologação, use o host, o banco e a role próprios do ambiente. O exemplo local cria um dump lógico e restaura em um banco separado, previamente criado e vazio. As ferramentas podem solicitar a senha interativamente.

```powershell
pg_dump -h 127.0.0.1 -p 5432 -U '<role-dev>' -d verserp_dev -Fc -f verserp_dev.dump
pg_restore -h 127.0.0.1 -p 5432 -U '<role-restore>' -d verserp_dev_restore --no-owner --no-privileges --exit-on-error verserp_dev.dump
```

Use uma role com acesso de leitura ao banco de origem para o dump, e uma role com permissão de criar objetos no destino para a restauração. Proteja o arquivo de dump e mantenha-o fora do Git. Aponte a sessão de validação para o banco restaurado com `VERSERP_DB=postgresql` e `DB_NAME=verserp_dev_restore`, ajuste a role e execute `python manage.py check`, `python manage.py showmigrations` e uma conferência dos dados.

## SQLite opcional em desenvolvimento

Com a aplicação parada e sem processo escrevendo no banco, faça cópia consistente de `db.sqlite3` para local protegido. Identifique data/ambiente e mantenha o arquivo fora do Git. Antes de restaurar, preserve o banco atual; restaure somente em ambiente controlado e valide:

```powershell
python manage.py check
python manage.py showmigrations
```

Uma simples cópia durante escrita pode ficar inconsistente. Nunca teste restauração sobre dados que precisam ser preservados.

## Produção com PostgreSQL

PostgreSQL foi definido como banco de produção, mas o procedimento definitivo de backup e restauração será estabelecido durante a implantação junto ao TI, conforme a distribuição, versão e ferramentas compatíveis com o Windows Server 2019 Standard. Não há comando operacional definitivo documentado antes dessa validação.

A política deverá possuir duas categorias independentes: PostgreSQL no servidor e pastas corporativas nas quais os usuários arquivam manualmente PDFs, planilhas e demais arquivos exportados. Uma categoria não substitui a outra. Também deverá prever criptografia, retenção, cópia externa, controle de acesso e testes conjuntos e periódicos de restauração. RPO e RTO serão definidos operacionalmente.

Antes de executar `deploy/windows/update.ps1`, registre o commit atual e valide um backup recente do PostgreSQL e a recuperação das pastas corporativas. Após uma falha de migration, use o plano de rollback para decidir se é necessário restaurar o banco. Se houver restauração, valide o schema e os dados em ambiente isolado e use `collectstatic` para recompor os estáticos da revisão recuperada antes de iniciar o serviço `VersERP`.

Use o [runbook de produção](runbook_producao_windows.md#16-backup-e-restauração) para planejar e validar a recuperação em ambiente isolado.
