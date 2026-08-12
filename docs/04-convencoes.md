# Convenções do Projeto

Este documento define padrões utilizados no desenvolvimento do VersERP.

O objetivo é manter consistência à medida que novos módulos forem adicionados.

---

## Python

### Classes

Utilizar `PascalCase`.

Exemplo:

```python
class PessoaForm:
    pass
```

### Funções e métodos

Utilizar `snake_case`.

Exemplo:

```python
def lista_pessoas():
    pass
```

### Variáveis

Utilizar `snake_case`.

Exemplo:

```python
razao_social = ""
```

### Models

Utilizar nome no singular.

Exemplos:

```text
Pessoa
Proposta
ContaReceber
```

---

## Aplicações Django

Apps devem representar domínios ou responsabilidades claras.

Exemplos:

```text
core
pessoas
comercial
financeiro
compras
```

Evitar colocar models de domínio dentro do `core`.

---

## Templates

Nomes de arquivos devem utilizar `snake_case`.

Exemplos:

```text
lista.html
formulario.html
detalhe.html
```

Templates específicos de um app devem utilizar namespace de diretório.

Exemplo:

```text
pessoas/templates/pessoas/lista.html
```

---

## URLs

Cada aplicação deve possuir seu próprio `urls.py`.

Quando aplicável, utilizar `app_name`.

Exemplo:

```python
app_name = "pessoas"
```

Uso nos templates:

```django
{% url 'pessoas:lista' %}
```

---

## CSS

Utilizar classes descritivas e reutilizáveis.

Exemplos:

```text
.page-header
.dashboard-panel
.status-badge
.detail-card
```

Evitar estilos inline sempre que possível.

Utilizar variáveis do Design System em vez de repetir valores diretamente.

Exemplo:

```css
color: var(--primary);
background: var(--surface);
border: 1px solid var(--border);
```

---

## Organização do CSS

Separar estilos por responsabilidade:

```text
base/
components/
layout/
pages/
```

Evitar concentrar todo o CSS em um único arquivo.

---

## Banco de Dados

Models devem utilizar nomes no singular.

Cadastros utilizados como referência por outros módulos devem evitar exclusão física quando houver necessidade de preservar histórico.

Para Pessoa, o padrão atual é:

```text
ativo = True / False
```

---

## CPF e CNPJ

Documentos devem ser armazenados sem caracteres de formatação sempre que possível.

Exemplo armazenado:

```text
36119890000100
```

Exemplo apresentado:

```text
36.119.890/0001-00
```

A validação de integridade do documento deve ocorrer no backend.

Máscaras de entrada podem ser tratadas no frontend.

---

## Formulários

Validações relevantes para integridade dos dados devem existir no backend, mesmo quando também houver validação ou máscara no navegador.

O frontend melhora a experiência do usuário.

O backend é responsável por garantir a validade dos dados recebidos.

---

## Integrações Externas

APIs externas devem preferencialmente ser consumidas pelo backend quando houver necessidade de:

- normalização;
- tratamento de erros;
- proteção da arquitetura interna;
- futura substituição do fornecedor.

A interface não deve depender diretamente da estrutura bruta retornada pela API externa.

---

## Commits

Utilizar Conventional Commits.

Principais tipos:

```text
feat:
fix:
docs:
refactor:
style:
test:
chore:
```

Exemplos:

```text
feat: implementa cadastro de pessoas
fix: corrige validacao de cnpj
docs: atualiza arquitetura do projeto
refactor: reorganiza estrutura css
```

Commits devem representar checkpoints coerentes do desenvolvimento.

---

## Git

Antes de mudanças estruturais importantes, criar um checkpoint.

Fluxo recomendado:

```powershell
git status
git add .
git commit -m "tipo: descricao"
git push
```

Não versionar:

- `.venv`;
- arquivos temporários;
- credenciais;
- segredos;
- configurações locais sensíveis.

---

## Segurança

Credenciais e chaves privadas não devem ser adicionadas diretamente ao repositório.

Antes da implantação em produção, configurações sensíveis deverão ser movidas para variáveis de ambiente.

---

## Idioma

O código pode utilizar nomenclatura em português nos domínios de negócio quando isso melhorar a clareza do ERP.

Exemplos:

```text
Pessoa
razao_social
classificacao
ativo
```

Termos técnicos próprios do framework permanecem conforme a convenção do Django.