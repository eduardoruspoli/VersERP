from datetime import date
from decimal import Decimal

from django.test import TestCase

from pessoas.models import Pessoa
from .models import ContaBancaria, Empresa, LancamentoFinanceiro, ParcelaFinanceira
from .services import calcular_aging, calcular_fluxo_projetado


class GerencialComplementarTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao_social="Empresa gerencial", cnpj="72.000.000/0001-01")
        self.pessoa = Pessoa.objects.create(razao_social="Pessoa gerencial")
        ContaBancaria.objects.create(empresa=self.empresa, banco="Banco", saldo_inicial=Decimal("1000.00"))

    def parcela(self, tipo, vencimento, valor):
        lancamento = LancamentoFinanceiro.objects.create(empresa=self.empresa, pessoa=self.pessoa, tipo=tipo, descricao="Teste", valor_total=valor)
        return ParcelaFinanceira.objects.create(lancamento=lancamento, numero=1, vencimento=vencimento, valor=valor)

    def test_aging_separa_a_vencer_e_atraso(self):
        self.parcela("RECEBER", date(2026, 8, 25), Decimal("100.00"))
        self.parcela("RECEBER", date(2026, 8, 1), Decimal("200.00"))
        dados = calcular_aging(self.empresa, "RECEBER", date(2026, 8, 19))
        self.assertEqual(dados["faixas"]["a_vencer"], Decimal("100.00"))
        self.assertEqual(dados["faixas"]["vencido_1_30"], Decimal("200.00"))

    def test_fluxo_usa_apenas_saldos_abertos_sem_duplicidade(self):
        self.parcela("RECEBER", date(2026, 8, 25), Decimal("300.00"))
        self.parcela("PAGAR", date(2026, 8, 26), Decimal("120.00"))
        dados = calcular_fluxo_projetado(self.empresa, date(2026, 8, 19), date(2026, 8, 31), "DIARIO")
        self.assertEqual(dados["saldo_atual"], Decimal("1000.00"))
        self.assertEqual(dados["saldo_final"], Decimal("1180.00"))
