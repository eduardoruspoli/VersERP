# Desenvolvimento

Use ambiente virtual, migrations incrementais e testes de todos os apps. Não edite `db.sqlite3`, migrations aplicadas ou snapshots congelados. Novas consultas multiempresa devem usar `core.access`, validar POST no backend e cobrir URL/FK manipulados. Prefira `select_related`, `prefetch_related`, agregações e services reutilizáveis.
