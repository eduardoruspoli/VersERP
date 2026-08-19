from io import BytesIO

from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa


def resposta_pdf(template, contexto, nome_arquivo):
    """Renderiza HTML Django em PDF sem depender de navegador externo."""
    html = render_to_string(template, contexto)
    destino = BytesIO()
    resultado = pisa.CreatePDF(html, dest=destino, encoding="utf-8")
    if resultado.err:
        raise RuntimeError("Não foi possível gerar o documento PDF.")
    resposta = HttpResponse(destino.getvalue(), content_type="application/pdf")
    resposta["Content-Disposition"] = f'inline; filename="{nome_arquivo}"'
    return resposta
