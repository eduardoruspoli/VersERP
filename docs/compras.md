# Compras

O módulo preserva a distinção entre previsto, solicitado, cotado, comprado, recebido, realizado financeiro e pago.

## Fluxo

- Solicitação de Compra: pertence a uma empresa e a uma obra ativa; pode selecionar itens da revisão efetivamente aprovada, registrar substituição ou item não previsto e guardar snapshots.
- Cotação: consolida itens de solicitações e propostas de fornecedores em mapa comparativo, com seleção de ofertas.
- Pedido de Compra: pode consolidar obras por alocações operacionais, registra fornecedor, itens, valores, workflow de aprovação e documento/PDF.
- Recebimento: registra quantidades aceitas/rejeitadas, recebimentos parciais e divergências sem apagar histórico.
- Documento de Compra: vincula pedidos e recebimentos, confere itens, divergências e parcelas e oferece preview financeiro.

Após a conferência, a integração Compras → Financeiro cria lançamento, parcelas, rateios e classificações contábeis múltiplas de forma transacional e idempotente. A alocação operacional do pedido permanece separada de `RateioCentroCusto`.

## Relatórios

Previsto × Comprado compara a revisão aprovada da proposta com solicitações, pedidos e recebimentos da obra. O histórico de fornecedores é derivado dos pedidos, preços e divergências registrados. Consultas e ações são recortadas pelas empresas autorizadas do usuário.
