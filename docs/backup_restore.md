# Backup e restauração

## Desenvolvimento com SQLite

Com a aplicação parada e sem processo escrevendo no banco, faça cópia consistente de `db.sqlite3` para local protegido. Identifique data/ambiente e mantenha o arquivo fora do Git. Antes de restaurar, preserve o banco atual; restaure somente em ambiente controlado e valide:

```powershell
python manage.py check
python manage.py showmigrations
```

Uma simples cópia durante escrita pode ficar inconsistente. Nunca teste restauração sobre dados que precisam ser preservados.

## Produção com PostgreSQL

PostgreSQL foi definido como banco de produção, mas o procedimento definitivo de backup e restauração será estabelecido durante a implantação junto ao TI, conforme a distribuição, versão e ferramentas compatíveis com o Windows Server 2019 Standard. Não há comando operacional definitivo documentado antes dessa validação.

A política deverá possuir duas categorias independentes: PostgreSQL no servidor e pastas corporativas nas quais os usuários arquivam manualmente PDFs, planilhas e demais arquivos exportados. Uma categoria não substitui a outra. Também deverá prever criptografia, retenção, cópia externa, controle de acesso e testes conjuntos e periódicos de restauração. RPO e RTO serão definidos operacionalmente.

A cópia do SQLite local não é apresentada como estratégia definitiva de produção. Nenhum backup ou restore real é executado por estes procedimentos documentais.
