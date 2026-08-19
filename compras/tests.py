from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comercial.models import Proposta, PropostaItem, PropostaRevisao
from financeiro.models import CentroCusto, Empresa, PlanoConta
from pessoas.models import Pessoa

from .models import HistoricoSolicitacaoCompra, SolicitacaoCompra, SolicitacaoCompraItem
from .services import abrir_solicitacao, cancelar_solicitacao


class ComprasBase(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="comprador", password="teste123")
        self.empresa = Empresa.objects.create(razao_social="Empresa Compras", cnpj="51.111.111/0001-51")
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
