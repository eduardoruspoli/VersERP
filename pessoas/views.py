import re

from django.core import paginator
from django.core import paginator
import requests

from django.http import JsonResponse, request
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required

from .forms import PessoaForm
from .models import Pessoa

@login_required
def lista_pessoas(request):
    pessoas = Pessoa.objects.all()

    busca = request.GET.get("busca", "").strip()
    classificacao = request.GET.get("classificacao", "").strip()
    status = request.GET.get("status", "").strip()

    if busca:
        pessoas = pessoas.filter(
            Q(razao_social__icontains=busca)
            | Q(nome_fantasia__icontains=busca)
            | Q(cpf_cnpj__icontains=busca)
            | Q(email__icontains=busca)
        )

    if classificacao:
        pessoas = pessoas.filter(
            classificacao=classificacao
        )

    if status == "ativo":
        pessoas = pessoas.filter(ativo=True)

    elif status == "inativo":
        pessoas = pessoas.filter(ativo=False)

    paginator = Paginator(pessoas, 10)
    
    numero_pagina = request.GET.get("page")
    
    pagina = paginator.get_page(numero_pagina)

    contexto = {
        "pessoas": pagina,
        "pagina": pagina,
        "busca": busca,
        "classificacao_selecionada": classificacao,
        "status_selecionado": status,
    }

    return render(
        request,
        "pessoas/lista.html",
        contexto,
    )

@login_required
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

@login_required
def editar_pessoa(request, pk):
    pessoa = get_object_or_404(Pessoa, pk=pk)

    if request.method == "POST":
        form = PessoaForm(
            request.POST,
            instance=pessoa,
        )

        if form.is_valid():
            form.save()
            return redirect("pessoas:lista")

    else:
        form = PessoaForm(instance=pessoa)

    contexto = {
        "form": form,
        "pessoa": pessoa,
        "modo_edicao": True,
    }

    return render(
        request,
        "pessoas/formulario.html",
        contexto,
    )


@login_required
def detalhe_pessoa(request, pk):
    pessoa = get_object_or_404(Pessoa, pk=pk)

    contexto = {
        "pessoa": pessoa,
    }

    return render(
        request,
        "pessoas/detalhe.html",
        contexto,
    )


@login_required
def alterar_status_pessoa(request, pk):
    pessoa = get_object_or_404(Pessoa, pk=pk)

    if request.method == "POST":
        pessoa.ativo = not pessoa.ativo
        pessoa.save(update_fields=["ativo"])

    return redirect("pessoas:lista")


@login_required
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