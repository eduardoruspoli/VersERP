from io import BytesIO
from pathlib import Path

from django.http import HttpResponse
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from xhtml2pdf import pisa


def _link_callback(uri, rel):
    caminho_uri = uri.removeprefix("/")
    if caminho_uri.startswith("static/"):
        caminho = finders.find(caminho_uri.removeprefix("static/"))
        if caminho:
            return str(Path(caminho).resolve())
    return uri


def resposta_pdf(template, contexto, nome_arquivo):
    """Renderiza HTML Django em PDF sem depender de navegador externo."""
    html = render_to_string(template, contexto)
    destino = BytesIO()
    resultado = pisa.CreatePDF(html, dest=destino, encoding="utf-8", link_callback=_link_callback)
    if resultado.err:
        raise RuntimeError("Não foi possível gerar o documento PDF.")
    resposta = HttpResponse(destino.getvalue(), content_type="application/pdf")
    resposta["Content-Disposition"] = f'inline; filename="{nome_arquivo}"'
    return resposta
