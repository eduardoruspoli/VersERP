# 🚀 VersERP

> Sistema ERP desenvolvido em Python/Django para gerenciamento
> comercial, financeiro e administrativo.

## 📖 Sobre o Projeto

O **VersERP** nasceu com o objetivo de substituir controles realizados
em planilhas e evoluir gradualmente para um ERP completo.

O projeto está sendo desenvolvido de forma modular, permitindo que
novas áreas de negócio sejam incorporadas progressivamente sem
comprometer a organização da aplicação.

## 🎯 Objetivos

- Eliminar controles descentralizados em planilhas
- Centralizar as informações da empresa
- Automatizar processos administrativos
- Integrar as áreas comercial, financeira e operacional
- Aprender e aplicar Python e Django em um projeto real
- Construir um projeto profissional e evolutivo

## 🛠 Tecnologias

- Python 3.14
- Django 6
- HTML5
- CSS3
- JavaScript
- SQLite
- Bootstrap Icons
- Git
- GitHub
- Visual Studio Code

## 🏗 Arquitetura

O VersERP utiliza a arquitetura **MVT (Model-View-Template)** do Django.

O projeto é organizado em aplicações independentes por domínio de
negócio.

Aplicações implementadas atualmente:

- `core` — estrutura geral e dashboard
- `pessoas` — clientes e fornecedores

Novos módulos serão adicionados seguindo a mesma estratégia de
modularização.

## 📂 Estrutura do Projeto

```text
VersERP/
│
├── config/
├── core/
├── pessoas/
├── docs/
├── static/
│   ├── css/
│   ├── icons/
│   ├── images/
│   └── js/
├── templates/
│   ├── includes/
│   └── base.html
├── db.sqlite3
├── manage.py
├── requirements.txt
└── README.md
```

## 👥 Módulo Pessoas

O módulo Pessoas é o primeiro módulo de negócio concluído do VersERP.

Ele centraliza o cadastro de:

- Pessoas Físicas
- Pessoas Jurídicas
- Clientes
- Fornecedores
- Pessoas que são simultaneamente clientes e fornecedores

### Funcionalidades

- Cadastro
- Edição
- Tela de detalhes
- Ativação e inativação
- Pesquisa
- Filtros
- Paginação
- Validação de CPF
- Validação de CNPJ
- Máscaras de documentos
- Consulta automática de CNPJ
- Preenchimento automático de dados empresariais

## 🔗 Integrações

### CNPJ.ws

O VersERP possui integração com a **CNPJ.ws** para auxiliar no cadastro
de Pessoas Jurídicas.

A consulta permite obter dados cadastrais de uma empresa a partir do
CNPJ e preencher automaticamente informações disponíveis no formulário.

Os dados retornados devem ser conferidos pelo usuário antes do
salvamento.

## 🎨 Interface

A interface do VersERP possui uma estrutura visual própria composta por:

- Sidebar
- Header
- Footer
- Dashboard
- Cards
- Tabelas
- Formulários
- Badges de status
- Design System baseado em variáveis CSS

Os estilos são separados por responsabilidade entre:

```text
base/
components/
layout/
pages/
```

## 📌 Roadmap

### Concluído

- [x] Planejamento inicial
- [x] Ambiente de desenvolvimento
- [x] Estrutura Django
- [x] Arquitetura inicial
- [x] Layout Base
- [x] Design System inicial
- [x] Sidebar
- [x] Header
- [x] Footer
- [x] Dashboard inicial
- [x] Módulo Pessoas
- [x] Integração para consulta de CNPJ

### Próximas etapas

- [ ] Autenticação e controle de acesso
- [ ] Comercial
- [ ] Financeiro
- [ ] Compras
- [ ] Relatórios
- [ ] Configurações

O planejamento detalhado está documentado em:

```text
docs/03-roadmap.md
```

## 📚 Documentação

A documentação técnica do projeto está localizada em:

```text
docs/
```

Arquivos principais:

```text
01-ambiente.md
02-arquitetura.md
03-roadmap.md
04-convencoes.md
CHANGELOG.md
```

A documentação é atualizada conforme o projeto evolui.

## ▶️ Executando o Projeto

Crie e ative o ambiente virtual conforme descrito em:

```text
docs/01-ambiente.md
```

Com o ambiente ativo, instale as dependências:

```powershell
pip install -r requirements.txt
```

Aplique as migrations:

```powershell
python manage.py migrate
```

Execute:

```powershell
python manage.py runserver
```

A aplicação ficará disponível normalmente em:

```text
http://127.0.0.1:8000/
```

## 📈 Status

**Versão atual:** `0.4.0`

🚧 **Em desenvolvimento.**

### Estado atual

- Fundação do sistema: concluída
- Interface base: concluída
- Módulo Pessoas: concluído para a etapa atual
- Próximos módulos: em planejamento

## 🔒 Produção

O VersERP ainda está em ambiente de desenvolvimento.

Antes da utilização em produção serão necessárias configurações
adicionais de:

- banco de dados;
- segurança;
- variáveis de ambiente;
- servidor WSGI/ASGI;
- HTTPS;
- arquivos estáticos;
- logs;
- backups;
- estratégia de deploy.

## 👨‍💻 Autor

Desenvolvido por **Eduardo Ruspoli**.

## 📄 Licença

Licença MIT.