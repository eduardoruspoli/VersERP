from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone
from django.utils.dateparse import parse_date

from .forms import (
    BaixaFinanceiraForm,
    CriarLancamentoOFXForm,
    ImportacaoOFXForm,
    LancamentoFinanceiroForm,
    ParcelaFormSet,
    TransferenciaBancariaForm,
)
from .models import (
    BaixaFinanceira,
    ContaBancaria,
    ImportacaoOFX,
    LancamentoFinanceiro,
    MovimentacaoBancaria,
    MovimentoOFX,
    ParcelaFinanceira,
    TransferenciaBancaria,
)
from .ofx import (
    ErroOFX,
    ler_ofx,
)


# ============================================================
# FUNÇÕES AUXILIARES - LANÇAMENTOS
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
# FUNÇÕES AUXILIARES - CONCILIAÇÃO
# ============================================================


def tipo_lancamento_para_movimento(
    tipo_lancamento,
):
    if tipo_lancamento == "PAGAR":
        return "SAIDA"

    if tipo_lancamento == "RECEBER":
        return "ENTRADA"

    return None


def baixa_ja_conciliada(
    baixa,
    ignorar_movimento_id=None,
):
    queryset = (
        MovimentoOFX.objects
        .filter(
            baixa_conciliada=baixa,
            status="CONCILIADO",
        )
    )

    if ignorar_movimento_id:
        queryset = queryset.exclude(
            pk=ignorar_movimento_id
        )

    return queryset.exists()


def transferencia_ja_conciliada(
    transferencia,
    conta_bancaria,
    ignorar_movimento_id=None,
):
    queryset = (
        MovimentoOFX.objects
        .filter(
            transferencia_conciliada=transferencia,
            conta_bancaria=conta_bancaria,
            status="CONCILIADO",
        )
    )

    if ignorar_movimento_id:
        queryset = queryset.exclude(
            pk=ignorar_movimento_id
        )

    return queryset.exists()


def encontrar_candidatos_movimento(
    movimento,
):
    """
    Primeira versão do motor de sugestão.

    Critérios:
    - mesma conta bancária
    - mesma data
    - mesmo sentido
    - mesmo valor efetivamente movimentado
    - baixa ainda não conciliada
    """

    baixas = (
        BaixaFinanceira.objects
        .filter(
            conta_bancaria=(
                movimento.conta_bancaria
            ),
            data=movimento.data,
        )
        .select_related(
            "parcela",
            "parcela__lancamento",
            "parcela__lancamento__pessoa",
        )
        .order_by(
            "id"
        )
    )

    candidatos = []

    for baixa in baixas:
        lancamento = (
            baixa.parcela.lancamento
        )

        tipo_movimento = (
            tipo_lancamento_para_movimento(
                lancamento.tipo
            )
        )

        if (
            tipo_movimento
            != movimento.tipo
        ):
            continue

        if (
            baixa.valor_movimento
            != movimento.valor
        ):
            continue

        if baixa_ja_conciliada(
            baixa,
            ignorar_movimento_id=(
                movimento.pk
            ),
        ):
            continue

        candidatos.append(
            baixa
        )

    return candidatos


def encontrar_transferencias_movimento(
    movimento,
):
    """
    Procura transferências efetivadas compatíveis
    com um movimento OFX.

    Critérios:
    - mesma conta bancária
    - mesma data
    - mesmo valor
    - mesmo sentido
    - transferência ainda não conciliada
      nesta conta
    """

    if movimento.tipo == "SAIDA":
        transferencias = (
            TransferenciaBancaria.objects
            .filter(
                conta_origem=(
                    movimento.conta_bancaria
                ),
                data=movimento.data,
                valor=movimento.valor,
                status="EFETIVADA",
            )
            .select_related(
                "conta_origem",
                "conta_destino",
            )
            .order_by(
                "id"
            )
        )

    else:
        transferencias = (
            TransferenciaBancaria.objects
            .filter(
                conta_destino=(
                    movimento.conta_bancaria
                ),
                data=movimento.data,
                valor=movimento.valor,
                status="EFETIVADA",
            )
            .select_related(
                "conta_origem",
                "conta_destino",
            )
            .order_by(
                "id"
            )
        )

    candidatos = []

    for transferencia in transferencias:
        if transferencia_ja_conciliada(
            transferencia,
            movimento.conta_bancaria,
            ignorar_movimento_id=(
                movimento.pk
            ),
        ):
            continue

        candidatos.append(
            transferencia
        )

    return candidatos


def preparar_movimentos_para_tela(
    movimentos,
):
    resultado = []

    for movimento in movimentos:
        candidatos = []
        transferencias_candidatas = []

        if (
            movimento.status
            == "PENDENTE"
        ):
            candidatos = (
                encontrar_candidatos_movimento(
                    movimento
                )
            )

            transferencias_candidatas = (
                encontrar_transferencias_movimento(
                    movimento
                )
            )

        quantidade_total = (
            len(candidatos)
            + len(
                transferencias_candidatas
            )
        )

        resultado.append(
            {
                "movimento": movimento,
                "candidatos": candidatos,
                "transferencias_candidatas": (
                    transferencias_candidatas
                ),
                "quantidade_candidatos": (
                    quantidade_total
                ),
                "tem_candidato_unico": (
                    quantidade_total == 1
                ),
            }
        )

    return resultado


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

    # =========================================================
    # MOVIMENTAÇÕES COMPLETAS DA CONTA
    # =========================================================

    movimentacoes = list(
        MovimentacaoBancaria.objects
        .filter(
            conta_bancaria=conta
        )
        .select_related(
            "baixa_financeira",
            (
                "baixa_financeira__"
                "parcela"
            ),
            (
                "baixa_financeira__"
                "parcela__lancamento"
            ),
            (
                "baixa_financeira__"
                "parcela__lancamento__pessoa"
            ),
            "transferencia",
            "transferencia__conta_origem",
            "transferencia__conta_destino",
        )
        .order_by(
            "data",
            "id",
        )
    )

    # =========================================================
    # SALDO CORRENTE DO EXTRATO INTERNO
    # =========================================================

    saldo_corrente = (
        conta.saldo_inicial
        or Decimal("0.00")
    )

    total_entradas_extrato = Decimal(
        "0.00"
    )

    total_saidas_extrato = Decimal(
        "0.00"
    )

    for movimento in movimentacoes:

        if movimento.tipo == "ENTRADA":

            total_entradas_extrato += (
                movimento.valor
            )

            saldo_corrente += (
                movimento.valor
            )

        else:

            total_saidas_extrato += (
                movimento.valor
            )

            saldo_corrente -= (
                movimento.valor
            )

        movimento.saldo_apos = (
            saldo_corrente
        )

        # Campos prontos para apresentação no extrato.
        # Mantêm a regra de negócio centralizada em MovimentacaoBancaria
        # e evitam que o template precise inferir o sentido do movimento.
        movimento.valor_entrada = (
            movimento.valor
            if movimento.tipo == "ENTRADA"
            else None
        )

        movimento.valor_saida = (
            movimento.valor
            if movimento.tipo == "SAIDA"
            else None
        )

        movimento.valor_extrato = (
            movimento.valor
            if movimento.tipo == "ENTRADA"
            else -movimento.valor
        )

        movimento.historico_extrato = (
            movimento.descricao
            or ""
        )

        movimento.documento_extrato = (
            movimento.documento
            or ""
        )

        movimento.origem_extrato = (
            movimento.get_origem_display()
        )

    saldo_extrato = saldo_corrente

    # =========================================================
    # FILTROS DA TELA
    # =========================================================

    busca = (
        request.GET.get(
            "q",
            "",
        )
        .strip()
    )

    tipo = (
        request.GET.get(
            "tipo",
            "",
        )
        .strip()
    )

    origem = (
        request.GET.get(
            "origem",
            "",
        )
        .strip()
    )

    data_de_texto = (
        request.GET.get(
            "data_de",
            "",
        )
        .strip()
    )

    data_ate_texto = (
        request.GET.get(
            "data_ate",
            "",
        )
        .strip()
    )

    data_de = parse_date(
        data_de_texto
    )

    data_ate = parse_date(
        data_ate_texto
    )

    movimentacoes_filtradas = []

    for movimento in movimentacoes:

        if (
            busca
            and busca.lower()
            not in (
                (
                    movimento.descricao
                    or ""
                )
                + " "
                + (
                    movimento.documento
                    or ""
                )
            ).lower()
        ):
            continue

        if (
            tipo
            and movimento.tipo != tipo
        ):
            continue

        if (
            origem
            and movimento.origem != origem
        ):
            continue

        if (
            data_de
            and movimento.data < data_de
        ):
            continue

        if (
            data_ate
            and movimento.data > data_ate
        ):
            continue

        movimentacoes_filtradas.append(
            movimento
        )

    # Exibe mais recente primeiro,
    # mas mantém o saldo correto de cada movimento.
    movimentacoes_filtradas.reverse()

    contexto = {
        "conta": conta,

        "movimentacoes": (
            movimentacoes_filtradas
        ),

        "total_entradas_extrato": (
            total_entradas_extrato
        ),

        "total_saidas_extrato": (
            total_saidas_extrato
        ),

        "saldo_extrato": (
            saldo_extrato
        ),

        "filtro_busca": busca,
        "filtro_tipo": tipo,
        "filtro_origem": origem,

        "filtro_data_de": (
            data_de_texto
        ),

        "filtro_data_ate": (
            data_ate_texto
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

# ============================================================
# TRANSFERÊNCIAS BANCÁRIAS
# ============================================================


@login_required
@permission_required(
    "financeiro.view_transferenciabancaria",
    raise_exception=True,
)
def transferencias_bancarias(request):
    transferencias = (
        TransferenciaBancaria.objects
        .select_related(
            "conta_origem",
            "conta_origem__empresa",
            "conta_destino",
            "conta_destino__empresa",
        )
        .order_by(
            "-data",
            "-id",
        )
    )

    busca = (
        request.GET.get(
            "q",
            "",
        )
        .strip()
    )

    status = (
        request.GET.get(
            "status",
            "",
        )
        .strip()
    )

    conta_id = (
        request.GET.get(
            "conta",
            "",
        )
        .strip()
    )

    data_de_texto = (
        request.GET.get(
            "data_de",
            "",
        )
        .strip()
    )

    data_ate_texto = (
        request.GET.get(
            "data_ate",
            "",
        )
        .strip()
    )

    if busca:
        transferencias = (
            transferencias.filter(
                Q(
                    documento__icontains=busca
                )
                | Q(
                    observacoes__icontains=busca
                )
                | Q(
                    conta_origem__banco__icontains=busca
                )
                | Q(
                    conta_origem__agencia__icontains=busca
                )
                | Q(
                    conta_origem__conta__icontains=busca
                )
                | Q(
                    conta_destino__banco__icontains=busca
                )
                | Q(
                    conta_destino__agencia__icontains=busca
                )
                | Q(
                    conta_destino__conta__icontains=busca
                )
            )
        )

    if status in (
        "EFETIVADA",
        "CANCELADA",
    ):
        transferencias = (
            transferencias.filter(
                status=status
            )
        )

    if conta_id:
        transferencias = (
            transferencias.filter(
                Q(
                    conta_origem_id=conta_id
                )
                | Q(
                    conta_destino_id=conta_id
                )
            )
        )

    data_de = parse_date(
        data_de_texto
    )

    data_ate = parse_date(
        data_ate_texto
    )

    if data_de:
        transferencias = (
            transferencias.filter(
                data__gte=data_de
            )
        )

    if data_ate:
        transferencias = (
            transferencias.filter(
                data__lte=data_ate
            )
        )

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
        "transferencias": transferencias,
        "contas": contas,
        "filtro_busca": busca,
        "filtro_status": status,
        "filtro_conta": conta_id,
        "filtro_data_de": data_de_texto,
        "filtro_data_ate": data_ate_texto,
    }

    return render(
        request,
        (
            "financeiro/"
            "transferencias_bancarias.html"
        ),
        contexto,
    )


@login_required
@permission_required(
    "financeiro.add_transferenciabancaria",
    raise_exception=True,
)
def nova_transferencia_bancaria(request):
    if request.method == "POST":
        form = TransferenciaBancariaForm(
            request.POST
        )

        if form.is_valid():
            with transaction.atomic():
                transferencia = form.save(
                    commit=False
                )

                transferencia.status = (
                    "EFETIVADA"
                )

                transferencia.save()

            messages.success(
                request,
                (
                    "Transferência bancária "
                    "registrada com sucesso."
                ),
            )

            return redirect(
                (
                    "financeiro:"
                    "transferencias_bancarias"
                )
            )

    else:
        form = TransferenciaBancariaForm(
            initial={
                "data": (
                    timezone.localdate()
                ),
            }
        )

    contexto = {
        "form": form,
    }

    return render(
        request,
        (
            "financeiro/"
            "transferencia_bancaria_formulario.html"
        ),
        contexto,
    )


# ============================================================
# CONCILIAÇÃO BANCÁRIA
# ============================================================


@login_required
@permission_required(
    "financeiro.view_importacaoofx",
    raise_exception=True,
)
def conciliacao_bancaria(request):
    importacoes = (
        ImportacaoOFX.objects
        .select_related(
            "conta_bancaria",
            "conta_bancaria__empresa",
        )
        .prefetch_related(
            "movimentos"
        )
        .order_by(
            "-criado_em",
            "-id",
        )
    )

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

    busca = (
        request.GET.get(
            "q",
            "",
        )
        .strip()
    )

    conta_id = (
        request.GET.get(
            "conta",
            "",
        )
        .strip()
    )

    status = (
        request.GET.get(
            "status",
            "",
        )
        .strip()
    )

    data_de_texto = (
        request.GET.get(
            "data_de",
            "",
        )
        .strip()
    )

    data_ate_texto = (
        request.GET.get(
            "data_ate",
            "",
        )
        .strip()
    )

    if busca:
        importacoes = (
            importacoes.filter(
                Q(
                    nome_arquivo__icontains=busca
                )
                | Q(
                    conta_bancaria__banco__icontains=busca
                )
                | Q(
                    conta_bancaria__agencia__icontains=busca
                )
                | Q(
                    conta_bancaria__conta__icontains=busca
                )
                | Q(
                    conta_bancaria__empresa__razao_social__icontains=busca
                )
                | Q(
                    conta_bancaria__empresa__nome_fantasia__icontains=busca
                )
            )
        )

    if conta_id:
        importacoes = (
            importacoes.filter(
                conta_bancaria_id=conta_id
            )
        )

    if status in (
        "PROCESSANDO",
        "CONCLUIDA",
        "ERRO",
    ):
        importacoes = (
            importacoes.filter(
                status=status
            )
        )

    data_de = parse_date(
        data_de_texto
    )

    data_ate = parse_date(
        data_ate_texto
    )

    if data_de:
        importacoes = (
            importacoes.filter(
                criado_em__date__gte=data_de
            )
        )

    if data_ate:
        importacoes = (
            importacoes.filter(
                criado_em__date__lte=data_ate
            )
        )

    contexto = {
        "importacoes": importacoes,
        "contas": contas,
        "filtro_busca": busca,
        "filtro_conta": conta_id,
        "filtro_status": status,
        "filtro_data_de": data_de_texto,
        "filtro_data_ate": data_ate_texto,
    }

    return render(
        request,
        (
            "financeiro/"
            "conciliacao_bancaria.html"
        ),
        contexto,
    )


@login_required
@permission_required(
    "financeiro.add_importacaoofx",
    raise_exception=True,
)
def importar_ofx(request):
    if request.method == "POST":
        form = ImportacaoOFXForm(
            request.POST,
            request.FILES,
        )

        if form.is_valid():
            conta_bancaria = (
                form.cleaned_data[
                    "conta_bancaria"
                ]
            )

            arquivo = (
                form.cleaned_data[
                    "arquivo"
                ]
            )

            try:
                dados_ofx = ler_ofx(
                    arquivo
                )

            except ErroOFX as exc:
                form.add_error(
                    "arquivo",
                    str(exc),
                )

            except Exception:
                form.add_error(
                    "arquivo",
                    (
                        "Não foi possível processar "
                        "o arquivo OFX."
                    ),
                )

            else:
                importacao = None

                try:
                    with transaction.atomic():
                        importacao = (
                            ImportacaoOFX.objects
                            .create(
                                conta_bancaria=(
                                    conta_bancaria
                                ),
                                nome_arquivo=(
                                    arquivo.name
                                ),
                                data_inicio=(
                                    dados_ofx[
                                        "data_inicio"
                                    ]
                                ),
                                data_fim=(
                                    dados_ofx[
                                        "data_fim"
                                    ]
                                ),
                                status=(
                                    "PROCESSANDO"
                                ),
                            )
                        )

                        criados = 0
                        duplicados = 0

                        for dados_movimento in (
                            dados_ofx[
                                "movimentos"
                            ]
                        ):
                            try:
                                (
                                    movimento,
                                    criado,
                                ) = (
                                    MovimentoOFX.objects
                                    .get_or_create(
                                        conta_bancaria=(
                                            conta_bancaria
                                        ),
                                        identificador=(
                                            dados_movimento[
                                                "identificador"
                                            ]
                                        ),
                                        defaults={
                                            "importacao": (
                                                importacao
                                            ),
                                            "data": (
                                                dados_movimento[
                                                    "data"
                                                ]
                                            ),
                                            "tipo": (
                                                dados_movimento[
                                                    "tipo"
                                                ]
                                            ),
                                            "valor": (
                                                dados_movimento[
                                                    "valor"
                                                ]
                                            ),
                                            "descricao": (
                                                dados_movimento[
                                                    "descricao"
                                                ]
                                            ),
                                            "documento": (
                                                dados_movimento[
                                                    "documento"
                                                ]
                                            ),
                                            "status": (
                                                "PENDENTE"
                                            ),
                                        },
                                    )
                                )

                            except IntegrityError:
                                criado = False

                            if criado:
                                criados += 1
                            else:
                                duplicados += 1

                        importacao.status = (
                            "CONCLUIDA"
                        )

                        importacao.save(
                            update_fields=[
                                "status",
                            ]
                        )

                except Exception as exc:
                    if importacao is not None:
                        (
                            ImportacaoOFX.objects
                            .filter(
                                pk=importacao.pk
                            )
                            .update(
                                status="ERRO",
                                mensagem_erro=(
                                    str(exc)[:2000]
                                ),
                            )
                        )

                    form.add_error(
                        None,
                        (
                            "Ocorreu um erro ao "
                            "gravar a importação."
                        ),
                    )

                else:
                    if duplicados:
                        messages.warning(
                            request,
                            (
                                f"{criados} movimento(s) "
                                "importado(s) e "
                                f"{duplicados} movimento(s) "
                                "já existente(s) ignorado(s)."
                            ),
                        )

                    else:
                        messages.success(
                            request,
                            (
                                f"{criados} movimento(s) "
                                "OFX importado(s) "
                                "com sucesso."
                            ),
                        )

                    return redirect(
                        (
                            "financeiro:"
                            "detalhe_importacao_ofx"
                        ),
                        pk=importacao.pk,
                    )

    else:
        form = (
            ImportacaoOFXForm()
        )

    contexto = {
        "form": form,
    }

    return render(
        request,
        "financeiro/importar_ofx.html",
        contexto,
    )


@login_required
@permission_required(
    "financeiro.view_importacaoofx",
    raise_exception=True,
)
def detalhe_importacao_ofx(
    request,
    pk,
):
    importacao = get_object_or_404(
        ImportacaoOFX.objects
        .select_related(
            "conta_bancaria",
            "conta_bancaria__empresa",
        ),
        pk=pk,
    )

    movimentos_base = (
        importacao
        .movimentos
        .select_related(
            "baixa_conciliada",
            (
                "baixa_conciliada__"
                "parcela"
            ),
            (
                "baixa_conciliada__"
                "parcela__lancamento"
            ),
            (
                "baixa_conciliada__"
                "parcela__lancamento__pessoa"
            ),
            "transferencia_conciliada",
            (
                "transferencia_conciliada__"
                "conta_origem"
            ),
            (
                "transferencia_conciliada__"
                "conta_destino"
            ),
        )
    )

    total_entradas = sum(
        (
            movimento.valor
            for movimento
            in movimentos_base.filter(
                tipo="ENTRADA"
            )
        ),
        Decimal("0.00"),
    )

    total_saidas = sum(
        (
            movimento.valor
            for movimento
            in movimentos_base.filter(
                tipo="SAIDA"
            )
        ),
        Decimal("0.00"),
    )

    busca = (
        request.GET.get(
            "q",
            "",
        )
        .strip()
    )

    status = (
        request.GET.get(
            "status",
            "",
        )
        .strip()
    )

    tipo = (
        request.GET.get(
            "tipo",
            "",
        )
        .strip()
    )

    data_de_texto = (
        request.GET.get(
            "data_de",
            "",
        )
        .strip()
    )

    data_ate_texto = (
        request.GET.get(
            "data_ate",
            "",
        )
        .strip()
    )

    movimentos = movimentos_base

    if busca:
        movimentos = (
            movimentos.filter(
                Q(
                    descricao__icontains=busca
                )
                | Q(
                    documento__icontains=busca
                )
                | Q(
                    identificador__icontains=busca
                )
                | Q(
                    baixa_conciliada__parcela__lancamento__descricao__icontains=busca
                )
                | Q(
                    baixa_conciliada__parcela__lancamento__numero_documento__icontains=busca
                )
                | Q(
                    baixa_conciliada__parcela__lancamento__pessoa__razao_social__icontains=busca
                )
            )
        )

    if status in (
        "PENDENTE",
        "CONCILIADO",
        "IGNORADO",
    ):
        movimentos = (
            movimentos.filter(
                status=status
            )
        )

    if tipo in (
        "ENTRADA",
        "SAIDA",
    ):
        movimentos = (
            movimentos.filter(
                tipo=tipo
            )
        )

    data_de = parse_date(
        data_de_texto
    )

    data_ate = parse_date(
        data_ate_texto
    )

    if data_de:
        movimentos = (
            movimentos.filter(
                data__gte=data_de
            )
        )

    if data_ate:
        movimentos = (
            movimentos.filter(
                data__lte=data_ate
            )
        )

    movimentos = (
        movimentos.order_by(
            "data",
            "id",
        )
    )

    total_filtrados = (
        movimentos.count()
    )

    movimentos_tela = (
        preparar_movimentos_para_tela(
            movimentos
        )
    )

    contexto = {
        "importacao": importacao,
        "movimentos_tela": movimentos_tela,
        "total_entradas": total_entradas,
        "total_saidas": total_saidas,
        "total_filtrados": total_filtrados,
        "filtro_busca": busca,
        "filtro_status": status,
        "filtro_tipo": tipo,
        "filtro_data_de": data_de_texto,
        "filtro_data_ate": data_ate_texto,
    }

    return render(
        request,
        (
            "financeiro/"
            "importacao_ofx_detalhe.html"
        ),
        contexto,
    )


@login_required
@permission_required(
    "financeiro.change_movimentoofx",
    raise_exception=True,
)
def conciliar_movimento_ofx(
    request,
    pk,
    baixa_pk,
):
    movimento = get_object_or_404(
        MovimentoOFX.objects
        .select_related(
            "importacao",
            "conta_bancaria",
        ),
        pk=pk,
    )

    baixa = get_object_or_404(
        BaixaFinanceira.objects
        .select_related(
            "parcela",
            "parcela__lancamento",
        ),
        pk=baixa_pk,
    )

    if request.method != "POST":
        return redirect(
            (
                "financeiro:"
                "detalhe_importacao_ofx"
            ),
            pk=movimento.importacao_id,
        )

    tipo_esperado = (
        tipo_lancamento_para_movimento(
            baixa.parcela.lancamento.tipo
        )
    )

    if (
        baixa.conta_bancaria_id
        != movimento.conta_bancaria_id
    ):
        messages.error(
            request,
            (
                "A baixa pertence a outra "
                "conta bancária."
            ),
        )

    elif (
        tipo_esperado
        != movimento.tipo
    ):
        messages.error(
            request,
            (
                "O sentido da baixa não "
                "corresponde ao movimento "
                "do extrato."
            ),
        )

    elif (
        baixa.valor_movimento
        != movimento.valor
    ):
        messages.error(
            request,
            (
                "O valor da baixa não "
                "corresponde ao movimento "
                "do extrato."
            ),
        )

    elif baixa_ja_conciliada(
        baixa,
        ignorar_movimento_id=(
            movimento.pk
        ),
    ):
        messages.error(
            request,
            (
                "Esta baixa já foi conciliada "
                "com outro movimento bancário."
            ),
        )

    else:
        with transaction.atomic():
            movimento.baixa_conciliada = (
                baixa
            )

            movimento.status = (
                "CONCILIADO"
            )

            movimento.save(
                update_fields=[
                    "baixa_conciliada",
                    "status",
                    "atualizado_em",
                ]
            )

        messages.success(
            request,
            (
                "Movimento conciliado "
                "com sucesso."
            ),
        )

    return redirect(
        (
            "financeiro:"
            "detalhe_importacao_ofx"
        ),
        pk=movimento.importacao_id,
    )


@login_required
@permission_required(
    "financeiro.change_movimentoofx",
    raise_exception=True,
)
def conciliar_transferencia_movimento_ofx(
    request,
    pk,
    transferencia_pk,
):
    movimento = get_object_or_404(
        MovimentoOFX.objects
        .select_related(
            "importacao",
            "conta_bancaria",
        ),
        pk=pk,
    )

    transferencia = get_object_or_404(
        TransferenciaBancaria.objects
        .select_related(
            "conta_origem",
            "conta_destino",
        ),
        pk=transferencia_pk,
        status="EFETIVADA",
    )

    if request.method != "POST":
        return redirect(
            (
                "financeiro:"
                "detalhe_importacao_ofx"
            ),
            pk=movimento.importacao_id,
        )

    if movimento.status != "PENDENTE":
        messages.error(
            request,
            (
                "Este movimento não está "
                "mais pendente."
            ),
        )

    elif (
        transferencia.valor
        != movimento.valor
    ):
        messages.error(
            request,
            (
                "O valor da transferência "
                "não corresponde ao movimento "
                "do extrato."
            ),
        )

    elif (
        transferencia.data
        != movimento.data
    ):
        messages.error(
            request,
            (
                "A data da transferência "
                "não corresponde ao movimento "
                "do extrato."
            ),
        )

    elif (
        movimento.tipo == "SAIDA"
        and transferencia.conta_origem_id
        != movimento.conta_bancaria_id
    ):
        messages.error(
            request,
            (
                "Esta transferência não "
                "corresponde à saída desta "
                "conta bancária."
            ),
        )

    elif (
        movimento.tipo == "ENTRADA"
        and transferencia.conta_destino_id
        != movimento.conta_bancaria_id
    ):
        messages.error(
            request,
            (
                "Esta transferência não "
                "corresponde à entrada desta "
                "conta bancária."
            ),
        )

    elif transferencia_ja_conciliada(
        transferencia,
        movimento.conta_bancaria,
        ignorar_movimento_id=(
            movimento.pk
        ),
    ):
        messages.error(
            request,
            (
                "Esta transferência já foi "
                "conciliada com outro movimento "
                "OFX desta conta."
            ),
        )

    else:
        with transaction.atomic():
            movimento.baixa_conciliada = (
                None
            )

            movimento.transferencia_conciliada = (
                transferencia
            )

            movimento.status = (
                "CONCILIADO"
            )

            movimento.full_clean()

            movimento.save(
                update_fields=[
                    "baixa_conciliada",
                    "transferencia_conciliada",
                    "status",
                    "atualizado_em",
                ]
            )

        messages.success(
            request,
            (
                "Transferência conciliada "
                "com o movimento bancário "
                "com sucesso."
            ),
        )

    return redirect(
        (
            "financeiro:"
            "detalhe_importacao_ofx"
        ),
        pk=movimento.importacao_id,
    )


@login_required
@permission_required(
    "financeiro.change_movimentoofx",
    raise_exception=True,
)
def ignorar_movimento_ofx(
    request,
    pk,
):
    movimento = get_object_or_404(
        MovimentoOFX.objects
        .select_related(
            "importacao"
        ),
        pk=pk,
    )

    if request.method == "POST":
        movimento.status = (
            "IGNORADO"
        )

        movimento.baixa_conciliada = (
            None
        )

        movimento.transferencia_conciliada = (
            None
        )

        movimento.save(
            update_fields=[
                "status",
                "baixa_conciliada",
                "transferencia_conciliada",
                "atualizado_em",
            ]
        )

        messages.success(
            request,
            (
                "Movimento marcado "
                "como ignorado."
            ),
        )

    return redirect(
        (
            "financeiro:"
            "detalhe_importacao_ofx"
        ),
        pk=movimento.importacao_id,
    )


@login_required
@permission_required(
    "financeiro.change_movimentoofx",
    raise_exception=True,
)
def reabrir_movimento_ofx(
    request,
    pk,
):
    movimento = get_object_or_404(
        MovimentoOFX.objects
        .select_related(
            "importacao"
        ),
        pk=pk,
    )

    if request.method == "POST":
        movimento.status = (
            "PENDENTE"
        )

        movimento.baixa_conciliada = (
            None
        )

        movimento.transferencia_conciliada = (
            None
        )

        movimento.save(
            update_fields=[
                "status",
                "baixa_conciliada",
                "transferencia_conciliada",
                "atualizado_em",
            ]
        )

        messages.success(
            request,
            (
                "Movimento reaberto "
                "para conciliação."
            ),
        )

    return redirect(
        (
            "financeiro:"
            "detalhe_importacao_ofx"
        ),
        pk=movimento.importacao_id,
    )

# ============================================================
# CONCILIAÇÃO - BUSCA E CRIAÇÃO A PARTIR DO OFX
# ============================================================


def tipo_movimento_para_lancamento(
    tipo_movimento,
):
    if tipo_movimento == "ENTRADA":
        return "RECEBER"

    return "PAGAR"


@login_required
@permission_required(
    "financeiro.view_movimentoofx",
    raise_exception=True,
)
def buscar_movimento_ofx(
    request,
    pk,
):
    movimento = get_object_or_404(
        MovimentoOFX.objects
        .select_related(
            "importacao",
            "conta_bancaria",
            "conta_bancaria__empresa",
        ),
        pk=pk,
    )

    if movimento.status != "PENDENTE":
        messages.info(
            request,
            (
                "Somente movimentos pendentes "
                "podem ser pesquisados."
            ),
        )

        return redirect(
            "financeiro:detalhe_importacao_ofx",
            pk=movimento.importacao_id,
        )

    tipo_lancamento = (
        tipo_movimento_para_lancamento(
            movimento.tipo
        )
    )

    data_inicial = (
        movimento.data
        - timedelta(days=30)
    )

    data_final = (
        movimento.data
        + timedelta(days=30)
    )

    # --------------------------------------------------------
    # BAIXAS JÁ EXISTENTES
    # --------------------------------------------------------

    baixas_possiveis = (
        BaixaFinanceira.objects
        .filter(
            conta_bancaria=(
                movimento.conta_bancaria
            ),
            parcela__lancamento__tipo=(
                tipo_lancamento
            ),
            data__range=(
                data_inicial,
                data_final,
            ),
        )
        .select_related(
            "parcela",
            "parcela__lancamento",
            "parcela__lancamento__pessoa",
        )
        .order_by(
            "-data",
            "-id",
        )
    )

    baixas_compativeis = []

    for baixa in baixas_possiveis:
        if (
            baixa.valor_movimento
            != movimento.valor
        ):
            continue

        if baixa_ja_conciliada(
            baixa,
            ignorar_movimento_id=(
                movimento.pk
            ),
        ):
            continue

        baixas_compativeis.append(
            baixa
        )

    # --------------------------------------------------------
    # PARCELAS QUE AINDA NÃO POSSUEM A BAIXA
    # --------------------------------------------------------

    parcelas_possiveis = (
        ParcelaFinanceira.objects
        .filter(
            lancamento__empresa=(
                movimento
                .conta_bancaria
                .empresa
            ),
            lancamento__tipo=(
                tipo_lancamento
            ),
            status__in=[
                "ABERTA",
                "PARCIAL",
            ],
        )
        .select_related(
            "lancamento",
            "lancamento__pessoa",
            "lancamento__plano_conta",
        )
        .order_by(
            "vencimento",
            "numero",
        )
    )

    parcelas_compativeis = []

    for parcela in parcelas_possiveis:
        if (
            parcela.saldo
            == movimento.valor
        ):
            parcelas_compativeis.append(
                parcela
            )

        if (
            len(parcelas_compativeis)
            >= 100
        ):
            break

    transferencias_compativeis = (
        encontrar_transferencias_movimento(
            movimento
        )
    )

    contexto = {
        "movimento": movimento,
        "tipo_lancamento": (
            tipo_lancamento
        ),
        "baixas_compativeis": (
            baixas_compativeis
        ),
        "transferencias_compativeis": (
            transferencias_compativeis
        ),
        "parcelas_compativeis": (
            parcelas_compativeis
        ),
    }

    return render(
        request,
        (
            "financeiro/"
            "buscar_movimento_ofx.html"
        ),
        contexto,
    )


@login_required
@permission_required(
    (
        "financeiro.add_baixafinanceira",
        "financeiro.change_movimentoofx",
    ),
    raise_exception=True,
)
def baixar_parcela_movimento_ofx(
    request,
    pk,
    parcela_pk,
):
    movimento = get_object_or_404(
        MovimentoOFX.objects
        .select_related(
            "importacao",
            "conta_bancaria",
            "conta_bancaria__empresa",
        ),
        pk=pk,
    )

    parcela = get_object_or_404(
        ParcelaFinanceira.objects
        .select_related(
            "lancamento",
            "lancamento__empresa",
            "lancamento__pessoa",
        ),
        pk=parcela_pk,
    )

    if request.method != "POST":
        return redirect(
            "financeiro:buscar_movimento_ofx",
            pk=movimento.pk,
        )

    if movimento.status != "PENDENTE":
        messages.error(
            request,
            "Este movimento não está mais pendente."
        )

        return redirect(
            "financeiro:detalhe_importacao_ofx",
            pk=movimento.importacao_id,
        )

    tipo_esperado = (
        tipo_movimento_para_lancamento(
            movimento.tipo
        )
    )

    if (
        parcela.lancamento.tipo
        != tipo_esperado
    ):
        messages.error(
            request,
            (
                "O tipo do lançamento não "
                "corresponde ao movimento bancário."
            ),
        )

    elif (
        parcela.lancamento.empresa_id
        != movimento.conta_bancaria.empresa_id
    ):
        messages.error(
            request,
            (
                "O lançamento pertence "
                "a outra empresa."
            ),
        )

    elif (
        parcela.status
        not in (
            "ABERTA",
            "PARCIAL",
        )
    ):
        messages.error(
            request,
            (
                "Esta parcela não está "
                "disponível para baixa."
            ),
        )

    elif (
        parcela.saldo
        != movimento.valor
    ):
        messages.error(
            request,
            (
                "O saldo da parcela não "
                "corresponde ao valor do extrato."
            ),
        )

    else:
        with transaction.atomic():
            baixa = BaixaFinanceira(
                parcela=parcela,
                conta_bancaria=(
                    movimento.conta_bancaria
                ),
                data=movimento.data,
                valor=movimento.valor,
                juros=Decimal("0.00"),
                multa=Decimal("0.00"),
                desconto=Decimal("0.00"),
                observacoes=(
                    "Baixa criada pela "
                    "conciliação bancária OFX. "
                    f"FITID: {movimento.identificador}"
                ),
            )

            baixa.save()

            movimento.baixa_conciliada = (
                baixa
            )

            movimento.status = (
                "CONCILIADO"
            )

            movimento.save(
                update_fields=[
                    "baixa_conciliada",
                    "status",
                    "atualizado_em",
                ]
            )

        messages.success(
            request,
            (
                "Baixa registrada e movimento "
                "conciliado com sucesso."
            ),
        )

        return redirect(
            "financeiro:detalhe_importacao_ofx",
            pk=movimento.importacao_id,
        )

    return redirect(
        "financeiro:buscar_movimento_ofx",
        pk=movimento.pk,
    )


@login_required
@permission_required(
    (
        "financeiro.add_lancamentofinanceiro",
        "financeiro.add_baixafinanceira",
        "financeiro.change_movimentoofx",
    ),
    raise_exception=True,
)
def criar_lancamento_movimento_ofx(
    request,
    pk,
):
    movimento = get_object_or_404(
        MovimentoOFX.objects
        .select_related(
            "importacao",
            "conta_bancaria",
            "conta_bancaria__empresa",
        ),
        pk=pk,
    )

    if movimento.status != "PENDENTE":
        messages.info(
            request,
            (
                "Este movimento já foi "
                "tratado na conciliação."
            ),
        )

        return redirect(
            "financeiro:detalhe_importacao_ofx",
            pk=movimento.importacao_id,
        )

    tipo_lancamento = (
        tipo_movimento_para_lancamento(
            movimento.tipo
        )
    )

    if request.method == "POST":
        form = CriarLancamentoOFXForm(
            request.POST,
            tipo=tipo_lancamento,
        )

        if form.is_valid():
            with transaction.atomic():
                lancamento = form.save(
                    commit=False
                )

                lancamento.empresa = (
                    movimento
                    .conta_bancaria
                    .empresa
                )

                lancamento.tipo = (
                    tipo_lancamento
                )

                lancamento.origem = (
                    "CONCILIACAO"
                )

                lancamento.data_emissao = (
                    movimento.data
                )

                lancamento.data_competencia = (
                    movimento.data
                )

                lancamento.valor_total = (
                    movimento.valor
                )

                lancamento.status = (
                    "ABERTO"
                )

                lancamento.full_clean()

                lancamento.save()

                parcela = ParcelaFinanceira(
                    lancamento=lancamento,
                    numero=1,
                    vencimento=(
                        movimento.data
                    ),
                    valor=(
                        movimento.valor
                    ),
                    status="ABERTA",
                )

                parcela.full_clean()

                parcela.save()

                baixa = BaixaFinanceira(
                    parcela=parcela,
                    conta_bancaria=(
                        movimento
                        .conta_bancaria
                    ),
                    data=movimento.data,
                    valor=movimento.valor,
                    juros=Decimal("0.00"),
                    multa=Decimal("0.00"),
                    desconto=Decimal("0.00"),
                    observacoes=(
                        "Lançamento e baixa "
                        "criados pela conciliação "
                        "bancária OFX. "
                        f"FITID: {movimento.identificador}"
                    ),
                )

                baixa.save()

                movimento.baixa_conciliada = (
                    baixa
                )

                movimento.status = (
                    "CONCILIADO"
                )

                movimento.save(
                    update_fields=[
                        "baixa_conciliada",
                        "status",
                        "atualizado_em",
                    ]
                )

            if (
                tipo_lancamento
                == "PAGAR"
            ):
                mensagem = (
                    "Conta a pagar criada, "
                    "baixada e conciliada "
                    "com sucesso."
                )
            else:
                mensagem = (
                    "Conta a receber criada, "
                    "recebida e conciliada "
                    "com sucesso."
                )

            messages.success(
                request,
                mensagem,
            )

            return redirect(
                "financeiro:detalhe_importacao_ofx",
                pk=movimento.importacao_id,
            )

    else:
        form = CriarLancamentoOFXForm(
            tipo=tipo_lancamento,
            initial={
                "descricao": (
                    movimento
                    .descricao[:250]
                ),
                "numero_documento": (
                    movimento
                    .documento[:50]
                ),
            },
        )

    contexto = {
        "form": form,
        "movimento": movimento,
        "tipo_lancamento": (
            tipo_lancamento
        ),
    }

    return render(
        request,
        (
            "financeiro/"
            "criar_lancamento_ofx.html"
        ),
        contexto,
    )