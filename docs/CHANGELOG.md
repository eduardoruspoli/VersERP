# Changelog

Todas as alterações relevantes do VersERP serão registradas neste arquivo.

O projeto utiliza versionamento incremental durante a fase de desenvolvimento.

---

## [0.4.0] - 2026-08-11

### Adicionado

#### Módulo Pessoas

- Aplicação Django `pessoas`
- Model `Pessoa`
- Cadastro de Pessoa Física e Jurídica
- Classificação como Cliente, Fornecedor ou ambos
- Dados de identificação
- Dados de contato
- Endereço
- Observações
- Status ativo/inativo
- Registro no Django Admin
- Formulário de cadastro
- Edição de cadastro
- Tela de detalhes
- Listagem de Pessoas
- Pesquisa
- Filtro por classificação
- Filtro por status
- Paginação de 10 registros por página
- Ativação e inativação de cadastros
- Máscaras de CPF e CNPJ
- Validação de CPF
- Validação de CNPJ
- Formatação de documentos na apresentação
- Integração com CNPJ.ws
- Consulta de CNPJ
- Preenchimento automático de dados empresariais

### Alterado

- Evolução da estrutura de templates
- Evolução da organização de CSS
- Integração do módulo Pessoas ao layout principal
- Estrutura do projeto preparada para novos módulos de negócio

---

## [0.3.0]

### Adicionado

- Layout base
- Sidebar
- Header
- Footer
- Dashboard inicial
- Design System inicial
- Estrutura modular de CSS

---

## [0.2.0]

### Adicionado

- Estrutura inicial do projeto
- Configuração de templates
- Configuração de arquivos estáticos
- Documentação inicial

---

## [0.1.0]

### Adicionado

- Projeto Django criado
- Ambiente de desenvolvimento configurado
- SQLite configurado
- Aplicação Core criada