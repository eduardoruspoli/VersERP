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

## Banco de Dados

- SQLite

## Como executar

```bash
python -m venv .venv --without-pip
```

```bash
.venv\Scripts\activate
```

```bash
python -m ensurepip
```

```bash
pip install django
```

```bash
python manage.py runserver
```
---

## Estrutura Inicial do Projeto

```text
VersERP/
├── config/
├── core/
├── docs/
├── static/
├── templates/
├── manage.py
├── db.sqlite3
└── README.md
```

---

## Observações

Durante a criação do ambiente virtual foi necessário utilizar:

```powershell
python -m venv .venv --without-pip
```

Em seguida:

```powershell
python -m ensurepip
```

Essa abordagem resolveu o problema encontrado na criação automática do ambiente virtual utilizando o Python 3.14.