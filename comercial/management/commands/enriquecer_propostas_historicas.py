import hashlib
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

from django.core.management.base import BaseCommand, CommandError
from pypdf import PdfReader

from comercial.models import Proposta


CODIGO_RE = re.compile(r"(?i)\b(VERS\d+)(?:\.(\d+))?\b")
REVISAO_RE = re.compile(r"(?i)\b(?:RV|REV)[ ._-]*(\d+)\b")
MOEDA_RE = re.compile(r"R\$\s*([\d.]+,\d{2})")


PUBLIC_FIELDS = {
    "escopo_incluido": ("escopo", "escopo_incluido"),
    "nao_incluso": ("nao incluso", "nao_incluso"),
    "normas_procedimentos": ("normas", "normas_procedimentos"),
    "qualificacao_mao_obra": ("qualificacao", "qualificacao_mao_obra"),
    "obrigacoes_contratada": ("obrigacoes", "obrigacoes_contratada"),
    "observacoes_comerciais": ("observacoes", "observacoes_comerciais"),
}


def normalizar(texto):
    return re.sub(
        r"[^a-z0-9]+",
        "",
        unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower(),
    )


def interpretar_documento(path):
    codigo = CODIGO_RE.search(path.stem)
    if not codigo:
        codigo = CODIGO_RE.search(path.parent.name)
    if not codigo:
        return None
    revisao = int(codigo.group(2) or 0)
    return codigo.group(1).upper(), revisao


def revisao_ambigua(path):
    return bool(REVISAO_RE.search(path.stem) and not re.search(r"(?i)VERS\d+\.\d+", path.stem))


def texto_pdf(path):
    leitor = PdfReader(str(path))
    return "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)


def texto_docx(path):
    with ZipFile(path) as arquivo:
        documentos = [nome for nome in arquivo.namelist() if nome == "word/document.xml"]
        if not documentos:
            return ""
        xml = arquivo.read(documentos[0]).decode("utf-8", "ignore")
    xml = re.sub(r"</w:p>|</w:tr>|</w:tc>", "\n", xml)
    return re.sub(r"<[^>]+>", " ", xml)


def extrair_texto(path):
    if path.suffix.lower() == ".pdf":
        return texto_pdf(path)
    if path.suffix.lower() == ".docx":
        return texto_docx(path)
    return ""


def arquivo_comercial(path):
    partes = {parte.lower() for parte in path.parts}
    nome = normalizar(path.name)
    if any("anex" in parte for parte in partes):
        return False, "anexo"
    if "custosporarea" in nome or "custo" in nome or "rfq" in nome:
        return False, "interno"
    if path.suffix.lower() not in {".pdf", ".docx"}:
        return False, "formato não prioritário"
    return True, ""


def extrair_revisao(texto):
    match = REVISAO_RE.search(texto)
    return int(match.group(1)) if match else None


def extrair_campo(texto, campo):
    normalizado = normalizar(texto)
    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
    marcadores = {
        "escopo_incluido": ("escopo de fornecimento",),
        "nao_incluso": ("nao incluso",),
        "normas_procedimentos": ("normas, procedimentos", "normas e procedimentos"),
        "qualificacao_mao_obra": ("qualificacao da mao",),
        "obrigacoes_contratada": ("obrigacoes da versatile", "obrigacoes da contratada"),
        "observacoes_comerciais": ("observacoes e adendos", "atencao"),
    }
    marcador = next((m for m in marcadores[campo] if m in normalizado), None)
    if not marcador:
        return ""
    for indice, linha in enumerate(linhas):
        if marcador in normalizar(linha):
            trecho = linhas[indice + 1 : indice + 8]
            return "\n".join(trecho).strip()
    return ""


def extrair_valor(texto):
    valores = MOEDA_RE.findall(texto.replace("\n", " "))
    if not valores:
        return None
    valor = valores[-1].replace(".", "").replace(",", ".")
    return float(valor)


def extrair_linha(texto, prefixo):
    for linha in texto.splitlines():
        if normalizar(linha).startswith(normalizar(prefixo)):
            return linha.split(maxsplit=2)[-1].strip(" :.-")
    return ""


def extrair_data(texto):
    meses = {
        "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
        "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    }
    match = re.search(r"(?:Santo Ant[aã]o|Ant[aã]o),?\s*(\d{1,2})\s+de\s+([A-Za-zçã]+)\s+de\s+(\d{4})", texto, re.I)
    if not match:
        return None
    mes = meses.get(normalizar(match.group(2)))
    return datetime(int(match.group(3)), mes, int(match.group(1))).date() if mes else None


class Command(BaseCommand):
    help = "Analisa documentos históricos e sugere enriquecimento sem gravar dados."

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True)
        parser.add_argument("--empresa", type=int)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if not options["dry_run"]:
            raise CommandError("Este comando é somente dry-run; informe --dry-run.")
        origem = Path(options["source"])
        if not origem.is_dir():
            raise CommandError("A pasta --source não existe ou não é uma pasta.")
        propostas = Proposta.objects.select_related("cliente").prefetch_related("revisoes")
        if options.get("empresa"):
            propostas = propostas.filter(empresa_id=options["empresa"])
        por_codigo = {proposta.codigo: proposta for proposta in propostas}
        documentos = defaultdict(list)
        ignorados = Counter()
        for caminho in sorted(origem.rglob("*")):
            if not caminho.is_file():
                continue
            permitido, motivo = arquivo_comercial(caminho)
            if not permitido:
                if motivo in {"anexo", "interno"}:
                    ignorados[motivo] += 1
                continue
            identificacao = interpretar_documento(caminho)
            if not identificacao:
                ignorados["sem código"] += 1
                continue
            if revisao_ambigua(caminho):
                ignorados["revisão ambígua RV/REV"] += 1
                continue
            documentos[identificacao].append(caminho)
        sugestoes = []
        conflitos = Counter()
        ambiguos = []
        analisadas = set()
        for (codigo, revisao), caminhos in sorted(documentos.items()):
            proposta = por_codigo.get(codigo)
            if not proposta:
                ignorados["proposta ausente"] += len(caminhos)
                continue
            revisao_obj = proposta.revisoes.filter(numero=revisao).first()
            if not revisao_obj:
                ignorados["revisão ausente"] += len(caminhos)
                continue
            if len(caminhos) > 2:
                ambiguos.append((codigo, revisao, [str(c) for c in caminhos]))
                continue
            analisadas.add((codigo, revisao))
            caminho = next((p for p in caminhos if p.suffix.lower() == ".pdf"), caminhos[0])
            try:
                texto = extrair_texto(caminho)
            except Exception as erro:
                ambiguos.append((codigo, revisao, [f"{c}: {erro}" for c in caminhos]))
                continue
            origem_hash = hashlib.sha256(caminho.read_bytes()).hexdigest()
            for campo, marcadores in PUBLIC_FIELDS.items():
                atual = getattr(revisao_obj, campo)
                sugerido = extrair_campo(texto, campo)
                if not sugerido:
                    continue
                status = "IGUAL" if normalizar(atual) == normalizar(sugerido) else ("PREENCHER" if not atual else "CONFLITO")
                if status == "CONFLITO":
                    conflitos[campo] += 1
                sugestoes.append({"codigo": codigo, "revisao": revisao, "campo": campo, "atual": atual, "sugerido": sugerido[:500], "arquivo": caminho.name, "tipo": caminho.suffix.lower(), "sha256": origem_hash, "status": status})
            valor_documental = extrair_valor(texto)
            if valor_documental is not None and abs(float(revisao_obj.preco_venda_final) - valor_documental) > 0.009:
                conflitos["valor"] += 1
                sugestoes.append({"codigo": codigo, "revisao": revisao, "campo": "preco_venda_final", "atual": str(revisao_obj.preco_venda_final), "sugerido": f"{valor_documental:.2f}", "arquivo": caminho.name, "tipo": caminho.suffix.lower(), "sha256": origem_hash, "status": "CONFLITO"})
            comparacoes = (
                ("cliente", extrair_linha(texto, "Ao Cliente"), proposta.cliente.razao_social),
                ("contato", extrair_linha(texto, "Att"), revisao_obj.aos_cuidados_de),
                ("data", extrair_data(texto), revisao_obj.data_proposta),
            )
            for campo, sugerido, atual in comparacoes:
                if not sugerido:
                    continue
                iguais = normalizar(sugerido) in normalizar(atual) or normalizar(atual) in normalizar(sugerido) if campo != "data" else sugerido == atual
                if not iguais:
                    conflitos[campo] += 1
                    sugestoes.append({"codigo": codigo, "revisao": revisao, "campo": campo, "atual": str(atual), "sugerido": str(sugerido), "arquivo": caminho.name, "tipo": caminho.suffix.lower(), "sha256": origem_hash, "status": "CONFLITO"})
        resumo = Counter(item["status"] for item in sugestoes)
        self.stdout.write(f"DRY-RUN: propostas analisadas={len({c for c, _ in analisadas})}; revisões analisadas={len(analisadas)}")
        self.stdout.write(f"SUGESTOES: preencher={resumo['PREENCHER']}; iguais={resumo['IGUAL']}; conflitos={resumo['CONFLITO']}; não extraídos={len(analisadas) - len({(x['codigo'], x['revisao']) for x in sugestoes})}")
        self.stdout.write(f"CONFLITOS: {dict(conflitos)}")
        self.stdout.write(f"DOCUMENTOS IGNORADOS: {dict(ignorados)}")
        self.stdout.write(f"DOCUMENTOS AMBÍGUOS: {len(ambiguos)}")
        for item in sugestoes:
            if item["status"] in {"PREENCHER", "CONFLITO"}:
                self.stdout.write(f"{item['status']}: {item['codigo']} rev {item['revisao']:02d} {item['campo']} atual={item['atual']!r} sugerido={item['sugerido']!r} origem={item['arquivo']}")
