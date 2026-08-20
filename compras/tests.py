from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from pypdf import PdfReader
from django.utils import timezone

from comercial.models import Proposta, PropostaItem, PropostaRevisao
from financeiro.models import CentroCusto, Empresa, PlanoConta
from pessoas.models import Pessoa
from core.models import UsuarioEmpresa

from .models import (CotacaoFornecedor, CotacaoFornecedorItem, EscolhaCotacaoItem,
                     DivergenciaRecebimento, HistoricoPedidoCompra, PedidoCompra, PedidoCompraItem,
                     PedidoItemAlocacaoObra, ProcessoCotacao, ProcessoCotacaoItem,
                     RecebimentoCompra, RecebimentoCompraItem, SolicitacaoCompra, SolicitacaoCompraItem)
from .models import (DocumentoCompra, DocumentoCompraItem, DocumentoCompraPedido,
                     DocumentoCompraItemRecebimento, DivergenciaDocumentoCompra)
from .services import (abrir_solicitacao, calcular_custos_cotacao, cancelar_processo_cotacao,
                       cancelar_pedido, cancelar_solicitacao, concluir_processo_cotacao,
                       enviar_pedido, gerar_pedidos_da_cotacao, iniciar_processo_cotacao,
                       montar_mapa_comparativo, recalcular_pedido, rejeitar_pedido,
                       selecionar_oferta, submeter_pedido, aprovar_pedido,
                       cancelar_recebimento, confirmar_recebimento,
                       quantidades_recebimento_pedido, resolver_divergencia,
                       calcular_previsto_comprado)
from .services import (cancelar_documento_compra, concluir_conferencia_documento,
                       iniciar_conferencia_documento, reabrir_conferencia_documento,
                       resolver_divergencia_documento, validar_fechamento_documento,
                       vincular_recebimento_documento)


class ComprasBase(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="comprador", password="teste123")
        self.empresa = Empresa.objects.create(razao_social="Empresa Compras", cnpj="51.111.111/0001-51")
        UsuarioEmpresa.objects.create(usuario=self.usuario, empresa=self.empresa)
        self.outra_empresa = Empresa.objects.create(razao_social="Outra Empresa", cnpj="52.222.222/0001-52")
        self.cliente = Pessoa.objects.create(razao_social="Cliente Obra", classificacao=Pessoa.Classificacao.CLIENTE)
        self.plano = PlanoConta.objects.create(codigo="TESTE-COMPRA-01", nome="Materiais compra", tipo="CUSTO", natureza="DEVEDORA")
        self.proposta = Proposta.objects.create(empresa=self.empresa, cliente=self.cliente, codigo="VERS7001", numero_sequencial=7001, responsavel_interno=self.usuario)
        self.revisao = PropostaRevisao.objects.create(proposta=self.proposta, numero=0, data_proposta=date(2026, 8, 19), nome_servico="Obra Compras")
        self.proposta_item = PropostaItem.objects.create(revisao=self.revisao, tipo=PropostaItem.Tipo.MATERIAL, descricao="Cabo 4 mm", quantidade=500, unidade="M", custo_unitario=Decimal("5.00"), plano_conta=self.plano)
        self.obra = CentroCusto.objects.create(empresa=self.empresa, cliente=self.cliente, codigo=self.proposta.codigo, nome=self.revisao.nome_servico)
        self.proposta.status = Proposta.Status.APROVADA
        self.proposta.revisao_aprovada = self.revisao
        self.proposta.centro_custo = self.obra
        self.proposta.save()
        PropostaRevisao.objects.filter(pk=self.revisao.pk).update(congelada=True)
        self.revisao.refresh_from_db()

    def permissao(self, *nomes):
        self.usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="compras", codename__in=nomes))
        for atributo in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
            self.usuario.__dict__.pop(atributo, None)

    def solicitacao(self, obra=None, empresa=None):
        return SolicitacaoCompra.objects.create(empresa=empresa or self.empresa, obra=obra or self.obra, solicitante=self.usuario, criado_por=self.usuario, data_solicitacao=date(2026, 8, 19))

    def item(self, solicitacao=None, proposta_item=None, tipo="NAO_PREVISTO", **kwargs):
        dados = {"solicitacao": solicitacao or self.solicitacao(), "descricao": "Material solicitado", "quantidade": Decimal("10"), "unidade": "UN", "proposta_item": proposta_item, "tipo_origem": tipo}
        dados.update(kwargs)
        return SolicitacaoCompraItem.objects.create(**dados)


class SolicitacaoCompraModelTests(ComprasBase):
    def revisao_um_aprovada(self):
        revisao_um = PropostaRevisao.objects.create(proposta=self.proposta, numero=1, data_proposta=date(2026, 8, 20), nome_servico="Obra revisão 01")
        item_um = PropostaItem.objects.create(revisao=revisao_um, tipo=PropostaItem.Tipo.MATERIAL, descricao="Material revisão 01", quantidade=25, unidade="CX", custo_unitario=Decimal("12.50"), plano_conta=self.plano)
        PropostaRevisao.objects.filter(pk=revisao_um.pk).update(congelada=True, enviada_em=timezone.now())
        self.proposta.revisao_atual = 1
        self.proposta.revisao_aprovada = revisao_um
        self.proposta.save()
        revisao_um.refresh_from_db()
        return revisao_um, item_um

    def test_obra_e_obrigatoria(self):
        with self.assertRaises(ValidationError):
            SolicitacaoCompra.objects.create(empresa=self.empresa, solicitante=self.usuario, criado_por=self.usuario)

    def test_obra_de_outra_empresa_e_rejeitada(self):
        outra_obra = CentroCusto.objects.create(empresa=self.outra_empresa, codigo="OUTRA-01", nome="Outra")
        with self.assertRaises(ValidationError):
            self.solicitacao(obra=outra_obra)

    def test_obra_inativa_e_rejeitada(self):
        self.obra.ativo = False; self.obra.save()
        with self.assertRaises(ValidationError):
            self.solicitacao()

    def test_item_previsto_preenche_snapshots(self):
        item = self.item(proposta_item=self.proposta_item, tipo=SolicitacaoCompraItem.TipoOrigem.PREVISTO, descricao="", unidade="")
        self.assertEqual(item.descricao, "Cabo 4 mm")
        self.assertEqual(item.quantidade_prevista_snapshot, Decimal("500"))
        self.assertEqual(item.custo_unitario_previsto_snapshot, Decimal("5"))
        self.assertEqual(item.plano_conta_previsto, self.plano)
        self.assertEqual(item.descricao_prevista_snapshot, "Cabo 4 mm")
        self.assertEqual(item.unidade_prevista_snapshot, "M")

    def test_somente_item_da_revisao_um_aprovada_e_aceito(self):
        revisao_um, item_um = self.revisao_um_aprovada()
        solicitacao = self.solicitacao()
        criado = self.item(solicitacao=solicitacao, proposta_item=item_um, tipo="PREVISTO")
        self.assertEqual(criado.proposta_item.revisao, revisao_um)
        with self.assertRaises(ValidationError):
            self.item(solicitacao=solicitacao, proposta_item=self.proposta_item, tipo="PREVISTO")

    def test_revisao_posterior_nao_altera_solicitacao_existente(self):
        _, item_um = self.revisao_um_aprovada()
        criado = self.item(proposta_item=item_um, tipo="PREVISTO", descricao="Solicitado")
        snapshots = (criado.descricao_prevista_snapshot, criado.quantidade_prevista_snapshot, criado.unidade_prevista_snapshot, criado.custo_unitario_previsto_snapshot, criado.plano_conta_previsto_id)
        revisao_dois = PropostaRevisao.objects.create(proposta=self.proposta, numero=2, data_proposta=date(2026, 8, 21), nome_servico="Revisão posterior")
        PropostaItem.objects.create(revisao=revisao_dois, tipo=PropostaItem.Tipo.MATERIAL, descricao="Material revisão 02", quantidade=999, unidade="UN", custo_unitario=999)
        self.proposta.revisao_atual = 2
        self.proposta.save()
        criado.refresh_from_db()
        self.assertEqual((criado.descricao_prevista_snapshot, criado.quantidade_prevista_snapshot, criado.unidade_prevista_snapshot, criado.custo_unitario_previsto_snapshot, criado.plano_conta_previsto_id), snapshots)
        self.assertEqual(self.proposta.revisao_aprovada_id, item_um.revisao_id)

    def test_item_de_revisao_posterior_nao_aprovada_e_rejeitado(self):
        self.revisao_um_aprovada()
        revisao_dois = PropostaRevisao.objects.create(proposta=self.proposta, numero=2, data_proposta=date(2026, 8, 21), nome_servico="Posterior não aprovada")
        item_dois = PropostaItem.objects.create(revisao=revisao_dois, tipo=PropostaItem.Tipo.MATERIAL, descricao="Não aprovado", quantidade=1, custo_unitario=1)
        self.proposta.revisao_atual = 2
        self.proposta.save()
        with self.assertRaises(ValidationError):
            self.item(proposta_item=item_dois, tipo="PREVISTO")

    def test_item_de_outra_proposta_e_rejeitado(self):
        outra = Proposta.objects.create(empresa=self.empresa, cliente=self.cliente, codigo="VERS7002", numero_sequencial=7002)
        revisao = PropostaRevisao.objects.create(proposta=outra, numero=0, data_proposta=date.today(), nome_servico="Outra")
        item_alheio = PropostaItem.objects.create(revisao=revisao, tipo=PropostaItem.Tipo.MATERIAL, descricao="Alheio", quantidade=1, custo_unitario=1)
        with self.assertRaises(ValidationError):
            self.item(proposta_item=item_alheio, tipo=SolicitacaoCompraItem.TipoOrigem.PREVISTO)

    def test_item_de_proposta_de_outra_empresa_e_rejeitado(self):
        cliente = Pessoa.objects.create(razao_social="Cliente outra empresa", classificacao=Pessoa.Classificacao.CLIENTE)
        proposta = Proposta.objects.create(empresa=self.outra_empresa, cliente=cliente, codigo="VERS8001", numero_sequencial=8001)
        revisao = PropostaRevisao.objects.create(proposta=proposta, numero=0, data_proposta=date.today(), nome_servico="Outra empresa")
        item = PropostaItem.objects.create(revisao=revisao, tipo=PropostaItem.Tipo.MATERIAL, descricao="Item externo", quantidade=1, custo_unitario=1)
        proposta.revisao_aprovada = revisao; proposta.status = Proposta.Status.APROVADA; proposta.save()
        with self.assertRaises(ValidationError):
            self.item(proposta_item=item, tipo="PREVISTO")

    def test_item_sem_proposta_e_nao_previsto(self):
        item = self.item(tipo=SolicitacaoCompraItem.TipoOrigem.NAO_PREVISTO)
        self.assertEqual(item.tipo_origem, SolicitacaoCompraItem.TipoOrigem.NAO_PREVISTO)
        self.assertIsNone(item.quantidade_prevista_snapshot)

    def test_substituicao_preserva_original(self):
        descricao_original = self.proposta_item.descricao
        item = self.item(proposta_item=self.proposta_item, tipo=SolicitacaoCompraItem.TipoOrigem.SUBSTITUICAO, descricao="Cabo substituto", descricao_item_substituido="Cabo 4 mm")
        self.proposta_item.refresh_from_db()
        self.assertEqual(item.tipo_origem, SolicitacaoCompraItem.TipoOrigem.SUBSTITUICAO)
        self.assertEqual(self.proposta_item.descricao, descricao_original)

    def test_substituicao_exige_descricao_e_item_previsto(self):
        with self.assertRaises(ValidationError):
            self.item(proposta_item=self.proposta_item, tipo=SolicitacaoCompraItem.TipoOrigem.SUBSTITUICAO)
        with self.assertRaises(ValidationError):
            self.item(tipo=SolicitacaoCompraItem.TipoOrigem.SUBSTITUICAO, descricao_item_substituido="Original")

    def test_quantidade_deve_ser_positiva(self):
        with self.assertRaises(ValidationError):
            self.item(quantidade=0)

    def test_proposta_aprovada_nao_e_alterada(self):
        estado = (self.proposta.status, self.proposta.revisao_aprovada_id, self.proposta_item.quantidade, self.proposta_item.custo_unitario)
        self.item(proposta_item=self.proposta_item, tipo=SolicitacaoCompraItem.TipoOrigem.PREVISTO)
        self.proposta.refresh_from_db(); self.proposta_item.refresh_from_db()
        self.assertEqual((self.proposta.status, self.proposta.revisao_aprovada_id, self.proposta_item.quantidade, self.proposta_item.custo_unitario), estado)

    def test_isolamento_por_empresa(self):
        outra_obra = CentroCusto.objects.create(empresa=self.outra_empresa, codigo="OBRA-52", nome="Obra 52")
        outra = self.solicitacao(obra=outra_obra, empresa=self.outra_empresa)
        self.assertNotEqual(outra.empresa, self.empresa)
        self.assertFalse(SolicitacaoCompra.objects.filter(empresa=self.empresa, pk=outra.pk).exists())


class SolicitacaoWorkflowTests(ComprasBase):
    def test_abertura_registra_historico(self):
        solicitacao = self.solicitacao(); self.item(solicitacao=solicitacao)
        self.permissao("change_solicitacaocompra")
        abrir_solicitacao(solicitacao, self.usuario)
        evento = solicitacao.historico.get()
        self.assertEqual((evento.status_anterior, evento.status_novo, evento.usuario), ("RASCUNHO", "ABERTA", self.usuario))

    def test_abertura_sem_item_e_bloqueada(self):
        self.permissao("change_solicitacaocompra")
        with self.assertRaises(ValidationError): abrir_solicitacao(self.solicitacao(), self.usuario)

    def test_transicao_invalida_e_bloqueada(self):
        solicitacao = self.solicitacao(); self.item(solicitacao=solicitacao); self.permissao("change_solicitacaocompra")
        abrir_solicitacao(solicitacao, self.usuario)
        with self.assertRaises(ValidationError): abrir_solicitacao(solicitacao, self.usuario)

    def test_cancelamento_exige_motivo_e_permissao(self):
        solicitacao = self.solicitacao()
        with self.assertRaises(PermissionDenied): cancelar_solicitacao(solicitacao, self.usuario, "Motivo")
        self.permissao("cancelar_solicitacao")
        with self.assertRaises(ValidationError): cancelar_solicitacao(solicitacao, self.usuario, "")
        cancelar_solicitacao(solicitacao, self.usuario, "Necessidade cancelada")
        self.assertEqual(solicitacao.historico.get().observacao, "Necessidade cancelada")

    def test_cancelamento_de_aberta(self):
        solicitacao = self.solicitacao(); self.item(solicitacao=solicitacao); self.permissao("change_solicitacaocompra", "cancelar_solicitacao")
        abrir_solicitacao(solicitacao, self.usuario); cancelar_solicitacao(solicitacao, self.usuario, "Cancelada aberta")
        solicitacao.refresh_from_db(); self.assertEqual(solicitacao.status, "CANCELADA")

    def test_item_e_obra_ficam_imutaveis_apos_abertura(self):
        solicitacao = self.solicitacao(); item = self.item(solicitacao=solicitacao); self.permissao("change_solicitacaocompra")
        abrir_solicitacao(solicitacao, self.usuario)
        item.descricao = "Alterado"
        with self.assertRaises(ValidationError): item.save()
        nova_obra = CentroCusto.objects.create(empresa=self.empresa, codigo="NOVA-OBRA", nome="Nova")
        solicitacao.obra = nova_obra
        with self.assertRaises(ValidationError): solicitacao.save()


class SolicitacaoViewsTests(ComprasBase):
    def setUp(self):
        super().setUp(); self.client.force_login(self.usuario)

    def test_listagem_e_menu_exigem_view(self):
        self.assertEqual(self.client.get(reverse("compras:solicitacao_lista")).status_code, 403)
        self.permissao("view_solicitacaocompra")
        resposta = self.client.get(reverse("compras:solicitacao_lista"))
        self.assertContains(resposta, "Compras")
        self.assertContains(resposta, 'aria-current="page"')

    def test_criacao_exige_add(self):
        self.assertEqual(self.client.get(reverse("compras:solicitacao_criar")).status_code, 403)

    def test_filtro_lista_oferece_apenas_empresas_autorizadas(self):
        self.permissao("view_solicitacaocompra")
        resposta = self.client.get(reverse("compras:solicitacao_lista"))
        self.assertContains(resposta, self.empresa.razao_social)
        self.assertNotContains(resposta, self.outra_empresa.razao_social)
        self.assertEqual(self.client.get(reverse("compras:solicitacao_lista"), {"empresa": self.outra_empresa.pk}).status_code, 403)

    def test_nova_solicitacao_inicia_com_um_item_e_template_progressivo(self):
        self.permissao("add_solicitacaocompra")
        resposta = self.client.get(reverse("compras:solicitacao_criar"))
        self.assertContains(resposta, 'name="itens-TOTAL_FORMS" value="1"', html=False)
        self.assertContains(resposta, 'id="item-form-template"')
        self.assertContains(resposta, "Item previsto da proposta")

    def test_criacao_com_item_nao_previsto(self):
        self.permissao("add_solicitacaocompra", "view_solicitacaocompra")
        dados = {"empresa": self.empresa.pk, "obra": self.obra.pk, "data_solicitacao": "2026-08-19", "prioridade": "NORMAL", "observacao": "Teste", "itens-TOTAL_FORMS": "3", "itens-INITIAL_FORMS": "0", "itens-MIN_NUM_FORMS": "0", "itens-MAX_NUM_FORMS": "1000", "itens-0-proposta_item": "", "itens-0-tipo_origem": "NAO_PREVISTO", "itens-0-descricao": "Material extra", "itens-0-quantidade": "2", "itens-0-unidade": "UN", "itens-0-data_necessaria": "2026-08-25", "itens-0-descricao_item_substituido": "", "itens-0-observacao": "", "itens-1-proposta_item": "", "itens-1-tipo_origem": "NAO_PREVISTO", "itens-1-descricao": "", "itens-1-quantidade": "", "itens-1-unidade": "", "itens-1-data_necessaria": "", "itens-1-descricao_item_substituido": "", "itens-1-observacao": "", "itens-2-proposta_item": "", "itens-2-tipo_origem": "NAO_PREVISTO", "itens-2-descricao": "", "itens-2-quantidade": "", "itens-2-unidade": "", "itens-2-data_necessaria": "", "itens-2-descricao_item_substituido": "", "itens-2-observacao": ""}
        resposta = self.client.post(reverse("compras:solicitacao_criar"), dados)
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(SolicitacaoCompraItem.objects.get().tipo_origem, "NAO_PREVISTO")

    def test_detalhe_mostra_origens_snapshots_e_historico(self):
        solicitacao = self.solicitacao(); self.item(solicitacao=solicitacao, proposta_item=self.proposta_item, tipo="PREVISTO"); self.permissao("view_solicitacaocompra")
        resposta = self.client.get(reverse("compras:solicitacao_detalhe", args=[solicitacao.pk]))
        self.assertContains(resposta, "Previsto")
        self.assertContains(resposta, "R$ 5,00")

    def test_endpoint_oferece_itens_da_revisao_aprovada(self):
        self.permissao("add_solicitacaocompra")
        resposta = self.client.get(reverse("compras:itens_previstos_obra", args=[self.obra.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["itens"][0]["id"], self.proposta_item.pk)

    def test_endpoint_oferece_somente_revisao_um_aprovada(self):
        revisao_um = PropostaRevisao.objects.create(proposta=self.proposta, numero=1, data_proposta=date(2026, 8, 20), nome_servico="Revisão 01")
        item_um = PropostaItem.objects.create(revisao=revisao_um, tipo=PropostaItem.Tipo.MATERIAL, descricao="Único aprovado", quantidade=1, custo_unitario=1)
        self.proposta.revisao_atual = 1; self.proposta.revisao_aprovada = revisao_um; self.proposta.save()
        self.permissao("add_solicitacaocompra")
        ids = [item["id"] for item in self.client.get(reverse("compras:itens_previstos_obra", args=[self.obra.pk])).json()["itens"]]
        self.assertEqual(ids, [item_um.pk])
        self.assertNotIn(self.proposta_item.pk, ids)


class ProcessoCotacaoTests(ComprasBase):
    def setUp(self):
        super().setUp()
        self.solic = self.solicitacao(); self.item_sc = self.item(solicitacao=self.solic)
        self.solic.status = SolicitacaoCompra.Status.ABERTA; self.solic.save(update_fields=["status"])
        self.processo = ProcessoCotacao.objects.create(empresa=self.empresa, responsavel=self.usuario, criado_por=self.usuario)
        self.pi = ProcessoCotacaoItem.objects.create(processo=self.processo, solicitacao_item=self.item_sc, quantidade_cotada=10, unidade="UN")
        self.f1 = Pessoa.objects.create(razao_social="Fornecedor TESTE A", classificacao=Pessoa.Classificacao.FORNECEDOR)
        self.f2 = Pessoa.objects.create(razao_social="Fornecedor TESTE B", classificacao=Pessoa.Classificacao.AMBOS)

    def cotacao(self, fornecedor=None, **kwargs):
        dados={"processo":self.processo,"fornecedor":fornecedor or self.f1,"registrada_por":self.usuario,"status":CotacaoFornecedor.Status.RECEBIDA}; dados.update(kwargs)
        return CotacaoFornecedor.objects.create(**dados)

    def oferta(self, cotacao=None, item=None, **kwargs):
        dados={"cotacao":cotacao or self.cotacao(),"processo_item":item or self.pi,"quantidade_ofertada":10,"unidade":"UN","preco_unitario":Decimal("10")}; dados.update(kwargs)
        return CotacaoFornecedorItem.objects.create(**dados)

    def test_item_de_outra_empresa_e_rejeitado(self):
        obra=CentroCusto.objects.create(empresa=self.outra_empresa,codigo="TESTE-COT-2",nome="Outra")
        sc=self.solicitacao(obra=obra,empresa=self.outra_empresa); it=self.item(solicitacao=sc); sc.status="ABERTA"; sc.save(update_fields=["status"])
        with self.assertRaises(ValidationError): ProcessoCotacaoItem.objects.create(processo=self.processo,solicitacao_item=it,quantidade_cotada=1,unidade="UN")

    def test_item_duplicado_e_bloqueado(self):
        with self.assertRaises(ValidationError): ProcessoCotacaoItem.objects.create(processo=self.processo,solicitacao_item=self.item_sc,quantidade_cotada=1,unidade="UN")

    def test_solicitacao_invalida_e_item_cancelado(self):
        sc=self.solicitacao(); it=self.item(solicitacao=sc)
        with self.assertRaises(ValidationError): ProcessoCotacaoItem.objects.create(processo=self.processo,solicitacao_item=it,quantidade_cotada=1,unidade="UN")
        SolicitacaoCompraItem.objects.filter(pk=self.item_sc.pk).update(cancelado=True); self.item_sc.refresh_from_db()
        with self.assertRaises(ValidationError): self.pi.full_clean()

    def test_fornecedor_inativo_ou_cliente_e_rejeitado(self):
        self.f1.ativo=False; self.f1.save()
        with self.assertRaises(ValidationError): self.cotacao(self.f1)
        with self.assertRaises(ValidationError): self.cotacao(self.cliente)

    def test_multiplos_fornecedores_e_ausencia_de_oferta(self):
        c1=self.cotacao(self.f1); c2=self.cotacao(self.f2); self.oferta(c1)
        self.assertEqual(self.processo.cotacoes_fornecedor.count(),2); self.assertFalse(c2.itens.exists())

    def test_preco_desconto_impostos_frete_e_despesas(self):
        c=self.cotacao(valor_frete=Decimal("10"),desconto_global=Decimal("5"),impostos_globais=Decimal("2"),outras_despesas=Decimal("3"))
        o=self.oferta(c,desconto_item=Decimal("4"),impostos_item=Decimal("1"))
        self.assertEqual(o.preco_total,Decimal("100.00")); self.assertEqual(calcular_custos_cotacao(c)[o.pk]["custo_efetivo"],Decimal("107.00"))

    def test_rateio_fecha_centavos_deterministicamente(self):
        sc2=self.solicitacao(); i2=self.item(solicitacao=sc2,descricao="B"); sc2.status="ABERTA"; sc2.save(update_fields=["status"])
        pi2=ProcessoCotacaoItem.objects.create(processo=self.processo,solicitacao_item=i2,quantidade_cotada=1,unidade="UN")
        c=self.cotacao(valor_frete=Decimal("0.01")); o1=self.oferta(c,preco_unitario=1); o2=self.oferta(c,item=pi2,preco_unitario=1,quantidade_ofertada=10)
        custos=calcular_custos_cotacao(c); self.assertEqual(sum(x["frete_rateado"] for x in custos.values()),Decimal("0.01")); self.assertEqual(custos[min(o1.pk,o2.pk)]["frete_rateado"],Decimal("0.01"))

    def test_inicio_atualiza_solicitacao_e_historico(self):
        self.permissao("change_processocotacao"); iniciar_processo_cotacao(self.processo,self.usuario); self.solic.refresh_from_db()
        self.assertEqual(self.solic.status,"EM_COTACAO"); self.assertEqual(self.processo.historico.count(),1)

    def test_escolha_menor_custo_e_fornecedores_diferentes(self):
        c1=self.cotacao(self.f1); c2=self.cotacao(self.f2); o1=self.oferta(c1,preco_unitario=10); o2=self.oferta(c2,preco_unitario=11)
        self.permissao("change_processocotacao","selecionar_fornecedor"); iniciar_processo_cotacao(self.processo,self.usuario)
        escolha=selecionar_oferta(self.pi,o1,self.usuario); self.assertTrue(escolha.era_menor_preco)

    def test_escolha_mais_cara_exige_justificativa(self):
        c1=self.cotacao(self.f1); c2=self.cotacao(self.f2); self.oferta(c1,preco_unitario=10); cara=self.oferta(c2,preco_unitario=11)
        self.permissao("change_processocotacao","selecionar_fornecedor"); iniciar_processo_cotacao(self.processo,self.usuario)
        with self.assertRaises(ValidationError): selecionar_oferta(self.pi,cara,self.usuario)
        self.assertEqual(selecionar_oferta(self.pi,cara,self.usuario,"Melhor prazo").justificativa,"Melhor prazo")

    def test_indisponivel_e_vencida_nao_podem_ser_escolhidas(self):
        c=self.cotacao(validade=date(2020,1,1)); o=self.oferta(c)
        self.permissao("change_processocotacao","selecionar_fornecedor"); iniciar_processo_cotacao(self.processo,self.usuario)
        with self.assertRaises(ValidationError): selecionar_oferta(self.pi,o,self.usuario)
        c.validade=None; c.save(); o.disponivel=False; o.save()
        with self.assertRaises(ValidationError): selecionar_oferta(self.pi,o,self.usuario)

    def test_conclusao_exige_escolha_e_congela(self):
        c=self.cotacao(); o=self.oferta(c); self.permissao("change_processocotacao","selecionar_fornecedor"); iniciar_processo_cotacao(self.processo,self.usuario)
        with self.assertRaises(ValidationError): concluir_processo_cotacao(self.processo,self.usuario)
        selecionar_oferta(self.pi,o,self.usuario); concluir_processo_cotacao(self.processo,self.usuario)
        o.preco_unitario=12
        with self.assertRaises(ValidationError): o.save()

    def test_cancelamento_e_permissoes(self):
        with self.assertRaises(PermissionDenied): cancelar_processo_cotacao(self.processo,self.usuario,"motivo")
        self.permissao("cancelar_cotacao"); cancelar_processo_cotacao(self.processo,self.usuario,"motivo")
        self.assertEqual(self.processo.status,"CANCELADA"); self.assertEqual(self.processo.historico.get().observacao,"motivo")

    def test_mapa_nao_cria_escolha_automatica(self):
        self.oferta(self.cotacao()); mapa=montar_mapa_comparativo(self.processo)
        self.assertEqual(len(mapa),1); self.assertFalse(EscolhaCotacaoItem.objects.exists())

    def test_views_exigem_permissao_e_renderizam(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(reverse("compras:cotacao_lista")).status_code,403)
        self.permissao("view_processocotacao")
        self.assertEqual(self.client.get(reverse("compras:cotacao_lista")).status_code,200)
        self.assertContains(self.client.get(reverse("compras:cotacao_detalhe",args=[self.processo.pk])),self.processo.identificacao)


class PedidoCompraTests(ComprasBase):
    def setUp(self):
        super().setUp()
        self.fornecedor=Pessoa.objects.create(razao_social="Fornecedor Pedido",classificacao=Pessoa.Classificacao.FORNECEDOR)

    def pedido(self,**kwargs):
        dados={"empresa":self.empresa,"fornecedor":self.fornecedor,"origem":PedidoCompra.Origem.DIRETA,"justificativa_origem":"Compra direta TESTE","numero_pedido_versatile":"PC TESTE 01","condicao_pagamento":"28 dias","prazo_entrega":"5 dias","criado_por":self.usuario}; dados.update(kwargs)
        return PedidoCompra.objects.create(**dados)

    def item_pedido(self,pedido=None,**kwargs):
        dados={"pedido":pedido or self.pedido(),"descricao_mercadoria":"Material pedido","quantidade":Decimal("10"),"unidade":"UN","valor_unitario":Decimal("10")}; dados.update(kwargs)
        item=PedidoCompraItem.objects.create(**dados); recalcular_pedido(item.pedido); item.refresh_from_db(); return item

    def alocar(self,item,obra=None,**kwargs):
        dados={"pedido_item":item,"obra":obra or self.obra,"quantidade":item.quantidade,"valor":item.custo_total,"tipo_origem":"NAO_PREVISTO"}; dados.update(kwargs)
        return PedidoItemAlocacaoObra.objects.create(**dados)

    def test_numero_obrigatorio_normaliza_espacos_e_preserva_conteudo(self):
        with self.assertRaises(ValidationError): self.pedido(numero_pedido_versatile="  ")
        p=self.pedido(numero_pedido_versatile="  PC   Ab-01  "); self.assertEqual(p.numero_pedido_versatile,"PC Ab-01")

    def test_numero_unico_por_empresa_e_repetido_em_outra(self):
        self.pedido()
        with self.assertRaises(ValidationError): self.pedido()
        obra=CentroCusto.objects.create(empresa=self.outra_empresa,codigo="PED-OUTRA",nome="Outra")
        p=self.pedido(empresa=self.outra_empresa,numero_pedido_versatile="PC TESTE 01"); self.assertEqual(p.empresa,self.outra_empresa)

    def test_direto_e_emergencial_exigem_justificativa(self):
        for origem in (PedidoCompra.Origem.DIRETA,PedidoCompra.Origem.EMERGENCIAL):
            with self.assertRaises(ValidationError): self.pedido(origem=origem,justificativa_origem="",numero_pedido_versatile=f"{origem}-1")
        self.assertEqual(self.pedido(origem="EMERGENCIAL",numero_pedido_versatile="EM-1").origem,"EMERGENCIAL")

    def test_fornecedor_inativo_e_rejeitado(self):
        self.fornecedor.ativo=False; self.fornecedor.save()
        with self.assertRaises(ValidationError): self.pedido()

    def test_custos_globais_e_arredondamento(self):
        p=self.pedido(frete=Decimal("0.01"),desconto=Decimal("1"),impostos=Decimal("2"),outras_despesas=Decimal("3"))
        a=self.item_pedido(p,quantidade=1,valor_unitario=10); b=self.item_pedido(p,quantidade=1,valor_unitario=10,descricao_mercadoria="B")
        recalcular_pedido(p); a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual(a.frete_alocado+b.frete_alocado,Decimal("0.01")); self.assertEqual(p.total,Decimal("24.01"))

    def test_multiplas_obras_fecham_quantidade_e_valor(self):
        p=self.pedido(); item=self.item_pedido(p); obra2=CentroCusto.objects.create(empresa=self.empresa,codigo="OBRA-PED-2",nome="Obra 2")
        self.alocar(item,quantidade=4,valor=40); self.alocar(item,obra2,quantidade=6,valor=60)
        self.permissao("change_pedidocompra"); submeter_pedido(p,self.usuario); p.refresh_from_db(); self.assertEqual(p.status,"AGUARDANDO_APROVACAO")

    def test_alocacao_incorreta_bloqueia_submissao(self):
        p=self.pedido(); item=self.item_pedido(p); self.alocar(item,quantidade=9,valor=90); self.permissao("change_pedidocompra")
        with self.assertRaises(ValidationError): submeter_pedido(p,self.usuario)

    def test_obra_inativa_e_empresa_divergente(self):
        p=self.pedido(); item=self.item_pedido(p); self.obra.ativo=False; self.obra.save()
        with self.assertRaises(ValidationError): self.alocar(item)
        outra=CentroCusto.objects.create(empresa=self.outra_empresa,codigo="PED-OUT",nome="Outra")
        with self.assertRaises(ValidationError): self.alocar(item,outra)

    def _cotacao_dupla(self):
        sc1=self.solicitacao(); i1=self.item(solicitacao=sc1,proposta_item=self.proposta_item,tipo="PREVISTO"); sc1.status="EM_COTACAO"; sc1.save(update_fields=["status"])
        obra2=CentroCusto.objects.create(empresa=self.empresa,codigo="PED-OBRA-2",nome="Segunda obra")
        sc2=self.solicitacao(obra=obra2); i2=self.item(solicitacao=sc2); sc2.status="EM_COTACAO"; sc2.save(update_fields=["status"])
        processo=ProcessoCotacao.objects.create(empresa=self.empresa,responsavel=self.usuario,criado_por=self.usuario)
        pi1=ProcessoCotacaoItem.objects.create(processo=processo,solicitacao_item=i1,quantidade_cotada=10,unidade="UN")
        pi2=ProcessoCotacaoItem.objects.create(processo=processo,solicitacao_item=i2,quantidade_cotada=10,unidade="UN")
        f2=Pessoa.objects.create(razao_social="Fornecedor Pedido 2",classificacao="FORNECEDOR")
        escolhas=[]
        for idx,(pi,forn) in enumerate(((pi1,self.fornecedor),(pi2,f2))):
            c=CotacaoFornecedor.objects.create(processo=processo,fornecedor=forn,nome_contato=f"Vendedor {idx}",condicao_pagamento="30 dias",prazo_entrega="7 dias",valor_frete=Decimal("5"),status="RECEBIDA",registrada_por=self.usuario)
            o=CotacaoFornecedorItem.objects.create(cotacao=c,processo_item=pi,quantidade_ofertada=10,unidade="UN",preco_unitario=10+idx)
            escolhas.append(EscolhaCotacaoItem.objects.create(processo_item=pi,oferta_escolhida=o,escolhido_por=self.usuario,era_menor_preco=True))
        ProcessoCotacao.objects.filter(pk=processo.pk).update(status="CONCLUIDA"); processo.status="CONCLUIDA"
        return processo,escolhas

    def test_cotacao_gera_um_pedido_por_fornecedor_com_snapshots(self):
        processo,escolhas=self._cotacao_dupla(); self.permissao("criar_pedido")
        pedidos=gerar_pedidos_da_cotacao(processo,{self.fornecedor.pk:"COT-A",escolhas[1].oferta_escolhida.cotacao.fornecedor_id:"COT-B"},self.usuario)
        self.assertEqual(len(pedidos),2); self.assertEqual({p.fornecedor_id for p in pedidos},{e.oferta_escolhida.cotacao.fornecedor_id for e in escolhas})
        primeiro=PedidoCompraItem.objects.get(escolha_cotacao_item=escolhas[0]); self.assertEqual(primeiro.proposta_codigo_snapshot,"VERS7001"); self.assertEqual(primeiro.alocacoes.get().obra,self.obra)

    def test_nao_duplica_pedido_da_mesma_escolha(self):
        processo,escolhas=self._cotacao_dupla(); self.permissao("criar_pedido"); numeros={e.oferta_escolhida.cotacao.fornecedor_id:f"N-{n}" for n,e in enumerate(escolhas)}
        gerar_pedidos_da_cotacao(processo,numeros,self.usuario)
        with self.assertRaises(ValidationError): gerar_pedidos_da_cotacao(processo,numeros,self.usuario)

    def test_aprovacao_envio_e_imutabilidade(self):
        p=self.pedido(); item=self.item_pedido(p); self.alocar(item); self.permissao("change_pedidocompra","aprovar_pedido","enviar_pedido")
        p=submeter_pedido(p,self.usuario); p=aprovar_pedido(p,self.usuario); self.assertEqual(p.aprovado_por,self.usuario)
        p=enviar_pedido(p,self.usuario); self.assertEqual(p.status,"ENVIADO_FORNECEDOR")
        item.descricao_mercadoria="Alterado"
        with self.assertRaises(ValidationError): item.save()

    def test_rejeicao_exige_motivo_e_registra_historico(self):
        p=self.pedido(); item=self.item_pedido(p); self.alocar(item); self.permissao("change_pedidocompra","rejeitar_pedido"); p=submeter_pedido(p,self.usuario)
        with self.assertRaises(ValidationError): rejeitar_pedido(p,self.usuario,"")
        p=rejeitar_pedido(p,self.usuario,"Preço não aprovado"); self.assertEqual(p.status,"REJEITADO"); self.assertEqual(p.historico.first().observacao,"Preço não aprovado")

    def test_cancelamento_exige_motivo(self):
        p=self.pedido(); item=self.item_pedido(p); self.alocar(item); self.permissao("change_pedidocompra","aprovar_pedido","cancelar_pedido"); p=submeter_pedido(p,self.usuario); p=aprovar_pedido(p,self.usuario)
        with self.assertRaises(ValidationError): cancelar_pedido(p,self.usuario,"")
        self.assertEqual(cancelar_pedido(p,self.usuario,"Cancelado pelo gestor").status,"CANCELADO")

    def test_transicao_invalida_e_permissoes(self):
        p=self.pedido()
        with self.assertRaises(PermissionDenied): submeter_pedido(p,self.usuario)
        self.permissao("aprovar_pedido")
        with self.assertRaises(ValidationError): aprovar_pedido(p,self.usuario)

    def test_documento_imprimivel_nao_expoe_comparativo(self):
        p=self.pedido(observacoes="Observação pública"); item=self.item_pedido(p); self.alocar(item); self.permissao("view_pedidocompra","view_custos_compra"); self.client.force_login(self.usuario)
        resposta=self.client.get(reverse("compras:pedido_imprimir",args=[p.pk])); self.assertEqual(resposta.status_code,200); self.assertContains(resposta,"PEDIDO DE COMPRA"); self.assertContains(resposta,"PC TESTE 01"); self.assertNotContains(resposta,"Compra direta TESTE"); self.assertNotContains(resposta,"mapa comparativo")

    def test_pdf_pedido_valido_com_fornecedor_itens_obras_e_sem_dados_de_cotacao(self):
        p=self.pedido(observacoes="Observação pública",dados_bancarios="Banco TESTE"); item=self.item_pedido(p); obra2=CentroCusto.objects.create(empresa=self.empresa,codigo="OBRA-PDF-2",nome="Obra PDF 2"); self.alocar(item,quantidade=4,valor=40); self.alocar(item,obra2,quantidade=6,valor=60); recalcular_pedido(p); PedidoCompra.objects.filter(pk=p.pk).update(status="APROVADO"); self.permissao("view_pedidocompra","view_custos_compra"); self.client.force_login(self.usuario)
        resposta=self.client.get(reverse("compras:pedido_pdf",args=[p.pk])); self.assertEqual(resposta.status_code,200); self.assertTrue(resposta.content.startswith(b"%PDF")); texto="\n".join(pg.extract_text() or "" for pg in PdfReader(BytesIO(resposta.content)).pages); self.assertIn("PEDIDO DE COMPRA",texto); self.assertIn("PC TESTE 01",texto); self.assertIn("VERS7001",texto); self.assertIn("OBRA-PDF-2",texto); self.assertNotIn("mapa comparativo",texto.lower()); self.assertNotIn("Compra direta TESTE",texto)

    def test_detalhe_oculta_custos_sem_permissao(self):
        p=self.pedido(); item=self.item_pedido(p); self.alocar(item); self.permissao("view_pedidocompra"); self.client.force_login(self.usuario)
        detalhe=self.client.get(reverse("compras:pedido_detalhe",args=[p.pk]))
        self.assertNotContains(detalhe,"Valor unitário")
        self.assertNotContains(detalhe,"R$ 100,00")
        self.assertEqual(self.client.get(reverse("compras:pedido_imprimir",args=[p.pk])).status_code,403)
        self.assertEqual(self.client.get(reverse("compras:fornecedor_historico",args=[p.fornecedor_id])).status_code,403)


class RecebimentoCompraTests(ComprasBase):
    def setUp(self):
        super().setUp(); self.fornecedor=Pessoa.objects.create(razao_social="Fornecedor Recebimento",classificacao="FORNECEDOR")
    def pedido(self,quantidade=100,status="APROVADO",numero="REC-TESTE-1"):
        p=PedidoCompra.objects.create(empresa=self.empresa,fornecedor=self.fornecedor,origem="DIRETA",justificativa_origem="Teste",numero_pedido_versatile=numero,condicao_pagamento="28 dias",prazo_entrega="5 dias",criado_por=self.usuario)
        item=PedidoCompraItem.objects.create(pedido=p,descricao_mercadoria="Material recebido",quantidade=quantidade,unidade="UN",valor_unitario=10)
        recalcular_pedido(p); PedidoCompra.objects.filter(pk=p.pk).update(status=status); p.status=status; item.refresh_from_db(); return p,item
    def recebimento(self,pedido,item,recebida,aceita,rejeitada=0):
        r=RecebimentoCompra.objects.create(pedido=pedido,responsavel=self.usuario,criado_por=self.usuario)
        ri=RecebimentoCompraItem.objects.create(recebimento=r,pedido_item=item,quantidade_recebida=recebida,quantidade_aceita=aceita,quantidade_rejeitada=rejeitada)
        return r,ri
    def test_recebimento_total(self):
        p,i=self.pedido(); r,_=self.recebimento(p,i,100,100); self.permissao("registrar_recebimento"); confirmar_recebimento(r,self.usuario); p.refresh_from_db()
        self.assertEqual(p.status,"RECEBIDO"); self.assertEqual(quantidades_recebimento_pedido(p)[i.pk]["pendente"],0)
    def test_parcial_rejeitado_nao_reduz_pendencia(self):
        p,i=self.pedido(); r,_=self.recebimento(p,i,60,55,5); self.permissao("registrar_recebimento"); confirmar_recebimento(r,self.usuario); p.refresh_from_db(); q=quantidades_recebimento_pedido(p)[i.pk]
        self.assertEqual((q["recebida"],q["pendente"],p.status),(Decimal("55"),Decimal("45"),"PARCIALMENTE_RECEBIDO"))
    def test_multiplos_recebimentos_completam(self):
        p,i=self.pedido(); self.permissao("registrar_recebimento"); r1,_=self.recebimento(p,i,55,55); confirmar_recebimento(r1,self.usuario); p.refresh_from_db(); r2,_=self.recebimento(p,i,45,45); confirmar_recebimento(r2,self.usuario); p.refresh_from_db()
        self.assertEqual(p.status,"RECEBIDO"); self.assertEqual(quantidades_recebimento_pedido(p)[i.pk]["recebida"],100)
    def test_multiplos_itens_status_depende_de_todos(self):
        p,i1=self.pedido(); PedidoCompra.objects.filter(pk=p.pk).update(status="RASCUNHO"); p.status="RASCUNHO"; i2=PedidoCompraItem.objects.create(pedido=p,descricao_mercadoria="Segundo",quantidade=5,unidade="UN",valor_unitario=1); PedidoCompra.objects.filter(pk=p.pk).update(status="APROVADO"); p.status="APROVADO"
        r=RecebimentoCompra.objects.create(pedido=p,responsavel=self.usuario,criado_por=self.usuario); RecebimentoCompraItem.objects.create(recebimento=r,pedido_item=i1,quantidade_recebida=100,quantidade_aceita=100); RecebimentoCompraItem.objects.create(recebimento=r,pedido_item=i2,quantidade_recebida=2,quantidade_aceita=2); self.permissao("registrar_recebimento"); confirmar_recebimento(r,self.usuario); p.refresh_from_db(); self.assertEqual(p.status,"PARCIALMENTE_RECEBIDO")
    def test_excedente_e_concorrencia_logica_bloqueados(self):
        p,i=self.pedido(); self.permissao("registrar_recebimento"); r1,_=self.recebimento(p,i,60,60); r2,_=self.recebimento(p,i,50,50); confirmar_recebimento(r1,self.usuario)
        with self.assertRaises(ValidationError): confirmar_recebimento(r2,self.usuario)
        self.assertEqual(quantidades_recebimento_pedido(p)[i.pk]["recebida"],60)
    def test_pedido_recebido_bloqueia_novo(self):
        p,i=self.pedido(); self.permissao("registrar_recebimento"); r,_=self.recebimento(p,i,100,100); confirmar_recebimento(r,self.usuario); p.refresh_from_db()
        with self.assertRaises(ValidationError): RecebimentoCompra.objects.create(pedido=p,responsavel=self.usuario,criado_por=self.usuario)
    def test_cancelamento_reverte_quantidade_e_status(self):
        p,i=self.pedido(status="ENVIADO_FORNECEDOR"); self.permissao("registrar_recebimento","cancelar_recebimento"); r,_=self.recebimento(p,i,40,40); confirmar_recebimento(r,self.usuario); cancelar_recebimento(r,self.usuario,"Entrega anulada"); p.refresh_from_db()
        self.assertEqual(p.status,"ENVIADO_FORNECEDOR"); self.assertEqual(quantidades_recebimento_pedido(p)[i.pk]["recebida"],0); self.assertEqual(r.motivo_cancelamento,"Entrega anulada")
    def test_cancelamento_exige_motivo_e_permissao(self):
        p,i=self.pedido(); self.permissao("registrar_recebimento"); r,_=self.recebimento(p,i,10,10); confirmar_recebimento(r,self.usuario)
        with self.assertRaises(PermissionDenied): cancelar_recebimento(r,self.usuario,"motivo")
        self.permissao("cancelar_recebimento")
        with self.assertRaises(ValidationError): cancelar_recebimento(r,self.usuario,"")
    def test_quantidades_incoerentes(self):
        p,i=self.pedido()
        with self.assertRaises(ValidationError): self.recebimento(p,i,10,8,3)
    def test_divergencias_e_preco_nao_alteram_pedido(self):
        p,i=self.pedido(); r,ri=self.recebimento(p,i,10,8,2); valor=i.valor_unitario
        for n,tipo in enumerate(("QUANTIDADE_MENOR","MATERIAL_INCORRETO","DANIFICADO","PRECO_DIVERGENTE")):
            DivergenciaRecebimento.objects.create(recebimento_item=ri,tipo=tipo,descricao=f"Divergência {n}",quantidade_afetada=1)
        i.refresh_from_db(); self.assertEqual(i.valor_unitario,valor); self.assertEqual(ri.divergencias.count(),4)
    def test_resolucao_divergencia(self):
        p,i=self.pedido(); r,ri=self.recebimento(p,i,10,10); d=DivergenciaRecebimento.objects.create(recebimento_item=ri,tipo="OUTRO",descricao="Teste"); self.permissao("resolver_divergencia_recebimento"); resolver_divergencia(d,self.usuario,"Resolvido com fornecedor")
        self.assertTrue(d.resolvida); self.assertEqual(d.resolvida_por,self.usuario)
    def test_recebimento_confirmado_e_imutavel(self):
        p,i=self.pedido(); r,ri=self.recebimento(p,i,10,10); self.permissao("registrar_recebimento"); confirmar_recebimento(r,self.usuario); ri.quantidade_aceita=9
        with self.assertRaises(ValidationError): ri.save()
        r.observacao="alterada"
        with self.assertRaises(ValidationError): r.save()
    def test_pedido_cancelado_ou_rejeitado_nao_recebe(self):
        for n,status in enumerate(("CANCELADO","REJEITADO")):
            p,i=self.pedido(status=status,numero=f"REC-BLOQ-{n}")
            with self.assertRaises(ValidationError): RecebimentoCompra.objects.create(pedido=p,responsavel=self.usuario,criado_por=self.usuario)
    def test_isolamento_empresa_item_alheio(self):
        p,i=self.pedido(); obra=CentroCusto.objects.create(empresa=self.outra_empresa,codigo="REC-OUT",nome="Outra"); f=Pessoa.objects.create(razao_social="Fora",classificacao="FORNECEDOR"); p2=PedidoCompra.objects.create(empresa=self.outra_empresa,fornecedor=f,origem="DIRETA",justificativa_origem="x",numero_pedido_versatile="OUT",condicao_pagamento="x",prazo_entrega="x",criado_por=self.usuario); i2=PedidoCompraItem.objects.create(pedido=p2,descricao_mercadoria="Fora",quantidade=1,unidade="UN",valor_unitario=1); PedidoCompra.objects.filter(pk=p2.pk).update(status="APROVADO"); p2.status="APROVADO"; r=RecebimentoCompra.objects.create(pedido=p,responsavel=self.usuario,criado_por=self.usuario)
        with self.assertRaises(ValidationError): RecebimentoCompraItem.objects.create(recebimento=r,pedido_item=i2,quantidade_recebida=1,quantidade_aceita=1)
    def test_telas_e_permissoes(self):
        p,i=self.pedido(); r,ri=self.recebimento(p,i,10,10); self.client.force_login(self.usuario); self.assertEqual(self.client.get(reverse("compras:recebimento_detalhe",args=[r.pk])).status_code,403); self.permissao("view_recebimentocompra","view_pedidocompra"); self.assertContains(self.client.get(reverse("compras:recebimento_detalhe",args=[r.pk])),"Material recebido"); self.assertContains(self.client.get(reverse("compras:pedido_detalhe",args=[p.pk])),"Pendente")


class PrevistoCompradoTests(ComprasBase):
    def setUp(self):
        super().setUp(); self.fornecedor=Pessoa.objects.create(razao_social="Fornecedor Análise",classificacao="FORNECEDOR"); self.seq=0
    def comprar(self,proposta_item=None,quantidade=10,unitario=10,valor_alocacao=None,obra=None,tipo="PREVISTO",status="APROVADO",recebido=0,rejeitado=0):
        self.seq+=1; obra=obra or self.obra
        p=PedidoCompra.objects.create(empresa=obra.empresa,fornecedor=self.fornecedor,origem="DIRETA",justificativa_origem="Teste",numero_pedido_versatile=f"AN-{self.seq}",condicao_pagamento="28 dias",prazo_entrega="5 dias",criado_por=self.usuario)
        item=PedidoCompraItem.objects.create(pedido=p,proposta_item=proposta_item,descricao_mercadoria=f"Compra {self.seq}",quantidade=quantidade,unidade=proposta_item.unidade if proposta_item else "UN",valor_unitario=unitario); recalcular_pedido(p); item.refresh_from_db()
        aloc=PedidoItemAlocacaoObra.objects.create(pedido_item=item,obra=obra,proposta_item=proposta_item,quantidade=quantidade,valor=valor_alocacao if valor_alocacao is not None else item.custo_total,tipo_origem=tipo)
        PedidoCompra.objects.filter(pk=p.pk).update(status=status); p.status=status
        if recebido or rejeitado:
            r=RecebimentoCompra.objects.create(pedido=p,responsavel=self.usuario,criado_por=self.usuario); RecebimentoCompraItem.objects.create(recebimento=r,pedido_item=item,quantidade_recebida=recebido+rejeitado,quantidade_aceita=recebido,quantidade_rejeitada=rejeitado); RecebimentoCompra.objects.filter(pk=r.pk).update(status="CONFIRMADO")
        return p,item,aloc
    def linha(self,relatorio=None,item=None):
        item=item or self.proposta_item; return next(x for x in (relatorio or calcular_previsto_comprado(self.obra))["itens_previstos"] if x["previsto"].pk==item.pk)
    def test_item_previsto_sem_compra(self):
        l=self.linha(); self.assertEqual(l["situacao"],"NAO_COMPRADO"); self.assertEqual(l["pendente_compra"],Decimal("500"))
    def test_compra_parcial_total_e_acima(self):
        self.comprar(self.proposta_item,quantidade=60,unitario=5); l=self.linha(); self.assertEqual((l["percentual_comprado"],l["pendente_compra"]),(Decimal("12.00"),Decimal("440")))
        self.comprar(self.proposta_item,quantidade=500,unitario=5); l=self.linha(); self.assertIn("Quantidade acima do previsto",l["alertas"])
    def test_economia_e_custo_acima(self):
        self.comprar(self.proposta_item,quantidade=500,unitario=4); self.assertEqual(self.linha()["diferenca_financeira"],Decimal("-500.00"))
        self.comprar(self.proposta_item,quantidade=1,unitario=600); self.assertIn("Custo acima do previsto",self.linha()["alertas"])
    def test_media_ponderada_varios_pedidos_fornecedores(self):
        self.comprar(self.proposta_item,quantidade=100,unitario=4); outro=Pessoa.objects.create(razao_social="Outro Fornecedor Análise",classificacao="FORNECEDOR"); self.fornecedor=outro; self.comprar(self.proposta_item,quantidade=300,unitario=6); l=self.linha(); self.assertEqual(l["custo_medio"],Decimal("5.5000")); self.assertEqual(len(l["compras"]),2)
    def test_custo_efetivo_com_adicionais(self):
        p,item,a=self.comprar(self.proposta_item,quantidade=10,unitario=10); PedidoCompra.objects.filter(pk=p.pk).update(status="RASCUNHO",frete=10,desconto=5,impostos=2,outras_despesas=3); p.status="RASCUNHO"; p.frete=10;p.desconto=5;p.impostos=2;p.outras_despesas=3; recalcular_pedido(p); item.refresh_from_db(); PedidoItemAlocacaoObra.objects.filter(pk=a.pk).update(valor=item.custo_total); PedidoCompra.objects.filter(pk=p.pk).update(status="APROVADO"); self.assertEqual(self.linha()["valor_comprado"],Decimal("110.00"))
    def test_multiobra_nao_duplica_valor(self):
        outra=CentroCusto.objects.create(empresa=self.empresa,codigo="AN-OBRA-2",nome="Outra obra"); p,item,a=self.comprar(self.proposta_item,quantidade=10,unitario=10,valor_alocacao=40); PedidoCompra.objects.filter(pk=p.pk).update(status="RASCUNHO"); p.status="RASCUNHO"; PedidoItemAlocacaoObra.objects.create(pedido_item=item,obra=outra,proposta_item=self.proposta_item,quantidade=15,valor=60,tipo_origem="PREVISTO"); PedidoCompra.objects.filter(pk=p.pk).update(status="APROVADO"); self.assertEqual(self.linha()["valor_comprado"],Decimal("40"))
    def test_nao_previsto_e_substituicao(self):
        self.comprar(None,quantidade=2,unitario=20,tipo="NAO_PREVISTO"); self.comprar(self.proposta_item,quantidade=1,unitario=30,tipo="SUBSTITUICAO"); r=calcular_previsto_comprado(self.obra); self.assertEqual(len(r["nao_previstos"]),1); self.assertEqual(len(r["substituicoes"]),1)
    def test_recebimento_parcial_multiplos_e_rejeitado(self):
        self.comprar(self.proposta_item,quantidade=100,unitario=5,recebido=30,rejeitado=5); self.comprar(self.proposta_item,quantidade=50,unitario=5,recebido=50); l=self.linha(); self.assertEqual(l["quantidade_recebida"],Decimal("80")); self.assertEqual(l["pendente_recebimento"],Decimal("70"))
    def test_pedido_cancelado_ou_rejeitado_fora(self):
        self.comprar(self.proposta_item,status="CANCELADO"); self.comprar(self.proposta_item,status="REJEITADO"); self.assertEqual(self.linha()["quantidade_comprada"],0)
    def test_revisao_aprovada_exclusiva(self):
        nova=PropostaRevisao.objects.create(proposta=self.proposta,numero=1,data_proposta=date.today(),nome_servico="Não aprovada"); PropostaItem.objects.create(revisao=nova,tipo="MATERIAL",descricao="Fora",quantidade=999,custo_unitario=1); self.proposta.revisao_atual=1; self.proposta.save(); r=calcular_previsto_comprado(self.obra); self.assertEqual([x["previsto"].descricao for x in r["itens_previstos"]],["Cabo 4 mm"])
    def test_solicitado_por_vinculo_explicito(self):
        sc=self.solicitacao(); self.item(solicitacao=sc,proposta_item=self.proposta_item,tipo="PREVISTO",quantidade=25); self.assertEqual(self.linha()["quantidade_solicitada"],Decimal("25"))
    def test_ausencia_duplicidade_e_queries_controladas(self):
        self.comprar(self.proposta_item,quantidade=10); self.comprar(self.proposta_item,quantidade=20)
        with CaptureQueriesContext(connection) as contexto: r=calcular_previsto_comprado(self.obra)
        self.assertEqual(self.linha(r)["quantidade_comprada"],Decimal("30")); self.assertLessEqual(len(contexto),10)
    def test_isolamento_empresa(self):
        outra=CentroCusto.objects.create(empresa=self.outra_empresa,codigo="AN-OUT",nome="Outra"); self.comprar(None,obra=outra)
        self.assertEqual(self.linha()["quantidade_comprada"],0)
    def test_view_filtros_drilldown_e_permissao(self):
        self.comprar(self.proposta_item); self.client.force_login(self.usuario); url=reverse("compras:previsto_comprado_obra",args=[self.obra.pk]); self.assertEqual(self.client.get(url).status_code,403); self.permissao("view_pedidocompra"); resposta=self.client.get(url); self.assertContains(resposta,"Previsto × Comprado"); self.assertContains(self.client.get(reverse("compras:previsto_comprado_item",args=[self.obra.pk,self.proposta_item.pk])),"Drill-down")
