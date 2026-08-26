# Runbook de Produção do VersERP — Windows Server 2019

Este runbook prepara a implantação do VersERP no servidor alvo confirmado: **Microsoft Windows Server 2019 Standard, versão 1809, build 17763.9020**. Ele não registra o sistema como já implantado e usa placeholders para todas as decisões ainda dependentes do TI.

## 1. Arquitetura alvo

```text
Usuário → navegador → rede corporativa/VPN → HTTPS/IIS
        → proxy reverso IIS → servidor WSGI → VersERP/Django → PostgreSQL local
Usuário baixa/exporta arquivos → salva manualmente na pasta corporativa → backup externo
```

- servidor: Windows Server 2019 Standard;
- uso inicial estimado: até quatro usuários simultâneos;
- acesso normal: navegador pela rede corporativa ou VPN, nunca RDP;
- diretório ilustrativo da aplicação: `<APP_ROOT>\VersERP`;
- IIS é o frontend confirmado e o PostgreSQL deverá ficar no mesmo servidor;
- DNS, portas internas, componentes do proxy, certificado e caminhos definitivos serão definidos com o TI.

## 2. Decisão crítica sobre compatibilidade

O Django 6.0 suporta PostgreSQL 14 ou superior. O Psycopg 3.3 suporta Python 3.10–3.14, PostgreSQL 10–18 e Windows. Entretanto, a matriz atual da EDB para os instaladores Windows dos PostgreSQL 14–18 lista Windows Server 2022 (e, em alguns casos, 2025), não Windows Server 2019.

Por isso, **não há neste momento uma combinação PostgreSQL 14+ com suporte oficial da EDB confirmada para o servidor alvo**. Isso não prova que o software seja tecnicamente inexequível no Windows Server 2019, mas separa claramente “instalável em teste” de “formalmente suportado pelo fornecedor”. Não se deve contornar isso instalando PostgreSQL 13: ele não é suportado pelo Django 6.0.

Recomendação técnica condicional: PostgreSQL 17.x, sempre no patch de segurança vigente na implantação, por ser um major maduro, mantido e compatível com Django 6.0/Psycopg 3. Como o banco obrigatoriamente ficará neste Windows Server 2019, o TI deverá obter suporte formal de uma distribuição que cubra a plataforma ou aceitar documentadamente o risco após homologação completa. A decisão final deve ocorrer antes do go-live.

O Python 3.14 possui suporte para Windows moderno, mas sua documentação alerta que o método MSIX pode não estar disponível no Windows Server 2019. O TI deve validar instalação x64 pelo método avançado aplicável e executar os testes deste runbook. O funcionamento no computador de desenvolvimento não comprova o funcionamento no servidor.

Referências primárias:

- [Django 6.0 — bancos suportados](https://docs.djangoproject.com/en/6.0/ref/databases/)
- [Psycopg — instalação e compatibilidade](https://www.psycopg.org/psycopg3/docs/basic/install.html)
- [EDB — matriz de plataformas](https://www.enterprisedb.com/resources/platform-compatibility)
- [EDB — instalação no Windows](https://www.enterprisedb.com/docs/supported-open-source/postgresql/installing/windows/)
- [Python 3.14 no Windows](https://docs.python.org/3.14/using/windows.html)
- [Waitress](https://docs.pylonsproject.org/projects/waitress/en/stable/)
- [Microsoft — proxy reverso com IIS, URL Rewrite e ARR](https://learn.microsoft.com/en-us/iis/extensions/url-rewrite-module/reverse-proxy-with-url-rewrite-v2-and-application-request-routing)
- [WinSW — Windows Service Wrapper](https://github.com/winsw/winsw)

## 3. Checklist de informações do TI

- [ ] arquitetura do Windows confirmada como x64
- [ ] hostname
- [ ] DNS/nome interno do VersERP
- [ ] certificado HTTPS
- [ ] IIS instalado/habilitado com os componentes necessários
- [ ] URL Rewrite 2.0 e Application Request Routing (ARR) disponíveis
- [ ] proxy reverso IIS configurado
- [ ] portas
- [ ] firewall
- [ ] acesso via VPN
- [ ] solução suportada e versão final do PostgreSQL
- [ ] local de instalação do PostgreSQL
- [ ] nome do banco
- [ ] usuário do banco
- [ ] forma segura de armazenamento/fornecimento da senha
- [ ] diretório da aplicação
- [ ] diretório dos PDFs/documentos
- [ ] conta Windows que executará o VersERP
- [ ] permissões da conta
- [ ] política de backup
- [ ] retenção
- [ ] logs
- [ ] monitoramento

## 4. Pré-requisitos

Antes da janela de implantação:

1. resolver e registrar a aceitação de suporte/homologação do PostgreSQL no Windows Server 2019;
2. validar Windows x64, atualizações do sistema e Python 3.14.x x64;
3. definir conta de serviço sem privilégios administrativos rotineiros;
4. instalar Git, Python e cliente PostgreSQL conforme política do TI;
5. definir versão validada do Waitress, wrapper de serviço, HTTPS/IIS e entrega de segredos;
6. liberar somente portas e diretórios estritamente necessários;
7. validar espaço para aplicação, banco, estáticos, logs e documentos.

O projeto usa Django 6.0.8 e `psycopg[binary]==3.3.4`. A distribuição binária do Psycopg inclui bibliotecas cliente, mas a instalação real no servidor deve ser comprovada por `pip check`, conexão ao PostgreSQL e smoke test. `xhtml2pdf` também deve ser validado com a geração de um PDF de teste.

## 5. Obtenção controlada do código

Produção deve usar um commit ou tag aprovado, nunca acompanhar automaticamente a branch de desenvolvimento.

```powershell
Set-Location <APP_ROOT>
git clone <REPOSITORY_URL> VersERP
Set-Location <APP_ROOT>\VersERP
git fetch --tags
git checkout <TAG_OU_COMMIT_APROVADO>
git rev-parse HEAD
```

Registrar no chamado de mudança: hash completo, data, responsável, versão do Python, versão do PostgreSQL e horário da implantação. O diretório definitivo será escolhido pelo TI.

## 6. Ambiente virtual e dependências

```powershell
Set-Location <APP_ROOT>\VersERP
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
```

Não instalar pacotes avulsos no Python global. Qualquer nova dependência de produção deve primeiro ser versionada e testada no projeto.

## 7. Variáveis de produção e segredos

Variáveis existentes no projeto:

```text
VERSERP_ENV=production
DJANGO_SECRET_KEY=<segredo forte e exclusivo>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=<hosts explícitos separados por vírgula>
DJANGO_CSRF_TRUSTED_ORIGINS=<origens HTTPS completas separadas por vírgula>
DJANGO_SECURE_HSTS_SECONDS=31536000
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=false
DJANGO_SECURE_HSTS_PRELOAD=false
DJANGO_TRUST_X_FORWARDED_PROTO=false
VERSERP_LOG_DIR=<diretório absoluto, existente e gravável>
DB_NAME=<nome do banco>
DB_USER=<usuário dedicado>
DB_PASSWORD=<senha entregue por meio seguro>
DB_HOST=<hostname ou IP do PostgreSQL>
DB_PORT=<porta definida pelo TI; padrão do projeto: 5432>
```

Em produção, o projeto falha ao iniciar se a chave for insegura, `DEBUG` estiver ativo, os hosts forem ausentes/coringa, as variáveis obrigatórias do PostgreSQL estiverem ausentes ou o diretório de logs não for absoluto, existente e gravável. Não há fallback para SQLite.

O projeto não lê `.env` automaticamente. O mecanismo definitivo deve ser fornecido ao processo/serviço pelo TI, com acesso restrito à conta de serviço. `.env`, `DJANGO_SECRET_KEY` e senha do PostgreSQL não entram no Git, logs, scripts compartilhados nem chamado sem proteção.

## 8. PostgreSQL

Somente após resolver a compatibilidade descrita na seção 2:

1. instalar uma distribuição e major oficialmente suportados na plataforma aprovada;
2. aplicar o patch de segurança vigente;
3. criar banco e usuário exclusivos do VersERP;
4. não conceder `SUPERUSER`, `CREATEDB` ou `CREATEROLE` à aplicação;
5. permitir ao usuário da aplicação operar apenas seu banco/schema;
6. restringir rede e autenticação no PostgreSQL;
7. configurar `DB_*` e testar conexão.

Como aplicação e banco estarão no mesmo servidor, deve-se preferir conexão local e impedir exposição desnecessária da porta PostgreSQL à rede. O valor definitivo de `DB_HOST` será estabelecido após o TI definir a configuração local.

Exemplo ilustrativo, a ser adaptado e executado pelo administrador do banco:

```sql
CREATE ROLE <DB_USER> LOGIN PASSWORD '<DB_PASSWORD>'
  NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE DATABASE <DB_NAME> OWNER <DB_USER> ENCODING 'UTF8';
```

Teste sem gravar senha no comando ou histórico:

```powershell
psql -h <DB_HOST> -p <DB_PORT> -U <DB_USER> -d <DB_NAME> -c "SELECT 1;"
```

Com as variáveis do processo já configuradas:

```powershell
python manage.py check
python manage.py showmigrations
python manage.py migrate
python manage.py showmigrations
```

As migrations criam o schema no PostgreSQL. SQLite permanece banco de desenvolvimento; `db.sqlite3` não deve ser copiado como banco definitivo. Carga ou migração de dados existentes é procedimento separado, com reconciliação e rollback próprios. Importadores históricos nunca devem rodar automaticamente no deploy.

### Homologação obrigatória do PostgreSQL no servidor alvo

Se o TI aceitar uma distribuição sem suporte formal atual ao Windows Server 2019, antes do go-live deverá existir banco de homologação no próprio servidor e evidência de:

- instalação e inicialização automática do serviço PostgreSQL;
- instalação do Psycopg e conexão do Django;
- criação do banco, migrations e `showmigrations`;
- suíte completa do projeto contra PostgreSQL;
- operações CRUD representativas e isolamento multiempresa;
- concorrência básica para os quatro usuários previstos;
- reinício do Windows e retorno do PostgreSQL/aplicação;
- backup e restauração em banco separado;
- encoding UTF-8, acentuação, datas, timezone e decimais;
- PDFs, estáticos, arquivos persistentes e smoke test.

Essa homologação demonstra compatibilidade prática daquele ambiente, mas **não substitui suporte formal do fornecedor**.

## 9. Inicialização administrativa

Em banco novo, a ordem é:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py sincronizar_perfis
```

Em atualização, validar se o superusuário já existe e executar `sincronizar_perfis` após as migrations. Credenciais iniciais devem ser entregues por canal seguro e trocadas conforme política do TI.

## 10. Arquivos estáticos

O projeto possui `STATIC_URL='static/'` e `STATIC_ROOT=<APP_ROOT>\VersERP\staticfiles`. A coleta é compatível:

```powershell
python manage.py collectstatic --noinput
```

Django/Waitress não deve servir estáticos como solução de produção. Com o IIS confirmado, a arquitetura recomendada é `collectstatic → STATIC_ROOT → IIS`: o IIS serve `/static/` diretamente e encaminha somente requisições dinâmicas ao Waitress. A conta que executa `collectstatic` precisa escrever no diretório; o IIS precisa somente de leitura. Regras e ACLs ainda devem ser configuradas e testadas.

## 11. PDFs, planilhas e documentos

O comportamento correto e preservado é:

- propostas e pedidos geram PDF sob demanda com `xhtml2pdf`;
- o PDF é criado em memória (`BytesIO`) e retornado ao navegador;
- não existem `MEDIA_ROOT`/`MEDIA_URL` para publicação de documentos;
- o VersERP não arquiva automaticamente PDFs ou exportações;
- o usuário visualiza/baixa o arquivo e decide manualmente onde salvá-lo;
- arquivos que exigirem retenção são salvos pelo usuário na pasta corporativa adequada;
- a infraestrutura inclui essas pastas no backup externo/nuvem.

Não será criado `DOCUMENT_ROOT`, `MEDIA_ROOT`, `FileField` ou metadado de arquivamento por causa desse fluxo. A ausência de persistência automática **não é gap de deploy**. O item operacional é validar com o TI as pastas corporativas, suas permissões e o backup; com os usuários, validar o procedimento manual de nomenclatura e arquivamento.

## 12. Servidor WSGI e serviço Windows

O projeto expõe `config.wsgi.application` e fixa `waitress==3.0.2` como servidor WSGI de produção. O import foi validado localmente com Python 3.14.6 x64; a mesma combinação deverá ser confirmada no servidor.

Para este sistema síncrono e cerca de quatro usuários, **Waitress 3.0.2/WSGI** é puro Python, compatível com Windows e requer Python 3.9+. Django consome servidores WSGI compatíveis e o entrypoint real é `config.wsgi:application`. Gunicorn não é escolha automática no Windows; Uvicorn/Daphne agregariam complexidade sem necessidade assíncrona identificada.

Com Waitress futuramente instalado, o comando conceitual seria:

```powershell
<APP_ROOT>\VersERP\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:<PORTA_INTERNA> config.wsgi:application
```

`runserver` é proibido em produção. A arquitetura de reinicialização deve ser:

```text
Windows inicia → serviço VersERP inicia → Waitress inicia → Django disponível
```

Waitress deve escutar somente em loopback; a rede corporativa acessará exclusivamente o IIS.

Recomendação: **WinSW**, por possuir configuração declarativa, working directory, variáveis, logs e gerenciamento de executáveis como serviço. Usar conta dedicada, caminhos absolutos, variáveis seguras, reinício em falha e captura de stdout/stderr. NSSM é mais simples e conhecido, mas governança, atualização e suporte devem ser aceitos pelo TI. Serviço próprio com `pywin32` exigiria código e manutenção sem benefício atual. O requisito de serviço é confirmado; somente ferramenta e configuração permanecem por validar.

## 13. HTTPS e proxy

Arquitetura recomendada:

```text
Cliente → HTTPS/IIS → HTTP em 127.0.0.1:<PORTA_INTERNA> → Waitress/WSGI → Django
```

IIS é o frontend escolhido. Para atuar como proxy reverso, a solução usual documentada pela Microsoft requer **URL Rewrite 2.0** e **Application Request Routing (ARR)**, que não devem ser presumidos instalados. O site deverá terminar TLS, servir `/static/`, encaminhar rotas dinâmicas para o loopback do Waitress, preservar o `Host` necessário e remover/sobrescrever cabeçalhos externos conflitantes.

Com `VERSERP_ENV=production`, o Django ativa `SECURE_SSL_REDIRECT`, cookies seguros de sessão/CSRF e HSTS. Como IIS termina HTTPS e o salto local é HTTP, `DJANGO_TRUST_X_FORWARDED_PROTO=true` será necessário somente depois de configurar o IIS para sobrescrever de forma confiável `X-Forwarded-Proto=https`; sem isso pode ocorrer loop de redirecionamento. `DJANGO_ALLOWED_HOSTS` depende do DNS, `DJANGO_CSRF_TRUSTED_ORIGINS` exige a origem HTTPS completa e `HSTS_INCLUDE_SUBDOMAINS`/`HSTS_PRELOAD` só podem ser ativados após validação de todo o domínio. DNS, certificado, regra ARR/Rewrite, headers e firewall ainda precisam de configuração operacional.

## 14. Logs e monitoramento

O Django possui logging de produção em `VERSERP_LOG_DIR`, com nível `WARNING`, UTF-8, rotação em 10 MiB e dez arquivos de retenção local. Waitress permanece em stdout/stderr para captura pelo wrapper; IIS e PostgreSQL mantêm logs próprios. O TI ainda deve definir diretórios definitivos, retenção corporativa, ACL, coleta, alertas e correlação de horário.

Não existe endpoint dedicado de health check. Para a topologia simples ele é **MELHORIA FUTURA**; inicialmente o serviço pode ser monitorado por processo, porta e requisição autenticada/não destrutiva. Se o proxy ou monitor corporativo exigir endpoint, ele deverá ser implementado e testado antes da integração.

## 15. Validação técnica antes de iniciar o serviço

```powershell
python -m pip check
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py showmigrations
python manage.py collectstatic --noinput
```

O `check --deploy` deve rodar com as variáveis reais do processo e não substitui o teste HTTPS. Não criar migrations diretamente em produção.

## 16. Backup e restauração

São duas categorias independentes e obrigatórias. O backup deve abranger:

- PostgreSQL, com ferramenta compatível com o major escolhido;
- pastas corporativas onde os usuários salvam manualmente PDFs e exportações;
- inventário das configurações necessárias, sem expor segredos no backup documental;
- commit/tag implantado e versões do runtime.

O backup do PostgreSQL não substitui o das pastas corporativas; o backup das pastas não substitui o banco. O TI definirá backup lógico/físico do PostgreSQL, mecanismo externo/nuvem para os arquivos salvos pelos usuários, frequência, criptografia, retenção, RPO e RTO. Antes do go-live deve existir **teste conjunto de restauração em ambiente isolado**, seguido de migrations, checks, conferência de arquivos e reconciliação.

## 17. Rollback

Antes de cada deploy:

1. registrar commit/tag atual e novo;
2. parar escritas ou abrir janela de manutenção;
3. obter backup consistente do banco e dos documentos;
4. confirmar que a restauração foi planejada;
5. aplicar código, dependências, migrations e estáticos.

Rollback de código consiste em retornar ao commit/tag anterior, restaurar dependências/estáticos e reiniciar o serviço. Porém, após migration destrutiva ou incompatível, **não** reverter apenas o código: avaliar schema e dados e, se necessário, restaurar banco e documentos do mesmo ponto no tempo. Registrar a decisão e validar com smoke test.

## 18. Smoke test pós-deploy

- [ ] login abre
- [ ] autenticação funciona
- [ ] dashboard abre
- [ ] empresa e permissões estão corretas
- [ ] Comercial abre
- [ ] proposta pode ser consultada
- [ ] PDF de teste pode ser gerado
- [ ] Compras abre
- [ ] Financeiro abre
- [ ] RH abre
- [ ] documentos persistem no local esperado
- [ ] logout funciona
- [ ] acesso interno funciona
- [ ] acesso por VPN funciona

Usar registros controlados e evitar alterações desnecessárias em dados reais.

## 19. Checklist pré-go-live

- [ ] commit/tag correto
- [ ] Python validado
- [ ] venv criado
- [ ] requirements instalados
- [ ] `pip check` aprovado
- [ ] PostgreSQL aprovado pelo TI e homologado instalado
- [ ] banco criado
- [ ] usuário dedicado criado
- [ ] variáveis configuradas
- [ ] `DEBUG=False`
- [ ] `ALLOWED_HOSTS` validado
- [ ] origens CSRF validadas
- [ ] migrations aplicadas
- [ ] `collectstatic` executado
- [ ] servidor WSGI instalado e testado
- [ ] serviço Windows configurado e testado após reinício
- [ ] HTTPS validado
- [ ] pastas corporativas e procedimento manual de arquivamento validados
- [ ] permissões e usuários validados
- [ ] backup executado
- [ ] teste de restauração planejado e aprovado
- [ ] logs definidos
- [ ] rede e firewall validados
- [ ] VPN validada
- [ ] smoke test aprovado

## 20. Atualizações futuras

```text
desenvolvimento → testes → commit/tag aprovado → backup
→ janela de manutenção → atualizar código
→ atualizar requirements somente quando versionados → migrate
→ collectstatic → reiniciar serviço → smoke test
```

Nunca usar `git pull` indiscriminado em produção nem executar importadores históricos como parte automática desse fluxo.

## 21. Gaps de deploy

### BLOQUEADOR

1. **PostgreSQL/Windows:** o banco deve ficar no Server 2019, mas nenhuma versão PostgreSQL 14+ suportada pelo Django 6.0 aparece na matriz EDB atual como formalmente suportada nesse sistema. TI deve obter suporte ou formalizar risco e homologação.
2. **Serviço Windows:** o serviço é obrigatório, mas wrapper, conta, variáveis, reinício e permissões não foram configurados.
3. **IIS/HTTPS/rede:** IIS é requisito, mas ARR/URL Rewrite, DNS, certificado, regra, headers, porta interna e firewall ainda não foram configurados.
4. **Arquivos estáticos:** `collectstatic` existe, mas falta configurar IIS e ACLs para `STATIC_ROOT`.
5. **Segredos:** falta escolher o mecanismo seguro que fornecerá variáveis à conta de serviço.

### IMPORTANTE

1. **Python no servidor:** validar Python 3.14 x64 e método de instalação compatível com Server 2019.
2. **Dependências:** comprovar `psycopg[binary]`, `xhtml2pdf` e Waitress no servidor.
3. **Logs:** logging Django está implementado; faltam destino definitivo, logs do serviço/IIS/PostgreSQL e monitoramento.
4. **Backup/restore:** ferramenta, retenção, RPO/RTO e teste de restauração estão pendentes.
5. **Dados:** carga inicial ou migração do SQLite deve ser planejada separadamente e reconciliada.
6. **Filesystem:** diretórios e ACLs da aplicação, estáticos, logs e documentos não estão definidos.
7. **Homologação:** faltam smoke test e validação operacional no ambiente final.

### MELHORIA FUTURA

1. endpoint dedicado de health check;
2. observabilidade centralizada e alertas avançados;
3. automação controlada de deploy/rollback após estabilização do primeiro go-live.

Enquanto os itens bloqueadores permanecerem, o VersERP está **preparado em parte**, mas não pode ser declarado pronto para implantação. IIS, serviço Windows e PostgreSQL local são requisitos confirmados; pastas corporativas e seu backup são responsabilidades operacionais da infraestrutura, sem persistência automática pelo VersERP.
