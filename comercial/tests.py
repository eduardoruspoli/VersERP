from datetime import date
from decimal import Decimal
from io import BytesIO

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
from .services import aprovar_proposta, calcular_precificacao, calcular_previsto_realizado, cancelar_proposta, colocar_em_negociacao, criar_nova_revisao, criar_proposta, enviar_proposta, montar_contexto_publico_proposta, rejeitar_proposta, validar_fechamento_publico


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

    def test_custo_total_item_e_derivado(self):
        item = self.item("12.3456", "2")
        self.assertEqual(item.custo_total, Decimal("24.69"))

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
        self.assertContains(self.client.get(reverse("comercial:proposta_detalhe", args=[self.proposta.pk])), "Composição interna")

    def test_documento_publico_nao_expoe_dados_internos(self):
        self.item(); self.linha()
        resposta = self.client.get(reverse("comercial:documento_publico", args=[self.revisao.pk]))
        self.assertContains(resposta, "Solução fornecida")
        self.assertContains(resposta, "R$ 150,00")
        self.assertNotContains(resposta, "Fornecedor Secreto")
        self.assertNotContains(resposta, "Custo interno")
        self.assertNotContains(resposta, "Margem")

    def test_envio_invalido_exibe_erro_e_nao_congela(self):
        self.item(); self.revisao.percentual_formacao = 50; self.revisao.save(); self.linha("149")
        self.client.post(reverse("comercial:proposta_enviar", args=[self.proposta.pk]))
        self.revisao.refresh_from_db()
        self.assertFalse(self.revisao.congelada)

    def test_criacao_pela_tela(self):
        resposta = self.client.post(reverse("comercial:proposta_criar"), {"empresa": self.empresa.pk, "codigo": "VERS1918", "cliente": self.cliente.pk, "nome_servico": "Nova tela"})
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Proposta.objects.filter(revisoes__nome_servico="Nova tela").exists())

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
        self.linha("200",PropostaLinhaPublica.Grupo.SERVICO); self.revisao.preco_venda_final=200; self.revisao.save(); resposta=self.client.get(reverse("comercial:proposta_pdf",args=[self.revisao.pk])); texto="\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(resposta.content)).pages); self.assertIn("Subtotal serviços",texto); self.assertNotIn("Subtotal materiais",texto)

    def test_pdf_material_servico_flags_e_revisao(self):
        self.linha("100",PropostaLinhaPublica.Grupo.MATERIAL); self.linha("50",PropostaLinhaPublica.Grupo.SERVICO); self.revisao.preco_venda_final=150; self.revisao.normas_procedimentos="NORMA SECRETA DESABILITADA"; self.revisao.exibir_normas_procedimentos=False; self.revisao.save(); resposta=self.client.get(reverse("comercial:proposta_pdf",args=[self.revisao.pk])); texto="\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(resposta.content)).pages); self.assertIn("Subtotal materiais",texto); self.assertIn("Subtotal serviços",texto); self.assertIn("Revisão 0",texto); self.assertNotIn("NORMA SECRETA",texto)


class RelatorioPropostasTests(ComercialBase):
    def setUp(self):
        super().setUp(); self.usuario.user_permissions.add(Permission.objects.get(content_type__app_label="comercial",codename="view_proposta")); self.client.force_login(self.usuario)
        self.revisao.data_proposta=date(2026,8,10); self.revisao.preco_venda_final=Decimal("1000"); self.revisao.aos_cuidados_de="Contato Alfa"; self.revisao.observacoes_comerciais="Observação relatório"; self.revisao.save()
    def url(self,**dados):
        dados={"empresa":self.empresa.pk,**dados}; from urllib.parse import urlencode; return reverse("comercial:relatorio_propostas")+"?"+urlencode(dados)
    def test_resumo_colunas_e_sem_duplicidade(self):
        resposta=self.client.get(self.url()); self.assertContains(resposta,"VERS1917",count=1); self.assertContains(resposta,"R$ 1.000,00"); self.assertContains(resposta,"Contato Alfa"); self.assertContains(resposta,"Serviço TESTE")
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
