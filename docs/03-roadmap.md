# Roadmap

Este documento separa o que já está entregue das decisões ainda abertas. Não constitui promessa de prazo.

## Implementado

- fundação Django, interface responsiva e design system;
- autenticação, perfis, permissões e matriz usuário × empresa;
- cadastro de clientes e fornecedores;
- Comercial com propostas, revisões, formação de preço, workflow, PDF, acompanhamento e previsto × realizado;
- Obras/Centros de Custo vinculados a propostas aprovadas;
- Compras com solicitações, cotações, pedidos, recebimentos, documentos, divergências, previsto × comprado e integração financeira;
- Financeiro com pagar/receber, bancos, transferências, OFX, Plano de Contas, rateios, classificações múltiplas, dashboard, DRE e relatórios;
- RH com cadastro funcional, contratos, jornadas, ponto, banco de horas, eventos e conferência;
- Central de Configurações, Central de Relatórios, exportações e dashboard;
- importação histórica de propostas;
- configurações seguras e separadas para desenvolvimento/produção;
- preparação do projeto para PostgreSQL em produção, mantendo SQLite no desenvolvimento;
- configuração fail-closed do banco de produção e inclusão validada do Psycopg 3.

## Estabilização concluída

- suíte completa com 400 testes;
- checks do Django e migrations sem pendências;
- atualização para Django 6.0.8;
- correções de isolamento multiempresa em Compras e OFX;
- remoção de `.pyc`/`__pycache__` do versionamento;
- proteção de `.env`, SQLite e dados reais pelo `.gitignore`;
- configuração segura e separada para desenvolvimento e produção;
- documentação técnica revisada para refletir o estado atual.

## Próxima etapa

- preparação do runbook e implantação no ambiente Windows da infraestrutura da empresa.

## Pendências reais

- homologação operacional com usuários e dados representativos;
- revisão periódica de permissões e cenários multiempresa;
- definição de estratégia operacional para arquivos persistentes, logs e monitoramento;
- validação final dos procedimentos de backup e restauração na infraestrutura escolhida.

## Pendências de infraestrutura

- confirmação da versão/edição exata do Windows com o TI;
- versão e instalação definitiva do PostgreSQL;
- criação do banco, usuário e credenciais;
- DNS/nome interno e certificados;
- servidor WSGI/ASGI e proxy reverso;
- caminho e permissões do armazenamento corporativo;
- regras necessárias de firewall e VPN;
- política de backup, retenção, RPO/RTO e observabilidade.

Funcionalidades futuras somente devem entrar no roadmap após definição de escopo; este documento não presume estoque, emissão fiscal, assinatura digital ou outras integrações como já aprovadas.
