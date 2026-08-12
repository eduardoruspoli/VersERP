import calendar

from datetime import date
from decimal import Decimal, ROUND_DOWN

from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.db import transaction
from django.shortcuts import redirect, render

from .forms import LancamentoFinanceiroForm
from .models import (
    LancamentoFinanceiro,
    ParcelaFinanceira,
)


def adicionar_meses(data_base, meses):
    mes = data_base.month - 1 + meses
    ano = data_base.year + mes // 12
    mes = mes % 12 + 1

    ultimo_dia = calendar.monthrange(ano, mes)[1]
    dia = min(data_base.day, ultimo_dia)

    return date(ano, mes, dia)


def gerar_parcelas(
    lancamento,
    quantidade,
    primeiro_vencimento,
):
    valor_total = lancamento.valor_total

    valor_base = (
        valor_total / quantidade
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_DOWN,
    )

    valor_distribuido = valor_base * quantidade
    diferenca = valor_total - valor_distribuido

    parcelas = []

    for numero in range(1, quantidade + 1):
        valor = valor_base

        if numero == quantidade:
            valor += diferenca

        parcelas.append(
            ParcelaFinanceira(
                lancamento=lancamento,
                numero=numero,
                vencimento=adicionar_meses(
                    primeiro_vencimento,
                    numero - 1,
                ),
                valor=valor,
                status="ABERTA",
            )
        )

    ParcelaFinanceira.objects.bulk_create(parcelas)


@login_required
@permission_required(
    "financeiro.view_lancamentofinanceiro",
    raise_exception=True,
)
def contas_pagar(request):
    lancamentos = LancamentoFinanceiro.objects.filter(
        tipo="PAGAR"
    )

    contexto = {
        "lancamentos": lancamentos,
    }

    return render(
        request,
        "financeiro/contas_pagar.html",
        contexto,
    )


@login_required
@permission_required(
    "financeiro.add_lancamentofinanceiro",
    raise_exception=True,
)
def nova_conta_pagar(request):
    if request.method == "POST":
        form = LancamentoFinanceiroForm(request.POST)

        if form.is_valid():
            condicao = form.cleaned_data[
                "condicao_pagamento"
            ]

            if condicao == "AVISTA":
                quantidade = 1
            else:
                quantidade = form.cleaned_data[
                    "quantidade_parcelas"
                ]

            primeiro_vencimento = form.cleaned_data[
                "primeiro_vencimento"
            ]

            with transaction.atomic():
                lancamento = form.save(commit=False)

                lancamento.tipo = "PAGAR"
                lancamento.origem = "MANUAL"
                lancamento.status = "ABERTO"

                lancamento.save()

                gerar_parcelas(
                    lancamento=lancamento,
                    quantidade=quantidade,
                    primeiro_vencimento=primeiro_vencimento,
                )

            return redirect(
                "financeiro:contas_pagar"
            )

    else:
        form = LancamentoFinanceiroForm()

    contexto = {
        "form": form,
    }

    return render(
        request,
        "financeiro/conta_pagar_formulario.html",
        contexto,
    )