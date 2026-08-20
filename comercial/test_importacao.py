from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import ValidationError
from django.test import TestCase

from financeiro.models import Empresa
from pessoas.models import Pessoa
from .management.commands.importar_propostas_historicas import interpretar_codigo_historico
from .models import Proposta, PropostaRevisao


class ImportacaoHistoricaTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao_social="Empresa importação", cnpj="71.000.000/0001-01")

    def arquivo(self, pasta, linhas):
        caminho = Path(pasta) / "historico.csv"
        caminho.write_text("numero;data;cliente;servico;valor;status;contato\n" + "\n".join(linhas), encoding="utf-8")
        return caminho

    def arquivo_xlsx(self, pasta, linhas, cabecalho=None):
        from openpyxl import Workbook
        caminho = Path(pasta) / "historico.xlsx"
        planilha = Workbook().active
        planilha.append(["RELATÓRIO HISTÓRICO DE PROPOSTAS"])
        planilha.append(cabecalho or ["Nº Prop.", "Data Emissão.", "Emitente", "Cliente", "Contato", "Descrição", "Status", "Valor", "Observação"])
        for linha in linhas:
            planilha.append(linha)
        planilha.parent.save(caminho)
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

    def test_duplicidade_no_mesmo_arquivo_nao_cria_propostas_repetidas(self):
        with TemporaryDirectory() as pasta:
            caminho = self.arquivo(pasta, [
                "VERS9004;03/08/2026;Cliente Único;Projeto A;100,00;Enviada;",
                "VERS9004;04/08/2026;Cliente Único;Projeto B;200,00;Enviada;",
            ])
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk)
        self.assertEqual(Proposta.objects.filter(codigo="VERS9004").count(), 1)

    def test_mesmo_cliente_novo_e_reutilizado_dentro_do_arquivo(self):
        with TemporaryDirectory() as pasta:
            caminho = self.arquivo(pasta, [
                "VERS9005;03/08/2026;Cliente Repetido;Projeto A;100,00;Enviada;",
                "VERS9006;04/08/2026;CLIENTE REPETIDO;Projeto B;200,00;Enviada;",
            ])
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk)
        self.assertEqual(Pessoa.objects.count(), 1)
        self.assertEqual(Proposta.objects.values("cliente_id").distinct().count(), 1)

    def test_xlsx_detecta_titulo_cabecalho_real_e_aliases(self):
        with TemporaryDirectory() as pasta:
            cabecalho = ["Nº Prop.", "Data Emissão.", "Emitente", "Cliente", "Contato", "Descrição", "Status", 0, "observação"]
            caminho = self.arquivo_xlsx(pasta, [["VERS9010", "10/08/2026", "YULI", "Cliente XLSX", "Maria", "Serviço XLSX", "Faturada", 150, "NF teste"]], cabecalho)
            saida = StringIO()
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk, dry_run=True, stdout=saida)
        self.assertIn("'validas': 1", saida.getvalue())
        self.assertEqual(Proposta.objects.count(), 0)
        self.assertEqual(Pessoa.objects.count(), 0)

    def test_cabecalho_normalizado_sem_acentos_e_pontuacao(self):
        with TemporaryDirectory() as pasta:
            cabecalho = [" Numero ", "Data de Emissao", "CLIENTE", "Descricao", "STATUS", "Valor Total"]
            caminho = self.arquivo_xlsx(pasta, [["VERS9011", "11/08/2026", "Cliente", "Serviço", "Fechada", 200]], cabecalho)
            saida = StringIO()
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk, dry_run=True, stdout=saida)
        self.assertIn("'validas': 1", saida.getvalue())

    def test_data_inicial_filtra_e_conta_linhas_anteriores(self):
        with TemporaryDirectory() as pasta:
            caminho = self.arquivo(pasta, [
                "VERS9012;31/12/2025;Cliente;Antiga;100,00;Faturada;Maria",
                "VERS9013;01/01/2026;Cliente;Atual;200,00;Fechada;Maria",
            ])
            saida = StringIO()
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk, dry_run=True, data_inicial="2026-01-01", stdout=saida)
        self.assertIn("'validas': 1", saida.getvalue())
        self.assertIn("'anteriores_corte': 1", saida.getvalue())
        self.assertEqual(Proposta.objects.count(), 0)

    def test_data_inicial_invalida_e_rejeitada(self):
        with TemporaryDirectory() as pasta:
            caminho = self.arquivo(pasta, ["VERS9014;01/01/2026;Cliente;Serviço;10,00;Faturada;Maria"])
            with self.assertRaises(CommandError):
                call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk, dry_run=True, data_inicial="01/01/2026")

    def test_xlsx_mantem_deteccao_de_duplicidade_interna(self):
        with TemporaryDirectory() as pasta:
            caminho = self.arquivo_xlsx(pasta, [
                ["VERS9015", "01/01/2026", "YULI", "Cliente", "Maria", "A", "Faturada", 10, ""],
                ["VERS9015", "02/01/2026", "YULI", "Cliente", "Maria", "B", "Faturada", 20, ""],
            ])
            saida = StringIO()
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk, dry_run=True, stdout=saida)
        self.assertIn("'duplicadas': 1", saida.getvalue())

    def test_codigo_revisionado_identifica_base_e_revisao(self):
        self.assertEqual(interpretar_codigo_historico("VERS1862.1"), ("VERS1862", 1))
        self.assertEqual(interpretar_codigo_historico("VERS1900.2"), ("VERS1900", 2))
        self.assertEqual(interpretar_codigo_historico("VERS1901"), ("VERS1901", 0))

    def test_revisao_sem_base_e_bloqueada(self):
        with TemporaryDirectory() as pasta:
            caminho = self.arquivo(pasta, ["VERS9900.1;01/01/2026;Cliente;Revisão;100,00;Enviada;Maria"])
            saida = StringIO()
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk, dry_run=True, stdout=saida)
        self.assertIn("'revisoes_sem_base': 1", saida.getvalue())
        self.assertEqual(Proposta.objects.count(), 0)

    def test_dry_run_com_revisao_nao_grava(self):
        with TemporaryDirectory() as pasta:
            caminho = self.arquivo(pasta, [
                "VERS9901;01/01/2026;Cliente;Original;100,00;negociação;Maria",
                "VERS9901.1;02/01/2026;Cliente;Revisão;120,00;faturada;Maria",
            ])
            saida = StringIO()
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk, dry_run=True, stdout=saida)
        self.assertIn("'propostas_base': 1", saida.getvalue())
        self.assertIn("'revisoes_historicas': 1", saida.getvalue())
        self.assertEqual(Proposta.objects.count(), 0)
        self.assertEqual(PropostaRevisao.objects.count(), 0)

    def test_status_historico_de_cada_revisao_e_preservado(self):
        with TemporaryDirectory() as pasta:
            caminho = self.arquivo(pasta, [
                "VERS9902;01/01/2026;Cliente;Original;100,00;negociação;Maria",
                "VERS9902.1;02/01/2026;Cliente;Revisão;120,00;faturada;João",
            ])
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk)
        proposta = Proposta.objects.get(codigo="VERS9902")
        self.assertEqual(proposta.status, Proposta.Status.RASCUNHO)
        self.assertEqual(proposta.revisao_atual, 1)
        self.assertIsNone(proposta.revisao_aprovada)
        self.assertIn("Status histórico: negociação", proposta.revisoes.get(numero=0).observacoes_internas)
        self.assertIn("Status histórico: faturada", proposta.revisoes.get(numero=1).observacoes_internas)

    def test_data_invalida_anterior_ao_recorte_nao_e_erro(self):
        with TemporaryDirectory() as pasta:
            caminho = self.arquivo(pasta, [
                "VERS9903;data inválida;Cliente;Antiga;100,00;faturada;Maria",
                "VERS9904;01/01/2026;Cliente;Atual;100,00;negociação;Maria",
            ])
            saida = StringIO()
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk, dry_run=True, data_inicial="2026-01-01", stdout=saida)
        self.assertIn("'datas_invalidas_ignoradas': 1", saida.getvalue())
        self.assertIn("'erros_estruturais': 0", saida.getvalue())

    def test_cliente_incompleto_e_valido_para_importacao_autorizada(self):
        with TemporaryDirectory() as pasta:
            caminho = self.arquivo(pasta, ["VERS9905;01/01/2026;ARB;Serviço;100,00;negociação;Maria"])
            saida = StringIO()
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk, dry_run=True, stdout=saida)
        self.assertIn("'validas': 1", saida.getvalue())
        self.assertIn("'clientes_incompletos': 1", saida.getvalue())
        self.assertIn("'erros_estruturais': 0", saida.getvalue())

    def test_cliente_confirmado_e_criado_com_dados_mapeados(self):
        with TemporaryDirectory() as pasta:
            caminho = self.arquivo(pasta, ["VERS9907;01/01/2026;MDZ;Serviço;100,00;negociação;Maria"])
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk)
        cliente = Proposta.objects.get().cliente
        self.assertEqual(cliente.razao_social, "MONDELEZ BRASIL NORTE NORDESTE LTDA")
        self.assertEqual(cliente.cpf_cnpj, "10144076000144")
        self.assertIn("MDZ / MDLZ", cliente.observacoes)

    def test_cliente_incompleto_e_idempotente_por_nome_normalizado(self):
        with TemporaryDirectory() as pasta:
            caminho = self.arquivo(pasta, ["VERS9908;01/01/2026;MJ ENGENHARIA;Serviço;100,00;negociação;Maria"])
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk)
            call_command("importar_propostas_historicas", caminho, empresa=self.empresa.pk)
        cliente = Pessoa.objects.get(razao_social="MJ ENGENHARIA")
        self.assertEqual(cliente.cpf_cnpj, "")
        self.assertIn("Cadastro incompleto", cliente.observacoes)
        self.assertEqual(Pessoa.objects.filter(razao_social="MJ ENGENHARIA").count(), 1)

    def test_model_normal_nao_aceita_codigo_decimal(self):
        cliente = Pessoa.objects.create(razao_social="Cliente", classificacao=Pessoa.Classificacao.CLIENTE)
        proposta = Proposta(empresa=self.empresa, cliente=cliente, codigo="VERS9906.1")
        with self.assertRaises(ValidationError):
            proposta.full_clean()

    def test_enriquecimento_exige_dry_run(self):
        with TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "documentos"
            caminho.mkdir()
            with self.assertRaises(CommandError):
                call_command("enriquecer_propostas_historicas", source=caminho, stdout=StringIO())
        self.assertEqual(Proposta.objects.count(), 0)

    def test_enriquecimento_dry_run_nao_grava_e_e_deterministico(self):
        with TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "documentos"
            caminho.mkdir()
            (caminho / "VERS9001 RV01.pdf").write_bytes(b"documento")
            primeira = StringIO()
            segunda = StringIO()
            call_command("enriquecer_propostas_historicas", source=caminho, dry_run=True, stdout=primeira)
            call_command("enriquecer_propostas_historicas", source=caminho, dry_run=True, stdout=segunda)
        self.assertEqual(primeira.getvalue(), segunda.getvalue())
        self.assertEqual(Proposta.objects.count(), 0)
        self.assertEqual(PropostaRevisao.objects.count(), 0)
