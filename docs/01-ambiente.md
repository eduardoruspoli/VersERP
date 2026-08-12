# Ambiente de Desenvolvimento

## Sistema Operacional

- Windows 11

## IDE

- Visual Studio Code

## Linguagens

- Python 3.14
- HTML5
- CSS3
- JavaScript

## Framework

- Django 6

Versão utilizada atualmente durante o desenvolvimento:

```text
Django 6.0.7
```

## Banco de Dados

Atualmente o projeto utiliza:

- SQLite

O SQLite é utilizado durante a fase inicial de desenvolvimento.

A arquitetura deverá permitir futura migração para um banco de dados mais adequado ao ambiente de produção.

---

## Ambiente Virtual

O projeto utiliza ambiente virtual Python localizado em:

```text
.venv/
```

### Criar o ambiente

No Windows:

```powershell
python -m venv .venv --without-pip
```

### Ativar

```powershell
.venv\Scripts\activate
```

### Instalar o pip

```powershell
python -m ensurepip
```

### Instalar dependências

```powershell
pip install -r requirements.txt
```

Caso o arquivo de dependências ainda não esteja atualizado:

```powershell
pip install django
```

---

## Executar o projeto

Com o ambiente virtual ativado:

```powershell
python manage.py runserver
```

O servidor de desenvolvimento ficará disponível normalmente em:

```text
http://127.0.0.1:8000/
```

---

## Comandos Django utilizados

Verificar o projeto:

```powershell
python manage.py check
```

Criar migrations:

```powershell
python manage.py makemigrations
```

Aplicar migrations:

```powershell
python manage.py migrate
```

Criar usuário administrativo:

```powershell
python manage.py createsuperuser
```

Executar servidor:

```powershell
python manage.py runserver
```

---

## Estrutura Atual do Projeto

```text
VersERP/
│
├── .venv/
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
├── README.md
└── requirements.txt
```

---

## Django Admin

O Django Admin está habilitado no projeto.

Endereço durante o desenvolvimento:

```text
http://127.0.0.1:8000/admin/
```

O módulo Pessoas está registrado no Admin.

---

## Observação sobre Python 3.14

Durante a criação inicial do ambiente virtual foi necessário utilizar:

```powershell
python -m venv .venv --without-pip
```

e posteriormente:

```powershell
python -m ensurepip
```

Essa abordagem resolveu o problema encontrado na criação automática do ambiente virtual utilizando Python 3.14.

---

## Ambiente de Produção

O servidor executado através de:

```powershell
python manage.py runserver
```

é exclusivamente para desenvolvimento.

Antes da publicação do VersERP deverão ser definidos:

- banco de dados de produção;
- servidor WSGI ou ASGI;
- configuração de variáveis de ambiente;
- tratamento da `SECRET_KEY`;
- configuração de `DEBUG`;
- configuração de `ALLOWED_HOSTS`;
- estratégia de arquivos estáticos;
- HTTPS;
- backups;
- logs;
- estratégia de deploy.