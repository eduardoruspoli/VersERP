from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from financeiro.models import Empresa
from pessoas.models import Pessoa

from .models import (ApuracaoDiaria, CompetenciaPonto, ConferenciaFolha,
                     ContratoFuncionario, EventoFolha, Feriado, Funcionario,
                     Jornada, JornadaDia, MarcacaoPonto, OcorrenciaPonto,
                     RetornoContabilidade, ValeAdiantamento)
from .services import (apurar_competencia, apurar_dia, atualizar_conferencia,
                       calcular_desconto_bh_negativo, calcular_horas_100,
                       calcular_previa_funcionario, calcular_previas_empresa, comparar_retorno,
                       contrato_vigente, fechar_competencia,
                       gerar_parcelas_vale, minutos_trabalhados,
                       reabrir_competencia, sincronizar_eventos_automaticos)


class RHBase(TestCase):
    def setUp(self):
        self.usuario=get_user_model().objects.create_user(username="rh",password="teste123")
        self.empresa=Empresa.objects.create(razao_social="Empresa RH",cnpj="10.000.000/0001-01",principal=True)
        self.outra=Empresa.objects.create(razao_social="Outra",cnpj="20.000.000/0001-02")
        self.pessoa=Pessoa.objects.create(tipo_pessoa=Pessoa.TipoPessoa.FISICA,razao_social="Funcionário Teste",cpf_cnpj="111.111.111-11")
        self.funcionario=Funcionario.objects.create(empresa=self.empresa,pessoa=self.pessoa,cargo_atual="Técnico",data_admissao=date(2026,1,1))
        self.contrato=ContratoFuncionario.objects.create(funcionario=self.funcionario,inicio_vigencia=date(2026,1,1),salario_base=Decimal("2200"),divisor_salarial=220)
        self.jornada=Jornada.objects.create(funcionario=self.funcionario,inicio_vigencia=date(2026,1,1))
        for dia in range(5): JornadaDia.objects.create(jornada=self.jornada,dia_semana=dia,trabalha=True,minutos_previstos=480)

    def permitir(self,*codigos):
        self.usuario.user_permissions.add(*Permission.objects.filter(codename__in=codigos))


class FuncionarioContratoTests(RHBase):
    def test_funcionario_isolado_por_empresa_na_view(self):
        self.permitir("view_funcionario"); self.client.force_login(self.usuario)
        resposta=self.client.get(reverse("rh:funcionario_detalhe",args=[self.funcionario.pk]),{"empresa":self.outra.pk})
        self.assertEqual(resposta.status_code,404)

    def test_matricula_unica_por_empresa(self):
        self.funcionario.matricula="A1"; self.funcionario.save()
        pessoa=Pessoa.objects.create(tipo_pessoa="PF",razao_social="Outro")
        with self.assertRaises(ValidationError): Funcionario.objects.create(empresa=self.empresa,pessoa=pessoa,matricula="A1",cargo_atual="X",data_admissao=date(2026,1,1))

    def test_divisor_220_e_valor_hora(self): self.assertEqual(self.contrato.valor_hora,Decimal("10.0000"))

    def test_contrato_vigente_historico(self):
        self.contrato.fim_vigencia=date(2026,6,30); self.contrato.save()
        novo=ContratoFuncionario.objects.create(funcionario=self.funcionario,inicio_vigencia=date(2026,7,1),salario_base=Decimal("3300"),divisor_salarial=220)
        self.assertEqual(contrato_vigente(self.funcionario,date(2026,5,1)),self.contrato)
        self.assertEqual(contrato_vigente(self.funcionario,date(2026,8,1)),novo)

    def test_sobreposicao_contratual_rejeitada(self):
        with self.assertRaises(ValidationError): ContratoFuncionario.objects.create(funcionario=self.funcionario,inicio_vigencia=date(2026,5,1),salario_base=1000)

    def test_sobreposicao_jornada_rejeitada(self):
        with self.assertRaises(ValidationError): Jornada.objects.create(funcionario=self.funcionario,inicio_vigencia=date(2026,5,1))

    def test_salario_oculto_sem_permissao(self):
        self.permitir("view_funcionario"); self.client.force_login(self.usuario)
        resposta=self.client.get(reverse("rh:funcionario_detalhe",args=[self.funcionario.pk]),{"empresa":self.empresa.pk})
        self.assertNotContains(resposta,"2.200")

    def test_salario_visivel_com_permissao(self):
        self.permitir("view_funcionario","view_remuneracao"); self.client.force_login(self.usuario)
        resposta=self.client.get(reverse("rh:funcionario_detalhe",args=[self.funcionario.pk]),{"empresa":self.empresa.pk})
        self.assertContains(resposta,"2200")


class PontoTests(RHBase):
    def marcar(self,data_ref,horarios,origem=MarcacaoPonto.Origem.RELOGIO):
        return [MarcacaoPonto.objects.create(funcionario=self.funcionario,data=data_ref,horario=h,origem=origem) for h in horarios]

    def test_marcacoes_relogio_jornada_completa(self):
        self.marcar(date(2026,4,6),[time(8),time(12),time(13),time(17)])
        dados=apurar_dia(self.funcionario,date(2026,4,6)); self.assertEqual(dados["minutos_trabalhados"],480); self.assertEqual(dados["credito_bh_minutos"],0)

    def test_marcacao_manual_identificada(self):
        item=self.marcar(date(2026,4,6),[time(8)],MarcacaoPonto.Origem.MANUAL)[0]; self.assertEqual(item.origem,"MANUAL")

    def test_marcacao_impar_rejeita_apuracao(self):
        itens=self.marcar(date(2026,4,6),[time(8)])
        with self.assertRaises(ValidationError): minutos_trabalhados(itens)

    def test_credito_bh_em_minutos(self):
        self.marcar(date(2026,4,6),[time(8),time(12),time(13),time(18,17)])
        self.assertEqual(apurar_dia(self.funcionario,date(2026,4,6))["credito_bh_minutos"],77)

    def test_debito_bh_em_minutos(self):
        self.marcar(date(2026,4,6),[time(8),time(12),time(13),time(16)])
        self.assertEqual(apurar_dia(self.funcionario,date(2026,4,6))["debito_bh_minutos"],60)

    def test_falta(self): self.assertTrue(apurar_dia(self.funcionario,date(2026,4,6))["falta"])

    def test_abono_compensa_debito(self):
        OcorrenciaPonto.objects.create(funcionario=self.funcionario,data_inicio=date(2026,4,6),tipo="ABONO",descricao="Abono",minutos_abonados=480)
        dados=apurar_dia(self.funcionario,date(2026,4,6)); self.assertEqual(dados["debito_bh_minutos"],0); self.assertTrue(dados["abonado"])

    def test_domingo_vai_para_horas_100_e_nao_bh(self):
        self.marcar(date(2026,4,5),[time(8),time(14,52)])
        dados=apurar_dia(self.funcionario,date(2026,4,5)); self.assertEqual(dados["horas_100_minutos"],412); self.assertEqual(dados["credito_bh_minutos"],0)

    def test_feriado_vai_para_horas_100(self):
        Feriado.objects.create(empresa=self.empresa,data=date(2026,4,6),nome="Teste")
        self.marcar(date(2026,4,6),[time(8),time(14)])
        dados=apurar_dia(self.funcionario,date(2026,4,6)); self.assertEqual(dados["horas_100_minutos"],360); self.assertEqual(dados["debito_bh_minutos"],0)

    def test_competencia_fechada_bloqueia_marcacao(self):
        CompetenciaPonto.objects.create(funcionario=self.funcionario,competencia=date(2026,4,1),status="FECHADO")
        with self.assertRaises(ValidationError): self.marcar(date(2026,4,6),[time(8)])

    def test_competencia_fechada_bloqueia_ocorrencia(self):
        CompetenciaPonto.objects.create(funcionario=self.funcionario,competencia=date(2026,4,1),status="FECHADO")
        with self.assertRaises(ValidationError):
            OcorrenciaPonto.objects.create(funcionario=self.funcionario,data_inicio=date(2026,4,6),tipo="ABONO",descricao="Tardia")


class FechamentoBHTests(RHBase):
    def competencia(self,saldo=-120,horas=360,status="APURADO"):
        return CompetenciaPonto.objects.create(funcionario=self.funcionario,competencia=date(2026,4,1),status=status,saldo_final_minutos=saldo,horas_100_minutos=horas)

    def test_exemplo_obrigatorio_valores_separados(self):
        item=self.competencia(); self.assertEqual(calcular_horas_100(item),Decimal("120.00")); self.assertEqual(calcular_desconto_bh_negativo(item),Decimal("20.00"))

    def test_bh_557_e_horas_652_nao_somam(self):
        item=self.competencia(357,412); sincronizar_eventos_automaticos(item)
        self.assertEqual(item.saldo_final_minutos,357); self.assertEqual(item.horas_100_minutos,412)

    def test_eventos_automaticos_idempotentes(self):
        item=self.competencia(); sincronizar_eventos_automaticos(item); sincronizar_eventos_automaticos(item)
        self.assertEqual(EventoFolha.objects.filter(origem="FECHAMENTO_PONTO").count(),2)

    def test_fechamento_exige_permissao(self):
        with self.assertRaises(PermissionDenied): fechar_competencia(self.competencia(),self.usuario)

    def test_fechar_e_reabrir_com_auditoria(self):
        self.permitir("fechar_ponto","reabrir_ponto"); item=self.competencia(); fechar_competencia(item,self.usuario); item.refresh_from_db(); self.assertEqual(item.status,"FECHADO")
        reabrir_competencia(item,self.usuario,"Correção necessária"); item.refresh_from_db(); self.assertEqual(item.status,"REABERTO"); self.assertEqual(self.funcionario.historicos.count(),2)

    def test_reabertura_exige_motivo(self):
        self.permitir("reabrir_ponto"); item=self.competencia(status="FECHADO")
        with self.assertRaises(ValidationError): reabrir_competencia(item,self.usuario,"")

    def test_saldo_anterior_transportado(self):
        CompetenciaPonto.objects.create(funcionario=self.funcionario,competencia=date(2026,3,1),status="FECHADO",saldo_final_minutos=45)
        atual=self.competencia(0,0,"RASCUNHO"); apurar_competencia(atual); atual.refresh_from_db(); self.assertEqual(atual.saldo_anterior_minutos,45)


class EventosValesContabilidadeTests(RHBase):
    def test_evento_outra_empresa_rejeitado(self):
        evento=EventoFolha(empresa=self.outra,funcionario=self.funcionario,competencia=date(2026,4,1),tipo="PREMIO",descricao="X",natureza="PROVENTO",valor=10)
        with self.assertRaises(ValidationError): evento.save()

    def test_vale_centavos_deterministicos(self):
        vale=ValeAdiantamento.objects.create(funcionario=self.funcionario,data=date(2026,4,1),descricao="Vale",valor_total=Decimal("100"),quantidade_parcelas=3)
        parcelas=gerar_parcelas_vale(vale,date(2026,4,1)); self.assertEqual([p.valor for p in parcelas],[Decimal("33.33"),Decimal("33.33"),Decimal("33.34")])

    def test_vale_idempotente(self):
        vale=ValeAdiantamento.objects.create(funcionario=self.funcionario,data=date(2026,4,1),descricao="Vale",valor_total=100,quantidade_parcelas=3)
        gerar_parcelas_vale(vale,date(2026,4,1)); gerar_parcelas_vale(vale,date(2026,4,1)); self.assertEqual(vale.parcelas.count(),3)

    def test_previa_gerencial(self):
        EventoFolha.objects.create(empresa=self.empresa,funcionario=self.funcionario,competencia=date(2026,4,1),tipo="PREMIO",descricao="Prêmio",natureza="PROVENTO",valor=100)
        previa=calcular_previa_funcionario(self.funcionario,date(2026,4,1)); self.assertEqual(previa["liquido_gerencial"],Decimal("2300.00"))

    def test_previas_empresa_tem_consultas_em_lote(self):
        with self.assertNumQueries(4):
            previas=list(calcular_previas_empresa(self.empresa,date(2026,4,1)))
        self.assertEqual(len(previas),1)

    def test_retorno_preserva_valor_e_nao_calcula_inss(self):
        retorno=RetornoContabilidade.objects.create(funcionario=self.funcionario,competencia=date(2026,4,1),inss=Decimal("201.37"))
        comparacao=comparar_retorno(retorno); inss=next(x for x in comparacao["itens"] if x["nome"]=="INSS"); self.assertIsNone(inss["esperado"]); self.assertEqual(inss["informado"],Decimal("201.37"))

    def test_conferencia_divergente_e_justificada(self):
        self.permitir("conferir_folha"); retorno=RetornoContabilidade.objects.create(funcionario=self.funcionario,competencia=date(2026,4,1))
        conf=atualizar_conferencia(retorno,"JUSTIFICADO","Validado com contador",self.usuario); self.assertEqual(conf.status,"JUSTIFICADO")

    def test_justificativa_obrigatoria(self):
        self.permitir("conferir_folha"); retorno=RetornoContabilidade.objects.create(funcionario=self.funcionario,competencia=date(2026,4,1))
        with self.assertRaises(ValidationError): atualizar_conferencia(retorno,"JUSTIFICADO","",self.usuario)


class SegurancaViewsTests(RHBase):
    def test_dashboard_sem_permissao_403(self):
        self.client.force_login(self.usuario); self.assertEqual(self.client.get(reverse("rh:dashboard")).status_code,403)

    def test_dashboard_com_permissao(self):
        self.permitir("view_rh"); self.client.force_login(self.usuario); self.assertEqual(self.client.get(reverse("rh:dashboard"),{"empresa":self.empresa.pk}).status_code,200)

    def test_post_mutavel_nao_aceita_get(self):
        self.permitir("ajustar_ponto"); item=CompetenciaPonto.objects.create(funcionario=self.funcionario,competencia=date(2026,4,1))
        self.client.force_login(self.usuario); self.client.get(reverse("rh:competencia_apurar",args=[item.pk]),{"empresa":self.empresa.pk}); item.refresh_from_db(); self.assertEqual(item.status,"RASCUNHO")
