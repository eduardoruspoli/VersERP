# Arquitetura do VersERP

## Visão geral

O VersERP é um monólito modular Django organizado pelo padrão MVT. Models persistem dados e protegem invariantes; forms validam entradas; views aplicam autorização, selecionam dados e renderizam respostas; templates apresentam a interface; services concentram operações transacionais, workflows, integrações internas e cálculos gerenciais.

`config/` contém settings e roteamento global. Templates e estáticos compartilhados ficam em `templates/` e `static/`; cada app mantém suas rotas, migrations e responsabilidades de domínio.

## Aplicações

- `core`: login, dashboard geral, perfis, vínculos usuário × empresa, configurações, relatórios centrais, exportações e middleware complementar de isolamento.
- `pessoas`: cadastro mestre de pessoas físicas/jurídicas, clientes e fornecedores.
- `comercial`: propostas, revisões, composição, formação de preço, workflow, documento/PDF comercial, CRM leve e previsto × realizado.
- `compras`: solicitações por obra, cotações, pedidos multiobra, recebimentos, documentos, divergências e integração com o Financeiro.
- `financeiro`: títulos, parcelas, baixas, contas bancárias, transferências, OFX, Plano de Contas, obras/centros de custo, rateios, DRE e relatórios.
- `rh`: funcionários, contratos, jornadas, ponto, banco de horas, eventos, vales e conferência do retorno contábil.

## Relações principais

`Pessoa` é cadastro mestre compartilhado. `Empresa` é o tenant lógico dos objetos operacionais. Uma proposta aprovada cria e referencia uma Obra (`CentroCusto`); Compras pode usar itens da revisão aprovada e alocar pedidos a obras; documentos de compra conferidos podem gerar lançamentos e classificações no Financeiro. Relatórios usam essas referências sem recalcular ou modificar snapshots históricos.

## Isolamento e autorização

Autenticação usa o sistema do Django. Groups e Permissions determinam ações; `UsuarioEmpresa` determina empresas acessíveis. Superusuários têm acesso global. Usuários comuns devem receber querysets recortados por empresa, e validações críticas permanecem nas views/services. `EmpresaAccessMiddleware` atua como barreira complementar para parâmetros explícitos e rotas mapeadas, não como única defesa.

O cadastro `Pessoa` é compartilhado; o isolamento ocorre nos objetos empresariais que o referenciam. Tornar pessoas exclusivas por empresa exigiria decisão de domínio e migration futura.

## Dados, transações e interface

SQLite é usado no desenvolvimento. Workflows como aprovação, recebimento e integração financeira usam services e `transaction.atomic()` quando a operação precisa ser indivisível. Valores derivados de relatórios não são persistidos quando podem ser calculados das fontes oficiais.

`templates/base.html` compõe header, sidebar e conteúdo. O CSS é organizado em base, componentes, layout e páginas. JavaScript auxilia a experiência, mas não substitui validações do backend.

## Documento relacionado

`docs/arquitetura.md` é um resumo executivo anterior e ainda coerente. Ele se sobrepõe a este documento e pode ser consolidado futuramente, sem exclusão nesta atualização.
