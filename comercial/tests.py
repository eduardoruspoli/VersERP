from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from financeiro.models import Empresa
from pessoas.models import Pessoa

from .models import ModeloConteudoProposta, Proposta, PropostaItem, PropostaLinhaPublica, PropostaRevisao, PropostaTributo
from .services import calcular_precificacao, criar_nova_revisao, criar_proposta, enviar_proposta, montar_contexto_publico_proposta, validar_fechamento_publico


class ComercialBase(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="comercial", password="teste123")
        self.empresa = Empresa.objects.create(razao_social="Empresa Teste", nome_fantasia="Vers Teste", cnpj="11.111.111/0001-11")
        self.cliente = Pessoa.objects.create(razao_social="Cliente Teste", classificacao=Pessoa.Classificacao.CLIENTE, ativo=True, cpf_cnpj="22.222.222/0001-22")
        self.fornecedor = Pessoa.objects.create(razao_social="Fornecedor Secreto", classificacao=Pessoa.Classificacao.FORNECEDOR, ativo=True)
        self.proposta, self.revisao = criar_proposta(empresa=self.empresa, cliente=self.cliente, nome_servico="Serviço TESTE", usuario=self.usuario)

    def item(self, custo="100.00", quantidade="1"):
        return PropostaItem.objects.create(revisao=self.revisao, tipo=PropostaItem.Tipo.MATERIAL, descricao="Material interno", quantidade=Decimal(quantidade), custo_unitario=Decimal(custo), fornecedor=self.fornecedor)

    def linha(self, valor="150.00", grupo=PropostaLinhaPublica.Grupo.MATERIAL):
        return PropostaLinhaPublica.objects.create(revisao=self.revisao, grupo=grupo, descricao="Solução fornecida", valor_total=Decimal(valor))


class DominioPropostaTests(ComercialBase):
    def test_codigo_sequencial_por_empresa(self):
        segunda, _ = criar_proposta(empresa=self.empresa, cliente=self.cliente, nome_servico="Outra")
        self.assertEqual((self.proposta.codigo, segunda.codigo), ("VERS0001", "VERS0002"))

    def test_modelo_padrao_e_copiado_como_snapshot(self):
        modelo = ModeloConteudoProposta.objects.create(empresa=self.empresa, nome="Padrão", padrao=True, texto_introdutorio="Texto original")
        _, revisao = criar_proposta(empresa=self.empresa, cliente=self.cliente, nome_servico="Nova")
        modelo.texto_introdutorio = "Texto alterado"
        modelo.save()
        revisao.refresh_from_db()
        self.assertEqual(revisao.texto_introdutorio, "Texto original")

    def test_custo_total_item_e_derivado(self):
        item = self.item("12.3456", "2")
        self.assertEqual(item.custo_total, Decimal("24.69"))

    def test_markup_com_tributos(self):
        self.item()
        self.revisao.percentual_formacao = Decimal("50")
        self.revisao.save()
        PropostaTributo.objects.create(revisao=self.revisao, nome="Impostos", percentual=Decimal("10"))
        calculo = calcular_precificacao(self.revisao)
        self.assertEqual(calculo["preco_final"], Decimal("166.67"))
        self.assertEqual(calculo["tributos"], Decimal("16.67"))

    def test_margem_com_tributos(self):
        self.item()
        self.revisao.formacao_preco = PropostaRevisao.FormacaoPreco.MARGEM
        self.revisao.percentual_formacao = Decimal("20")
        self.revisao.save()
        PropostaTributo.objects.create(revisao=self.revisao, nome="Impostos", percentual=Decimal("10"))
        self.assertEqual(calcular_precificacao(self.revisao)["preco_final"], Decimal("142.86"))

    def test_preco_manual(self):
        self.item()
        self.revisao.formacao_preco = PropostaRevisao.FormacaoPreco.MANUAL
        self.revisao.preco_venda_final = Decimal("230")
        self.revisao.save()
        self.assertEqual(calcular_precificacao(self.revisao)["preco_final"], Decimal("230.00"))

    def test_linhas_publicas_nao_alteram_precificacao(self):
        self.item()
        antes = calcular_precificacao(self.revisao)
        self.linha("9999")
        self.assertEqual(calcular_precificacao(self.revisao), antes)

    def test_fechamento_publico_exato(self):
        self.revisao.preco_venda_final = Decimal("150")
        self.revisao.save()
        self.linha("149.99")
        with self.assertRaises(ValidationError):
            validar_fechamento_publico(self.revisao)

    def test_envio_recalcula_valida_e_congela(self):
        self.item()
        self.revisao.percentual_formacao = Decimal("50")
        self.revisao.save()
        self.linha("150")
        enviada = enviar_proposta(self.revisao, self.usuario)
        self.assertTrue(enviada.congelada)
        self.assertEqual(enviada.preco_venda_final, Decimal("150.00"))
        self.proposta.refresh_from_db()
        self.assertEqual(self.proposta.status, Proposta.Status.ENVIADA)

    def test_revisao_congelada_bloqueia_item(self):
        self.item(); self.revisao.percentual_formacao = Decimal("50"); self.revisao.save(); self.linha("150"); enviar_proposta(self.revisao)
        with self.assertRaises(ValidationError):
            PropostaItem.objects.create(revisao=self.revisao, tipo=PropostaItem.Tipo.OUTROS, descricao="Novo", quantidade=1, custo_unitario=1)

    def test_nova_revisao_clona_dados_e_descongela(self):
        self.item(); self.revisao.percentual_formacao = Decimal("50"); self.revisao.save(); self.linha("150"); enviar_proposta(self.revisao)
        nova = criar_nova_revisao(self.revisao, self.usuario)
        self.assertEqual(nova.numero, 1)
        self.assertFalse(nova.congelada)
        self.assertEqual(nova.itens.count(), 1)
        self.assertEqual(nova.linhas_publicas.count(), 1)

    def test_visibilidade_preserva_snapshot(self):
        self.revisao.normas_procedimentos = "NR-10"
        self.revisao.exibir_normas_procedimentos = False
        self.revisao.save()
        contexto = montar_contexto_publico_proposta(self.revisao)
        self.assertEqual(contexto["blocos"]["normas_procedimentos"], "")
        self.revisao.refresh_from_db()
        self.assertEqual(self.revisao.normas_procedimentos, "NR-10")

    def test_contexto_publico_tem_allowlist_sem_dados_internos(self):
        self.item(); self.linha()
        texto = repr(montar_contexto_publico_proposta(self.revisao))
        for segredo in ("Fornecedor Secreto", "custo_total", "markup", "observacoes_internas", "plano_conta"):
            self.assertNotIn(segredo, texto)


class ViewsPropostaTests(ComercialBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.usuario)

    def test_lista_e_detalhe(self):
        self.assertContains(self.client.get(reverse("comercial:proposta_lista")), "VERS0001")
        self.assertContains(self.client.get(reverse("comercial:proposta_detalhe", args=[self.proposta.pk])), "Composição interna")

    def test_documento_publico_nao_expoe_dados_internos(self):
        self.item(); self.linha()
        resposta = self.client.get(reverse("comercial:documento_publico", args=[self.revisao.pk]))
        self.assertContains(resposta, "Solução fornecida")
        self.assertContains(resposta, "R$ 150,00")
        self.assertNotContains(resposta, "Fornecedor Secreto")
        self.assertNotContains(resposta, "Custo interno")
        self.assertNotContains(resposta, "Margem")

    def test_envio_invalido_exibe_erro_e_nao_congela(self):
        self.item(); self.revisao.percentual_formacao = 50; self.revisao.save(); self.linha("149")
        self.client.post(reverse("comercial:proposta_enviar", args=[self.proposta.pk]))
        self.revisao.refresh_from_db()
        self.assertFalse(self.revisao.congelada)

    def test_criacao_pela_tela(self):
        resposta = self.client.post(reverse("comercial:proposta_criar"), {"empresa": self.empresa.pk, "cliente": self.cliente.pk, "nome_servico": "Nova tela", "modelo": ""})
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Proposta.objects.filter(revisoes__nome_servico="Nova tela").exists())
