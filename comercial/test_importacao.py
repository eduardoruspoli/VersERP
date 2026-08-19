from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase

from financeiro.models import Empresa
from pessoas.models import Pessoa
from .models import Proposta


class ImportacaoHistoricaTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao_social="Empresa importação", cnpj="71.000.000/0001-01")

    def arquivo(self, pasta, linhas):
        caminho = Path(pasta) / "historico.csv"
        caminho.write_text("numero;data;cliente;servico;valor;status;contato\n" + "\n".join(linhas), encoding="utf-8")
        return caminho

    def test_dry_run_nao_grava(self):
        with TemporaryDirectory() as pasta:
            caminho = self.arquivo(pasta, ["VERS9001;01/08/2026;Cliente Novo;Serviço;1.250,50;Faturada;Maria"])
            saida = StringIO()
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk, dry_run=True, stdout=saida)
        self.assertEqual(Proposta.objects.count(), 0)
        self.assertEqual(Pessoa.objects.count(), 0)
        self.assertIn("DRY-RUN", saida.getvalue())

    def test_importacao_e_idempotente_e_preserva_status(self):
        with TemporaryDirectory() as pasta:
            caminho = self.arquivo(pasta, ["VERS9002;02/08/2026;Cliente Histórico;Manutenção;2000,00;Faturada;João"])
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk)
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk)
        proposta = Proposta.objects.get()
        self.assertEqual(proposta.origem, Proposta.Origem.IMPORTADO_HISTORICO)
        self.assertEqual(proposta.status_historico, "Faturada")
        self.assertEqual(proposta.revisoes.get().aos_cuidados_de, "João")
        self.assertEqual(Proposta.objects.count(), 1)

    def test_cliente_existente_e_reutilizado(self):
        cliente = Pessoa.objects.create(razao_social="Ácme Ltda", classificacao=Pessoa.Classificacao.CLIENTE)
        with TemporaryDirectory() as pasta:
            caminho = self.arquivo(pasta, ["VERS9003;03/08/2026;ACME LTDA;Projeto;100,00;Enviada;"])
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk)
        self.assertEqual(Proposta.objects.get().cliente, cliente)
        self.assertEqual(Pessoa.objects.count(), 1)
