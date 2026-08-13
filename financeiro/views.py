from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.db import transaction
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone

from .forms import (
    BaixaFinanceiraForm,
    LancamentoFinanceiroForm,
    ParcelaFormSet,
)
from .models import (
    BaixaFinanceira,
    ContaBancaria,
    LancamentoFinanceiro,
    ParcelaFinanceira,
)


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================


def preparar_formset_parcelas(request):
    quantidade = request.POST.get(
        "quantidade_parcelas",
        "1",
    )

    try:
        quantidade = int(quantidade)
    except (TypeError, ValueError):
        quantidade = 1

    if quantidade < 1:
        quantidade = 1

    dados_formset = request.POST.copy()

    dados_formset[
        "parcelas-TOTAL_FORMS"
    ] = str(quantidade)

    dados_formset[
        "parcelas-INITIAL_FORMS"
    ] = "0"

    dados_formset[
        "parcelas-MIN_NUM_FORMS"
    ] = "0"

    dados_formset[
        "parcelas-MAX_NUM_FORMS"
    ] = "1000"

    return ParcelaFormSet(
        dados_formset,
        prefix="parcelas",
    )


def total_formset_parcelas(
    parcela_formset,
):
    return sum(
        (
            parcela.cleaned_data["valor"]
            for parcela in parcela_formset
        ),
        Decimal("0.00"),
    )


def queryset_lancamentos(tipo):
    return (
        LancamentoFinanceiro.objects
        .filter(
            tipo=tipo
        )
        .select_related(
            "empresa",
            "pessoa",
            "plano_conta",
        )
        .prefetch_related(
            "parcelas",
            "parcelas__baixas",
        )
    )


def obter_lancamento(
    pk,
    tipo,
):
    return get_object_or_404(
        queryset_lancamentos(tipo),
        pk=pk,
    )


def calcular_totais_lancamento(
    lancamento,
):
    parcelas = (
        lancamento
        .parcelas
        .order_by(
            "numero"
        )
    )

    total_baixado = sum(
        (
            parcela.total_baixado
            for parcela in parcelas
        ),
        Decimal("0.00"),
    )

    saldo_total = sum(
        (
            parcela.saldo
            for parcela in parcelas
        ),
        Decimal("0.00"),
    )

    return (
        parcelas,
        total_baixado,
        saldo_total,
    )


def dados_iniciais_parcelas(
    lancamento,
):
    return [
        {
            "numero": parcela.numero,
            "vencimento": parcela.vencimento,
            "valor": parcela.valor,
        }
        for parcela
        in (
            lancamento
            .parcelas
            .order_by(
                "numero"
            )
        )
    ]


def formulario_edicao_lancamento(
    lancamento,
):
    quantidade_parcelas = (
        lancamento
        .parcelas
        .count()
    )

    primeira_parcela = (
        lancamento
        .parcelas
        .order_by(
            "numero"
        )
        .first()
    )

    return LancamentoFinanceiroForm(
        instance=lancamento,
        initial={
            "condicao_pagamento": (
                "AVISTA"
                if quantidade_parcelas == 1
                else "PARCELADO"
            ),
            "quantidade_parcelas": (
                quantidade_parcelas
            ),
            "primeiro_vencimento": (
                primeira_parcela.vencimento
                if primeira_parcela
                else None
            ),
        },
    )


def salvar_novas_parcelas(
    lancamento,
    parcela_formset,
):
    parcelas = []

    for parcela_form in parcela_formset:
        dados = (
            parcela_form.cleaned_data
        )

        parcelas.append(
            ParcelaFinanceira(
                lancamento=lancamento,
                numero=dados["numero"],
                vencimento=dados[
                    "vencimento"
                ],
                valor=dados["valor"],
                status="ABERTA",
            )
        )

    (
        ParcelaFinanceira
        .objects
        .bulk_create(
            parcelas
        )
    )


def criar_lancamento_financeiro(
    request,
    tipo,
    template,
    detalhe_url,
    mensagem_sucesso,
):
    if request.method == "POST":
        form = LancamentoFinanceiroForm(
            request.POST
        )

        parcela_formset = (
            preparar_formset_parcelas(
                request
            )
        )

        form_valido = (
            form.is_valid()
        )

        parcelas_validas = (
            parcela_formset.is_valid()
        )

        if (
            form_valido
            and parcelas_validas
        ):
            valor_total = (
                form.cleaned_data[
                    "valor_total"
                ]
            )

            total_parcelas = (
                total_formset_parcelas(
                    parcela_formset
                )
            )

            if (
                total_parcelas
                != valor_total
            ):
                form.add_error(
                    None,
                    (
                        "A soma das parcelas "
                        "deve ser igual ao valor "
                        "total do lançamento."
                    ),
                )

            else:
                with transaction.atomic():
                    lancamento = form.save(
                        commit=False
                    )

                    lancamento.tipo = tipo
                    lancamento.origem = (
                        "MANUAL"
                    )
                    lancamento.status = (
                        "ABERTO"
                    )

                    lancamento.save()

                    salvar_novas_parcelas(
                        lancamento,
                        parcela_formset,
                    )

                messages.success(
                    request,
                    mensagem_sucesso,
                )

                return redirect(
                    detalhe_url,
                    pk=lancamento.pk,
                )

    else:
        form = (
            LancamentoFinanceiroForm()
        )

        parcela_formset = (
            ParcelaFormSet(
                prefix="parcelas"
            )
        )

    contexto = {
        "form": form,
        "parcela_formset": (
            parcela_formset
        ),
        "tipo_lancamento": tipo,
        "modo_edicao": False,
        "possui_baixas": False,
    }

    return render(
        request,
        template,
        contexto,
    )


def editar_lancamento_financeiro(
    request,
    pk,
    tipo,
    template,
    detalhe_url,
    mensagem_sucesso,
):
    lancamento = get_object_or_404(
        LancamentoFinanceiro,
        pk=pk,
        tipo=tipo,
    )

    possui_baixas = (
        lancamento
        .parcelas
        .filter(
            baixas__isnull=False
        )
        .exists()
    )

    if request.method == "POST":
        form = (
            LancamentoFinanceiroForm(
                request.POST,
                instance=lancamento,
            )
        )

        parcela_formset = (
            preparar_formset_parcelas(
                request
            )
        )

        form_valido = (
            form.is_valid()
        )

        parcelas_validas = (
            parcela_formset.is_valid()
        )

        if possui_baixas:
            form.add_error(
                None,
                (
                    "Este lançamento possui "
                    "baixas financeiras. "
                    "Os valores e parcelas "
                    "não podem ser alterados "
                    "livremente."
                ),
            )

        elif (
            form_valido
            and parcelas_validas
        ):
            valor_total = (
                form.cleaned_data[
                    "valor_total"
                ]
            )

            total_parcelas = (
                total_formset_parcelas(
                    parcela_formset
                )
            )

            if (
                total_parcelas
                != valor_total
            ):
                form.add_error(
                    None,
                    (
                        "A soma das parcelas "
                        "deve ser igual ao valor "
                        "total do lançamento."
                    ),
                )

            else:
                with transaction.atomic():
                    lancamento_editado = (
                        form.save(
                            commit=False
                        )
                    )

                    lancamento_editado.tipo = (
                        tipo
                    )

                    lancamento_editado.save()

                    (
                        lancamento
                        .parcelas
                        .all()
                        .delete()
                    )

                    salvar_novas_parcelas(
                        lancamento_editado,
                        parcela_formset,
                    )

                messages.success(
                    request,
                    mensagem_sucesso,
                )

                return redirect(
                    detalhe_url,
                    pk=lancamento.pk,
                )

    else:
        form = (
            formulario_edicao_lancamento(
                lancamento
            )
        )

        parcela_formset = (
            ParcelaFormSet(
                initial=(
                    dados_iniciais_parcelas(
                        lancamento
                    )
                ),
                prefix="parcelas",
            )
        )

    contexto = {
        "form": form,
        "parcela_formset": (
            parcela_formset
        ),
        "lancamento": lancamento,
        "tipo_lancamento": tipo,
        "modo_edicao": True,
        "possui_baixas": (
            possui_baixas
        ),
    }

    return render(
        request,
        template,
        contexto,
    )


def registrar_baixa_financeira(
    request,
    pk,
    tipo,
    template,
    detalhe_url,
    mensagem_sucesso,
):
    parcela = get_object_or_404(
        ParcelaFinanceira.objects
        .select_related(
            "lancamento",
            "lancamento__empresa",
            "lancamento__pessoa",
        ),
        pk=pk,
        lancamento__tipo=tipo,
    )

    lancamento = (
        parcela.lancamento
    )

    if (
        parcela.status
        == "CANCELADA"
    ):
        messages.error(
            request,
            (
                "Não é possível registrar "
                "movimentação em uma "
                "parcela cancelada."
            ),
        )

        return redirect(
            detalhe_url,
            pk=lancamento.pk,
        )

    if (
        parcela.saldo
        <= Decimal("0.00")
    ):
        messages.info(
            request,
            (
                "Esta parcela já está "
                "totalmente liquidada."
            ),
        )

        return redirect(
            detalhe_url,
            pk=lancamento.pk,
        )

    if request.method == "POST":
        form = BaixaFinanceiraForm(
            request.POST,
            empresa=lancamento.empresa,
            saldo=parcela.saldo,
        )

        if form.is_valid():
            with transaction.atomic():
                baixa = form.save(
                    commit=False
                )

                baixa.parcela = (
                    parcela
                )

                baixa.save()

            messages.success(
                request,
                mensagem_sucesso,
            )

            return redirect(
                detalhe_url,
                pk=lancamento.pk,
            )

    else:
        form = BaixaFinanceiraForm(
            empresa=lancamento.empresa,
            saldo=parcela.saldo,
            initial={
                "data": (
                    timezone.localdate()
                ),
            },
        )

    contexto = {
        "form": form,
        "parcela": parcela,
        "lancamento": lancamento,
        "tipo_lancamento": tipo,
    }

    return render(
        request,
        template,
        contexto,
    )


# ============================================================
# PÁGINA INICIAL DO FINANCEIRO
# ============================================================


@login_required
@permission_required(
    "financeiro.view_lancamentofinanceiro",
    raise_exception=True,
)
def financeiro_index(request):
    return render(
        request,
        "financeiro/index.html",
    )


# ============================================================
# CONTAS A PAGAR
# ============================================================


@login_required
@permission_required(
    "financeiro.view_lancamentofinanceiro",
    raise_exception=True,
)
def contas_pagar(request):
    lancamentos = (
        queryset_lancamentos(
            "PAGAR"
        )
        .order_by(
            "-id"
        )
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
    "financeiro.view_lancamentofinanceiro",
    raise_exception=True,
)
def detalhe_conta_pagar(
    request,
    pk,
):
    lancamento = obter_lancamento(
        pk,
        "PAGAR",
    )

    (
        parcelas,
        total_baixado,
        saldo_total,
    ) = calcular_totais_lancamento(
        lancamento
    )

    contexto = {
        "lancamento": lancamento,
        "parcelas": parcelas,
        "total_baixado": (
            total_baixado
        ),
        "saldo_total": saldo_total,
    }

    return render(
        request,
        (
            "financeiro/"
            "conta_pagar_detalhe.html"
        ),
        contexto,
    )


@login_required
@permission_required(
    "financeiro.add_lancamentofinanceiro",
    raise_exception=True,
)
def nova_conta_pagar(request):
    return criar_lancamento_financeiro(
        request=request,
        tipo="PAGAR",
        template=(
            "financeiro/"
            "conta_pagar_formulario.html"
        ),
        detalhe_url=(
            "financeiro:"
            "detalhe_conta_pagar"
        ),
        mensagem_sucesso=(
            "Conta a pagar "
            "cadastrada com sucesso."
        ),
    )


@login_required
@permission_required(
    "financeiro.change_lancamentofinanceiro",
    raise_exception=True,
)
def editar_conta_pagar(
    request,
    pk,
):
    return editar_lancamento_financeiro(
        request=request,
        pk=pk,
        tipo="PAGAR",
        template=(
            "financeiro/"
            "conta_pagar_formulario.html"
        ),
        detalhe_url=(
            "financeiro:"
            "detalhe_conta_pagar"
        ),
        mensagem_sucesso=(
            "Conta a pagar "
            "atualizada com sucesso."
        ),
    )


@login_required
@permission_required(
    "financeiro.add_baixafinanceira",
    raise_exception=True,
)
def baixar_parcela(
    request,
    pk,
):
    return registrar_baixa_financeira(
        request=request,
        pk=pk,
        tipo="PAGAR",
        template=(
            "financeiro/"
            "baixa_formulario.html"
        ),
        detalhe_url=(
            "financeiro:"
            "detalhe_conta_pagar"
        ),
        mensagem_sucesso=(
            "Pagamento registrado "
            "com sucesso."
        ),
    )


# ============================================================
# CONTAS A RECEBER
# ============================================================


@login_required
@permission_required(
    "financeiro.view_lancamentofinanceiro",
    raise_exception=True,
)
def contas_receber(request):
    lancamentos = (
        queryset_lancamentos(
            "RECEBER"
        )
        .order_by(
            "-id"
        )
    )

    contexto = {
        "lancamentos": lancamentos,
    }

    return render(
        request,
        "financeiro/contas_receber.html",
        contexto,
    )


@login_required
@permission_required(
    "financeiro.view_lancamentofinanceiro",
    raise_exception=True,
)
def detalhe_conta_receber(
    request,
    pk,
):
    lancamento = obter_lancamento(
        pk,
        "RECEBER",
    )

    (
        parcelas,
        total_baixado,
        saldo_total,
    ) = calcular_totais_lancamento(
        lancamento
    )

    contexto = {
        "lancamento": lancamento,
        "parcelas": parcelas,
        "total_baixado": (
            total_baixado
        ),
        "saldo_total": saldo_total,
    }

    return render(
        request,
        (
            "financeiro/"
            "conta_receber_detalhe.html"
        ),
        contexto,
    )


@login_required
@permission_required(
    "financeiro.add_lancamentofinanceiro",
    raise_exception=True,
)
def nova_conta_receber(request):
    return criar_lancamento_financeiro(
        request=request,
        tipo="RECEBER",
        template=(
            "financeiro/"
            "conta_receber_formulario.html"
        ),
        detalhe_url=(
            "financeiro:"
            "detalhe_conta_receber"
        ),
        mensagem_sucesso=(
            "Conta a receber "
            "cadastrada com sucesso."
        ),
    )


@login_required
@permission_required(
    "financeiro.change_lancamentofinanceiro",
    raise_exception=True,
)
def editar_conta_receber(
    request,
    pk,
):
    return editar_lancamento_financeiro(
        request=request,
        pk=pk,
        tipo="RECEBER",
        template=(
            "financeiro/"
            "conta_receber_formulario.html"
        ),
        detalhe_url=(
            "financeiro:"
            "detalhe_conta_receber"
        ),
        mensagem_sucesso=(
            "Conta a receber "
            "atualizada com sucesso."
        ),
    )


@login_required
@permission_required(
    "financeiro.add_baixafinanceira",
    raise_exception=True,
)
def receber_parcela(
    request,
    pk,
):
    return registrar_baixa_financeira(
        request=request,
        pk=pk,
        tipo="RECEBER",
        template=(
            "financeiro/"
            "recebimento_formulario.html"
        ),
        detalhe_url=(
            "financeiro:"
            "detalhe_conta_receber"
        ),
        mensagem_sucesso=(
            "Recebimento registrado "
            "com sucesso."
        ),
    )


# ============================================================
# CONTAS BANCÁRIAS
# ============================================================


@login_required
@permission_required(
    "financeiro.view_contabancaria",
    raise_exception=True,
)
def contas_bancarias(request):
    contas = (
        ContaBancaria.objects
        .filter(
            ativa=True
        )
        .select_related(
            "empresa"
        )
        .order_by(
            "empresa",
            "banco",
            "agencia",
            "conta",
        )
    )

    contexto = {
        "contas": contas,
    }

    return render(
        request,
        (
            "financeiro/"
            "contas_bancarias.html"
        ),
        contexto,
    )


@login_required
@permission_required(
    "financeiro.view_contabancaria",
    raise_exception=True,
)
def detalhe_conta_bancaria(
    request,
    pk,
):
    conta = get_object_or_404(
        ContaBancaria.objects
        .select_related(
            "empresa"
        ),
        pk=pk,
        ativa=True,
    )

    movimentacoes = (
        BaixaFinanceira.objects
        .filter(
            conta_bancaria=conta
        )
        .select_related(
            "parcela",
            "parcela__lancamento",
            (
                "parcela__"
                "lancamento__pessoa"
            ),
        )
        .order_by(
            "-data",
            "-id",
        )
    )

    contexto = {
        "conta": conta,
        "movimentacoes": (
            movimentacoes
        ),
    }

    return render(
        request,
        (
            "financeiro/"
            "conta_bancaria_detalhe.html"
        ),
        contexto,
    )