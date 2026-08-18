from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from pessoas.models import Pessoa

from .forms import CriarLancamentoOFXForm, LancamentoFinanceiroForm
from .models import Empresa, LancamentoFinanceiro, PlanoConta


class PlanoContaModelTests(TestCase):
    naturezas_por_tipo = {
        "ATIVO": "DEVEDORA",
        "PASSIVO": "CREDORA",
        "PATRIMONIO_LIQUIDO": "CREDORA",
        "RECEITA": "CREDORA",
        "CUSTO": "DEVEDORA",
        "DESPESA": "DEVEDORA",
    }

    def criar_conta(self, codigo, tipo="DESPESA", **kwargs):
        dados = {
            "codigo": codigo,
            "nome": f"Conta {codigo}",
            "tipo": tipo,
            "natureza": self.naturezas_por_tipo[tipo],
        }
        dados.update(kwargs)
        return PlanoConta.objects.create(**dados)

    def test_valida_natureza_por_grupo_contabil(self):
        for indice, (tipo, natureza) in enumerate(
            self.naturezas_por_tipo.items(), start=1
        ):
            natureza_incorreta = (
                "CREDORA" if natureza == "DEVEDORA" else "DEVEDORA"
            )
            conta = PlanoConta(
                codigo=f"T.{indice}",
                nome=f"Conta {tipo}",
                tipo=tipo,
                natureza=natureza_incorreta,
            )

            with self.subTest(tipo=tipo):
                with self.assertRaisesMessage(
                    ValidationError, "Para este grupo contábil"
                ):
                    conta.full_clean()

    def test_impede_conta_como_pai_dela_mesma(self):
        conta = self.criar_conta("T.6")
        conta.conta_pai = conta

        with self.assertRaisesMessage(
            ValidationError, "superior a ela mesma"
        ):
            conta.full_clean()

    def test_impede_ciclo_indireto(self):
        pai = self.criar_conta("T.6")
        filha = self.criar_conta("T.6.01", conta_pai=pai)
        neta = self.criar_conta("T.6.01.01", conta_pai=filha)
        pai.conta_pai = neta

        with self.assertRaisesMessage(
            ValidationError, "ciclo na hierarquia"
        ):
            pai.full_clean()

    def test_impede_hierarquia_entre_grupos(self):
        pai = self.criar_conta("T.4", tipo="RECEITA")
        filha = PlanoConta(
            codigo="T.6.01",
            nome="Despesa",
            tipo="DESPESA",
            natureza="DEVEDORA",
            conta_pai=pai,
        )

        with self.assertRaisesMessage(
            ValidationError, "mesmo grupo contábil"
        ):
            filha.full_clean()

    def test_conta_estrutural_nao_aceita_lancamento(self):
        conta = PlanoConta(
            codigo="T.6",
            nome="Despesas",
            tipo="DESPESA",
            natureza="DEVEDORA",
            estrutural=True,
            aceita_lancamento=True,
        )

        with self.assertRaisesMessage(ValidationError, "conta estrutural"):
            conta.full_clean()

    def test_impede_conta_ativa_sob_pai_inativo(self):
        pai = self.criar_conta("T.6", ativo=False)
        filha = PlanoConta(
            codigo="T.6.01",
            nome="Despesa ativa",
            tipo="DESPESA",
            natureza="DEVEDORA",
            conta_pai=pai,
            ativo=True,
        )

        with self.assertRaisesMessage(
            ValidationError, "conta inativa"
        ):
            filha.full_clean()

    def test_conta_redutora_usa_natureza_inversa(self):
        depreciacao = PlanoConta(
            codigo="T.1.90",
            nome="Depreciação Acumulada",
            tipo="ATIVO",
            natureza="CREDORA",
            conta_redutora=True,
        )
        depreciacao.full_clean()

        depreciacao.natureza = "DEVEDORA"

        with self.assertRaisesMessage(
            ValidationError, "conta redutora"
        ):
            depreciacao.full_clean()

    def test_plano_padrao_foi_criado_com_contas_redutoras(self):
        depreciacao = PlanoConta.objects.get(codigo="1.02.02.900")
        prejuizos = PlanoConta.objects.get(codigo="3.03.02")

        self.assertEqual(depreciacao.natureza, "CREDORA")
        self.assertTrue(depreciacao.conta_redutora)
        self.assertEqual(prejuizos.natureza, "DEVEDORA")
        self.assertTrue(prejuizos.conta_redutora)

    def test_todas_as_contas_padrao_respeitam_as_regras_do_model(self):
        for conta in PlanoConta.objects.select_related("conta_pai"):
            with self.subTest(codigo=conta.codigo):
                conta.full_clean()


class PlanoContaLancamentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(
            razao_social="Empresa Teste",
            cnpj="00.000.000/0001-00",
        )
        cls.pessoa = Pessoa.objects.create(razao_social="Pessoa Teste")
        cls.contas = {
            "CUSTO": PlanoConta.objects.create(
                codigo="T.5.01", nome="Custo", tipo="CUSTO", natureza="DEVEDORA"
            ),
            "DESPESA": PlanoConta.objects.create(
                codigo="T.6.01",
                nome="Despesa",
                tipo="DESPESA",
                natureza="DEVEDORA",
            ),
            "RECEITA": PlanoConta.objects.create(
                codigo="T.4.01",
                nome="Receita",
                tipo="RECEITA",
                natureza="CREDORA",
            ),
            "ATIVO": PlanoConta.objects.create(
                codigo="T.1.01", nome="Ativo", tipo="ATIVO", natureza="DEVEDORA"
            ),
        }

    def criar_lancamento(self, tipo, plano_conta):
        return LancamentoFinanceiro(
            empresa=self.empresa,
            pessoa=self.pessoa,
            tipo=tipo,
            descricao="Lançamento de teste",
            data_emissao=date.today(),
            data_competencia=date.today(),
            valor_total=Decimal("100.00"),
            plano_conta=plano_conta,
        )

    def test_pagar_aceita_custo_e_despesa(self):
        for tipo_conta in ("CUSTO", "DESPESA"):
            with self.subTest(tipo_conta=tipo_conta):
                self.criar_lancamento(
                    "PAGAR", self.contas[tipo_conta]
                ).full_clean()

    def test_pagar_rejeita_outros_grupos(self):
        with self.assertRaisesMessage(ValidationError, "custo ou despesa"):
            self.criar_lancamento(
                "PAGAR", self.contas["RECEITA"]
            ).full_clean()

    def test_receber_aceita_somente_receita(self):
        self.criar_lancamento(
            "RECEBER", self.contas["RECEITA"]
        ).full_clean()

        with self.assertRaisesMessage(ValidationError, "conta de receita"):
            self.criar_lancamento(
                "RECEBER", self.contas["DESPESA"]
            ).full_clean()

    def test_formulario_de_lancamento_filtra_por_tipo(self):
        contas_pagar = set(
            LancamentoFinanceiroForm(tipo="PAGAR")
            .fields["plano_conta"]
            .queryset
        )
        contas_receber = set(
            LancamentoFinanceiroForm(tipo="RECEBER")
            .fields["plano_conta"]
            .queryset
        )

        self.assertIn(self.contas["CUSTO"], contas_pagar)
        self.assertIn(self.contas["DESPESA"], contas_pagar)
        self.assertTrue(
            all(
                conta.tipo in ("CUSTO", "DESPESA")
                for conta in contas_pagar
            )
        )
        self.assertIn(self.contas["RECEITA"], contas_receber)
        self.assertTrue(
            all(conta.tipo == "RECEITA" for conta in contas_receber)
        )

    def test_fluxo_ofx_filtra_planos_com_as_mesmas_regras(self):
        contas_pagar = set(
            CriarLancamentoOFXForm(tipo="PAGAR")
            .fields["plano_conta"]
            .queryset
        )
        contas_receber = set(
            CriarLancamentoOFXForm(tipo="RECEBER")
            .fields["plano_conta"]
            .queryset
        )

        self.assertIn(self.contas["CUSTO"], contas_pagar)
        self.assertIn(self.contas["DESPESA"], contas_pagar)
        self.assertTrue(
            all(
                conta.tipo in ("CUSTO", "DESPESA")
                for conta in contas_pagar
            )
        )
        self.assertIn(self.contas["RECEITA"], contas_receber)
        self.assertTrue(
            all(conta.tipo == "RECEITA" for conta in contas_receber)
        )
