from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from financeiro.models import (CentroCusto, Empresa, LancamentoFinanceiro,
    ParcelaFinanceira, PlanoConta, RateioCentroCusto)
from pessoas.models import Pessoa
from .models import (DivergenciaDocumentoCompra, DocumentoCompra, DocumentoCompraItem,
    DocumentoCompraItemRecebimento, DocumentoCompraParcela, DocumentoCompraPedido,
    PedidoCompra, PedidoCompraItem, PedidoItemAlocacaoObra, RecebimentoCompra,
    RecebimentoCompraItem)
from .services import (cancelar_documento_compra, concluir_conferencia_documento,
    iniciar_conferencia_documento, reabrir_conferencia_documento,
    gerar_parcelas_documento, montar_preview_financeiro_documento,
    resolver_divergencia_documento, validar_fechamento_documento,
    vincular_recebimento_documento)


class DocumentoCompraTests(TestCase):
    def setUp(self):
        self.usuario=get_user_model().objects.create_user(username="doc",password="teste123")
        self.empresa=Empresa.objects.create(razao_social="TESTE Empresa Documento",cnpj="53.333.333/0001-53")
        self.fornecedor=Pessoa.objects.create(razao_social="TESTE Fornecedor Documento",classificacao=Pessoa.Classificacao.FORNECEDOR)
        self.plano=PlanoConta.objects.create(codigo="TESTE-DOC-01",nome="Materiais",tipo="CUSTO",natureza="DEVEDORA")
        self.plano_despesa=PlanoConta.objects.create(codigo="TESTE-DOC-02",nome="Fretes",tipo="DESPESA",natureza="DEVEDORA")
        self.pedido=PedidoCompra.objects.create(empresa=self.empresa,fornecedor=self.fornecedor,origem=PedidoCompra.Origem.DIRETA,justificativa_origem="Teste",numero_pedido_versatile="TESTE-PC-DOC",condicao_pagamento="30 dias",prazo_entrega="Imediato",criado_por=self.usuario)
        self.pedido_item=PedidoCompraItem.objects.create(pedido=self.pedido,descricao_mercadoria="Material A",quantidade=10,unidade="UN",valor_unitario=10,plano_conta=self.plano)
        PedidoCompra.objects.filter(pk=self.pedido.pk).update(status=PedidoCompra.Status.APROVADO); self.pedido.status=PedidoCompra.Status.APROVADO
        self.recebimento=RecebimentoCompra.objects.create(pedido=self.pedido,responsavel=self.usuario,criado_por=self.usuario)
        self.recebimento_item=RecebimentoCompraItem.objects.create(recebimento=self.recebimento,pedido_item=self.pedido_item,quantidade_recebida=10,quantidade_aceita=10,quantidade_rejeitada=0)
        RecebimentoCompra.objects.filter(pk=self.recebimento.pk).update(status=RecebimentoCompra.Status.CONFIRMADO); self.recebimento.status=RecebimentoCompra.Status.CONFIRMADO

    def permissao(self,*nomes):
        self.usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="compras",codename__in=nomes))
        for cache in ("_perm_cache","_user_perm_cache","_group_perm_cache"): self.usuario.__dict__.pop(cache,None)
    def documento(self,**kwargs):
        dados={"empresa":self.empresa,"fornecedor":self.fornecedor,"tipo":DocumentoCompra.Tipo.NOTA_FISCAL,"numero":" NF 001 ","serie":" a ","data_emissao":date(2026,8,19),"valor_bruto":Decimal("100"),"criado_por":self.usuario}; dados.update(kwargs); return DocumentoCompra.objects.create(**dados)
    def item(self,documento=None,**kwargs):
        dados={"documento":documento or self.documento(),"pedido_item":self.pedido_item,"descricao_snapshot":"Material A","quantidade_faturada":10,"unidade":"UN","valor_unitario_faturado":10,"plano_conta":self.plano}; dados.update(kwargs); return DocumentoCompraItem.objects.create(**dados)
    def fechado(self):
        d=self.documento(); i=self.item(d); DocumentoCompraPedido.objects.create(documento=d,pedido=self.pedido); vincular_recebimento_documento(i,self.recebimento_item,10); return d,i

    def test_formula_e_normalizacao(self):
        d=self.documento(valor_bruto=100,desconto=5,frete=8,impostos=3,outras_despesas=2,chave_fiscal="ABC 12.3"); self.assertEqual(d.valor_total,108); self.assertEqual((d.numero_normalizado,d.serie_normalizada,d.chave_fiscal),("NF001","A","ABC123"))
    def test_duplicidade_normalizada(self):
        self.documento()
        with self.assertRaises(ValidationError): self.documento(numero="nf001",serie="A")
    def test_chave_fiscal_unica(self):
        self.documento(chave_fiscal="123.456")
        with self.assertRaises(ValidationError): self.documento(numero="2",chave_fiscal="123456")
    def test_fornecedor_deve_coincidir(self):
        outro=Pessoa.objects.create(razao_social="Outro",classificacao=Pessoa.Classificacao.FORNECEDOR); d=self.documento(fornecedor=outro)
        with self.assertRaises(ValidationError): self.item(d)
    def test_multiplas_contas_explicitamente(self):
        d=self.documento(valor_bruto=150); a=self.item(d); b=self.item(d,pedido_item=None,descricao_snapshot="Frete",quantidade_faturada=1,valor_unitario_faturado=50,plano_conta=self.plano_despesa); self.assertNotEqual(a.plano_conta,b.plano_conta)
    def test_conta_de_receita_rejeitada(self):
        p=PlanoConta.objects.create(codigo="TESTE-DOC-R",nome="Receita",tipo="RECEITA",natureza="CREDORA")
        with self.assertRaises(ValidationError): self.item(plano_conta=p)
    def test_item_sem_conta_e_rejeitado_no_dominio(self):
        with self.assertRaises(ValidationError): self.item(plano_conta=None)
    def test_fechamento_exato(self):
        d=self.documento(valor_bruto=101); self.item(d); DocumentoCompraPedido.objects.create(documento=d,pedido=self.pedido)
        with self.assertRaises(ValidationError): validar_fechamento_documento(d)
    def test_recebimento_nao_e_usado_duas_vezes(self):
        d=self.documento(); i=self.item(d); vincular_recebimento_documento(i,self.recebimento_item,7); d2=self.documento(numero="2"); i2=self.item(d2)
        with self.assertRaises(ValidationError): vincular_recebimento_documento(i2,self.recebimento_item,4)
    def test_conferencia_sem_divergencia(self):
        self.permissao("conferir_documento_compra"); d,_=self.fechado(); iniciar_conferencia_documento(d,self.usuario); concluir_conferencia_documento(d,self.usuario); d.refresh_from_db(); self.assertEqual(d.status,DocumentoCompra.Status.CONFERIDO)
    def test_detecta_resolve_e_reabre(self):
        self.permissao("conferir_documento_compra","resolver_divergencia_documento"); d,i=self.fechado(); DocumentoCompraItemRecebimento.objects.filter(documento_item=i).update(quantidade_vinculada=8); iniciar_conferencia_documento(d,self.usuario); concluir_conferencia_documento(d,self.usuario); d.refresh_from_db(); self.assertEqual(d.status,DocumentoCompra.Status.DIVERGENTE); div=d.divergencias.get(tipo=DivergenciaDocumentoCompra.Tipo.QUANTIDADE_MAIOR); resolver_divergencia_documento(div,self.usuario,"Aceito"); reabrir_conferencia_documento(d,self.usuario); concluir_conferencia_documento(d,self.usuario); d.refresh_from_db(); self.assertEqual(d.status,DocumentoCompra.Status.CONFERIDO)
    def test_sem_vinculo_gera_divergencia(self):
        self.permissao("conferir_documento_compra"); d=self.documento(); self.item(d,pedido_item=None); iniciar_conferencia_documento(d,self.usuario); concluir_conferencia_documento(d,self.usuario); self.assertTrue(d.divergencias.filter(tipo=DivergenciaDocumentoCompra.Tipo.ITEM_SEM_VINCULO).exists())
    def test_conferido_e_imutavel(self):
        self.permissao("conferir_documento_compra"); d,i=self.fechado(); iniciar_conferencia_documento(d,self.usuario); concluir_conferencia_documento(d,self.usuario); d.refresh_from_db(); i.refresh_from_db(); d.observacoes="x"; i.descricao_snapshot="x"
        with self.assertRaises(ValidationError): d.save()
        with self.assertRaises(ValidationError): i.save()
    def test_cancelamento_exige_motivo_e_permissao(self):
        d=self.documento()
        with self.assertRaises(PermissionDenied): cancelar_documento_compra(d,self.usuario,"motivo")
        self.permissao("cancelar_documento_compra")
        with self.assertRaises(ValidationError): cancelar_documento_compra(d,self.usuario,"")
        cancelar_documento_compra(d,self.usuario,"Duplicado"); d.refresh_from_db(); self.assertEqual(d.status,DocumentoCompra.Status.CANCELADO)
    def test_permissoes_e_views(self):
        self.client.force_login(self.usuario); d=self.documento(); self.assertEqual(self.client.get(reverse("compras:documento_lista")).status_code,403); self.permissao("view_documentocompra"); self.assertEqual(self.client.get(reverse("compras:documento_lista")).status_code,200); self.assertEqual(self.client.get(reverse("compras:documento_detalhe",args=[d.pk])).status_code,200)
    def test_nao_cria_financeiro(self):
        antes=LancamentoFinanceiro.objects.count(); self.fechado(); self.assertEqual(LancamentoFinanceiro.objects.count(),antes)

    def preparar_preview(self,total=Decimal("100.00"),duas_obras=False):
        obra1=CentroCusto.objects.create(empresa=self.empresa,codigo="TESTE-OBRA-A",nome="Obra A")
        PedidoCompra.objects.filter(pk=self.pedido.pk).update(status=PedidoCompra.Status.RASCUNHO); self.pedido.status=PedidoCompra.Status.RASCUNHO
        PedidoItemAlocacaoObra.objects.create(pedido_item=self.pedido_item,obra=obra1,quantidade=7 if duas_obras else 10,valor=70 if duas_obras else 100,tipo_origem="NAO_PREVISTO")
        if duas_obras:
            obra2=CentroCusto.objects.create(empresa=self.empresa,codigo="TESTE-OBRA-B",nome="Obra B")
            PedidoItemAlocacaoObra.objects.create(pedido_item=self.pedido_item,obra=obra2,quantidade=3,valor=30,tipo_origem="NAO_PREVISTO")
        PedidoCompra.objects.filter(pk=self.pedido.pk).update(status=PedidoCompra.Status.APROVADO); self.pedido.status=PedidoCompra.Status.APROVADO
        d=self.documento(valor_bruto=total); i=self.item(d,quantidade_faturada=1,valor_unitario_faturado=total); DocumentoCompra.objects.filter(pk=d.pk).update(status=DocumentoCompra.Status.CONFERIDO); d.status=DocumentoCompra.Status.CONFERIDO
        DocumentoCompraParcela.objects.create(documento=d,numero=1,vencimento=date(2026,9,18),valor=total)
        return d,i

    def test_parcela_unica_manual(self):
        d=self.documento(); p=DocumentoCompraParcela.objects.create(documento=d,numero=1,vencimento=date(2026,8,19),valor=100); self.assertEqual(p.valor,100)
    def test_geracao_30_60_90_e_centavos(self):
        self.permissao("add_documentocompraparcela"); d=self.documento(valor_bruto=Decimal("10000.00")); parcelas=gerar_parcelas_documento(d,self.usuario,3,30,30); self.assertEqual([p.valor for p in parcelas],[Decimal("3333.33"),Decimal("3333.33"),Decimal("3333.34")]); self.assertEqual([p.vencimento for p in parcelas],[date(2026,9,19),date(2026,10,19),date(2026,11,19)])
    def test_parcelas_nao_fechando_bloqueiam(self):
        d,_=self.preparar_preview(); d.parcelas.update(valor=99); preview=montar_preview_financeiro_documento(d); self.assertFalse(preview["pronto"]); self.assertTrue(any("parcelas totalizam" in m for m in preview["motivos"]))
    def test_parcela_editavel_antes_integracao(self):
        d=self.documento(); p=DocumentoCompraParcela.objects.create(documento=d,numero=1,vencimento=date(2026,9,1),valor=100); p.observacao="Alterada"; p.save(); self.assertEqual(p.observacao,"Alterada")
    def test_documento_nao_conferido_bloqueia(self):
        d=self.documento(); DocumentoCompraParcela.objects.create(documento=d,numero=1,vencimento=date(2026,9,1),valor=100); self.assertIn("O documento ainda não está conferido.",montar_preview_financeiro_documento(d)["motivos"])
    def test_multiplos_planos_agrupados(self):
        d,i=self.preparar_preview(total=150); DocumentoCompra.objects.filter(pk=d.pk).update(status="RASCUNHO"); d.status="RASCUNHO"; i.quantidade_faturada=1;i.valor_unitario_faturado=100;i.save(); self.item(d,pedido_item=self.pedido_item,descricao_snapshot="Serviço",quantidade_faturada=1,valor_unitario_faturado=50,plano_conta=self.plano_despesa); DocumentoCompra.objects.filter(pk=d.pk).update(status="CONFERIDO"); d.status="CONFERIDO"; preview=montar_preview_financeiro_documento(d); self.assertEqual({c["plano_conta"] for c in preview["classificacoes"]},{self.plano,self.plano_despesa}); self.assertEqual(preview["total_classificacoes"],150)
    def test_conta_inativa_bloqueia(self):
        d,_=self.preparar_preview(); PlanoConta.objects.filter(pk=self.plano.pk).update(ativo=False); self.assertTrue(any("inválida" in m for m in montar_preview_financeiro_documento(d)["motivos"]))
    def test_conta_estrutural_bloqueia(self):
        d,_=self.preparar_preview(); PlanoConta.objects.filter(pk=self.plano.pk).update(estrutural=True,aceita_lancamento=False); self.assertTrue(any("inválida" in m for m in montar_preview_financeiro_documento(d)["motivos"]))
    def test_custo_e_despesa_validos(self):
        d,_=self.preparar_preview(); self.assertFalse(any("conta" in m.lower() for m in montar_preview_financeiro_documento(d)["motivos"]))
    def test_documento_parcial_rateia_valor_faturado(self):
        d,_=self.preparar_preview(total=Decimal("40.00")); preview=montar_preview_financeiro_documento(d); self.assertEqual(preview["total_rateios"],Decimal("40.00"))
    def test_duas_obras_e_centavos_fecham(self):
        d,_=self.preparar_preview(total=Decimal("100.01"),duas_obras=True); preview=montar_preview_financeiro_documento(d); self.assertEqual(sum((r["valor"] for r in preview["rateios"]),Decimal("0")),Decimal("100.01")); self.assertEqual(len(preview["rateios"]),2)
    def test_competencia_e_data_emissao(self):
        d,_=self.preparar_preview(); self.assertEqual(montar_preview_financeiro_documento(d)["competencia"],d.data_emissao)
    def test_preview_pronto(self):
        d,_=self.preparar_preview(); preview=montar_preview_financeiro_documento(d); self.assertTrue(preview["pronto"],preview["motivos"])
    def test_divergencia_bloqueante_bloqueia(self):
        d,_=self.preparar_preview(); DivergenciaDocumentoCompra.objects.create(documento=d,tipo="OUTRO",descricao="Teste",bloqueante=True); self.assertFalse(montar_preview_financeiro_documento(d)["pronto"])
    def test_preview_nao_persiste_financeiro(self):
        d,_=self.preparar_preview(); antes=(LancamentoFinanceiro.objects.count(),ParcelaFinanceira.objects.count(),RateioCentroCusto.objects.count()); montar_preview_financeiro_documento(d); self.assertEqual((LancamentoFinanceiro.objects.count(),ParcelaFinanceira.objects.count(),RateioCentroCusto.objects.count()),antes)
    def test_isolamento_empresa_no_rateio(self):
        d,_=self.preparar_preview(); outra=Empresa.objects.create(razao_social="Outra Preview",cnpj="55.555.555/0001-55"); PedidoItemAlocacaoObra.objects.filter(pedido_item=self.pedido_item).update(obra=CentroCusto.objects.create(empresa=outra,codigo="OUTRA",nome="Outra")); self.assertTrue(any("outra empresa" in m for m in montar_preview_financeiro_documento(d)["motivos"]))
    def test_permissao_preview(self):
        d,_=self.preparar_preview(); self.client.force_login(self.usuario); url=reverse("compras:documento_preview_financeiro",args=[d.pk]); self.assertEqual(self.client.get(url).status_code,403); self.permissao("view_preview_financeiro_documento"); self.assertEqual(self.client.get(url).status_code,200)
