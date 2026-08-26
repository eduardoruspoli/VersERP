# Changelog

Todas as alterações relevantes do VersERP serão registradas neste arquivo.

O projeto utiliza versionamento incremental durante a fase de desenvolvimento.

## Não lançado

### Evoluções recentes

- refinamento do fluxo de propostas, criação da Rev. 00 e aplicação automática do modelo padrão da empresa;
- composição interna, formação de preço por item, linhas públicas automáticas e juros de antecipação;
- documento comercial/PDF e preservação da separação entre dados internos e públicos;
- isolamento multiempresa reforçado nos relatórios de Compras e na importação OFX;
- configuração segura de produção com ambiente fail-closed, HTTPS, cookies seguros e HSTS;
- atualização de segurança para Django 6.0.8;
- remoção de arquivos Python gerados (`.pyc` e `__pycache__`) do versionamento;
- atualização da documentação técnica para refletir o estado atual;
- suporte a PostgreSQL em produção, mantendo SQLite no desenvolvimento;
- inclusão do Psycopg 3 para conexão com PostgreSQL;
- validação fail-closed das variáveis obrigatórias do banco de produção;
- suíte completa atualizada para 400 testes aprovados.

## [0.5.0] - 2026-08-12

### Adicionado

#### Autenticação

- Tela própria de login do VersERP
- Logout seguro através de requisição POST
- Proteção de páginas para usuários autenticados
- Redirecionamento após login através do parâmetro `next`
- Identificação do usuário autenticado no header

#### Controle de Acesso

- Grupos de usuários
- Grupo Gerência Administrativa
- Grupo Financeiro e Compras
- Grupo RH
- Permissões de Pessoas por grupo
- Proteção de views através das permissões do Django
- Tratamento de acesso não autorizado com HTTP 403
- Controle de exibição de ações conforme permissões
- Controle de acesso ao módulo Pessoas pela sidebar
- Separação entre conta técnica Admin e usuários operacionais

#### Interface

- Página de login integrada ao Design System
- Botão de logout no header
- Módulos futuros identificados na sidebar
- Inclusão do módulo RH na estrutura futura do VersERP

### Segurança

- Usuários operacionais não possuem acesso ao Django Admin
- Permissões atribuídas através de grupos
- Exclusão de Pessoa não concedida aos grupos operacionais
- Validação de permissões realizada também no backend

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
