# Financeiro

## Operação

O módulo cobre Contas a Pagar e a Receber, parcelas, baixas, contas bancárias, movimentações, transferências internas, importação/conciliação OFX, Plano de Contas e Obras/Centros de Custo. Lançamentos podem possuir múltiplas classificações contábeis e rateios por obra.

Competência, caixa e conciliação são conceitos separados: lançamentos/classificações alimentam resultado; baixas e movimentações representam caixa. Saldo do título usa principal em aberto, enquanto pago/recebido no período usa o movimento efetivo. Transferências alteram contas individuais, mas se anulam no consolidado operacional.

## Relatórios

- Dashboard Financeiro Executivo;
- Relatório Gerencial por Obra, por competência e caixa;
- DRE Gerencial Consolidada por competência;
- aging de pagar e receber;
- fluxo de caixa realizado e projetado;
- painel da obra e relatórios do Plano de Contas.

A projeção considera somente títulos cadastrados. DRE e relatório por obra usam classificações analíticas e rateios sem dupla contagem. Baixas parciais são distribuídas proporcionalmente com tratamento determinístico de centavos.

## Segurança e limites

Contas, títulos, obras e importações são filtrados pelas empresas autorizadas. No OFX, o formulário limita contas bancárias e o backend revalida a empresa. O fechamento operacional de competência e o banco definitivo de produção continuam decisões pendentes.
