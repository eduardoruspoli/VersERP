# Comercial

## Propostas e revisões

A proposta pertence a uma empresa e cliente e usa número no padrão `VERSxxxx`, único por empresa. A criação gera exatamente a Rev. 00; o modelo de conteúdo padrão ativo da empresa é aplicado quando existe, sem impedir a criação quando não existe. Os dados informados na proposta prevalecem sobre textos genéricos.

A revisão atual pode ser editada enquanto não estiver congelada. Nova revisão só é criada por ação explícita e copia a composição/snapshots da origem. Revisões enviadas são congeladas para preservar o documento comercial e o histórico.

## Composição e formação de preço

`PropostaItem` é a fonte interna de custos e cálculos. Há itens de material, mão de obra, serviço de terceiro, juros de antecipação, frete, locação/equipamento e outros. Fornecedor, custo, Plano de Contas, observações internas e percentuais não são expostos ao cliente.

Na formação por item, o valor unitário de venda aplica o percentual sobre o custo unitário: `custo × (1 + percentual/100)`. Juros de antecipação são um serviço próprio calculado pela taxa mensal, base aplicável e prazo em meses comerciais. Tributos e modos de formação da revisão participam dos cálculos definidos no service.

`PropostaLinhaPublica` serve somente à apresentação. Linhas automáticas de MATERIAIS e SERVIÇOS derivam da composição e precisam fechar com o preço final antes do envio; não recalculam custo ou margem.

## Documento e workflow

O documento público HTML/PDF usa uma lista permitida de dados, textos institucionais em snapshot, escopo, condições e valores públicos. Custos, fornecedores e margens internas não entram no contexto público.

O workflow contempla envio, negociação, aprovação, rejeição e cancelamento, com permissões e histórico. Aprovação válida cria uma única Obra/Centro de Custo com o código da proposta e registra a revisão efetivamente aprovada. O módulo também oferece acompanhamento comercial, relatório de propostas e previsto × realizado da obra.
