# Permissões e empresas

## Modelo de acesso

O VersERP combina duas dimensões:

- Django Groups/Permissions define quais ações o usuário pode executar;
- `UsuarioEmpresa` define em quais empresas ele pode operar.

A Central de Configurações administra perfis e vínculos conforme permissões próprias. `python manage.py sincronizar_perfis` cria ou sincroniza os perfis padrão. Superusuários têm acesso global; usuários comuns sem empresa autorizada não recebem dados operacionais.

## Aplicação no backend

Views usam autenticação e permissões funcionais, e querysets/services recortam objetos por empresa. Campos de seleção também devem limitar FKs ao escopo autorizado. Esconder botões é apenas apresentação e nunca substitui a validação no servidor.

O `EmpresaAccessMiddleware` bloqueia empresa explícita manipulada e complementa rotas mapeadas, mas a defesa principal permanece na consulta e operação do domínio. Downloads, PDFs, Compras, OFX e demais objetos empresariais seguem o mesmo princípio.

O Django Admin é reservado a usuários com acesso administrativo; possuir login operacional não concede acesso ao Admin.
