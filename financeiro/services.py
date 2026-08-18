from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Prefetch, Sum
from django.db.models.functions import Coalesce

from .models import (
    BaixaFinanceira,
    LancamentoFinanceiro,
    PlanoConta,
    RateioCentroCusto,
)


CENTAVO = Decimal("0.01")
ZERO = Decimal("0.00")

DRE_SECOES = (
    ("receitas_operacionais", "Receitas Operacionais"),
    ("custos", "(-) Custos"),
    ("despesas_operacionais", "(-) Despesas Operacionais"),
    ("receitas_financeiras", "(+) Receitas Financeiras"),
    ("despesas_financeiras", "(-) Despesas Financeiras"),
)


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


def _mapa_contas_dre():
    contas = list(
        PlanoConta.objects.filter(
            tipo__in=("RECEITA", "CUSTO", "DESPESA")
        ).select_related("conta_pai").order_by("codigo")
    )
    return contas, {conta.pk: conta for conta in contas}


def ids_descendentes_conta(conta, contas=None):
    contas = contas or list(PlanoConta.objects.all())
    filhos = defaultdict(list)
    for item in contas:
        filhos[item.conta_pai_id].append(item.pk)
    encontrados = set()
    pendentes = [conta.pk]
    while pendentes:
        conta_id = pendentes.pop()
        if conta_id in encontrados:
            continue
        encontrados.add(conta_id)
        pendentes.extend(filhos[conta_id])
    return encontrados


def _secao_conta_dre(conta, por_id, receitas_financeiras_id, despesas_financeiras_id):
    ancestrais = set()
    atual = conta
    while atual and atual.pk not in ancestrais:
        ancestrais.add(atual.pk)
        atual = por_id.get(atual.conta_pai_id)

    if conta.tipo == "RECEITA":
        if receitas_financeiras_id in ancestrais:
            return "receitas_financeiras"
        return "receitas_operacionais"
    if conta.tipo == "CUSTO":
        return "custos"
    if despesas_financeiras_id in ancestrais:
        return "despesas_financeiras"
    return "despesas_operacionais"


def _periodo_comparativo(data_inicial, data_final, tipo):
    if tipo == "ANTERIOR":
        duracao = (data_final - data_inicial).days + 1
        fim = data_inicial - timedelta(days=1)
        return fim - timedelta(days=duracao - 1), fim
    if tipo == "ANO_ANTERIOR":
        def ano_anterior(valor):
            try:
                return valor.replace(year=valor.year - 1)
            except ValueError:
                return date(valor.year - 1, 2, 28)
        return ano_anterior(data_inicial), ano_anterior(data_final)
    return None


def _valores_dre(
    empresa,
    data_inicial,
    data_final,
    obra=None,
    conta_filtro=None,
    usar_fallback=True,
    contas=None,
):
    contas = contas or list(PlanoConta.objects.all())
    ids_contas = None
    if conta_filtro:
        ids_contas = ids_descendentes_conta(conta_filtro, contas)

    if obra:
        queryset = RateioCentroCusto.objects.filter(
            centro_custo=obra,
            lancamento__empresa=empresa,
            lancamento__plano_conta__aceita_lancamento=True,
            lancamento__plano_conta__tipo__in=("RECEITA", "CUSTO", "DESPESA"),
        ).exclude(lancamento__status="CANCELADO")
        prefixo = "lancamento__"
        campo_valor = "valor"
        campo_conta = "lancamento__plano_conta_id"
    else:
        queryset = LancamentoFinanceiro.objects.filter(
            empresa=empresa,
            plano_conta__aceita_lancamento=True,
            plano_conta__tipo__in=("RECEITA", "CUSTO", "DESPESA"),
        ).exclude(status="CANCELADO")
        prefixo = ""
        campo_valor = "valor_total"
        campo_conta = "plano_conta_id"

    if ids_contas is not None:
        queryset = queryset.filter(**{f"{prefixo}plano_conta_id__in": ids_contas})

    campo_competencia = f"{prefixo}data_competencia"
    campo_emissao = f"{prefixo}data_emissao"
    if usar_fallback:
        queryset = queryset.annotate(
            data_referencia=Coalesce(campo_competencia, campo_emissao)
        ).filter(data_referencia__range=(data_inicial, data_final))
        fallback = queryset.filter(**{f"{campo_competencia}__isnull": True}).count()
    else:
        queryset = queryset.filter(
            **{f"{campo_competencia}__range": (data_inicial, data_final)}
        )
        fallback = 0

    agregados = queryset.values(campo_conta).annotate(total=Sum(campo_valor))
    valores = {
        item[campo_conta]: moeda(item["total"])
        for item in agregados
    }
    return valores, fallback


def _linhas_dre(valores, comparativos, contas, por_id):
    receitas_financeiras = next(
        (conta for conta in contas if conta.codigo == "4.02"), None
    )
    despesas_financeiras = next(
        (conta for conta in contas if conta.codigo == "6.09"), None
    )
    totais_diretos = defaultdict(lambda: ZERO)
    comparativos_diretos = defaultdict(lambda: ZERO)
    secoes_por_conta = {}

    for conta_id in set(valores) | set(comparativos):
        conta = por_id.get(conta_id)
        if not conta or not conta.aceita_lancamento:
            continue
        secao = _secao_conta_dre(
            conta,
            por_id,
            receitas_financeiras.pk if receitas_financeiras else None,
            despesas_financeiras.pk if despesas_financeiras else None,
        )
        sinal = Decimal("-1") if conta.conta_redutora else Decimal("1")
        totais_diretos[conta_id] += valores.get(conta_id, ZERO) * sinal
        comparativos_diretos[conta_id] += comparativos.get(conta_id, ZERO) * sinal
        secoes_por_conta[conta_id] = secao

    secoes = []
    totais_secoes = defaultdict(lambda: ZERO)
    comparativos_secoes = defaultdict(lambda: ZERO)
    raizes = {"4", "5", "6"}

    for codigo_secao, nome_secao in DRE_SECOES:
        acumulado = defaultdict(lambda: ZERO)
        acumulado_comparativo = defaultdict(lambda: ZERO)
        for conta_id, secao in secoes_por_conta.items():
            if secao != codigo_secao:
                continue
            atual = por_id.get(conta_id)
            visitadas = set()
            while atual and atual.pk not in visitadas:
                acumulado[atual.pk] += totais_diretos[conta_id]
                acumulado_comparativo[atual.pk] += comparativos_diretos[conta_id]
                visitadas.add(atual.pk)
                atual = por_id.get(atual.conta_pai_id)

        linhas = []
        for conta in contas:
            if conta.codigo in raizes or conta.pk not in acumulado:
                continue
            atual = conta
            pertence = False
            while atual:
                if secoes_por_conta.get(atual.pk) == codigo_secao:
                    pertence = True
                    break
                atual = por_id.get(atual.conta_pai_id)
            if not pertence:
                descendentes_analiticos = [
                    conta_id for conta_id, secao in secoes_por_conta.items()
                    if secao == codigo_secao
                ]
                pertence = bool(descendentes_analiticos and conta.pk in acumulado)
            if not pertence:
                continue
            nivel = 0
            pai = por_id.get(conta.conta_pai_id)
            while pai and pai.codigo not in raizes:
                nivel += 1
                pai = por_id.get(pai.conta_pai_id)
            atual_valor = moeda(acumulado[conta.pk])
            anterior_valor = moeda(acumulado_comparativo[conta.pk])
            variacao = atual_valor - anterior_valor
            percentual = (
                moeda(variacao * Decimal("100") / abs(anterior_valor))
                if anterior_valor else None
            )
            linhas.append({
                "conta": conta,
                "nivel": min(nivel, 5),
                "valor": atual_valor,
                "comparativo": anterior_valor,
                "variacao": moeda(variacao),
                "variacao_percentual": percentual,
                "analitica": conta.aceita_lancamento,
            })

        total = sum(
            (valor for conta_id, valor in totais_diretos.items()
             if secoes_por_conta.get(conta_id) == codigo_secao),
            ZERO,
        )
        total_comparativo = sum(
            (valor for conta_id, valor in comparativos_diretos.items()
             if secoes_por_conta.get(conta_id) == codigo_secao),
            ZERO,
        )
        totais_secoes[codigo_secao] = moeda(total)
        comparativos_secoes[codigo_secao] = moeda(total_comparativo)
        secoes.append({
            "codigo": codigo_secao,
            "nome": nome_secao,
            "linhas": linhas,
            "total": moeda(total),
            "total_comparativo": moeda(total_comparativo),
        })

    return secoes, totais_secoes, comparativos_secoes


def _resumo_dre(totais):
    receitas = totais["receitas_operacionais"]
    custos = totais["custos"]
    despesas = totais["despesas_operacionais"]
    receitas_financeiras = totais["receitas_financeiras"]
    despesas_financeiras = totais["despesas_financeiras"]
    bruto = receitas - custos
    operacional = bruto - despesas
    financeiro = receitas_financeiras - despesas_financeiras
    periodo = operacional + financeiro

    def margem(valor):
        return moeda(valor * Decimal("100") / receitas) if receitas else None

    return {
        "receitas_operacionais": moeda(receitas),
        "custos": moeda(custos),
        "resultado_bruto": moeda(bruto),
        "despesas_operacionais": moeda(despesas),
        "resultado_operacional": moeda(operacional),
        "receitas_financeiras": moeda(receitas_financeiras),
        "despesas_financeiras": moeda(despesas_financeiras),
        "resultado_financeiro": moeda(financeiro),
        "resultado_periodo": moeda(periodo),
        "margem_bruta": margem(bruto),
        "margem_operacional": margem(operacional),
        "margem_periodo": margem(periodo),
    }


def calcular_dre(
    empresa,
    data_inicial,
    data_final,
    obra=None,
    conta_filtro=None,
    usar_fallback=True,
    comparacao="NENHUMA",
):
    contas, por_id = _mapa_contas_dre()
    valores, fallback = _valores_dre(
        empresa, data_inicial, data_final, obra, conta_filtro,
        usar_fallback, contas,
    )
    periodo_comparativo = _periodo_comparativo(
        data_inicial, data_final, comparacao
    )
    valores_comparativos = {}
    fallback_comparativo = 0
    if periodo_comparativo:
        valores_comparativos, fallback_comparativo = _valores_dre(
            empresa,
            periodo_comparativo[0],
            periodo_comparativo[1],
            obra,
            conta_filtro,
            usar_fallback,
            contas,
        )

    secoes, totais, totais_comparativos = _linhas_dre(
        valores, valores_comparativos, contas, por_id
    )
    return {
        "resumo": _resumo_dre(totais),
        "resumo_comparativo": (
            _resumo_dre(totais_comparativos) if periodo_comparativo else None
        ),
        "secoes": secoes,
        "fallback_count": fallback,
        "fallback_comparativo_count": fallback_comparativo,
        "periodo_comparativo": periodo_comparativo,
        "tem_comparacao": bool(periodo_comparativo),
        "tem_dados": any(secao["linhas"] for secao in secoes),
    }


def drilldown_dre(
    empresa,
    conta,
    data_inicial,
    data_final,
    obra=None,
    usar_fallback=True,
):
    if not conta.aceita_lancamento:
        return {"itens": [], "total": ZERO}
    sinal = Decimal("-1") if conta.conta_redutora else Decimal("1")
    if obra:
        queryset = RateioCentroCusto.objects.filter(
            centro_custo=obra,
            lancamento__empresa=empresa,
            lancamento__plano_conta=conta,
        ).exclude(lancamento__status="CANCELADO")
        prefixo = "lancamento__"
        campo_valor = "valor"
        queryset = queryset.select_related(
            "lancamento__pessoa", "lancamento__plano_conta"
        )
    else:
        queryset = LancamentoFinanceiro.objects.filter(
            empresa=empresa,
            plano_conta=conta,
        ).exclude(status="CANCELADO").select_related("pessoa", "plano_conta")
        prefixo = ""
        campo_valor = "valor_total"

    competencia = f"{prefixo}data_competencia"
    emissao = f"{prefixo}data_emissao"
    if usar_fallback:
        queryset = queryset.annotate(
            data_referencia=Coalesce(competencia, emissao)
        ).filter(data_referencia__range=(data_inicial, data_final))
    else:
        queryset = queryset.filter(
            **{f"{competencia}__range": (data_inicial, data_final)}
        )

    ordem_data = "-data_referencia" if usar_fallback else f"-{competencia}"
    itens = []
    for item in queryset.order_by(ordem_data, "-id"):
        lancamento = item.lancamento if obra else item
        valor = moeda(getattr(item, campo_valor) * sinal)
        data_referencia = (
            item.data_referencia if usar_fallback else lancamento.data_competencia
        )
        itens.append({
            "lancamento": lancamento,
            "data_referencia": data_referencia,
            "valor": valor,
            "usou_fallback": lancamento.data_competencia is None,
        })
    return {
        "itens": itens,
        "total": moeda(sum((item["valor"] for item in itens), ZERO)),
    }
