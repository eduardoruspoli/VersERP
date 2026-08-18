from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from pessoas.models import Pessoa

from .forms import (
    CriarLancamentoOFXForm,
    LancamentoFinanceiroForm,
    RateioCentroCustoFormSet,
)
from .models import (
    CentroCusto,
    ContaBancaria,
    Empresa,
    ImportacaoOFX,
    LancamentoFinanceiro,
    PlanoConta,
    RateioCentroCusto,
    MovimentoOFX,
)


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


class ObrasRateioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(
            razao_social="Empresa Obras",
            cnpj="11.111.111/0001-11",
        )
        cls.outra_empresa = Empresa.objects.create(
            razao_social="Outra Empresa",
            cnpj="22.222.222/0001-22",
        )
        cls.cliente = Pessoa.objects.create(
            razao_social="Cliente da Obra",
        )
        cls.fornecedor = Pessoa.objects.create(
            razao_social="Fornecedor da Obra",
            classificacao=Pessoa.Classificacao.FORNECEDOR,
        )
        cls.obra = CentroCusto.objects.create(
            empresa=cls.empresa,
            cliente=cls.cliente,
            codigo="VERS1917",
            nome="Obra VERS1917",
        )
        cls.outra_obra = CentroCusto.objects.create(
            empresa=cls.empresa,
            codigo="VERS1920",
            nome="Obra VERS1920",
        )
        cls.obra_outra_empresa = CentroCusto.objects.create(
            empresa=cls.outra_empresa,
            codigo="VERS1917",
            nome="Obra de outra empresa",
        )
        cls.lancamento = LancamentoFinanceiro.objects.create(
            empresa=cls.empresa,
            pessoa=cls.fornecedor,
            tipo="PAGAR",
            descricao="Materiais da obra",
            valor_total=Decimal("100.00"),
            plano_conta=PlanoConta.objects.get(codigo="5.01.01"),
        )
        cls.usuario = get_user_model().objects.create_superuser(
            username="admin-obras",
            email="obras@example.com",
            password="senha-teste",
        )

    def dados_formset(self, linhas):
        dados = {
            "rateios-TOTAL_FORMS": str(len(linhas)),
            "rateios-INITIAL_FORMS": "0",
            "rateios-MIN_NUM_FORMS": "0",
            "rateios-MAX_NUM_FORMS": "1000",
        }

        for indice, linha in enumerate(linhas):
            for campo, valor in linha.items():
                dados[f"rateios-{indice}-{campo}"] = str(valor)

        return dados

    def criar_formset(self, linhas, modo="VALOR", valor=Decimal("100.00")):
        return RateioCentroCustoFormSet(
            self.dados_formset(linhas),
            prefix="rateios",
            empresa=self.empresa,
            valor_total=valor,
            modo_rateio=modo,
        )

    def test_codigo_da_obra_e_unico_por_empresa(self):
        self.assertEqual(self.obra.codigo, self.obra_outra_empresa.codigo)

        with self.assertRaises(ValidationError):
            CentroCusto.objects.create(
                empresa=self.empresa,
                codigo="VERS1917",
                nome="Código repetido",
            )

    def test_rateio_rejeita_obra_de_outra_empresa(self):
        with self.assertRaisesMessage(ValidationError, "mesma empresa"):
            RateioCentroCusto.objects.create(
                lancamento=self.lancamento,
                centro_custo=self.obra_outra_empresa,
                valor=Decimal("100.00"),
            )

    def test_rateio_rejeita_nova_obra_inativa_e_preserva_historico(self):
        rateio = RateioCentroCusto.objects.create(
            lancamento=self.lancamento,
            centro_custo=self.obra,
            valor=Decimal("100.00"),
        )
        self.obra.ativo = False
        self.obra.save()

        rateio.valor = Decimal("100.00")
        rateio.save()

        with self.assertRaisesMessage(ValidationError, "inativo"):
            RateioCentroCusto.objects.create(
                lancamento=self.lancamento,
                centro_custo=self.obra,
                valor=Decimal("100.00"),
            )

    def test_rateio_por_valor_deve_fechar_total(self):
        valido = self.criar_formset([
            {"centro_custo": self.obra.pk, "valor": "60,00"},
            {"centro_custo": self.outra_obra.pk, "valor": "40,00"},
        ])
        self.assertTrue(valido.is_valid(), valido.errors)

        invalido = self.criar_formset([
            {"centro_custo": self.obra.pk, "valor": "90,00"},
        ])
        self.assertFalse(invalido.is_valid())
        self.assertIn("igual ao valor total", str(invalido.non_form_errors()))

    def test_rateio_e_obrigatorio(self):
        formset = self.criar_formset([])
        self.assertFalse(formset.is_valid())
        self.assertIn("ao menos uma obra", str(formset.non_form_errors()))

    def test_rateio_nao_permite_obra_duplicada(self):
        formset = self.criar_formset([
            {"centro_custo": self.obra.pk, "valor": "50,00"},
            {"centro_custo": self.obra.pk, "valor": "50,00"},
        ])
        self.assertFalse(formset.is_valid())
        self.assertIn("mais de uma vez", str(formset.non_form_errors()))

    def test_rateio_percentual_exige_cem_por_cento(self):
        formset = self.criar_formset(
            [{"centro_custo": self.obra.pk, "percentual": "99.0000"}],
            modo="PERCENTUAL",
        )
        self.assertFalse(formset.is_valid())
        self.assertIn("100%", str(formset.non_form_errors()))

    def test_rateio_percentual_distribui_residuo_de_centavos(self):
        terceira_obra = CentroCusto.objects.create(
            empresa=self.empresa,
            codigo="VERS1921",
            nome="Obra VERS1921",
        )
        formset = self.criar_formset(
            [
                {"centro_custo": self.obra.pk, "percentual": "33.3333"},
                {"centro_custo": self.outra_obra.pk, "percentual": "33.3333"},
                {"centro_custo": terceira_obra.pk, "percentual": "33.3334"},
            ],
            modo="PERCENTUAL",
        )
        self.assertTrue(formset.is_valid(), formset.errors)
        self.assertEqual(
            [item["valor"] for item in formset.rateios_calculados],
            [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")],
        )

    def dados_lancamento_manual(self, incluir_rateio=True):
        dados = {
            "empresa": str(self.empresa.pk),
            "pessoa": str(self.fornecedor.pk),
            "descricao": "Combustível da obra",
            "numero_documento": "NF-1917",
            "data_emissao": "2026-08-18",
            "data_competencia": "2026-08-18",
            "valor_total": "100,00",
            "plano_conta": str(PlanoConta.objects.get(codigo="5.01.05").pk),
            "observacoes": "Teste integrado",
            "condicao_pagamento": "AVISTA",
            "quantidade_parcelas": "1",
            "primeiro_vencimento": "2026-08-20",
            "modo_rateio": "VALOR",
            "parcelas-TOTAL_FORMS": "1",
            "parcelas-INITIAL_FORMS": "0",
            "parcelas-MIN_NUM_FORMS": "0",
            "parcelas-MAX_NUM_FORMS": "1000",
            "parcelas-0-numero": "1",
            "parcelas-0-vencimento": "2026-08-20",
            "parcelas-0-valor": "100,00",
            "rateios-TOTAL_FORMS": "1" if incluir_rateio else "0",
            "rateios-INITIAL_FORMS": "0",
            "rateios-MIN_NUM_FORMS": "0",
            "rateios-MAX_NUM_FORMS": "1000",
        }

        if incluir_rateio:
            dados.update({
                "rateios-0-centro_custo": str(self.obra.pk),
                "rateios-0-valor": "100,00",
            })

        return dados

    def test_novo_lancamento_manual_exige_e_salva_rateio_atomicamente(self):
        self.client.force_login(self.usuario)
        url = reverse("financeiro:nova_conta_pagar")
        quantidade_inicial = LancamentoFinanceiro.objects.count()

        resposta_invalida = self.client.post(
            url,
            self.dados_lancamento_manual(incluir_rateio=False),
        )
        self.assertEqual(resposta_invalida.status_code, 200)
        self.assertEqual(LancamentoFinanceiro.objects.count(), quantidade_inicial)

        resposta = self.client.post(
            url,
            self.dados_lancamento_manual(incluir_rateio=True),
        )
        self.assertEqual(resposta.status_code, 302)
        lancamento = LancamentoFinanceiro.objects.latest("pk")
        self.assertEqual(lancamento.rateios_centro_custo.count(), 1)
        self.assertEqual(
            lancamento.rateios_centro_custo.get().valor,
            Decimal("100.00"),
        )
        detalhe = self.client.get(
            reverse("financeiro:detalhe_conta_pagar", args=[lancamento.pk])
        )
        self.assertContains(detalhe, "VERS1917")

    def test_telas_de_obras_listam_e_preservam_inativas(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("financeiro:centros_custo"))
        self.assertContains(resposta, "VERS1917")
        self.assertContains(resposta, "Obras / Centros de Custo")

        resposta_status = self.client.post(
            reverse(
                "financeiro:alternar_status_centro_custo",
                args=[self.obra.pk],
            )
        )
        self.assertEqual(resposta_status.status_code, 302)
        self.obra.refresh_from_db()
        self.assertFalse(self.obra.ativo)
        self.assertTrue(
            CentroCusto.objects.filter(pk=self.obra.pk).exists()
        )

    def test_fluxo_ofx_exige_rateio_por_obra(self):
        conta = ContaBancaria.objects.create(
            empresa=self.empresa,
            banco="Banco Teste",
        )
        importacao = ImportacaoOFX.objects.create(
            conta_bancaria=conta,
            nome_arquivo="teste.ofx",
            status="CONCLUIDA",
        )
        movimento = MovimentoOFX.objects.create(
            importacao=importacao,
            conta_bancaria=conta,
            identificador="FITID-OBRA",
            data=date.today(),
            tipo="SAIDA",
            valor=Decimal("100.00"),
            descricao="Material da obra",
        )
        self.client.force_login(self.usuario)
        quantidade_inicial = LancamentoFinanceiro.objects.count()
        resposta = self.client.post(
            reverse(
                "financeiro:criar_lancamento_movimento_ofx",
                args=[movimento.pk],
            ),
            {
                "pessoa": str(self.fornecedor.pk),
                "descricao": "Material da obra",
                "numero_documento": "OFX-1",
                "plano_conta": str(
                    PlanoConta.objects.get(codigo="5.01.01").pk
                ),
                "observacoes": "",
                "modo_rateio": "VALOR",
                "rateios-TOTAL_FORMS": "0",
                "rateios-INITIAL_FORMS": "0",
                "rateios-MIN_NUM_FORMS": "0",
                "rateios-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(LancamentoFinanceiro.objects.count(), quantidade_inicial)

        dados_validos = {
            "pessoa": str(self.fornecedor.pk),
            "descricao": "Material da obra",
            "numero_documento": "OFX-1",
            "plano_conta": str(
                PlanoConta.objects.get(codigo="5.01.01").pk
            ),
            "observacoes": "",
            "modo_rateio": "VALOR",
            "rateios-TOTAL_FORMS": "1",
            "rateios-INITIAL_FORMS": "0",
            "rateios-MIN_NUM_FORMS": "0",
            "rateios-MAX_NUM_FORMS": "1000",
            "rateios-0-centro_custo": str(self.obra.pk),
            "rateios-0-valor": "100,00",
        }
        resposta_valida = self.client.post(
            reverse(
                "financeiro:criar_lancamento_movimento_ofx",
                args=[movimento.pk],
            ),
            dados_validos,
        )
        self.assertEqual(resposta_valida.status_code, 302)
        lancamento = LancamentoFinanceiro.objects.latest("pk")
        self.assertEqual(lancamento.origem, "CONCILIACAO")
        self.assertEqual(
            lancamento.rateios_centro_custo.get().centro_custo,
            self.obra,
        )
