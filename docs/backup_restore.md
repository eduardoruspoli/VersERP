# Backup e restauração

## Desenvolvimento com SQLite

Com a aplicação parada e sem processo escrevendo no banco, faça cópia consistente de `db.sqlite3` para local protegido. Identifique data/ambiente e mantenha o arquivo fora do Git. Antes de restaurar, preserve o banco atual; restaure somente em ambiente controlado e valide:

```powershell
python manage.py check
python manage.py showmigrations
```

Uma simples cópia durante escrita pode ficar inconsistente. Nunca teste restauração sobre dados que precisam ser preservados.

## Produção com PostgreSQL

PostgreSQL foi definido como banco de produção, mas o procedimento definitivo de backup e restauração será estabelecido durante a implantação junto ao TI, conforme a versão, instalação e ferramentas disponíveis no ambiente Windows da infraestrutura da empresa. A versão/edição exata do Windows ainda será confirmada. Não há comando operacional definitivo documentado antes dessa validação.

A política deverá abranger o banco e os PDFs/documentos armazenados na infraestrutura corporativa; o caminho definitivo ainda será definido. Também deverá prever criptografia, retenção, cópia externa, controle de acesso e testes periódicos de restauração. RPO e RTO serão definidos operacionalmente.

A cópia do SQLite local não é apresentada como estratégia definitiva de produção. Nenhum backup ou restore real é executado por estes procedimentos documentais.
