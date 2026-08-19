# Arquitetura

O VersERP é um monólito modular Django. Models protegem invariantes; services executam operações transacionais e cálculos; views fazem autorização, filtros e apresentação. `Empresa` é o tenant lógico. `UsuarioEmpresa` limita em quais empresas um usuário normal atua; Groups/Permissions definem o que ele pode fazer. Superusuários acessam todas.

Pessoas são cadastros mestres compartilhados; o isolamento empresarial ocorre nos objetos operacionais que as utilizam. Alterar essa decisão para pessoas exclusivas por empresa exige migração e saneamento de duplicidades.

Estoque não foi implementado. O fluxo atual indica compra predominantemente destinada à obra. Caso surja armazenamento físico recorrente, recomenda-se `LocalEstoque`, `Produto`, `MovimentoEstoque` e `ReservaObra`, com recebimento gerando entrada e consumo/transferência gerando saída, sempre por empresa e lote documental.
