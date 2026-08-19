# Troubleshooting

- Migration pendente: rode `makemigrations --check --dry-run` e confira o model.
- Acesso 403/404: confira permissão funcional e vínculo `UsuarioEmpresa`.
- XLSX indisponível: instale `requirements-importacao.txt`.
- PDF: valide dependências de `xhtml2pdf` e assets estáticos.
- Testes lentos: execute primeiro o app afetado e depois a suíte completa.
