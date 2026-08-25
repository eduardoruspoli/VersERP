from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch
from pypdf import PdfReader

from financeiro.models import CentroCusto, Empresa, LancamentoFinanceiro, PlanoConta, RateioCentroCusto
from pessoas.models import Pessoa
from core.models import UsuarioEmpresa

from .models import ModeloConteudoProposta, Proposta, PropostaItem, PropostaLinhaPublica, PropostaRevisao, PropostaTributo
from .services import aprovar_proposta, calcular_precificacao, calcular_previsto_realizado, cancelar_proposta, colocar_em_negociacao, criar_nova_revisao, criar_proposta, enviar_proposta, montar_contexto_publico_proposta, rejeitar_proposta, sincronizar_linhas_publicas_automaticas, validar_fechamento_publico


class ComercialBase(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="comercial", password="teste123")
        self.empresa = Empresa.objects.create(razao_social="Empresa Teste", nome_fantasia="Vers Teste", cnpj="11.111.111/0001-11")
        UsuarioEmpresa.objects.create(usuario=self.usuario, empresa=self.empresa)
        self.cliente = Pessoa.objects.create(razao_social="Cliente Teste", classificacao=Pessoa.Classificacao.CLIENTE, ativo=True, cpf_cnpj="22.222.222/0001-22")
        self.fornecedor = Pessoa.objects.create(razao_social="Fornecedor Secreto", classificacao=Pessoa.Classificacao.FORNECEDOR, ativo=True)
        self.proposta, self.revisao = criar_proposta(empresa=self.empresa, codigo="VERS1917", cliente=self.cliente, nome_servico="Serviço TESTE", usuario=self.usuario)

    def item(self, custo="100.00", quantidade="1"):
        return PropostaItem.objects.create(revisao=self.revisao, tipo=PropostaItem.Tipo.MATERIAL, descricao="Material interno", quantidade=Decimal(quantidade), custo_unitario=Decimal(custo), fornecedor=self.fornecedor)

    def linha(self, valor="150.00", grupo=PropostaLinhaPublica.Grupo.MATERIAL):
        return PropostaLinhaPublica.objects.create(revisao=self.revisao, grupo=grupo, descricao="Solução fornecida", valor_total=Decimal(valor))


class DominioPropostaTests(ComercialBase):
    def test_numero_informado_e_preservado(self):
        segunda, _ = criar_proposta(empresa=self.empresa, codigo="VERS1918", cliente=self.cliente, nome_servico="Outra")
        self.assertEqual((self.proposta.codigo, segunda.codigo), ("VERS1917", "VERS1918"))

    def test_numero_e_normalizado_para_maiusculas_e_sem_espacos(self):
        proposta, _ = criar_proposta(empresa=self.empresa, codigo="  vers 1918  ", cliente=self.cliente, nome_servico="Normalizada")
        self.assertEqual(proposta.codigo, "VERS1918")
        self.assertEqual(proposta.numero_sequencial, 1918)

    def test_formato_invalido_e_rejeitado(self):
        with self.assertRaises(ValidationError):
            criar_proposta(empresa=self.empresa, codigo="PROP-1918", cliente=self.cliente, nome_servico="Inválida")

    def test_numero_duplicado_na_mesma_empresa_e_rejeitado(self):
        with self.assertRaises(ValidationError):
            criar_proposta(empresa=self.empresa, codigo="vers1917", cliente=self.cliente, nome_servico="Duplicada")

    def test_mesmo_numero_em_empresas_diferentes(self):
        outra_empresa = Empresa.objects.create(razao_social="Outra Empresa", cnpj="44.444.444/0001-44")
        proposta, _ = criar_proposta(empresa=outra_empresa, codigo="VERS1917", cliente=self.cliente, nome_servico="Outra empresa")
        self.assertEqual(proposta.codigo, "VERS1917")

    def test_criacao_sem_modelo_conteudo(self):
        self.assertIsNone(self.revisao.modelo_conteudo)
        self.assertEqual(self.revisao.numero, 0)

    def test_nova_proposta_nao_renumera_existente(self):
        codigo_original = self.proposta.codigo
        criar_proposta(empresa=self.empresa, codigo="VERS3000", cliente=self.cliente, nome_servico="Nova")
        self.proposta.refresh_from_db()
        self.assertEqual(self.proposta.codigo, codigo_original)

    def test_modelo_padrao_e_copiado_como_snapshot(self):
        modelo = ModeloConteudoProposta.objects.create(empresa=self.empresa, nome="Padrão", padrao=True, texto_introdutorio="Texto original")
        _, revisao = criar_proposta(empresa=self.empresa, codigo="VERS1918", cliente=self.cliente, nome_servico="Nova")
        modelo.texto_introdutorio = "Texto alterado"
        modelo.save()
        revisao.refresh_from_db()
        self.assertEqual(revisao.texto_introdutorio, "Texto original")
        self.assertEqual(revisao.modelo_conteudo_id, modelo.pk)

    def test_nova_proposta_cria_somente_revisao_zero_preparada(self):
        modelo = ModeloConteudoProposta.objects.create(
            empresa=self.empresa, nome="Modelo criação", ativo=True, padrao=True,
            texto_introdutorio="Apresentação padrão", normas_procedimentos="Normas padrão",
        )
        proposta, revisao = criar_proposta(
            empresa=self.empresa, codigo="VERS1918", cliente=self.cliente,
            nome_servico="Instalação elétrica", usuario=self.usuario,
            aos_cuidados_de="Maria", escopo_incluido="Escopo desta proposta",
            prazo_entrega="20 dias", condicao_pagamento="30 dias", validade_dias=20,
        )
        self.assertEqual(proposta.revisoes.count(), 1)
        self.assertEqual(revisao.numero, 0)
        self.assertEqual(revisao.modelo_conteudo, modelo)
        self.assertEqual(revisao.texto_introdutorio, "Apresentação padrão")
        self.assertEqual(revisao.normas_procedimentos, "Normas padrão")
        self.assertEqual(revisao.nome_servico, "Instalação elétrica")
        self.assertEqual(revisao.aos_cuidados_de, "Maria")
        self.assertEqual(revisao.escopo_incluido, "Escopo desta proposta")
        self.assertEqual(revisao.condicao_pagamento, "30 dias")
        self.assertEqual(revisao.validade_dias, 20)

    def test_dado_digitado_prevalece_sobre_modelo_e_branco_mantem_padrao(self):
        ModeloConteudoProposta.objects.create(
            empresa=self.empresa, nome="Modelo padrão", ativo=True, padrao=True,
            observacoes_comerciais="Observação padrão", texto_introdutorio="Texto padrão",
        )
        _, revisao = criar_proposta(
            empresa=self.empresa, codigo="VERS1918", cliente=self.cliente, nome_servico="Nova",
            observacoes_comerciais="Observação específica", texto_introdutorio="",
        )
        self.assertEqual(revisao.observacoes_comerciais, "Observação específica")
        self.assertEqual(revisao.texto_introdutorio, "Texto padrão")

    def test_modelo_de_outra_empresa_nao_e_aplicado(self):
        outra = Empresa.objects.create(razao_social="Outra empresa", cnpj="44.444.444/0001-44")
        ModeloConteudoProposta.objects.create(empresa=outra, nome="Padrão outra", ativo=True, padrao=True, texto_introdutorio="Não aplicar")
        _, revisao = criar_proposta(empresa=self.empresa, codigo="VERS1918", cliente=self.cliente, nome_servico="Nova")
        self.assertIsNone(revisao.modelo_conteudo)
        self.assertEqual(revisao.texto_introdutorio, "")

    def test_nova_logica_nao_modifica_proposta_historica_existente(self):
        historica = Proposta.objects.create(
            empresa=self.empresa, cliente=self.cliente, codigo="VERS1800", numero_sequencial=1800,
            origem=Proposta.Origem.IMPORTADO_HISTORICO, status_historico="faturada",
        )
        revisao_historica = PropostaRevisao.objects.create(
            proposta=historica, numero=0, data_proposta=date(2026, 1, 1),
            nome_servico="Histórico preservado", preco_venda_final=Decimal("123.45"), congelada=True,
        )
        ModeloConteudoProposta.objects.create(empresa=self.empresa, nome="Novo padrão", ativo=True, padrao=True, texto_introdutorio="Novo texto")
        criar_proposta(empresa=self.empresa, codigo="VERS1918", cliente=self.cliente, nome_servico="Nova")
        historica.refresh_from_db()
        revisao_historica.refresh_from_db()
        self.assertEqual(historica.status_historico, "faturada")
        self.assertEqual(revisao_historica.nome_servico, "Histórico preservado")
        self.assertEqual(revisao_historica.preco_venda_final, Decimal("123.45"))
        self.assertEqual(revisao_historica.texto_introdutorio, "")

    def test_custo_total_item_e_derivado(self):
        item = self.item("12.3456", "2")
        self.assertEqual(item.custo_total, Decimal("24.69"))

    def test_margem_item_soma_ao_valor_fornecedor_como_planilha(self):
        item = PropostaItem.objects.create(
            revisao=self.revisao,
            tipo=PropostaItem.Tipo.MATERIAL,
            descricao="Tinta",
            quantidade=Decimal("4"),
            custo_unitario=Decimal("125.00"),
            margem_formacao=Decimal("86"),
        )
        self.assertEqual(item.valor_unitario_venda, Decimal("232.50"))
        self.assertEqual(item.valor_total_venda, Decimal("930.00"))

        self.revisao.formacao_preco = PropostaRevisao.FormacaoPreco.MARKUP
        self.revisao.percentual_formacao = Decimal("0")
        self.revisao.save()
        calculo = calcular_precificacao(self.revisao)
        self.assertEqual(calculo["custo_total"], Decimal("500.00"))
        self.assertEqual(calculo["preco_final"], Decimal("930.00"))
        self.assertEqual(calculo["resultado"], Decimal("430.00"))

    def test_juros_antecipacao_usa_total_material_taxa_e_prazo(self):
        PropostaItem.objects.create(
            revisao=self.revisao, tipo=PropostaItem.Tipo.MATERIAL, descricao="Materiais",
            quantidade=Decimal("1"), custo_unitario=Decimal("13047.90"), margem_formacao=Decimal("0"),
        )
        juros = PropostaItem.objects.create(
            revisao=self.revisao, tipo=PropostaItem.Tipo.JUROS_ANTECIPACAO,
            descricao="Juros de Antecipação", quantidade=Decimal("1"), unidade="VB",
            custo_unitario=Decimal("0"), margem_formacao=Decimal("0"),
            taxa_juros_mensal=Decimal("2.4"), prazo_antecipacao_dias=90,
        )
        self.assertEqual(juros.base_juros_antecipacao, Decimal("13047.90"))
        self.assertEqual(juros.meses_antecipacao, Decimal("3.0000"))
        self.assertEqual(juros.valor_unitario_venda, Decimal("313.15"))
        self.assertEqual(juros.valor_total_venda, Decimal("939.45"))
        self.assertEqual(juros.custo_total, Decimal("0.00"))

    def test_juros_antecipacao_180_dias_equivale_a_seis_meses(self):
        PropostaItem.objects.create(
            revisao=self.revisao, tipo=PropostaItem.Tipo.MATERIAL, descricao="Materiais",
            quantidade=Decimal("1"), custo_unitario=Decimal("13047.90"), margem_formacao=Decimal("0"),
        )
        juros = PropostaItem.objects.create(
            revisao=self.revisao, tipo=PropostaItem.Tipo.JUROS_ANTECIPACAO,
            descricao="Juros de Antecipação", quantidade=Decimal("1"), unidade="VB",
            custo_unitario=Decimal("0"), margem_formacao=Decimal("0"),
            taxa_juros_mensal=Decimal("2.4"), prazo_antecipacao_dias=180,
        )
        self.assertEqual(juros.meses_antecipacao, Decimal("6.0000"))
        self.assertEqual(juros.valor_total_venda, Decimal("1878.90"))

    def test_juros_antecipacao_entra_no_total_de_servicos_sem_aumentar_custo(self):
        material = PropostaItem.objects.create(
            revisao=self.revisao, tipo=PropostaItem.Tipo.MATERIAL, descricao="Materiais",
            quantidade=Decimal("1"), custo_unitario=Decimal("1000"), margem_formacao=Decimal("0"),
        )
        PropostaItem.objects.create(
            revisao=self.revisao, tipo=PropostaItem.Tipo.JUROS_ANTECIPACAO,
            descricao="Juros de Antecipação", quantidade=Decimal("1"), unidade="VB",
            custo_unitario=Decimal("0"), margem_formacao=Decimal("0"),
            taxa_juros_mensal=Decimal("2.4"), prazo_antecipacao_dias=90,
        )
        self.revisao.formacao_preco = PropostaRevisao.FormacaoPreco.MARKUP
        self.revisao.save()
        sincronizar_linhas_publicas_automaticas(self.revisao)
        servico = self.revisao.linhas_publicas.get(origem_automatica=True, grupo=PropostaLinhaPublica.Grupo.SERVICO)
        calculo = calcular_precificacao(self.revisao)
        self.assertEqual(material.valor_total_venda, Decimal("1000.00"))
        self.assertEqual(servico.valor_total, Decimal("72.00"))
        self.assertEqual(calculo["custo_total"], Decimal("1000.00"))
        self.assertEqual(calculo["preco_final"], Decimal("1072.00"))

    def test_resumo_publico_material_e_servicos_e_gerado_automaticamente(self):
        PropostaItem.objects.create(
            revisao=self.revisao, tipo=PropostaItem.Tipo.MATERIAL, descricao="Tinta",
            quantidade=Decimal("4"), custo_unitario=Decimal("125"), margem_formacao=Decimal("86"),
        )
        PropostaItem.objects.create(
            revisao=self.revisao, tipo=PropostaItem.Tipo.MAO_OBRA, descricao="Serviço",
            quantidade=Decimal("2"), custo_unitario=Decimal("100"), margem_formacao=Decimal("50"),
        )
        sincronizar_linhas_publicas_automaticas(self.revisao)
        material = self.revisao.linhas_publicas.get(origem_automatica=True, grupo=PropostaLinhaPublica.Grupo.MATERIAL)
        servico = self.revisao.linhas_publicas.get(origem_automatica=True, grupo=PropostaLinhaPublica.Grupo.SERVICO)
        self.assertEqual(material.descricao, "MATERIAL")
        self.assertEqual(material.valor_total, Decimal("930.00"))
        self.assertEqual(servico.descricao, "SERVIÇOS")
        self.assertEqual(servico.valor_total, Decimal("300.00"))

    def test_valor_publico_editado_manualmente_nao_e_sobrescrito(self):
        item = PropostaItem.objects.create(
            revisao=self.revisao, tipo=PropostaItem.Tipo.MATERIAL, descricao="Tinta",
            quantidade=Decimal("1"), custo_unitario=Decimal("100"), margem_formacao=Decimal("50"),
        )
        sincronizar_linhas_publicas_automaticas(self.revisao)
        linha = self.revisao.linhas_publicas.get(origem_automatica=True, grupo=PropostaLinhaPublica.Grupo.MATERIAL)
        linha.valor_total = Decimal("175")
        linha.valor_automatico = False
        linha.save(update_fields=["valor_total", "valor_automatico"])
        item.quantidade = Decimal("2")
        item.save()
        sincronizar_linhas_publicas_automaticas(self.revisao)
        linha.refresh_from_db()
        self.assertEqual(linha.valor_total, Decimal("175.00"))

    def test_item_sem_margem_propria_usa_margem_padrao_revisao(self):
        self.revisao.formacao_preco = PropostaRevisao.FormacaoPreco.MARKUP
        self.revisao.percentual_formacao = Decimal("50")
        self.revisao.save()
        item = self.item("100", "2")
        self.assertEqual(item.margem_formacao_efetiva, Decimal("50"))
        self.assertEqual(item.valor_unitario_venda, Decimal("150.00"))
        self.assertEqual(calcular_precificacao(self.revisao)["preco_final"], Decimal("300.00"))

    def test_markup_com_tributos(self):
        self.item()
        self.revisao.percentual_formacao = Decimal("50")
        self.revisao.save()
        PropostaTributo.objects.create(revisao=self.revisao, nome="Impostos", percentual=Decimal("10"))
        calculo = calcular_precificacao(self.revisao)
        self.assertEqual(calculo["preco_final"], Decimal("166.67"))
        self.assertEqual(calculo["tributos"], Decimal("16.67"))

    def test_margem_com_tributos(self):
        self.item()
        self.revisao.formacao_preco = PropostaRevisao.FormacaoPreco.MARGEM
        self.revisao.percentual_formacao = Decimal("20")
        self.revisao.save()
        PropostaTributo.objects.create(revisao=self.revisao, nome="Impostos", percentual=Decimal("10"))
        self.assertEqual(calcular_precificacao(self.revisao)["preco_final"], Decimal("142.86"))

    def test_preco_manual(self):
        self.item()
        self.revisao.formacao_preco = PropostaRevisao.FormacaoPreco.MANUAL
        self.revisao.preco_venda_final = Decimal("230")
        self.revisao.save()
        self.assertEqual(calcular_precificacao(self.revisao)["preco_final"], Decimal("230.00"))

    def test_linhas_publicas_nao_alteram_precificacao(self):
        self.item()
        antes = calcular_precificacao(self.revisao)
        self.linha("9999")
        self.assertEqual(calcular_precificacao(self.revisao), antes)

    def test_fechamento_publico_exato(self):
        self.revisao.preco_venda_final = Decimal("150")
        self.revisao.save()
        self.linha("149.99")
        with self.assertRaises(ValidationError):
            validar_fechamento_publico(self.revisao)

    def test_envio_recalcula_valida_e_congela(self):
        self.item()
        self.revisao.percentual_formacao = Decimal("50")
        self.revisao.save()
        self.linha("150")
        enviada = enviar_proposta(self.revisao, self.usuario)
        self.assertTrue(enviada.congelada)
        self.assertEqual(enviada.preco_venda_final, Decimal("150.00"))
        self.proposta.refresh_from_db()
        self.assertEqual(self.proposta.status, Proposta.Status.ENVIADA)

    def test_revisao_congelada_bloqueia_item(self):
        self.item(); self.revisao.percentual_formacao = Decimal("50"); self.revisao.save(); self.linha("150"); enviar_proposta(self.revisao)
        with self.assertRaises(ValidationError):
            PropostaItem.objects.create(revisao=self.revisao, tipo=PropostaItem.Tipo.OUTROS, descricao="Novo", quantidade=1, custo_unitario=1)

    def test_nova_revisao_clona_dados_e_descongela(self):
        self.item(); self.revisao.percentual_formacao = Decimal("50"); self.revisao.save(); self.linha("150"); enviar_proposta(self.revisao)
        nova = criar_nova_revisao(self.revisao, self.usuario)
        self.assertEqual(nova.numero, 1)
        self.assertFalse(nova.congelada)
        self.assertEqual(nova.itens.count(), 1)
        self.assertEqual(nova.linhas_publicas.count(), 1)

    def test_visibilidade_preserva_snapshot(self):
        self.revisao.normas_procedimentos = "NR-10"
        self.revisao.exibir_normas_procedimentos = False
        self.revisao.save()
        contexto = montar_contexto_publico_proposta(self.revisao)
        self.assertEqual(contexto["blocos"]["normas_procedimentos"], "")
        self.revisao.refresh_from_db()
        self.assertEqual(self.revisao.normas_procedimentos, "NR-10")

    def test_contexto_publico_tem_allowlist_sem_dados_internos(self):
        self.item(); self.linha()
        texto = repr(montar_contexto_publico_proposta(self.revisao))
        for segredo in ("Fornecedor Secreto", "custo_total", "markup", "observacoes_internas", "plano_conta"):
            self.assertNotIn(segredo, texto)


class ViewsPropostaTests(ComercialBase):
    def setUp(self):
        super().setUp()
        self.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="comercial", codename__in=["view_proposta", "add_proposta"]
        ))
        self.client.force_login(self.usuario)

    def test_lista_e_detalhe(self):
        self.assertContains(self.client.get(reverse("comercial:proposta_lista")), "VERS1917")
        self.assertContains(self.client.get(reverse("comercial:proposta_detalhe", args=[self.proposta.pk])), "MATERIAL ELÉTRICO")
        self.assertContains(self.client.get(reverse("comercial:proposta_lista")), "Rascunho")

    def test_linha_publica_pode_ser_editada_sem_criar_revisao(self):
        self.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="comercial",
            codename__in=["change_propostalinhapublica"],
        ))
        linha = self.linha("150")
        resposta = self.client.post(reverse("comercial:linha_editar", args=[linha.pk]), {
            "ordem": 0,
            "grupo": PropostaLinhaPublica.Grupo.MATERIAL,
            "descricao": "Fornecimento de materiais elétricos",
            "quantidade": "1",
            "unidade": "VB",
            "valor_unitario": "930.00",
            "valor_total": "930.00",
            "observacao": "",
        })
        self.assertEqual(resposta.status_code, 302)
        linha.refresh_from_db()
        self.assertEqual(linha.descricao, "Fornecimento de materiais elétricos")
        self.assertEqual(linha.valor_total, Decimal("930.00"))
        self.assertEqual(self.proposta.revisoes.count(), 1)

    def test_editar_proposta_altera_cliente_e_nome_sem_criar_revisao(self):
        self.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="comercial",
            codename__in=["change_proposta", "change_propostarevisao"],
        ))
        novo_cliente = Pessoa.objects.create(
            razao_social="Cliente Novo",
            classificacao=Pessoa.Classificacao.CLIENTE,
            ativo=True,
            cpf_cnpj="33.333.333/0001-33",
        )
        dados = {
            "codigo": self.proposta.codigo,
            "cliente": novo_cliente.pk,
            "data_proposta": self.revisao.data_proposta.isoformat(),
            "nome_servico": "Nome corrigido",
            "validade_dias": self.revisao.validade_dias,
            "formacao_preco": self.revisao.formacao_preco,
            "percentual_formacao": self.revisao.percentual_formacao,
            "preco_venda_final": self.revisao.preco_venda_final,
        }
        resposta = self.client.post(reverse("comercial:revisao_editar", args=[self.revisao.pk]), dados)
        self.assertEqual(resposta.status_code, 302)
        self.proposta.refresh_from_db()
        self.revisao.refresh_from_db()
        self.assertEqual(self.proposta.cliente, novo_cliente)
        self.assertEqual(self.revisao.nome_servico, "Nome corrigido")
        self.assertEqual(self.proposta.revisoes.count(), 1)
        self.assertEqual(self.proposta.revisao_atual, 0)

    def test_lista_exibe_editar_e_edicao_altera_codigo_sem_nova_revisao(self):
        self.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="comercial",
            codename__in=["change_proposta", "change_propostarevisao"],
        ))
        lista = self.client.get(reverse("comercial:proposta_lista"))
        self.assertContains(lista, reverse("comercial:proposta_editar", args=[self.proposta.pk]))

        dados = {
            "codigo": "VERS1999",
            "cliente": self.cliente.pk,
            "data_proposta": self.revisao.data_proposta.isoformat(),
            "nome_servico": "Descrição corrigida da proposta",
            "validade_dias": self.revisao.validade_dias,
            "formacao_preco": self.revisao.formacao_preco,
            "percentual_formacao": self.revisao.percentual_formacao,
            "preco_venda_final": self.revisao.preco_venda_final,
        }
        resposta = self.client.post(reverse("comercial:proposta_editar", args=[self.proposta.pk]), dados)
        self.assertEqual(resposta.status_code, 302)
        self.proposta.refresh_from_db()
        self.revisao.refresh_from_db()
        self.assertEqual(self.proposta.codigo, "VERS1999")
        self.assertEqual(self.proposta.numero_sequencial, 1999)
        self.assertEqual(self.revisao.nome_servico, "Descrição corrigida da proposta")
        self.assertEqual(self.proposta.revisoes.count(), 1)
        self.assertEqual(self.proposta.revisao_atual, 0)

    def test_edicao_rejeita_codigo_duplicado_na_mesma_empresa(self):
        self.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="comercial",
            codename__in=["change_proposta", "change_propostarevisao"],
        ))
        outra, _ = criar_proposta(
            empresa=self.empresa, codigo="VERS1998", cliente=self.cliente,
            nome_servico="Outra proposta", usuario=self.usuario,
        )
        dados = {
            "codigo": outra.codigo,
            "cliente": self.cliente.pk,
            "data_proposta": self.revisao.data_proposta.isoformat(),
            "nome_servico": self.revisao.nome_servico,
            "validade_dias": self.revisao.validade_dias,
            "formacao_preco": self.revisao.formacao_preco,
            "percentual_formacao": self.revisao.percentual_formacao,
            "preco_venda_final": self.revisao.preco_venda_final,
        }
        resposta = self.client.post(reverse("comercial:proposta_editar", args=[self.proposta.pk]), dados)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Já existe uma proposta com este número nesta empresa.")
        self.proposta.refresh_from_db()
        self.assertEqual(self.proposta.codigo, "VERS1917")

    def test_excluir_proposta_exige_superusuario(self):
        resposta = self.client.post(reverse("comercial:proposta_excluir", args=[self.proposta.pk]))
        self.assertEqual(resposta.status_code, 403)
        self.assertTrue(Proposta.objects.filter(pk=self.proposta.pk).exists())

    def test_superusuario_pode_excluir_proposta_sem_dependencias(self):
        admin = get_user_model().objects.create_superuser(username="admin", password="teste123", email="admin@example.com")
        self.client.force_login(admin)
        resposta = self.client.post(reverse("comercial:proposta_excluir", args=[self.proposta.pk]))
        self.assertRedirects(resposta, reverse("comercial:proposta_lista"))
        self.assertFalse(Proposta.objects.filter(pk=self.proposta.pk).exists())

    def criar_historica(self):
        proposta, revisao = criar_proposta(empresa=self.empresa, codigo="VERS1918", cliente=self.cliente, nome_servico="Histórica", usuario=self.usuario)
        Proposta.objects.filter(pk=proposta.pk).update(
            origem=Proposta.Origem.IMPORTADO_HISTORICO,
            status_historico="Faturada",
            observacao_importacao="NF histórica",
        )
        PropostaRevisao.objects.filter(pk=revisao.pk).update(
            data_proposta=date(2026, 8, 12),
            aos_cuidados_de="Emitente Teste",
            observacoes_internas="Status histórico: Faturada\nEmitente: Emitente Teste",
        )
        return proposta

    def test_historica_exibe_status_historico_e_status_operacional_separados(self):
        proposta = self.criar_historica()
        lista = self.client.get(reverse("comercial:proposta_lista"))
        detalhe = self.client.get(reverse("comercial:proposta_detalhe", args=[proposta.pk]))
        self.assertContains(lista, "Faturada (histórico)")
        self.assertContains(detalhe, "Registro histórico importado")
        self.assertContains(detalhe, "Status operacional: Rascunho")
        self.assertContains(detalhe, "Status histórico: Faturada")
        self.assertContains(detalhe, "Emitente histórico: Emitente Teste")
        self.assertContains(detalhe, "Observação histórica: NF histórica")
        self.assertContains(detalhe, "Custo interno")
        self.assertContains(detalhe, "Não disponível")
        self.assertContains(detalhe, "Não calculado")
        self.assertNotContains(detalhe, "Gerar PDF")
        proposta.refresh_from_db()
        self.assertEqual(proposta.status, Proposta.Status.RASCUNHO)

    def test_documento_publico_nao_expoe_dados_internos(self):
        self.item(); self.linha()
        resposta = self.client.get(reverse("comercial:documento_publico", args=[self.revisao.pk]))
        self.assertContains(resposta, "Solução fornecida")
        self.assertContains(resposta, "R$ 150,00")
        self.assertNotContains(resposta, "Fornecedor Secreto")
        self.assertNotContains(resposta, "Custo interno")
        self.assertNotContains(resposta, "Margem")

    def test_documento_somente_servico_omite_materiais_e_formata_valor(self):
        self.revisao.escopo_incluido = "Instalação de equipamento"
        self.revisao.responsavel_nome = "Responsável Fictício"
        self.revisao.preco_venda_final = Decimal("1234.56")
        self.revisao.save()
        self.linha("1234.56", PropostaLinhaPublica.Grupo.SERVICO)
        resposta = self.client.get(reverse("comercial:documento_publico", args=[self.revisao.pk]))
        self.assertContains(resposta, "Instalação de equipamento")
        self.assertContains(resposta, "R$ 1.234,56")
        self.assertNotContains(resposta, "Lista de materiais")
        self.assertNotContains(resposta, "Subtotal materiais")
        self.assertContains(resposta, "Responsável Fictício")

    def test_documento_com_materiais_e_servicos_exibe_subtotais(self):
        self.revisao.preco_venda_final = Decimal("1500.00")
        self.revisao.save()
        self.linha("500.00", PropostaLinhaPublica.Grupo.MATERIAL)
        self.linha("1000.00", PropostaLinhaPublica.Grupo.SERVICO)
        resposta = self.client.get(reverse("comercial:documento_publico", args=[self.revisao.pk]))
        self.assertContains(resposta, "LISTA DE MATERIAIS")
        self.assertContains(resposta, "MATERIAIS")
        self.assertContains(resposta, "SERVIÇOS")
        self.assertContains(resposta, "R$ 1.500,00")

    def test_documento_historico_incompleto_e_pdf_renderizam_sem_workflow(self):
        Proposta.objects.filter(pk=self.proposta.pk).update(origem=Proposta.Origem.IMPORTADO_HISTORICO, status_historico="Fechada")
        documento = self.client.get(reverse("comercial:documento_publico", args=[self.revisao.pk]))
        pdf = self.client.get(reverse("comercial:proposta_pdf", args=[self.revisao.pk]))
        self.assertEqual(documento.status_code, 200)
        self.assertEqual(pdf.status_code, 400)
        self.assertIn("Documento original não disponível", pdf.content.decode())
        self.assertNotContains(documento, "LISTA DE MATERIAIS")
        self.assertNotContains(documento, "Nenhum item")
        self.proposta.refresh_from_db()
        self.assertEqual(self.proposta.status, Proposta.Status.RASCUNHO)

    def test_logo_institucional_existe(self):
        self.assertTrue(Path("static/img/versatile-logo.png").is_file())

    def test_pdf_multipagina_tem_paginacao_e_rodape_institucional(self):
        self.revisao.escopo_incluido = "\n".join(["Descrição detalhada do serviço com informações comerciais." for _ in range(100)])
        self.revisao.preco_venda_final = Decimal("1000.00")
        self.revisao.save()
        self.linha("1000.00", PropostaLinhaPublica.Grupo.SERVICO)
        resposta = self.client.get(reverse("comercial:proposta_pdf", args=[self.revisao.pk]))
        paginas = PdfReader(BytesIO(resposta.content)).pages
        texto = "\n".join(pagina.extract_text() or "" for pagina in paginas)
        self.assertGreaterEqual(len(paginas), 2)
        self.assertIn("CNPJ:", texto)
        self.assertIn("Página", texto)

    def test_documento_usa_dados_institucionais_e_responsavel_da_proposta(self):
        self.empresa.email = "comercial@empresa-ficticia.test"
        self.empresa.telefone = "(81) 3000-0000"
        self.empresa.save()
        self.usuario.first_name = "Ana"
        self.usuario.last_name = "Responsável"
        self.usuario.save()
        resposta = self.client.get(reverse("comercial:documento_publico", args=[self.revisao.pk]))
        self.assertContains(resposta, "comercial@empresa-ficticia.test")
        self.assertContains(resposta, "(81) 3000-0000")
        self.assertContains(resposta, "Ana Responsável")

    def test_documento_de_empresa_nao_autorizada_e_bloqueado(self):
        outra = Empresa.objects.create(razao_social="Outra Empresa", cnpj="55.555.555/0001-55")
        outra_proposta, outra_revisao = criar_proposta(empresa=outra, codigo="VERS2918", cliente=self.cliente, nome_servico="Fora", usuario=self.usuario)
        self.assertEqual(self.client.get(reverse("comercial:documento_publico", args=[outra_revisao.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("comercial:proposta_pdf", args=[outra_revisao.pk])).status_code, 403)

    def test_envio_invalido_exibe_erro_e_nao_congela(self):
        self.item(); self.revisao.percentual_formacao = 50; self.revisao.save(); self.linha("149")
        self.client.post(reverse("comercial:proposta_enviar", args=[self.proposta.pk]))
        self.revisao.refresh_from_db()
        self.assertFalse(self.revisao.congelada)

    def test_criacao_pela_tela(self):
        modelo = ModeloConteudoProposta.objects.create(
            empresa=self.empresa, nome="Padrão da tela", ativo=True, padrao=True,
            texto_introdutorio="Texto institucional",
        )
        resposta = self.client.post(reverse("comercial:proposta_criar"), {
            "empresa": self.empresa.pk, "codigo": "VERS1918", "cliente": self.cliente.pk,
            "nome_servico": "Nova tela", "aos_cuidados_de": "Contato da obra",
            "escopo_incluido": "Escopo digitado", "condicao_pagamento": "30 dias",
            "validade_dias": "20",
        })
        self.assertEqual(resposta.status_code, 302)
        proposta = Proposta.objects.get(codigo="VERS1918")
        revisao = proposta.revisoes.get()
        self.assertEqual(proposta.revisoes.count(), 1)
        self.assertEqual(revisao.numero, 0)
        self.assertEqual(revisao.modelo_conteudo, modelo)
        self.assertEqual(revisao.texto_introdutorio, "Texto institucional")
        self.assertEqual(revisao.aos_cuidados_de, "Contato da obra")
        self.assertEqual(revisao.escopo_incluido, "Escopo digitado")
        self.assertEqual(revisao.condicao_pagamento, "30 dias")
        self.assertEqual(revisao.validade_dias, 20)

    def test_tela_inicial_exibe_numero_e_nao_exibe_modelo(self):
        resposta = self.client.get(reverse("comercial:proposta_criar"))
        self.assertContains(resposta, "Número da proposta")
        self.assertNotContains(resposta, "Modelo")

    def test_menu_comercial_e_link_ativo_respeitam_permissao(self):
        resposta = self.client.get(reverse("comercial:proposta_lista"))
        self.assertContains(resposta, f'href="{reverse("comercial:proposta_lista")}"')
        self.assertContains(resposta, 'class="active"')
        self.usuario.user_permissions.clear()
        resposta = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(resposta, ">Comercial<")

    def test_listagem_exige_permissao_visualizar_proposta(self):
        self.usuario.user_permissions.clear()
        resposta = self.client.get(reverse("comercial:proposta_lista"))
        self.assertEqual(resposta.status_code, 403)

    def test_criacao_exige_permissao_adicionar_proposta(self):
        self.usuario.user_permissions.remove(Permission.objects.get(content_type__app_label="comercial", codename="add_proposta"))
        self.assertEqual(self.client.get(reverse("comercial:proposta_criar")).status_code, 403)

    def test_documento_publico_exige_permissao_visualizar(self):
        self.usuario.user_permissions.clear()
        self.assertEqual(self.client.get(reverse("comercial:documento_publico", args=[self.revisao.pk])).status_code, 403)

    def test_pdf_proposta_valido_e_sem_dados_internos(self):
        self.item(); self.linha("150",PropostaLinhaPublica.Grupo.SERVICO); self.revisao.preco_venda_final=150; self.revisao.observacoes_internas="SEGREDO INTERNO"; self.revisao.save()
        resposta=self.client.get(reverse("comercial:proposta_pdf",args=[self.revisao.pk])); self.assertEqual(resposta.status_code,200); self.assertEqual(resposta["Content-Type"],"application/pdf"); self.assertTrue(resposta.content.startswith(b"%PDF"))
        texto="\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(resposta.content)).pages); self.assertIn("VERS1917",texto); self.assertIn("Solução fornecida",texto); self.assertNotIn("Fornecedor Secreto",texto); self.assertNotIn("SEGREDO INTERNO",texto); self.assertNotIn("markup",texto.lower())

    def test_pdf_somente_servico_nao_exibe_subtotal_material(self):
        self.linha("200",PropostaLinhaPublica.Grupo.SERVICO); self.revisao.preco_venda_final=200; self.revisao.save(); resposta=self.client.get(reverse("comercial:proposta_pdf",args=[self.revisao.pk])); texto="\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(resposta.content)).pages); self.assertIn("SERVIÇOS",texto); self.assertNotIn("MATERIAIS",texto)

    def test_pdf_material_servico_flags_e_revisao(self):
        self.linha("100",PropostaLinhaPublica.Grupo.MATERIAL); self.linha("50",PropostaLinhaPublica.Grupo.SERVICO); self.revisao.preco_venda_final=150; self.revisao.normas_procedimentos="NORMA SECRETA DESABILITADA"; self.revisao.exibir_normas_procedimentos=False; self.revisao.save(); resposta=self.client.get(reverse("comercial:proposta_pdf",args=[self.revisao.pk])); texto="\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(resposta.content)).pages); self.assertIn("MATERIAIS",texto); self.assertIn("SERVIÇOS",texto); self.assertIn("VERS1917",texto); self.assertNotIn("NORMA SECRETA",texto)


class RelatorioPropostasTests(ComercialBase):
    def setUp(self):
        super().setUp(); self.usuario.user_permissions.add(Permission.objects.get(content_type__app_label="comercial",codename="view_proposta")); self.client.force_login(self.usuario)
        self.revisao.data_proposta=date(2026,8,10); self.revisao.preco_venda_final=Decimal("1000"); self.revisao.aos_cuidados_de="Contato Alfa"; self.revisao.observacoes_comerciais="Observação relatório"; self.revisao.save()
    def url(self,**dados):
        dados={"empresa":self.empresa.pk,**dados}; from urllib.parse import urlencode; return reverse("comercial:relatorio_propostas")+"?"+urlencode(dados)
    def test_resumo_colunas_e_sem_duplicidade(self):
        resposta=self.client.get(self.url()); self.assertContains(resposta,"VERS1917",count=1); self.assertContains(resposta,"R$ 1.000,00"); self.assertContains(resposta,"Contato Alfa"); self.assertContains(resposta,"Serviço TESTE")

    def test_paginacao_preserva_filtros_get(self):
        for indice in range(51):
            criar_proposta(empresa=self.empresa, codigo=f"VERS20{indice:02d}", cliente=self.cliente, nome_servico="Servico paginação", usuario=self.usuario)
        resposta = self.client.get(self.url(status="RASCUNHO", busca="Servico", page=1))
        self.assertEqual(resposta.context["pagination_query"], "empresa=%s&status=RASCUNHO&busca=Servico" % self.empresa.pk)
        self.assertContains(resposta, "page=2")
        self.assertNotContains(resposta, "?page=2")

    def test_relatorio_exibe_status_historico_mas_filtra_status_operacional(self):
        proposta, revisao = criar_proposta(empresa=self.empresa, codigo="VERS1918", cliente=self.cliente, nome_servico="Histórica", usuario=self.usuario)
        Proposta.objects.filter(pk=proposta.pk).update(origem=Proposta.Origem.IMPORTADO_HISTORICO, status_historico="Faturada")
        resposta = self.client.get(self.url(status="RASCUNHO"))
        self.assertContains(resposta, "Faturada (histórico)")
        self.assertContains(resposta, "R$ 1.000,00")
        self.assertEqual(Proposta.objects.get(pk=proposta.pk).status, Proposta.Status.RASCUNHO)
    def test_filtros_numero_cliente_contato_responsavel_status_periodo(self):
        filtros={"numero":"1917","cliente":self.cliente.pk,"contato":"Alfa","responsavel":self.usuario.pk,"status":"RASCUNHO","data_inicial":"2026-08-01","data_final":"2026-08-31"}; self.assertContains(self.client.get(self.url(**filtros)),"VERS1917")
        self.assertNotContains(self.client.get(self.url(status="APROVADA")),"VERS1917")
    def test_status_rejeitada_cancelada_aprovada(self):
        codigos=[]
        for indice,status in enumerate(("REJEITADA","CANCELADA","APROVADA"),1):
            p,r=criar_proposta(empresa=self.empresa,codigo=f"VERS192{indice}",cliente=self.cliente,nome_servico=status,usuario=self.usuario); Proposta.objects.filter(pk=p.pk).update(status=status); PropostaRevisao.objects.filter(pk=r.pk).update(preco_venda_final=100*indice); codigos.append(p.codigo)
        resposta=self.client.get(self.url()); [self.assertContains(resposta,codigo) for codigo in codigos]
    def test_isolamento_empresa_busca_e_permissao(self):
        outra=Empresa.objects.create(razao_social="Outra relatório",cnpj="33.333.333/0001-33"); criar_proposta(empresa=outra,codigo="VERS9999",cliente=self.cliente,nome_servico="Fora",usuario=self.usuario)
        self.assertNotContains(self.client.get(self.url(busca="VERS")),"VERS9999"); self.usuario.user_permissions.clear(); self.assertEqual(self.client.get(self.url()).status_code,403)


class WorkflowPropostaTests(ComercialBase):
    def conceder(self, *codenames):
        self.usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="comercial", codename__in=codenames))

    def enviar_valida(self):
        self.item()
        self.revisao.percentual_formacao = Decimal("50")
        self.revisao.save()
        self.linha("150")
        return enviar_proposta(self.revisao, self.usuario)

    def permitir_aprovacao(self):
        self.conceder("aprovar_proposta", "criar_obra_proposta")

    def test_transicao_enviada_para_negociacao(self):
        self.enviar_valida()
        colocar_em_negociacao(self.proposta, self.usuario)
        self.proposta.refresh_from_db()
        self.assertEqual(self.proposta.status, Proposta.Status.EM_NEGOCIACAO)

    def test_transicao_invalida_rascunho_para_negociacao(self):
        with self.assertRaises(ValidationError):
            colocar_em_negociacao(self.proposta, self.usuario)

    def test_aprovacao_cria_obra_e_metadados(self):
        revisao = self.enviar_valida(); self.permitir_aprovacao()
        proposta, obra = aprovar_proposta(self.proposta, self.usuario)
        self.assertEqual(obra.empresa, self.empresa)
        self.assertEqual(obra.cliente, self.cliente)
        self.assertEqual(obra.codigo, proposta.codigo)
        self.assertEqual(obra.nome, revisao.nome_servico)
        self.assertTrue(obra.ativo)
        self.assertEqual(proposta.revisao_aprovada, revisao)
        self.assertEqual(proposta.aprovada_por, self.usuario)
        self.assertIsNotNone(proposta.aprovada_em)

    def test_aprovacao_duplicada_e_bloqueada(self):
        self.enviar_valida(); self.permitir_aprovacao(); aprovar_proposta(self.proposta, self.usuario)
        with self.assertRaises(ValidationError):
            aprovar_proposta(self.proposta, self.usuario)
        self.assertEqual(CentroCusto.objects.filter(empresa=self.empresa, codigo=self.proposta.codigo).count(), 1)

    def test_colisao_de_codigo_bloqueia_sem_vincular(self):
        self.enviar_valida(); self.permitir_aprovacao()
        CentroCusto.objects.create(empresa=self.empresa, codigo=self.proposta.codigo, nome="Obra preexistente")
        with self.assertRaisesMessage(ValidationError, "aprovação foi bloqueada"):
            aprovar_proposta(self.proposta, self.usuario)
        self.proposta.refresh_from_db()
        self.assertIsNone(self.proposta.centro_custo_id)
        self.assertEqual(self.proposta.status, Proposta.Status.ENVIADA)

    def test_rollback_remove_obra_e_aprovacao_se_historico_falhar(self):
        self.enviar_valida(); self.permitir_aprovacao()
        with patch("comercial.services.PropostaHistoricoStatus.objects.create", side_effect=RuntimeError("falha")):
            with self.assertRaises(RuntimeError):
                aprovar_proposta(self.proposta, self.usuario)
        self.proposta.refresh_from_db()
        self.assertEqual(self.proposta.status, Proposta.Status.ENVIADA)
        self.assertIsNone(self.proposta.centro_custo_id)
        self.assertFalse(CentroCusto.objects.filter(empresa=self.empresa, codigo=self.proposta.codigo).exists())

    def test_rejeicao_exige_motivo_e_registra_historico(self):
        self.enviar_valida(); self.conceder("rejeitar_proposta")
        with self.assertRaises(ValidationError):
            rejeitar_proposta(self.proposta, self.usuario, "")
        rejeitar_proposta(self.proposta, self.usuario, "Cliente não aprovou o prazo")
        evento = self.proposta.historico_status.first()
        self.assertEqual(evento.status_novo, Proposta.Status.REJEITADA)
        self.assertEqual(evento.observacao, "Cliente não aprovou o prazo")

    def test_cancelamento_preserva_obra(self):
        self.enviar_valida(); self.permitir_aprovacao(); self.conceder("cancelar_proposta")
        proposta, obra = aprovar_proposta(self.proposta, self.usuario)
        cancelar_proposta(proposta, self.usuario, "Cancelada após aprovação")
        obra.refresh_from_db(); proposta.refresh_from_db()
        self.assertTrue(obra.ativo)
        self.assertEqual(proposta.centro_custo, obra)
        self.assertEqual(proposta.status, Proposta.Status.CANCELADA)

    def test_acoes_exigem_permissoes_backend(self):
        self.enviar_valida()
        with self.assertRaises(PermissionDenied): aprovar_proposta(self.proposta, self.usuario)
        with self.assertRaises(PermissionDenied): rejeitar_proposta(self.proposta, self.usuario, "Motivo")
        with self.assertRaises(PermissionDenied): cancelar_proposta(self.proposta, self.usuario, "Motivo")

    def test_aprovar_exige_as_duas_permissoes(self):
        self.enviar_valida(); self.conceder("aprovar_proposta")
        with self.assertRaises(PermissionDenied):
            aprovar_proposta(self.proposta, self.usuario)

    def test_revisao_nao_congelada_nao_aprova(self):
        self.permitir_aprovacao()
        self.proposta.status = Proposta.Status.ENVIADA; self.proposta.save()
        with self.assertRaises(ValidationError):
            aprovar_proposta(self.proposta, self.usuario)

    def test_historico_guarda_usuario_data_e_status_anterior(self):
        self.enviar_valida(); colocar_em_negociacao(self.proposta, self.usuario)
        evento = self.proposta.historico_status.first()
        self.assertEqual(evento.status_anterior, Proposta.Status.ENVIADA)
        self.assertEqual(evento.status_novo, Proposta.Status.EM_NEGOCIACAO)
        self.assertEqual(evento.usuario, self.usuario)
        self.assertIsNotNone(evento.criado_em)

    def test_view_aprovacao_retorna_403_sem_permissao(self):
        self.enviar_valida(); self.client.force_login(self.usuario)
        resposta = self.client.post(reverse("comercial:proposta_aprovar", args=[self.proposta.pk]))
        self.assertEqual(resposta.status_code, 403)


class PrevistoRealizadoTests(ComercialBase):
    def setUp(self):
        super().setUp()
        self.usuario.user_permissions.add(Permission.objects.get(content_type__app_label="comercial", codename="view_proposta"))
        self.conta_custo = PlanoConta.objects.create(codigo="9.91.01", nome="Materiais teste", tipo="CUSTO", natureza="DEVEDORA")
        self.conta_custo_sem_movimento = PlanoConta.objects.create(codigo="9.91.02", nome="Terceiros teste", tipo="CUSTO", natureza="DEVEDORA")
        self.conta_despesa = PlanoConta.objects.create(codigo="9.92.01", nome="Despesa não prevista", tipo="DESPESA", natureza="DEVEDORA")
        self.conta_receita = PlanoConta.objects.create(codigo="9.93.01", nome="Receita serviços teste", tipo="RECEITA", natureza="CREDORA")
        self.obra = CentroCusto.objects.create(empresa=self.empresa, cliente=self.cliente, codigo=self.proposta.codigo, nome=self.revisao.nome_servico)
        self.proposta.status = Proposta.Status.APROVADA
        self.proposta.centro_custo = self.obra
        self.proposta.revisao_aprovada = self.revisao
        self.proposta.save()

    def previsto(self):
        PropostaItem.objects.create(revisao=self.revisao, tipo=PropostaItem.Tipo.MATERIAL, descricao="Material", quantidade=1, custo_unitario=100, plano_conta=self.conta_custo)
        PropostaItem.objects.create(revisao=self.revisao, tipo=PropostaItem.Tipo.MAO_OBRA, descricao="Sem conta", quantidade=1, custo_unitario=50)
        PropostaItem.objects.create(revisao=self.revisao, tipo=PropostaItem.Tipo.SERVICO_TERCEIRO, descricao="Terceiros", quantidade=1, custo_unitario=25, plano_conta=self.conta_custo_sem_movimento)
        self.revisao.percentual_formacao = Decimal("50")
        self.revisao.save()

    def lancamento(self, tipo, conta, valor, obra=None, status="ABERTO"):
        lancamento = LancamentoFinanceiro.objects.create(empresa=self.empresa, pessoa=self.cliente, tipo=tipo, descricao=f"TESTE {conta.nome}", data_emissao=date(2026, 8, 1), data_competencia=date(2026, 8, 1), valor_total=Decimal(valor), plano_conta=conta, status=status)
        if obra:
            RateioCentroCusto.objects.create(lancamento=lancamento, centro_custo=obra, valor=Decimal(valor))
        return lancamento

    def realizados(self):
        self.lancamento("PAGAR", self.conta_custo, "120", self.obra)
        self.lancamento("PAGAR", self.conta_despesa, "30", self.obra)
        self.lancamento("RECEBER", self.conta_receita, "200", self.obra)

    def linha_conta(self, relatorio, conta):
        return next(linha for linha in relatorio["categorias"] if linha["plano_conta"] == conta)

    def test_proposta_sem_aprovacao_ou_sem_obra(self):
        self.proposta.status = Proposta.Status.ENVIADA; self.proposta.save()
        self.assertFalse(calcular_previsto_realizado(self.proposta)["disponivel"])
        self.proposta.status = Proposta.Status.APROVADA; self.proposta.centro_custo = None; self.proposta.save()
        self.assertFalse(calcular_previsto_realizado(self.proposta)["disponivel"])

    def test_usa_revisao_aprovada_e_nao_revisao_atual(self):
        self.previsto()
        posterior = PropostaRevisao.objects.create(proposta=self.proposta, numero=1, data_proposta=date(2026, 8, 2), nome_servico="Posterior", preco_venda_final=999, formacao_preco=PropostaRevisao.FormacaoPreco.MANUAL)
        self.proposta.revisao_atual = posterior.numero; self.proposta.save()
        relatorio = calcular_previsto_realizado(self.proposta)
        self.assertEqual(relatorio["revisao"], self.revisao)
        self.assertEqual(relatorio["resumo"]["custo_previsto"], Decimal("175.00"))

    def test_previsto_por_item_plano_e_sem_classificacao(self):
        self.previsto(); relatorio = calcular_previsto_realizado(self.proposta)
        self.assertEqual(self.linha_conta(relatorio, self.conta_custo)["previsto"], Decimal("100.00"))
        self.assertTrue(any("Sem classificação prevista" in linha["nome"] and linha["previsto"] == Decimal("50.00") for linha in relatorio["categorias"]))

    def test_custos_despesas_receitas_resultado_e_margens(self):
        self.previsto(); self.realizados(); resumo = calcular_previsto_realizado(self.proposta)["resumo"]
        self.assertEqual(resumo["receita_realizada"], Decimal("200.00"))
        self.assertEqual(resumo["custos_realizados"], Decimal("120.00"))
        self.assertEqual(resumo["despesas_realizadas"], Decimal("30.00"))
        self.assertEqual(resumo["resultado_realizado"], Decimal("50.00"))
        self.assertEqual(resumo["margem_realizada"], Decimal("25.00"))
        self.assertEqual(resumo["resultado_previsto"], Decimal("87.50"))

    def test_gasto_acima_previsto_e_nao_previsto(self):
        self.previsto(); self.realizados(); relatorio = calcular_previsto_realizado(self.proposta)
        material = self.linha_conta(relatorio, self.conta_custo)
        inesperado = self.linha_conta(relatorio, self.conta_despesa)
        self.assertEqual((material["diferenca"], material["percentual"], material["situacao"]), (Decimal("-20.00"), Decimal("120.00"), "acima"))
        self.assertEqual(inesperado["situacao"], "nao_previsto")
        self.assertIsNone(inesperado["percentual"])

    def test_item_previsto_sem_realizado(self):
        self.previsto(); linha = self.linha_conta(calcular_previsto_realizado(self.proposta), self.conta_custo_sem_movimento)
        self.assertEqual(linha["situacao"], "sem_realizado")

    def test_rateio_entre_obras_usa_apenas_parcela_da_obra(self):
        self.previsto()
        outra = CentroCusto.objects.create(empresa=self.empresa, codigo="OUTRA-TESTE", nome="Outra")
        lancamento = self.lancamento("PAGAR", self.conta_custo, "100")
        RateioCentroCusto.objects.create(lancamento=lancamento, centro_custo=self.obra, valor=40)
        RateioCentroCusto.objects.create(lancamento=lancamento, centro_custo=outra, valor=60)
        self.assertEqual(self.linha_conta(calcular_previsto_realizado(self.proposta), self.conta_custo)["realizado"], Decimal("40.00"))

    def test_cancelado_fica_fora_e_nao_ha_duplicidade(self):
        self.previsto(); self.lancamento("PAGAR", self.conta_custo, "20", self.obra); self.lancamento("PAGAR", self.conta_custo, "80", self.obra, "CANCELADO")
        relatorio = calcular_previsto_realizado(self.proposta)
        self.assertEqual(self.linha_conta(relatorio, self.conta_custo)["realizado"], Decimal("20.00"))
        self.assertEqual(len(relatorio["detalhes"]), 1)

    def test_isolamento_por_empresa(self):
        self.previsto()
        outra_empresa = Empresa.objects.create(razao_social="Outra Empresa", cnpj="33.333.333/0001-33")
        outra_obra = CentroCusto.objects.create(empresa=outra_empresa, codigo="ISOLADA", nome="Isolada")
        lancamento = LancamentoFinanceiro.objects.create(empresa=outra_empresa, pessoa=self.cliente, tipo="PAGAR", descricao="Fora", data_emissao=date(2026, 8, 1), valor_total=999, plano_conta=self.conta_custo)
        RateioCentroCusto.objects.create(lancamento=lancamento, centro_custo=outra_obra, valor=999)
        self.assertEqual(self.linha_conta(calcular_previsto_realizado(self.proposta), self.conta_custo)["realizado"], Decimal("0.00"))

    def test_view_renderiza_resumo_detalhes_e_link(self):
        self.previsto(); self.realizados(); self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("comercial:previsto_realizado", args=[self.proposta.pk]))
        self.assertContains(resposta, "Previsto × Realizado")
        self.assertContains(resposta, "R$ 200,00")
        self.assertContains(resposta, reverse("financeiro:detalhe_conta_pagar", args=[LancamentoFinanceiro.objects.filter(tipo="PAGAR").first().pk]))
