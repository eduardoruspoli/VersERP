from datetime import date
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from pessoas.models import Pessoa
from .models import (BaixaFinanceira, CentroCusto, ContaBancaria, Empresa, LancamentoFinanceiro,
    LancamentoFinanceiroClassificacao, ParcelaFinanceira, PlanoConta,
    RateioCentroCusto)
from .services import (calcular_dre, calcular_relatorio_obra,
    calcular_dashboard_financeiro, distribuir_classificacoes_por_rateios,
    drilldown_dre, salvar_classificacoes_lancamento,
    verificar_integridade_classificacoes)


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
    def test_multiplas_classificacoes_sao_oficiais(self):
        l=self.lancamento(); salvar_classificacoes_lancamento(l,[{"plano_conta":self.custo,"valor":60},{"plano_conta":self.despesa,"valor":40}]); l.refresh_from_db()
        self.assertEqual(l.classificacoes_contabeis.count(),2); self.assertIsNone(l.plano_conta)
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
    def test_soma_deve_coincidir_e_legado_sincroniza(self):
        l=self.lancamento()
        with self.assertRaises(ValidationError): salvar_classificacoes_lancamento(l,[{"plano_conta":self.custo,"valor":99}])
        salvar_classificacoes_lancamento(l,[{"plano_conta":self.despesa,"valor":100}]); l.refresh_from_db(); self.assertEqual(l.plano_conta,self.despesa)
        with self.assertRaises(ValidationError): salvar_classificacoes_lancamento(l,[{"plano_conta":self.despesa,"valor":50},{"plano_conta":self.despesa,"valor":50}])
    def test_alteracao_do_lancamento_sincroniza_classificacao(self):
        l=self.lancamento(); l.plano_conta=self.despesa; l.valor_total=Decimal("125.50"); l.save(); c=l.classificacoes_contabeis.get(); self.assertEqual((c.plano_conta,c.valor),(self.despesa,Decimal("125.50")))
    def test_integridade_detecta_soma_invalida(self):
        l=self.lancamento(); LancamentoFinanceiroClassificacao.objects.bulk_create([LancamentoFinanceiroClassificacao(lancamento=l,plano_conta=self.despesa,valor=100)])
        self.assertFalse(verificar_integridade_classificacoes(LancamentoFinanceiro.objects.filter(pk=l.pk))["integro"])
    def test_check_integridade(self):
        a=self.lancamento(); b=self.lancamento(plano=self.despesa,descricao="TESTE B"); self.assertTrue(verificar_integridade_classificacoes()["integro"]); b.classificacoes_contabeis.all().delete(); resultado=verificar_integridade_classificacoes(); self.assertFalse(resultado["integro"]); self.assertEqual(resultado["lancamentos_invalidos"],[b.pk])
    def test_classificacoes_congeladas_apos_baixa(self):
        l=self.lancamento(); parcela=ParcelaFinanceira.objects.create(lancamento=l,numero=1,vencimento=date(2026,9,1),valor=100); conta=ContaBancaria.objects.create(empresa=self.empresa,banco="TESTE Banco")
        BaixaFinanceira.objects.create(parcela=parcela,conta_bancaria=conta,data=date(2026,9,1),valor=10)
        with self.assertRaises(ValidationError): salvar_classificacoes_lancamento(l,[{"plano_conta":self.despesa,"valor":100}])


class ClassificacaoCompatibilidadeTests(ClassificacaoFinanceiraBase):
    def test_backfill_e_idempotente(self):
        l=self.lancamento(); l.classificacoes_contabeis.all().delete(); migration=import_module("financeiro.migrations.0010_lancamentofinanceiroclassificacao"); editor=SimpleNamespace(connection=connection); migration.preencher_classificacoes_unicas(apps,editor); migration.preencher_classificacoes_unicas(apps,editor); c=l.classificacoes_contabeis.get(); self.assertEqual((c.plano_conta_id,c.valor),(l.plano_conta_id,l.valor_total))
    def test_rateio_parcela_e_baixa_nao_sao_alterados(self):
        l=self.lancamento(); obra=CentroCusto.objects.create(empresa=self.empresa,codigo="TESTE-OBRA-CL",nome="Obra"); rateio=RateioCentroCusto.objects.create(lancamento=l,centro_custo=obra,valor=100); parcela=ParcelaFinanceira.objects.create(lancamento=l,numero=1,vencimento=date(2026,9,1),valor=100); l.observacoes="Atualizado"; l.save(); self.assertTrue(RateioCentroCusto.objects.filter(pk=rateio.pk,valor=100).exists()); self.assertTrue(ParcelaFinanceira.objects.filter(pk=parcela.pk,valor=100).exists())
    def test_dre_e_relatorio_obra_continuam_no_campo_legado(self):
        obra=CentroCusto.objects.create(empresa=self.empresa,codigo="TESTE-OBRA-DRE",nome="Obra"); l=self.lancamento(valor=120); RateioCentroCusto.objects.create(lancamento=l,centro_custo=obra,valor=120); dre=calcular_dre(self.empresa,date(2026,8,1),date(2026,8,31)); relatorio=calcular_relatorio_obra(obra,date(2026,8,1),date(2026,8,31)); self.assertEqual(dre["resumo"]["custos"],Decimal("120.00")); self.assertEqual(relatorio["custos"],Decimal("120.00"))
    def test_toda_criacao_manual_fica_classificada(self):
        criados=[self.lancamento(),self.lancamento(plano=self.despesa,descricao="TESTE D"),self.lancamento(tipo="RECEBER",descricao="TESTE R")]; self.assertTrue(verificar_integridade_classificacoes(LancamentoFinanceiro.objects.filter(pk__in=[l.pk for l in criados]))["integro"])


class DistribuicaoClassificacaoObraTests(ClassificacaoFinanceiraBase):
    def preparar_multiplo(self,total=Decimal("100.00"),valores=(Decimal("60.00"),Decimal("40.00")),rateios=(Decimal("70.00"),Decimal("30.00"))):
        l=self.lancamento(valor=total); l.classificacoes_contabeis.all().delete()
        classificacoes=LancamentoFinanceiroClassificacao.objects.bulk_create([
            LancamentoFinanceiroClassificacao(lancamento=l,plano_conta=self.custo,valor=valores[0],ordem=1),
            LancamentoFinanceiroClassificacao(lancamento=l,plano_conta=self.despesa,valor=valores[1],ordem=2),
        ])
        obras=[CentroCusto.objects.create(empresa=self.empresa,codigo=f"TESTE-MAT-{i}",nome=f"Obra {i}") for i in (1,2)]
        objetos=[RateioCentroCusto.objects.create(lancamento=l,centro_custo=obra,valor=valor) for obra,valor in zip(obras,rateios)]
        return l,classificacoes,objetos
    def test_exemplo_fecha_linhas_colunas_e_total(self):
        l,c,r=self.preparar_multiplo(); matriz=distribuir_classificacoes_por_rateios(l)
        self.assertEqual([matriz[(c[0].pk,x.pk)] for x in r],[Decimal("42.00"),Decimal("18.00")]); self.assertEqual([matriz[(c[1].pk,x.pk)] for x in r],[Decimal("28.00"),Decimal("12.00")])
        self.assertEqual(sum(matriz.values(),Decimal("0")),l.valor_total)
    def test_centavos_fecham_cada_linha_e_coluna(self):
        l,c,r=self.preparar_multiplo(Decimal("100.01"),(Decimal("33.34"),Decimal("66.67")),(Decimal("50.00"),Decimal("50.01"))); matriz=distribuir_classificacoes_por_rateios(l)
        for item in c: self.assertEqual(sum((matriz[(item.pk,x.pk)] for x in r),Decimal("0")),item.valor)
        for item in r: self.assertEqual(sum((matriz[(x.pk,item.pk)] for x in c),Decimal("0")),item.valor)
        self.assertEqual(sum(matriz.values(),Decimal("0")),Decimal("100.01"))
    def test_dre_sem_obra_le_exclusivamente_classificacoes(self):
        l,c,r=self.preparar_multiplo(); dre=calcular_dre(self.empresa,date(2026,8,1),date(2026,8,31)); self.assertEqual(dre["resumo"]["custos"],Decimal("60.00")); self.assertEqual(dre["resumo"]["despesas_operacionais"],Decimal("40.00"))
    def test_dre_por_obra_e_drilldown_usam_matriz(self):
        l,c,r=self.preparar_multiplo(); dre=calcular_dre(self.empresa,date(2026,8,1),date(2026,8,31),obra=r[0].centro_custo); self.assertEqual(dre["resumo"]["custos"],Decimal("42.00")); self.assertEqual(dre["resumo"]["despesas_operacionais"],Decimal("28.00")); drill=drilldown_dre(self.empresa,self.custo,date(2026,8,1),date(2026,8,31),obra=r[0].centro_custo); self.assertEqual(drill["total"],Decimal("42.00")); self.assertEqual(drill["itens"][0]["classificacao"].pk,c[0].pk)
    def test_relatorio_obra_classifica_sem_duplicar_rateio(self):
        l,c,r=self.preparar_multiplo(); relatorio=calcular_relatorio_obra(r[0].centro_custo,date(2026,8,1),date(2026,8,31)); self.assertEqual((relatorio["custos"],relatorio["despesas"]),(Decimal("42.00"),Decimal("28.00"))); self.assertEqual(relatorio["detalhes"][0]["valor_rateado"],Decimal("70.00")); self.assertEqual(sum((x["valor"] for x in relatorio["detalhes"][0]["classificacoes"]),Decimal("0")),Decimal("70.00"))
    def test_dashboard_reutiliza_dre_e_matriz(self):
        l,c,r=self.preparar_multiplo(); dashboard=calcular_dashboard_financeiro(self.empresa,date(2026,8,1),date(2026,8,31),hoje=date(2026,8,19)); self.assertEqual(dashboard["dre"]["resumo"]["custos"],Decimal("60.00")); self.assertEqual(dashboard["obras"]["custos_despesas"],Decimal("100.00"))
    def test_isolamento_por_empresa(self):
        l,c,r=self.preparar_multiplo(); outra=Empresa.objects.create(razao_social="TESTE Outra Matriz",cnpj="59.999.999/0001-59"); dre=calcular_dre(outra,date(2026,8,1),date(2026,8,31)); self.assertEqual(dre["resumo"]["custos"],Decimal("0.00"))
    def test_consultas_relatorio_permanecem_controladas(self):
        l,c,r=self.preparar_multiplo()
        with CaptureQueriesContext(connection) as consultas: calcular_relatorio_obra(r[0].centro_custo,date(2026,8,1),date(2026,8,31))
        self.assertLessEqual(len(consultas),15)
