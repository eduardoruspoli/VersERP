# Arquitetura

## Visão Geral

O VersERP é desenvolvido em Django e organizado em aplicações separadas por domínio de negócio.

O objetivo da arquitetura é permitir que novos módulos sejam adicionados gradualmente sem concentrar todas as responsabilidades em uma única aplicação.

O projeto utiliza a arquitetura baseada no padrão MVT (Model-View-Template) do Django.

---

## Estrutura Principal

```text
VersERP/
│
├── config/
├── core/
├── pessoas/
├── docs/
├── static/
├── templates/
├── db.sqlite3
├── manage.py
├── README.md
└── requirements.txt
```

---

## Config

```text
config/
```

Responsável pela configuração global do projeto Django.

Principais responsabilidades:

- settings;
- roteamento principal;
- configuração WSGI;
- configuração ASGI;
- registro das aplicações instaladas.

O arquivo:

```text
config/urls.py
```

funciona como roteador principal e encaminha as URLs para cada aplicação.

---

## Core

```text
core/
```

Responsável pelas funcionalidades gerais do VersERP que não pertencem diretamente a um domínio específico.

Atualmente concentra funcionalidades como:

- dashboard;
- estrutura inicial da aplicação;
- rotas gerais.

O `core` não deve se tornar um depósito para models pertencentes a outros domínios.

Por exemplo, o model `Pessoa` pertence ao app `pessoas`, e não ao `core`.

---

## Pessoas

```text
pessoas/
```

Aplicação responsável pelo cadastro unificado de pessoas físicas e jurídicas.

Uma Pessoa pode ser:

- Cliente;
- Fornecedor;
- Cliente e Fornecedor.

Estrutura principal:

```text
pessoas/
├── migrations/
├── templates/
│   └── pessoas/
│       ├── lista.html
│       ├── formulario.html
│       └── detalhe.html
├── admin.py
├── apps.py
├── forms.py
├── models.py
├── urls.py
└── views.py
```

### Model

`Pessoa`

Responsável pela persistência dos dados cadastrais.

### Forms

`PessoaForm`

Responsável pela entrada e validação dos dados através do Django Forms.

### Views

Responsáveis pelos fluxos de:

- listagem;
- cadastro;
- edição;
- detalhes;
- ativação/inativação;
- consulta de CNPJ.

### URLs

O módulo possui seu próprio namespace:

```text
pessoas
```

As rotas do módulo são incluídas pelo roteador principal do projeto.

---

## Templates

Os templates globais ficam em:

```text
templates/
```

O arquivo:

```text
templates/base.html
```

define a estrutura principal da interface.

Componentes compartilhados ficam em:

```text
templates/includes/
```

Exemplos:

- header;
- sidebar;
- footer.

Templates específicos de cada domínio devem permanecer associados ao respectivo módulo.

Exemplo:

```text
pessoas/templates/pessoas/
```

---

## Arquivos Estáticos

Os arquivos estáticos ficam centralizados em:

```text
static/
```

Estrutura:

```text
static/
├── css/
├── icons/
├── images/
└── js/
```

---

## CSS

O CSS está sendo organizado por responsabilidade.

Estrutura conceitual:

```text
css/
├── base/
├── components/
├── layout/
├── pages/
└── style.css
```

### Base

Responsável por:

- variáveis;
- reset;
- tipografia.

### Components

Responsável por componentes reutilizáveis:

- botões;
- cards;
- badges;
- formulários;
- tabelas.

### Layout

Responsável pela estrutura geral:

- header;
- sidebar;
- content;
- footer.

### Pages

Responsável por particularidades visuais de páginas ou módulos.

O arquivo `style.css` funciona como ponto central de carregamento dos estilos.

---

## Design System

O VersERP possui um Design System inicial baseado em variáveis CSS.

Entre as variáveis estão:

- cores;
- espaçamentos;
- bordas;
- sombras;
- transições;
- dimensões estruturais.

O objetivo é manter consistência visual entre os módulos.

---

## Banco de Dados

Atualmente:

```text
SQLite
```

O banco é adequado para a fase inicial de desenvolvimento.

A aplicação deve evitar dependências específicas do SQLite para facilitar futura migração de banco.

---

## Integrações Externas

### CNPJ.ws

O módulo Pessoas utiliza a CNPJ.ws para auxiliar no cadastro de Pessoas Jurídicas.

Arquitetura da consulta:

```text
Browser
   ↓
VersERP
   ↓
View Django
   ↓
CNPJ.ws
   ↓
View Django
   ↓
JSON normalizado
   ↓
JavaScript
   ↓
Formulário
```

A API externa não deve ser tratada como fonte permanente de dados do sistema.

Os dados retornados são utilizados para auxiliar o preenchimento e posteriormente são armazenados no banco do VersERP.

---

## Persistência de Documentos

CPF e CNPJ são armazenados preferencialmente somente com números.

Exemplo:

```text
36119890000100
```

A formatação:

```text
36.119.890/0001-00
```

é responsabilidade da camada de apresentação.

---

## Exclusão de Cadastros

Cadastros de Pessoa utilizam ativação/inativação em vez de exclusão física pela interface.

Isso prepara o sistema para preservar integridade referencial quando Pessoas estiverem relacionadas a:

- propostas;
- vendas;
- contas;
- compras;
- documentos;
- histórico comercial.

---

## Princípio de Modularização

Novas áreas de negócio devem, quando fizer sentido, ser implementadas como aplicações Django independentes.

A arquitetura deve priorizar:

- baixo acoplamento;
- responsabilidades claras;
- reutilização;
- manutenção simples;
- evolução incremental;
- consistência de interface.