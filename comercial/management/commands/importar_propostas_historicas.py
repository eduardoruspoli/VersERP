import csv
import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from comercial.models import Proposta, PropostaRevisao
from financeiro.models import Empresa
from pessoas.models import Pessoa


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", texto.upper())


def moeda(valor):
    texto = str(valor or "0").strip().replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    return Decimal(texto or "0")


def data(valor):
    if isinstance(valor, datetime):
        return valor.date()
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(str(valor).strip(), formato).date()
        except ValueError:
            pass
    raise ValueError("data inválida")


class Command(BaseCommand):
    help = "Analisa/importa propostas históricas de CSV ou XLSX de forma idempotente."

    def add_arguments(self, parser):
        parser.add_argument("arquivo")
        parser.add_argument("--empresa", type=int)
        parser.add_argument("--dry-run", action="store_true")

    def _linhas(self, caminho):
        if caminho.suffix.lower() == ".csv":
            with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
                primeira = arquivo.readline()
                arquivo.seek(0)
                yield from csv.DictReader(arquivo, delimiter=";" if ";" in primeira else ",")
            return
        if caminho.suffix.lower() == ".xlsx":
            try:
                from openpyxl import load_workbook
            except ImportError as exc:
                raise CommandError("Instale openpyxl para importar XLSX.") from exc
            planilha = load_workbook(caminho, read_only=True, data_only=True).active
            linhas = planilha.iter_rows(values_only=True)
            cabecalho = [str(x or "").strip() for x in next(linhas)]
            for valores in linhas:
                yield dict(zip(cabecalho, valores))
            return
        raise CommandError("Use um arquivo .csv ou .xlsx.")

    def handle(self, *args, **opcoes):
        caminho = Path(opcoes["arquivo"])
        if not caminho.exists():
            raise CommandError("Arquivo não encontrado.")
        empresas = Empresa.objects.filter(pk=opcoes.get("empresa")) if opcoes.get("empresa") else Empresa.objects.filter(ativa=True)
        if empresas.count() != 1:
            raise CommandError("Informe --empresa quando houver zero ou mais de uma empresa ativa.")
        empresa = empresas.get()
        relatorio = {"validas": 0, "duplicadas": 0, "erros": 0, "clientes_novos": 0, "ambiguos": 0, "importadas": 0}
        preparados = []
        existentes = {}
        for pessoa in Pessoa.objects.all():
            existentes.setdefault(normalizar(pessoa.razao_social), []).append(pessoa)
        for numero, linha in enumerate(self._linhas(caminho), start=2):
            try:
                codigo = "".join(str(linha.get("numero") or linha.get("Número") or linha.get("proposta") or "").upper().split())
                if not re.fullmatch(r"VERS\d+", codigo):
                    raise ValueError("número fora do padrão VERS")
                if Proposta.objects.filter(empresa=empresa, codigo=codigo).exists():
                    relatorio["duplicadas"] += 1
                    continue
                cliente_nome = str(linha.get("cliente") or linha.get("Cliente") or "").strip()
                if not cliente_nome:
                    raise ValueError("cliente ausente")
                candidatos = existentes.get(normalizar(cliente_nome), [])
                if len(candidatos) > 1:
                    relatorio["ambiguos"] += 1
                    continue
                cliente = candidatos[0] if candidatos else None
                if not cliente:
                    relatorio["clientes_novos"] += 1
                preparados.append({"codigo": codigo, "cliente": cliente, "cliente_nome": cliente_nome, "data": data(linha.get("data") or linha.get("Data")), "servico": str(linha.get("servico") or linha.get("Serviço") or linha.get("descricao") or "Proposta histórica").strip(), "contato": str(linha.get("contato") or linha.get("Contato") or "").strip(), "valor": moeda(linha.get("valor") or linha.get("Valor")), "status_historico": str(linha.get("status") or linha.get("Status") or "").strip(), "observacao": str(linha.get("observacao") or linha.get("Observação") or "").strip()})
                relatorio["validas"] += 1
            except (ValueError, InvalidOperation) as erro:
                relatorio["erros"] += 1
                self.stderr.write(f"Linha {numero}: {erro}")
        if not opcoes["dry_run"]:
            with transaction.atomic():
                for item in preparados:
                    cliente = item["cliente"] or Pessoa.objects.create(razao_social=item["cliente_nome"], classificacao=Pessoa.Classificacao.CLIENTE)
                    proposta = Proposta.objects.create(empresa=empresa, cliente=cliente, codigo=item["codigo"], numero_sequencial=int(item["codigo"][4:]), origem=Proposta.Origem.IMPORTADO_HISTORICO, status_historico=item["status_historico"], observacao_importacao=item["observacao"])
                    PropostaRevisao.objects.create(proposta=proposta, numero=0, data_proposta=item["data"], nome_servico=item["servico"], aos_cuidados_de=item["contato"], formacao_preco=PropostaRevisao.FormacaoPreco.MANUAL, preco_venda_final=item["valor"], congelada=True)
                    relatorio["importadas"] += 1
        modo = "DRY-RUN" if opcoes["dry_run"] else "IMPORTAÇÃO"
        self.stdout.write(self.style.SUCCESS(f"{modo}: {relatorio}"))
