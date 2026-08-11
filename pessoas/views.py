import re

import requests

from django.http import JsonResponse
from django.shortcuts import redirect, render

from .forms import PessoaForm
from .models import Pessoa


def lista_pessoas(request):
    pessoas = Pessoa.objects.all()

    contexto = {
        "pessoas": pessoas,
    }

    return render(
        request,
        "pessoas/lista.html",
        contexto,
    )


def nova_pessoa(request):

    if request.method == "POST":
        form = PessoaForm(request.POST)

        if form.is_valid():
            form.save()

            return redirect("pessoas:lista")

    else:
        form = PessoaForm()

    contexto = {
        "form": form,
    }

    return render(
        request,
        "pessoas/formulario.html",
        contexto,
    )

def consultar_cnpj(request):
    cnpj = request.GET.get("cnpj", "")
    cnpj = re.sub(r"\D", "", cnpj)

    if len(cnpj) != 14:
        return JsonResponse(
            {
                "sucesso": False,
                "erro": "Informe um CNPJ com 14 dígitos.",
            },
            status=400,
        )

    url = f"https://publica.cnpj.ws/cnpj/{cnpj}"

    try:
        resposta = requests.get(
            url,
            timeout=10,
        )

    except requests.RequestException:
        return JsonResponse(
            {
                "sucesso": False,
                "erro": "Não foi possível consultar o CNPJ no momento.",
            },
            status=503,
        )

    if resposta.status_code == 429:
        return JsonResponse(
            {
                "sucesso": False,
                "erro": (
                    "Limite de consultas atingido. "
                    "Aguarde cerca de 1 minuto e tente novamente."
                ),
            },
            status=429,
        )

    if resposta.status_code == 404:
        return JsonResponse(
            {
                "sucesso": False,
                "erro": "CNPJ não encontrado.",
            },
            status=404,
        )

    if resposta.status_code != 200:
        return JsonResponse(
            {
                "sucesso": False,
                "erro": (
                    f"Erro ao consultar o CNPJ. "
                    f"Status retornado: {resposta.status_code}."
                ),
            },
            status=502,
        )

    dados = resposta.json()

    estabelecimento = dados.get("estabelecimento") or {}

    cidade = estabelecimento.get("cidade") or {}
    estado = estabelecimento.get("estado") or {}

    resultado = {
        "sucesso": True,

        "razao_social": dados.get("razao_social", ""),

        "nome_fantasia": estabelecimento.get(
            "nome_fantasia",
            ""
        ),

        "cep": estabelecimento.get(
            "cep",
            ""
        ),

        "endereco": estabelecimento.get(
            "logradouro",
            ""
        ),

        "numero": estabelecimento.get(
            "numero",
            ""
        ),

        "complemento": estabelecimento.get(
            "complemento",
            ""
        ),

        "bairro": estabelecimento.get(
            "bairro",
            ""
        ),

        "cidade": cidade.get(
            "nome",
            ""
        ),

        "estado": estado.get(
            "sigla",
            ""
        ),

        "telefone": estabelecimento.get(
            "telefone1",
            ""
        ),

        "email": estabelecimento.get(
            "email",
            ""
        ),
    }

    return JsonResponse(resultado)