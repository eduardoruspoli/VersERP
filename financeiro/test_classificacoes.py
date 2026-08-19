from datetime import date
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from pessoas.models import Pessoa
from .models import (CentroCusto, Empresa, LancamentoFinanceiro,
    LancamentoFinanceiroClassificacao, ParcelaFinanceira, PlanoConta,
    RateioCentroCusto)
from .services import (calcular_dre, calcular_relatorio_obra,
    salvar_classificacoes_lancamento, verificar_integridade_classificacoes)


class ClassificacaoFinanceiraBase(TestCase):
    def setUp(self):
        self.empresa=Empresa.objects.create(razao_social="TESTE Classificações",cnpj="57.777.777/0001-57")
        self.pessoa=Pessoa.objects.create(razao_social="TESTE Pessoa",classificacao=Pessoa.Classificacao.AMBOS)
        self.custo=PlanoConta.objects.create(codigo="TESTE-CL-5",nome="Custo",tipo="CUSTO",natureza="DEVEDORA")
        self.despesa=PlanoConta.objects.create(codigo="TESTE-CL-6",nome="Despesa",tipo="DESPESA",natureza="DEVEDORA")
        self.receita=PlanoConta.objects.create(codigo="TESTE-CL-4",nome="Receita",tipo="RECEITA",natureza="CREDORA")

    def lancamento(self,tipo="PAGAR",plano=None,valor=Decimal("100.00"),status="ABERTO",**kwargs):
        plano=plano or (self.receita if tipo=="RECEBER" else self.custo)
        dados={"empresa":self.empresa,"pessoa":self.pessoa,"tipo":tipo,"descricao":"TESTE Lançamento","data_emissao":date(2026,8,19),"data_competencia":date(2026,8,19),"valor_total":valor,"plano_conta":plano,"status":status}; dados.update(kwargs)
        return LancamentoFinanceiro.objects.create(**dados)


class LancamentoClassificacaoModelTests(ClassificacaoFinanceiraBase):
    def test_pagar_custo_cria_classificacao_unica(self):
        l=self.lancamento(); c=l.classificacoes_contabeis.get(); self.assertEqual((c.plano_conta,c.valor,c.ordem),(self.custo,Decimal("100.00"),1))
    def test_pagar_despesa(self):
        l=self.lancamento(plano=self.despesa); self.assertEqual(l.classificacoes_contabeis.get().plano_conta,self.despesa)
    def test_receber_receita(self):
        l=self.lancamento(tipo="RECEBER"); self.assertEqual(l.classificacoes_contabeis.get().plano_conta,self.receita)
    def test_cancelado_e_liquidado_preservam_classificacao(self):
        for indice,status in enumerate(("CANCELADO","LIQUIDADO"),1):
            l=self.lancamento(status=status,descricao=f"TESTE {indice}"); self.assertEqual(l.classificacoes_contabeis.count(),1)
    def test_valor_positivo_e_constraint(self):
        l=self.lancamento()
        with self.assertRaises(ValidationError): LancamentoFinanceiroClassificacao.objects.create(lancamento=l,plano_conta=self.custo,valor=0)
    def test_segunda_classificacao_e_rejeitada(self):
        l=self.lancamento()
        with self.assertRaises(ValidationError): LancamentoFinanceiroClassificacao.objects.create(lancamento=l,plano_conta=self.despesa,valor=100)
    def test_conta_estrutural_e_sem_lancamento_rejeitadas(self):
        for indice,atributos in enumerate(({"estrutural":True},{"aceita_lancamento":False}),1):
            conta=PlanoConta.objects.create(codigo=f"TESTE-INV-{indice}",nome="Inválida",tipo="CUSTO",natureza="DEVEDORA")
            PlanoConta.objects.filter(pk=conta.pk).update(**atributos)
            for campo,valor in atributos.items(): setattr(conta,campo,valor)
            l=self.lancamento(); LancamentoFinanceiro.objects.filter(pk=l.pk).update(plano_conta=conta); l.plano_conta=conta; l.classificacoes_contabeis.all().delete()
            with self.assertRaises(ValidationError): LancamentoFinanceiroClassificacao.objects.create(lancamento=l,plano_conta=conta,valor=l.valor_total)
    def test_conta_inativa_nova_rejeitada_e_historica_preservada(self):
        l=self.lancamento(); c=l.classificacoes_contabeis.get(); PlanoConta.objects.filter(pk=self.custo.pk).update(ativo=False); self.custo.ativo=False
        c.observacao="Histórica"; c.save(); self.assertEqual(c.observacao,"Histórica")
        l.classificacoes_contabeis.all().delete()
        with self.assertRaises(ValidationError): LancamentoFinanceiroClassificacao.objects.create(lancamento=l,plano_conta=self.custo,valor=100)
    def test_grupos_incorretos_rejeitados(self):
        pagar=self.lancamento(); LancamentoFinanceiro.objects.filter(pk=pagar.pk).update(plano_conta=self.receita); pagar.plano_conta=self.receita; pagar.classificacoes_contabeis.all().delete()
        with self.assertRaises(ValidationError): LancamentoFinanceiroClassificacao.objects.create(lancamento=pagar,plano_conta=self.receita,valor=100)
        receber=self.lancamento(tipo="RECEBER"); LancamentoFinanceiro.objects.filter(pk=receber.pk).update(plano_conta=self.custo); receber.plano_conta=self.custo; receber.classificacoes_contabeis.all().delete()
        with self.assertRaises(ValidationError): LancamentoFinanceiroClassificacao.objects.create(lancamento=receber,plano_conta=self.custo,valor=100)
    def test_soma_e_plano_legado_devem_coincidir(self):
        l=self.lancamento()
        with self.assertRaises(ValidationError): salvar_classificacoes_lancamento(l,[{"plano_conta":self.custo,"valor":99}])
        with self.assertRaises(ValidationError): salvar_classificacoes_lancamento(l,[{"plano_conta":self.despesa,"valor":100}])
    def test_alteracao_do_lancamento_sincroniza_classificacao(self):
        l=self.lancamento(); l.plano_conta=self.despesa; l.valor_total=Decimal("125.50"); l.save(); c=l.classificacoes_contabeis.get(); self.assertEqual((c.plano_conta,c.valor),(self.despesa,Decimal("125.50")))
    def test_rollback_transacional_com_estado_invalido(self):
        l=self.lancamento(); LancamentoFinanceiroClassificacao.objects.bulk_create([LancamentoFinanceiroClassificacao(lancamento=l,plano_conta=self.despesa,valor=100)])
        l.descricao="NÃO DEVE PERSISTIR"
        with self.assertRaises(ValidationError): l.save()
        l.refresh_from_db(); self.assertEqual(l.descricao,"TESTE Lançamento")
    def test_check_integridade(self):
        a=self.lancamento(); b=self.lancamento(plano=self.despesa,descricao="TESTE B"); self.assertTrue(verificar_integridade_classificacoes()["integro"]); b.classificacoes_contabeis.all().delete(); resultado=verificar_integridade_classificacoes(); self.assertFalse(resultado["integro"]); self.assertEqual(resultado["lancamentos_invalidos"],[b.pk])


class ClassificacaoCompatibilidadeTests(ClassificacaoFinanceiraBase):
    def test_backfill_e_idempotente(self):
        l=self.lancamento(); l.classificacoes_contabeis.all().delete(); migration=import_module("financeiro.migrations.0010_lancamentofinanceiroclassificacao"); editor=SimpleNamespace(connection=connection); migration.preencher_classificacoes_unicas(apps,editor); migration.preencher_classificacoes_unicas(apps,editor); c=l.classificacoes_contabeis.get(); self.assertEqual((c.plano_conta_id,c.valor),(l.plano_conta_id,l.valor_total))
    def test_rateio_parcela_e_baixa_nao_sao_alterados(self):
        l=self.lancamento(); obra=CentroCusto.objects.create(empresa=self.empresa,codigo="TESTE-OBRA-CL",nome="Obra"); rateio=RateioCentroCusto.objects.create(lancamento=l,centro_custo=obra,valor=100); parcela=ParcelaFinanceira.objects.create(lancamento=l,numero=1,vencimento=date(2026,9,1),valor=100); l.observacoes="Atualizado"; l.save(); self.assertTrue(RateioCentroCusto.objects.filter(pk=rateio.pk,valor=100).exists()); self.assertTrue(ParcelaFinanceira.objects.filter(pk=parcela.pk,valor=100).exists())
    def test_dre_e_relatorio_obra_continuam_no_campo_legado(self):
        obra=CentroCusto.objects.create(empresa=self.empresa,codigo="TESTE-OBRA-DRE",nome="Obra"); l=self.lancamento(valor=120); RateioCentroCusto.objects.create(lancamento=l,centro_custo=obra,valor=120); dre=calcular_dre(self.empresa,date(2026,8,1),date(2026,8,31)); relatorio=calcular_relatorio_obra(obra,date(2026,8,1),date(2026,8,31)); self.assertEqual(dre["resumo"]["custos"],Decimal("120.00")); self.assertEqual(relatorio["custos"],Decimal("120.00"))
    def test_toda_criacao_manual_fica_classificada(self):
        criados=[self.lancamento(),self.lancamento(plano=self.despesa,descricao="TESTE D"),self.lancamento(tipo="RECEBER",descricao="TESTE R")]; self.assertTrue(verificar_integridade_classificacoes(LancamentoFinanceiro.objects.filter(pk__in=[l.pk for l in criados]))["integro"])
