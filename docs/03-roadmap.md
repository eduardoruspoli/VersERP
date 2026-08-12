# Roadmap

O desenvolvimento do VersERP é realizado de forma incremental.

As etapas abaixo representam a evolução funcional do sistema e podem ser reorganizadas conforme novas dependências forem identificadas.

---

## Sprint 1 — Fundação

- [x] Criar projeto Django
- [x] Configurar ambiente virtual
- [x] Configurar SQLite
- [x] Criar app Core
- [x] Configurar Templates
- [x] Configurar Static
- [x] Configurar Git
- [x] Criar documentação inicial

**Status:** Concluído

---

## Sprint 2 — Interface Base

- [x] Design System inicial
- [x] Layout principal
- [x] Sidebar
- [x] Header
- [x] Footer
- [x] Área de conteúdo
- [x] Dashboard inicial
- [x] Organização do CSS por responsabilidade
- [x] Bootstrap Icons
- [x] Interface responsiva inicial

**Status:** Concluído

---

## Sprint 3 — Estrutura de Cadastros

- [x] Definir estrutura modular de cadastros
- [x] Criar app Pessoas
- [x] Configurar URLs do app
- [x] Configurar templates do app
- [x] Registrar Pessoa no Django Admin
- [x] Criar migrations

**Status:** Concluído

---

## Sprint 4 — Módulo Pessoas

### Cadastro

- [x] Model Pessoa
- [x] Pessoa Física
- [x] Pessoa Jurídica
- [x] Cliente
- [x] Fornecedor
- [x] Cliente e Fornecedor
- [x] Dados principais
- [x] Contato
- [x] Endereço
- [x] Observações
- [x] Status do cadastro

### Documentos

- [x] CPF
- [x] CNPJ
- [x] Máscara de CPF
- [x] Máscara de CNPJ
- [x] Validação de CPF
- [x] Validação de CNPJ
- [x] Formatação na apresentação

### Consulta empresarial

- [x] Integração com CNPJ.ws
- [x] Consulta de CNPJ
- [x] Preenchimento automático do formulário

### Gerenciamento

- [x] Listagem
- [x] Pesquisa
- [x] Filtro por classificação
- [x] Filtro por status
- [x] Paginação
- [x] Edição
- [x] Ativação
- [x] Inativação
- [x] Tela de detalhes

**Status:** Concluído para a etapa atual

---

## Próximas Etapas

### Autenticação e Usuários

- [ ] Login
- [ ] Logout
- [ ] Usuários
- [ ] Perfis
- [ ] Permissões
- [ ] Controle de acesso por módulo

### Comercial

- [ ] Estrutura do módulo Comercial
- [ ] Propostas
- [ ] Itens de proposta
- [ ] Status de proposta
- [ ] Conversão futura em venda/pedido

### Financeiro

- [ ] Contas a receber
- [ ] Contas a pagar
- [ ] Categorias financeiras
- [ ] Formas de pagamento
- [ ] Fluxo de caixa

### Compras

- [ ] Solicitações
- [ ] Pedidos de compra
- [ ] Fornecedores
- [ ] Integração com Pessoas

### Relatórios

- [ ] Relatórios gerenciais
- [ ] Filtros
- [ ] Indicadores
- [ ] Exportações

### Configurações

- [ ] Dados da empresa
- [ ] Parâmetros do sistema
- [ ] Preferências
- [ ] Numerações e sequências

---

## Futuro

Funcionalidades que deverão ser avaliadas conforme o ERP evoluir:

- produtos e serviços;
- estoque;
- vendas/pedidos;
- faturamento;
- emissão fiscal;
- centros de custo;
- contas bancárias;
- conciliação;
- anexos;
- histórico de alterações;
- notificações;
- dashboard configurável;
- importação/exportação;
- API interna;
- integrações externas;
- multiempresa.