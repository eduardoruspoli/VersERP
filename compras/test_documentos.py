from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from financeiro.models import Empresa, LancamentoFinanceiro, PlanoConta
from pessoas.models import Pessoa
from .models import (DivergenciaDocumentoCompra, DocumentoCompra, DocumentoCompraItem,
    DocumentoCompraItemRecebimento, DocumentoCompraPedido, PedidoCompra, PedidoCompraItem,
    RecebimentoCompra, RecebimentoCompraItem)
from .services import (cancelar_documento_compra, concluir_conferencia_documento,
    iniciar_conferencia_documento, reabrir_conferencia_documento,
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
