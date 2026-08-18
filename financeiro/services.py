from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Prefetch
from django.db.models.functions import Coalesce

from .models import (
    BaixaFinanceira,
    PlanoConta,
    RateioCentroCusto,
)


CENTAVO = Decimal("0.01")
ZERO = Decimal("0.00")


def moeda(valor):
    return Decimal(valor or ZERO).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def distribuir_valor_rateios(valor, rateios):
    """Distribui um valor entre rateios e fecha centavos deterministicamente."""
    rateios = list(rateios)
    if not rateios:
        return {}

    total_rateado = sum((rateio.valor for rateio in rateios), ZERO)
    if total_rateado <= ZERO:
        return {rateio.pk: ZERO for rateio in rateios}

    valor = moeda(valor)
    distribuicao = {
        rateio.pk: moeda(valor * rateio.valor / total_rateado)
        for rateio in rateios
    }
    diferenca = valor - sum(distribuicao.values(), ZERO)

    if diferenca:
        destino = sorted(
            rateios,
            key=lambda rateio: (-rateio.valor, rateio.pk),
        )[0]
        distribuicao[destino.pk] += diferenca

    return distribuicao


def _contas_hierarquicas(valores_por_conta):
    contas = list(
        PlanoConta.objects.filter(
            tipo__in=("RECEITA", "CUSTO", "DESPESA")
        ).select_related("conta_pai").order_by("codigo")
    )
    por_id = {conta.pk: conta for conta in contas}
    totais = defaultdict(lambda: ZERO)

    for conta_id, valor in valores_por_conta.items():
        atual = por_id.get(conta_id)
        visitadas = set()
        while atual and atual.pk not in visitadas:
            totais[atual.pk] += valor
            visitadas.add(atual.pk)
            atual = por_id.get(atual.conta_pai_id)

    relevantes = {conta_id for conta_id, valor in totais.items() if valor}
    grupos = []
    nomes = {
        "RECEITA": "Receitas",
        "CUSTO": "Custos",
        "DESPESA": "Despesas",
    }

    for tipo in ("RECEITA", "CUSTO", "DESPESA"):
        linhas = []
        for conta in contas:
            if conta.tipo != tipo or conta.pk not in relevantes:
                continue
            nivel = 0
            pai = conta.conta_pai
            visitadas = set()
            while pai and pai.pk not in visitadas:
                nivel += 1
                visitadas.add(pai.pk)
                pai = pai.conta_pai
            linhas.append({
                "conta": conta,
                "nivel": min(nivel, 5),
                "valor": moeda(totais[conta.pk]),
                "direto": moeda(valores_por_conta.get(conta.pk, ZERO)),
            })
        grupos.append({"tipo": tipo, "nome": nomes[tipo], "linhas": linhas})

    return grupos


def calcular_relatorio_obra(obra, data_inicial, data_final):
    rateios = list(
        RateioCentroCusto.objects.filter(
            centro_custo=obra,
            lancamento__empresa=obra.empresa,
        )
        .exclude(lancamento__status="CANCELADO")
        .annotate(
            data_referencia=Coalesce(
                "lancamento__data_competencia",
                "lancamento__data_emissao",
            )
        )
        .filter(data_referencia__range=(data_inicial, data_final))
        .select_related("lancamento__plano_conta", "lancamento__pessoa")
        .prefetch_related(
            "lancamento__parcelas__baixas",
            "lancamento__rateios_centro_custo",
        )
        .order_by("-data_referencia", "-lancamento_id")
    )

    receitas = ZERO
    custos = ZERO
    despesas = ZERO
    valores_por_conta = defaultdict(lambda: ZERO)
    rateio_por_lancamento = {}
    lancamentos_por_id = {}

    for rateio in rateios:
        lancamento = rateio.lancamento
        valor = moeda(rateio.valor)
        valores_por_conta[lancamento.plano_conta_id] += valor
        rateio_por_lancamento[lancamento.pk] = rateio
        lancamentos_por_id[lancamento.pk] = lancamento

        if lancamento.plano_conta.tipo == "RECEITA":
            receitas += valor
        elif lancamento.plano_conta.tipo == "CUSTO":
            custos += valor
        elif lancamento.plano_conta.tipo == "DESPESA":
            despesas += valor

    resultado_bruto = receitas - custos
    resultado_obra = resultado_bruto - despesas
    margem = (resultado_obra * Decimal("100") / receitas) if receitas else None

    recebido = ZERO
    pago = ZERO
    caixa_por_lancamento = defaultdict(lambda: ZERO)
    lancamentos_com_obra = RateioCentroCusto.objects.filter(
        centro_custo=obra,
        lancamento__empresa=obra.empresa,
    ).exclude(lancamento__status="CANCELADO").values_list(
        "lancamento_id", flat=True
    )
    todos_rateios = RateioCentroCusto.objects.order_by("id")
    baixas = (
        BaixaFinanceira.objects.filter(
            parcela__lancamento_id__in=lancamentos_com_obra,
            data__range=(data_inicial, data_final),
        )
        .select_related("parcela__lancamento")
        .prefetch_related(
            Prefetch(
                "parcela__lancamento__rateios_centro_custo",
                queryset=todos_rateios,
                to_attr="rateios_relatorio",
            )
        )
        .order_by("data", "id")
    )

    for baixa in baixas:
        lancamento = baixa.parcela.lancamento
        rateios_lancamento = lancamento.rateios_relatorio
        rateio_obra = next(
            (item for item in rateios_lancamento if item.centro_custo_id == obra.pk),
            None,
        )
        if not rateio_obra:
            continue
        distribuicao = distribuir_valor_rateios(
            baixa.valor_movimento,
            rateios_lancamento,
        )
        valor_obra = distribuicao[rateio_obra.pk]
        caixa_por_lancamento[lancamento.pk] += valor_obra
        if lancamento.tipo == "RECEBER":
            recebido += valor_obra
        else:
            pago += valor_obra

    a_receber = ZERO
    a_pagar = ZERO
    detalhes = []
    competencia_mensal = defaultdict(
        lambda: {"receitas": ZERO, "custos_despesas": ZERO}
    )

    for rateio in rateios:
        lancamento = rateio.lancamento
        total_baixado = sum(
            (
                sum(
                    (baixa.valor for baixa in parcela.baixas.all()),
                    ZERO,
                )
                for parcela in lancamento.parcelas.all()
            ),
            ZERO,
        )
        saldo = max(lancamento.valor_total - total_baixado, ZERO)
        rateios_lancamento = list(lancamento.rateios_centro_custo.all())
        saldo_distribuido = distribuir_valor_rateios(saldo, rateios_lancamento)
        saldo_obra = saldo_distribuido.get(rateio.pk, ZERO)

        if lancamento.tipo == "RECEBER":
            a_receber += saldo_obra
        else:
            a_pagar += saldo_obra

        mes = rateio.data_referencia.replace(day=1)
        if lancamento.plano_conta.tipo == "RECEITA":
            competencia_mensal[mes]["receitas"] += rateio.valor
        else:
            competencia_mensal[mes]["custos_despesas"] += rateio.valor

        detalhes.append({
            "lancamento": lancamento,
            "data_referencia": rateio.data_referencia,
            "valor_rateado": moeda(rateio.valor),
            "movimento_periodo": moeda(caixa_por_lancamento[lancamento.pk]),
            "saldo": moeda(saldo_obra),
        })

    meses = []
    atual = data_inicial.replace(day=1)
    ultimo = data_final.replace(day=1)
    while atual <= ultimo:
        valores = competencia_mensal[atual]
        receitas_mes = moeda(valores["receitas"])
        saidas_mes = moeda(valores["custos_despesas"])
        meses.append({
            "rotulo": atual.strftime("%m/%Y"),
            "receitas": float(receitas_mes),
            "custos_despesas": float(saidas_mes),
            "resultado": float(receitas_mes - saidas_mes),
        })
        atual = (atual.replace(day=28) + timedelta(days=4)).replace(day=1)

    return {
        "receitas": moeda(receitas),
        "custos": moeda(custos),
        "resultado_bruto": moeda(resultado_bruto),
        "despesas": moeda(despesas),
        "resultado_obra": moeda(resultado_obra),
        "margem": moeda(margem) if margem is not None else None,
        "recebido": moeda(recebido),
        "pago": moeda(pago),
        "resultado_caixa": moeda(recebido - pago),
        "a_receber": moeda(a_receber),
        "a_pagar": moeda(a_pagar),
        "grupos_contas": _contas_hierarquicas(valores_por_conta),
        "detalhes": detalhes,
        "grafico_mensal": meses,
    }
