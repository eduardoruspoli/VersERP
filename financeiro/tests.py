from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from pessoas.models import Pessoa

from .forms import (
    CriarLancamentoOFXForm,
    DREFiltroForm,
    LancamentoFinanceiroForm,
    RateioCentroCustoFormSet,
    RelatorioObraFiltroForm,
)
from .models import (
    BaixaFinanceira,
    CentroCusto,
    ContaBancaria,
    Empresa,
    ImportacaoOFX,
    LancamentoFinanceiro,
    PlanoConta,
    RateioCentroCusto,
    MovimentoOFX,
    ParcelaFinanceira,
)
from .services import (
    calcular_dre,
    calcular_relatorio_obra,
    distribuir_valor_rateios,
    drilldown_dre,
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


class RelatorioGerencialObraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(
            razao_social="Empresa Relatório TESTE",
            cnpj="71.000.000/0001-01",
            principal=True,
        )
        cls.outra_empresa = Empresa.objects.create(
            razao_social="Outra Empresa Relatório TESTE",
            cnpj="72.000.000/0001-02",
        )
        cls.pessoa = Pessoa.objects.create(
            razao_social="Pessoa Relatório TESTE"
        )
        cls.obra = CentroCusto.objects.create(
            empresa=cls.empresa,
            codigo="REL-TESTE-1",
            nome="Obra Relatório",
        )
        cls.outra_obra = CentroCusto.objects.create(
            empresa=cls.empresa,
            codigo="REL-TESTE-2",
            nome="Obra Rateio",
        )
        cls.obra_inativa = CentroCusto.objects.create(
            empresa=cls.empresa,
            codigo="REL-TESTE-3",
            nome="Obra Inativa",
            ativo=False,
        )
        cls.obra_outra_empresa = CentroCusto.objects.create(
            empresa=cls.outra_empresa,
            codigo="REL-TESTE-1",
            nome="Obra Outra Empresa",
        )
        cls.receitas_pai = PlanoConta.objects.create(
            codigo="T.REL.4",
            nome="Receitas TESTE",
            tipo="RECEITA",
            natureza="CREDORA",
            aceita_lancamento=False,
            estrutural=True,
        )
        cls.receita = PlanoConta.objects.create(
            codigo="T.REL.4.1",
            nome="Receita Serviços TESTE",
            tipo="RECEITA",
            natureza="CREDORA",
            conta_pai=cls.receitas_pai,
        )
        cls.custo = PlanoConta.objects.create(
            codigo="T.REL.5.1",
            nome="Materiais TESTE",
            tipo="CUSTO",
            natureza="DEVEDORA",
        )
        cls.despesa = PlanoConta.objects.create(
            codigo="T.REL.6.1",
            nome="Despesa TESTE",
            tipo="DESPESA",
            natureza="DEVEDORA",
        )
        cls.conta_bancaria = ContaBancaria.objects.create(
            empresa=cls.empresa,
            banco="Banco TESTE",
            agencia="0001",
            conta="12345",
            tipo="CORRENTE",
        )

    def criar_lancamento(
        self,
        tipo,
        plano_conta,
        valor,
        rateios=None,
        competencia=date(2026, 3, 10),
        emissao=date(2026, 3, 1),
        status="ABERTO",
        empresa=None,
    ):
        empresa = empresa or self.empresa
        lancamento = LancamentoFinanceiro.objects.create(
            empresa=empresa,
            pessoa=self.pessoa,
            tipo=tipo,
            descricao=f"Lançamento {tipo} TESTE",
            data_emissao=emissao,
            data_competencia=competencia,
            valor_total=valor,
            plano_conta=plano_conta,
            status=status,
        )
        ParcelaFinanceira.objects.create(
            lancamento=lancamento,
            numero=1,
            vencimento=date(2026, 4, 10),
            valor=valor,
        )
        for obra, valor_rateio in rateios or [(self.obra, valor)]:
            RateioCentroCusto.objects.create(
                lancamento=lancamento,
                centro_custo=obra,
                valor=valor_rateio,
            )
        return lancamento

    def baixar(self, lancamento, valor, data_baixa=date(2026, 3, 20), **extras):
        return BaixaFinanceira.objects.create(
            parcela=lancamento.parcelas.get(),
            conta_bancaria=self.conta_bancaria,
            data=data_baixa,
            valor=valor,
            juros=extras.get("juros", Decimal("0.00")),
            multa=extras.get("multa", Decimal("0.00")),
            desconto=extras.get("desconto", Decimal("0.00")),
        )

    def relatorio(self, obra=None):
        return calcular_relatorio_obra(
            obra or self.obra,
            date(2026, 1, 1),
            date(2026, 12, 31),
        )

    def test_resultado_por_competencia(self):
        self.criar_lancamento("RECEBER", self.receita, Decimal("1000.00"))
        self.criar_lancamento("PAGAR", self.custo, Decimal("300.00"))
        self.criar_lancamento("PAGAR", self.despesa, Decimal("100.00"))

        resultado = self.relatorio()

        self.assertEqual(resultado["receitas"], Decimal("1000.00"))
        self.assertEqual(resultado["custos"], Decimal("300.00"))
        self.assertEqual(resultado["resultado_bruto"], Decimal("700.00"))
        self.assertEqual(resultado["despesas"], Decimal("100.00"))
        self.assertEqual(resultado["resultado_obra"], Decimal("600.00"))
        self.assertEqual(resultado["margem"], Decimal("60.00"))

    def test_rateio_entre_obras_afeta_somente_a_parte_da_obra(self):
        self.criar_lancamento(
            "PAGAR",
            self.custo,
            Decimal("100.00"),
            [(self.obra, Decimal("60.00")), (self.outra_obra, Decimal("40.00"))],
        )

        self.assertEqual(self.relatorio()["custos"], Decimal("60.00"))
        self.assertEqual(
            self.relatorio(self.outra_obra)["custos"], Decimal("40.00")
        )

    def test_baixa_parcial_calcula_caixa_e_saldo(self):
        lancamento = self.criar_lancamento(
            "RECEBER", self.receita, Decimal("100.00")
        )
        self.baixar(lancamento, Decimal("35.00"))

        resultado = self.relatorio()

        self.assertEqual(resultado["recebido"], Decimal("35.00"))
        self.assertEqual(resultado["a_receber"], Decimal("65.00"))
        self.assertEqual(resultado["resultado_caixa"], Decimal("35.00"))

    def test_multiplas_baixas_nao_duplicam_valores(self):
        lancamento = self.criar_lancamento(
            "PAGAR",
            self.custo,
            Decimal("200.00"),
            [(self.obra, Decimal("150.00")), (self.outra_obra, Decimal("50.00"))],
        )
        self.baixar(lancamento, Decimal("40.00"), date(2026, 3, 20))
        self.baixar(lancamento, Decimal("60.00"), date(2026, 4, 20))

        resultado = self.relatorio()

        self.assertEqual(resultado["pago"], Decimal("75.00"))
        self.assertEqual(resultado["a_pagar"], Decimal("75.00"))
        self.assertEqual(resultado["resultado_caixa"], Decimal("-75.00"))

    def test_caixa_inclui_juros_multa_e_desconto(self):
        lancamento = self.criar_lancamento(
            "PAGAR",
            self.custo,
            Decimal("100.00"),
            [(self.obra, Decimal("60.00")), (self.outra_obra, Decimal("40.00"))],
        )
        self.baixar(
            lancamento,
            Decimal("50.00"),
            juros=Decimal("2.00"),
            multa=Decimal("3.00"),
            desconto=Decimal("1.00"),
        )

        resultado = self.relatorio()

        self.assertEqual(resultado["pago"], Decimal("32.40"))
        self.assertEqual(resultado["a_pagar"], Decimal("30.00"))

    def test_caixa_do_periodo_independe_da_competencia(self):
        lancamento = self.criar_lancamento(
            "RECEBER",
            self.receita,
            Decimal("90.00"),
            competencia=date(2025, 12, 10),
            emissao=date(2025, 12, 1),
        )
        self.baixar(lancamento, Decimal("90.00"), date(2026, 1, 5))

        resultado = self.relatorio()

        self.assertEqual(resultado["receitas"], Decimal("0.00"))
        self.assertEqual(resultado["recebido"], Decimal("90.00"))
        self.assertEqual(resultado["detalhes"], [])

    def test_arredondamento_fecha_e_tem_destino_deterministico(self):
        rateios = [
            SimpleNamespace(pk=1, valor=Decimal("33.34")),
            SimpleNamespace(pk=2, valor=Decimal("33.33")),
            SimpleNamespace(pk=3, valor=Decimal("33.33")),
        ]
        distribuicao = distribuir_valor_rateios(Decimal("0.01"), rateios)

        self.assertEqual(sum(distribuicao.values()), Decimal("0.01"))
        self.assertEqual(distribuicao[1], Decimal("0.01"))

    def test_lancamento_cancelado_nao_entra(self):
        self.criar_lancamento(
            "RECEBER", self.receita, Decimal("500.00"), status="CANCELADO"
        )
        self.assertEqual(self.relatorio()["receitas"], Decimal("0.00"))

    def test_obra_inativa_preserva_relatorio_historico(self):
        CentroCusto.objects.filter(pk=self.obra_inativa.pk).update(ativo=True)
        self.obra_inativa.ativo = True
        self.criar_lancamento(
            "PAGAR",
            self.custo,
            Decimal("80.00"),
            [(self.obra_inativa, Decimal("80.00"))],
        )
        CentroCusto.objects.filter(pk=self.obra_inativa.pk).update(ativo=False)
        self.obra_inativa.ativo = False
        self.assertEqual(
            self.relatorio(self.obra_inativa)["custos"], Decimal("80.00")
        )

    def test_isolamento_por_empresa(self):
        self.criar_lancamento("RECEBER", self.receita, Decimal("100.00"))
        self.criar_lancamento(
            "RECEBER",
            self.receita,
            Decimal("900.00"),
            [(self.obra_outra_empresa, Decimal("900.00"))],
            empresa=self.outra_empresa,
        )
        self.assertEqual(self.relatorio()["receitas"], Decimal("100.00"))

    def test_consulta_sem_resultados_retorna_zeros(self):
        resultado = self.relatorio()
        self.assertEqual(resultado["resultado_obra"], Decimal("0.00"))
        self.assertEqual(resultado["resultado_caixa"], Decimal("0.00"))
        self.assertEqual(resultado["detalhes"], [])

    def test_competencia_usa_data_emissao_como_fallback(self):
        self.criar_lancamento(
            "RECEBER",
            self.receita,
            Decimal("75.00"),
            competencia=None,
            emissao=date(2026, 5, 2),
        )
        self.assertEqual(self.relatorio()["receitas"], Decimal("75.00"))

    def test_tabela_hierarquica_totaliza_conta_superior(self):
        self.criar_lancamento("RECEBER", self.receita, Decimal("125.00"))
        grupo_receitas = self.relatorio()["grupos_contas"][0]
        valores = {
            linha["conta"].pk: linha["valor"] for linha in grupo_receitas["linhas"]
        }
        self.assertEqual(valores[self.receitas_pai.pk], Decimal("125.00"))
        self.assertEqual(valores[self.receita.pk], Decimal("125.00"))

    def test_filtro_rejeita_obra_de_outra_empresa(self):
        form = RelatorioObraFiltroForm({
            "empresa": self.empresa.pk,
            "obra": self.obra_outra_empresa.pk,
            "data_inicial": "2026-01-01",
            "data_final": "2026-12-31",
        })
        self.assertFalse(form.is_valid())

    def test_view_exibe_obra_inativa_e_estado_sem_resultados(self):
        usuario = get_user_model().objects.create_superuser(
            username="relatorio_teste",
            password="senha-teste",
            email="relatorio@teste.local",
        )
        self.client.force_login(usuario)
        resposta = self.client.get(
            reverse("financeiro:relatorio_gerencial_obra"),
            {
                "empresa": self.empresa.pk,
                "obra": self.obra_inativa.pk,
                "data_inicial": "2026-01-01",
                "data_final": "2026-12-31",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Obra inativa")
        self.assertContains(resposta, "Nenhum lançamento no período")

    def test_detalhamento_e_paginado(self):
        for indice in range(21):
            lancamento = self.criar_lancamento(
                "RECEBER", self.receita, Decimal("1.00")
            )
            lancamento.descricao = f"Lançamento paginado {indice} TESTE"
            LancamentoFinanceiro.objects.filter(pk=lancamento.pk).update(
                descricao=lancamento.descricao
            )

        usuario = get_user_model().objects.create_superuser(
            username="paginacao_relatorio_teste",
            password="senha-teste",
            email="paginacao@teste.local",
        )
        self.client.force_login(usuario)
        parametros = {
            "empresa": self.empresa.pk,
            "obra": self.obra.pk,
            "data_inicial": "2026-01-01",
            "data_final": "2026-12-31",
            "page": 2,
        }
        resposta = self.client.get(
            reverse("financeiro:relatorio_gerencial_obra"), parametros
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["pagina"].number, 2)
        self.assertEqual(len(resposta.context["pagina"]), 1)


class DREGerencialTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(
            razao_social="Empresa DRE TESTE",
            cnpj="81.000.000/0001-01",
            principal=True,
        )
        cls.outra_empresa = Empresa.objects.create(
            razao_social="Outra Empresa DRE TESTE",
            cnpj="82.000.000/0001-02",
        )
        cls.pessoa = Pessoa.objects.create(razao_social="Pessoa DRE TESTE")
        cls.conta_bancaria = ContaBancaria.objects.create(
            empresa=cls.empresa,
            banco="Banco DRE TESTE",
            agencia="0001",
            conta="98765",
            tipo="CORRENTE",
        )
        cls.obra = CentroCusto.objects.create(
            empresa=cls.empresa, codigo="DRE-TESTE-1", nome="Obra DRE"
        )
        cls.outra_obra = CentroCusto.objects.create(
            empresa=cls.empresa, codigo="DRE-TESTE-2", nome="Outra Obra DRE"
        )
        cls.obra_inativa = CentroCusto.objects.create(
            empresa=cls.empresa,
            codigo="DRE-TESTE-3",
            nome="Obra DRE Inativa",
            ativo=False,
        )
        cls.receita = PlanoConta.objects.get(codigo="4.01.01")
        cls.receita_pai = PlanoConta.objects.get(codigo="4.01")
        cls.receita_financeira = PlanoConta.objects.get(codigo="4.02.01")
        cls.custo = PlanoConta.objects.get(codigo="5.01.01")
        cls.custo_pai = PlanoConta.objects.get(codigo="5.01")
        cls.despesa = PlanoConta.objects.get(codigo="6.01.01")
        cls.despesa_financeira = PlanoConta.objects.get(codigo="6.09.01")
        cls.receita_redutora = PlanoConta.objects.create(
            codigo="T.DRE.4.R",
            nome="Redutora de Receita TESTE",
            tipo="RECEITA",
            natureza="DEVEDORA",
            conta_redutora=True,
            conta_pai=cls.receita_pai,
        )
        cls.custo_redutor = PlanoConta.objects.create(
            codigo="T.DRE.5.R",
            nome="Redutora de Custo TESTE",
            tipo="CUSTO",
            natureza="CREDORA",
            conta_redutora=True,
            conta_pai=cls.custo_pai,
        )
        cls.receita_financeira_neta = PlanoConta.objects.create(
            codigo="T.DRE.RF",
            nome="Receita Financeira Neta TESTE",
            tipo="RECEITA",
            natureza="CREDORA",
            conta_pai=cls.receita_financeira,
        )

    def criar_lancamento(
        self,
        tipo,
        conta,
        valor,
        competencia=date(2026, 3, 10),
        emissao=date(2026, 3, 1),
        empresa=None,
        status="ABERTO",
        rateios=(),
        descricao="Lançamento DRE TESTE",
    ):
        lancamento = LancamentoFinanceiro.objects.create(
            empresa=empresa or self.empresa,
            pessoa=self.pessoa,
            tipo=tipo,
            descricao=descricao,
            data_emissao=emissao,
            data_competencia=competencia,
            valor_total=valor,
            plano_conta=conta,
            status=status,
        )
        for obra, parte in rateios:
            RateioCentroCusto.objects.create(
                lancamento=lancamento, centro_custo=obra, valor=parte
            )
        return lancamento

    def dre(self, **kwargs):
        dados = {
            "empresa": self.empresa,
            "data_inicial": date(2026, 1, 1),
            "data_final": date(2026, 12, 31),
        }
        dados.update(kwargs)
        return calcular_dre(**dados)

    def test_calculos_e_margens_da_estrutura_completa(self):
        self.criar_lancamento("RECEBER", self.receita, Decimal("1000"))
        self.criar_lancamento("PAGAR", self.custo, Decimal("300"))
        self.criar_lancamento("PAGAR", self.despesa, Decimal("100"))
        self.criar_lancamento(
            "RECEBER", self.receita_financeira, Decimal("50")
        )
        self.criar_lancamento(
            "PAGAR", self.despesa_financeira, Decimal("20")
        )

        resumo = self.dre()["resumo"]

        self.assertEqual(resumo["resultado_bruto"], Decimal("700.00"))
        self.assertEqual(resumo["resultado_operacional"], Decimal("600.00"))
        self.assertEqual(resumo["resultado_financeiro"], Decimal("30.00"))
        self.assertEqual(resumo["resultado_periodo"], Decimal("630.00"))
        self.assertEqual(resumo["margem_bruta"], Decimal("70.00"))
        self.assertEqual(resumo["margem_operacional"], Decimal("60.00"))
        self.assertEqual(resumo["margem_periodo"], Decimal("63.00"))

    def test_margens_sem_receita_sao_nulas(self):
        self.criar_lancamento("PAGAR", self.custo, Decimal("30"))
        resumo = self.dre()["resumo"]
        self.assertIsNone(resumo["margem_bruta"])
        self.assertIsNone(resumo["margem_operacional"])
        self.assertIsNone(resumo["margem_periodo"])

    def test_consulta_sem_resultados_tem_estado_vazio(self):
        dre = self.dre()
        self.assertFalse(dre["tem_dados"])
        self.assertEqual(dre["resumo"]["resultado_periodo"], Decimal("0.00"))

    def test_ajustes_da_baixa_nao_entram_no_resultado_financeiro(self):
        lancamento = self.criar_lancamento(
            "PAGAR", self.custo, Decimal("100")
        )
        parcela = ParcelaFinanceira.objects.create(
            lancamento=lancamento,
            numero=1,
            vencimento=date(2026, 3, 20),
            valor=Decimal("100"),
        )
        BaixaFinanceira.objects.create(
            parcela=parcela,
            conta_bancaria=self.conta_bancaria,
            data=date(2026, 3, 20),
            valor=Decimal("50"),
            juros=Decimal("10"),
            multa=Decimal("5"),
            desconto=Decimal("2"),
        )
        resumo = self.dre()["resumo"]
        self.assertEqual(resumo["custos"], Decimal("100.00"))
        self.assertEqual(resumo["resultado_financeiro"], Decimal("0.00"))

    def test_hierarquia_subtotaliza_sem_duplicar_agrupadora(self):
        self.criar_lancamento("RECEBER", self.receita, Decimal("120"))
        secao = self.dre()["secoes"][0]
        linhas = {linha["conta"].pk: linha for linha in secao["linhas"]}
        self.assertEqual(secao["total"], Decimal("120.00"))
        self.assertEqual(linhas[self.receita_pai.pk]["valor"], Decimal("120.00"))
        self.assertEqual(linhas[self.receita.pk]["valor"], Decimal("120.00"))

    def test_contas_redutoras_aplicam_sinal_liquido(self):
        self.criar_lancamento("RECEBER", self.receita, Decimal("1000"))
        self.criar_lancamento("RECEBER", self.receita_redutora, Decimal("100"))
        self.criar_lancamento("PAGAR", self.custo, Decimal("300"))
        self.criar_lancamento("PAGAR", self.custo_redutor, Decimal("50"))
        resumo = self.dre()["resumo"]
        self.assertEqual(resumo["receitas_operacionais"], Decimal("900.00"))
        self.assertEqual(resumo["custos"], Decimal("250.00"))
        self.assertEqual(resumo["resultado_bruto"], Decimal("650.00"))

    def test_financeiro_e_identificado_por_ancestralidade(self):
        self.criar_lancamento(
            "RECEBER", self.receita_financeira_neta, Decimal("45")
        )
        resumo = self.dre()["resumo"]
        self.assertEqual(resumo["receitas_operacionais"], Decimal("0.00"))
        self.assertEqual(resumo["receitas_financeiras"], Decimal("45.00"))

    def test_fallback_emissao_pode_ser_desativado(self):
        self.criar_lancamento(
            "RECEBER",
            self.receita,
            Decimal("90"),
            competencia=None,
            emissao=date(2026, 4, 2),
        )
        com_fallback = self.dre(usar_fallback=True)
        sem_fallback = self.dre(usar_fallback=False)
        self.assertEqual(com_fallback["resumo"]["receitas_operacionais"], Decimal("90.00"))
        self.assertEqual(com_fallback["fallback_count"], 1)
        self.assertEqual(sem_fallback["resumo"]["receitas_operacionais"], Decimal("0.00"))
        self.assertEqual(sem_fallback["fallback_count"], 0)

    def test_consolidado_nao_duplica_lancamento_rateado(self):
        self.criar_lancamento(
            "RECEBER",
            self.receita,
            Decimal("100"),
            rateios=((self.obra, Decimal("60")), (self.outra_obra, Decimal("40"))),
        )
        self.assertEqual(
            self.dre()["resumo"]["receitas_operacionais"], Decimal("100.00")
        )

    def test_filtro_obra_usa_exclusivamente_valor_rateado(self):
        self.criar_lancamento(
            "RECEBER",
            self.receita,
            Decimal("100"),
            rateios=((self.obra, Decimal("60")), (self.outra_obra, Decimal("40"))),
        )
        self.assertEqual(
            self.dre(obra=self.obra)["resumo"]["receitas_operacionais"],
            Decimal("60.00"),
        )

    def test_obra_inativa_permanece_consultavel(self):
        CentroCusto.objects.filter(pk=self.obra_inativa.pk).update(ativo=True)
        self.obra_inativa.ativo = True
        self.criar_lancamento(
            "PAGAR",
            self.custo,
            Decimal("70"),
            rateios=((self.obra_inativa, Decimal("70")),),
        )
        CentroCusto.objects.filter(pk=self.obra_inativa.pk).update(ativo=False)
        self.obra_inativa.ativo = False
        self.assertEqual(
            self.dre(obra=self.obra_inativa)["resumo"]["custos"],
            Decimal("70.00"),
        )

    def test_cancelados_e_outra_empresa_nao_entram(self):
        self.criar_lancamento(
            "RECEBER", self.receita, Decimal("100"), status="CANCELADO"
        )
        self.criar_lancamento(
            "RECEBER",
            self.receita,
            Decimal("900"),
            empresa=self.outra_empresa,
        )
        self.assertEqual(
            self.dre()["resumo"]["receitas_operacionais"], Decimal("0.00")
        )

    def test_filtro_plano_agrupador_inclui_descendentes(self):
        self.criar_lancamento("RECEBER", self.receita, Decimal("110"))
        self.criar_lancamento("PAGAR", self.custo, Decimal("80"))
        resumo = self.dre(conta_filtro=self.receita_pai)["resumo"]
        self.assertEqual(resumo["receitas_operacionais"], Decimal("110.00"))
        self.assertEqual(resumo["custos"], Decimal("0.00"))

    def test_comparacao_periodo_anterior_equivalente(self):
        self.criar_lancamento(
            "RECEBER", self.receita, Decimal("100"), competencia=date(2026, 3, 10)
        )
        self.criar_lancamento(
            "RECEBER", self.receita, Decimal("70"), competencia=date(2026, 2, 10)
        )
        dre = calcular_dre(
            self.empresa,
            date(2026, 3, 1),
            date(2026, 3, 31),
            comparacao="ANTERIOR",
        )
        self.assertEqual(dre["periodo_comparativo"], (date(2026, 1, 29), date(2026, 2, 28)))
        self.assertEqual(dre["resumo_comparativo"]["receitas_operacionais"], Decimal("70.00"))

    def test_comparacao_mesmo_periodo_ano_anterior(self):
        self.criar_lancamento(
            "RECEBER", self.receita, Decimal("55"), competencia=date(2025, 3, 10)
        )
        dre = calcular_dre(
            self.empresa,
            date(2026, 3, 1),
            date(2026, 3, 31),
            comparacao="ANO_ANTERIOR",
        )
        self.assertEqual(dre["periodo_comparativo"], (date(2025, 3, 1), date(2025, 3, 31)))
        self.assertEqual(dre["resumo_comparativo"]["receitas_operacionais"], Decimal("55.00"))

    def test_drilldown_fecha_com_valor_analitico(self):
        self.criar_lancamento("RECEBER", self.receita, Decimal("40"))
        self.criar_lancamento("RECEBER", self.receita, Decimal("60"))
        dre = self.dre()
        linha = next(
            linha for linha in dre["secoes"][0]["linhas"]
            if linha["conta"] == self.receita
        )
        detalhe = drilldown_dre(
            self.empresa,
            self.receita,
            date(2026, 1, 1),
            date(2026, 12, 31),
        )
        self.assertEqual(detalhe["total"], linha["valor"])
        self.assertEqual(len(detalhe["itens"]), 2)

    def test_form_isola_obra_por_empresa(self):
        form = DREFiltroForm({
            "empresa": self.outra_empresa.pk,
            "obra": self.obra.pk,
            "data_inicial": "2026-01-01",
            "data_final": "2026-12-31",
            "comparacao": "NENHUMA",
            "usar_fallback": "on",
        })
        self.assertFalse(form.is_valid())

    def test_view_e_drilldown_paginado(self):
        for indice in range(21):
            self.criar_lancamento(
                "RECEBER",
                self.receita,
                Decimal("1"),
                descricao=f"DRE paginação {indice} TESTE",
            )
        usuario = get_user_model().objects.create_superuser(
            username="dre_view_teste",
            password="senha-teste",
            email="dre@teste.local",
        )
        self.client.force_login(usuario)
        resposta = self.client.get(
            reverse("financeiro:dre_gerencial"),
            {
                "empresa": self.empresa.pk,
                "data_inicial": "2026-01-01",
                "data_final": "2026-12-31",
                "comparacao": "NENHUMA",
                "usar_fallback": "on",
                "conta_detalhe": self.receita.pk,
                "page": 2,
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["pagina"].number, 2)
        self.assertEqual(len(resposta.context["pagina"]), 1)
        self.assertContains(resposta, "DRE Gerencial Consolidada")
