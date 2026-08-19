from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import DecimalField, Prefetch, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import (
    BaixaFinanceira,
    CentroCusto,
    ContaBancaria,
    ImportacaoOFX,
    LancamentoFinanceiro,
    LancamentoFinanceiroClassificacao,
    MovimentacaoBancaria,
    MovimentoOFX,
    ParcelaFinanceira,
    PlanoConta,
    RateioCentroCusto,
)


CENTAVO = Decimal("0.01")
ZERO = Decimal("0.00")


@transaction.atomic
def salvar_classificacoes_lancamento(lancamento, classificacoes):
    """Valida e substitui a composição contábil oficial de um lançamento."""
    lancamento = LancamentoFinanceiro.objects.select_for_update().get(pk=lancamento.pk)
    classificacoes = list(classificacoes)
    if not classificacoes:
        raise ValidationError("Informe ao menos uma classificação contábil.")
    existentes = LancamentoFinanceiroClassificacao.objects.select_for_update().filter(lancamento=lancamento)
    if lancamento.parcelas.filter(baixas__isnull=False).exists():
        normalizadas_existentes = [(c.plano_conta_id, moeda(c.valor), c.observacao) for c in existentes.order_by("ordem", "pk")]
        normalizadas_novas = [(d.get("plano_conta").pk if d.get("plano_conta") else None, moeda(d.get("valor")), d.get("observacao", "")) for d in classificacoes]
        if normalizadas_novas != normalizadas_existentes:
            raise ValidationError("As classificações estão congeladas porque o lançamento possui baixa ou conciliação.")
        return list(existentes)
    contas = set()
    objetos = []
    total = ZERO
    for ordem, dados in enumerate(classificacoes, 1):
        plano = dados.get("plano_conta")
        valor = moeda(dados.get("valor"))
        if not plano:
            raise ValidationError("Informe o Plano de Contas de todas as classificações.")
        if plano.pk in contas:
            raise ValidationError("Não repita a mesma conta contábil no lançamento.")
        contas.add(plano.pk)
        if valor <= ZERO:
            raise ValidationError("O valor de cada classificação deve ser maior que zero.")
        if not plano.ativo or plano.estrutural or not plano.aceita_lancamento:
            raise ValidationError(f"A conta {plano.codigo} não está disponível para nova classificação.")
        if lancamento.tipo == "PAGAR" and plano.tipo not in {"CUSTO", "DESPESA"}:
            raise ValidationError("Contas a pagar aceitam somente contas de custo ou despesa.")
        if lancamento.tipo == "RECEBER" and plano.tipo != "RECEITA":
            raise ValidationError("Contas a receber aceitam somente contas de receita.")
        total += valor
        objetos.append(LancamentoFinanceiroClassificacao(
            lancamento=lancamento, plano_conta=plano, valor=valor,
            observacao=dados.get("observacao", ""), ordem=dados.get("ordem") or ordem,
        ))
    if moeda(total) != moeda(lancamento.valor_total):
        raise ValidationError("A soma das classificações deve ser igual ao valor total do lançamento.")
    existentes.delete()
    LancamentoFinanceiroClassificacao.objects.bulk_create(objetos)
    plano_legado = objetos[0].plano_conta if len(objetos) == 1 else None
    LancamentoFinanceiro.objects.filter(pk=lancamento.pk).update(plano_conta=plano_legado)
    lancamento.plano_conta = plano_legado
    return list(lancamento.classificacoes_contabeis.order_by("ordem", "pk"))


def verificar_integridade_classificacoes(queryset=None):
    """Retorna lançamentos cuja composição não fecha com o valor total."""
    queryset = queryset if queryset is not None else LancamentoFinanceiro.objects.all()
    invalidos = []
    for lancamento in queryset.prefetch_related("classificacoes_contabeis").iterator(chunk_size=1000):
        classificacoes = list(lancamento.classificacoes_contabeis.all())
        total = sum((item.valor for item in classificacoes), ZERO)
        legado_esperado = classificacoes[0].plano_conta_id if len(classificacoes) == 1 else None
        if not classificacoes or total != lancamento.valor_total or lancamento.plano_conta_id != legado_esperado:
            invalidos.append(lancamento.pk)
    return {"integro": not invalidos, "lancamentos_invalidos": invalidos}

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


def distribuir_classificacoes_por_rateios(lancamento):
    """Cruza classificações e obras sem persistir matriz, fechando linhas e colunas."""
    classificacoes = sorted(
        list(lancamento.classificacoes_contabeis.all()),
        key=lambda item: (item.ordem, item.plano_conta_id, item.pk),
    )
    rateios = sorted(
        list(lancamento.rateios_centro_custo.all()),
        key=lambda item: (item.centro_custo_id, item.pk),
    )
    total = moeda(lancamento.valor_total)
    if sum((item.valor for item in classificacoes), ZERO) != total:
        raise ValidationError("As classificações não fecham com o valor do lançamento.")
    if sum((item.valor for item in rateios), ZERO) != total:
        raise ValidationError("Os rateios não fecham com o valor do lançamento.")
    if not classificacoes or not rateios:
        return {}

    brutos = {}
    matriz = {}
    for classificacao in classificacoes:
        for rateio in rateios:
            chave = (classificacao.pk, rateio.pk)
            bruto = classificacao.valor * rateio.valor / total
            brutos[chave] = bruto
            matriz[chave] = bruto.quantize(CENTAVO, rounding=ROUND_DOWN)

    residuos_linha = {
        item.pk: int(((item.valor - sum(
            (matriz[(item.pk, rateio.pk)] for rateio in rateios), ZERO
        )) / CENTAVO).to_integral_value())
        for item in classificacoes
    }
    residuos_coluna = {
        item.pk: int(((item.valor - sum(
            (matriz[(classificacao.pk, item.pk)] for classificacao in classificacoes), ZERO
        )) / CENTAVO).to_integral_value())
        for item in rateios
    }
    candidatos = sorted(
        ((classificacao, rateio) for classificacao in classificacoes for rateio in rateios),
        key=lambda par: (
            -(brutos[(par[0].pk, par[1].pk)] - matriz[(par[0].pk, par[1].pk)]),
            par[0].ordem, par[0].plano_conta_id, par[1].centro_custo_id,
            par[0].pk, par[1].pk,
        ),
    )
    restantes = sum(residuos_linha.values())
    while restantes:
        distribuiu = False
        for classificacao, rateio in candidatos:
            if residuos_linha[classificacao.pk] and residuos_coluna[rateio.pk]:
                matriz[(classificacao.pk, rateio.pk)] += CENTAVO
                residuos_linha[classificacao.pk] -= 1
                residuos_coluna[rateio.pk] -= 1
                restantes -= 1
                distribuiu = True
                if not restantes:
                    break
        if not distribuiu:
            raise ValidationError("Não foi possível fechar os centavos da matriz contábil por obra.")
    return matriz


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
        .select_related("lancamento__pessoa")
        .prefetch_related(
            "lancamento__parcelas__baixas",
            "lancamento__rateios_centro_custo",
            "lancamento__classificacoes_contabeis__plano_conta",
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
        matriz = distribuir_classificacoes_por_rateios(lancamento)
        classificacoes_obra = []
        for classificacao in lancamento.classificacoes_contabeis.all():
            valor = moeda(matriz[(classificacao.pk, rateio.pk)])
            valores_por_conta[classificacao.plano_conta_id] += valor
            classificacoes_obra.append({"classificacao":classificacao,"plano_conta":classificacao.plano_conta,"valor":valor})
            if classificacao.plano_conta.tipo == "RECEITA": receitas += valor
            elif classificacao.plano_conta.tipo == "CUSTO": custos += valor
            elif classificacao.plano_conta.tipo == "DESPESA": despesas += valor
        rateio.classificacoes_obra = classificacoes_obra
        rateio_por_lancamento[lancamento.pk] = rateio
        lancamentos_por_id[lancamento.pk] = lancamento

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
        for dado in rateio.classificacoes_obra:
            if dado["plano_conta"].tipo == "RECEITA": competencia_mensal[mes]["receitas"] += dado["valor"]
            else: competencia_mensal[mes]["custos_despesas"] += dado["valor"]

        detalhes.append({
            "lancamento": lancamento,
            "data_referencia": rateio.data_referencia,
            "valor_rateado": moeda(rateio.valor),
            "classificacoes": rateio.classificacoes_obra,
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

    prefixo = "lancamento__"
    classificacoes = LancamentoFinanceiroClassificacao.objects.filter(
        lancamento__empresa=empresa,
        plano_conta__aceita_lancamento=True,
        plano_conta__tipo__in=("RECEITA", "CUSTO", "DESPESA"),
    ).exclude(lancamento__status="CANCELADO")
    if ids_contas is not None:
        classificacoes = classificacoes.filter(plano_conta_id__in=ids_contas)
    campo_competencia = "lancamento__data_competencia"
    campo_emissao = "lancamento__data_emissao"
    if usar_fallback:
        classificacoes = classificacoes.annotate(
            data_referencia=Coalesce(campo_competencia, campo_emissao)
        ).filter(data_referencia__range=(data_inicial, data_final))
        fallback = classificacoes.filter(lancamento__data_competencia__isnull=True).values("lancamento_id").distinct().count()
    else:
        classificacoes = classificacoes.filter(lancamento__data_competencia__range=(data_inicial, data_final))
        fallback = 0
    if not obra:
        agregados = classificacoes.values("plano_conta_id").annotate(total=Sum("valor"))
        valores = {item["plano_conta_id"]: moeda(item["total"]) for item in agregados}
        return valores, fallback

    ids_lancamentos = RateioCentroCusto.objects.filter(
        centro_custo=obra,
        lancamento__empresa=empresa,
    ).values("lancamento_id")
    classificacoes = classificacoes.filter(lancamento_id__in=Subquery(ids_lancamentos))
    if usar_fallback:
        fallback = classificacoes.filter(lancamento__data_competencia__isnull=True).values("lancamento_id").distinct().count()
    ids_filtrados = set(classificacoes.values_list("pk", flat=True))
    lancamentos = (
        LancamentoFinanceiro.objects.filter(pk__in=Subquery(classificacoes.values("lancamento_id")))
        .prefetch_related(
            Prefetch("classificacoes_contabeis", queryset=LancamentoFinanceiroClassificacao.objects.select_related("plano_conta")),
            "rateios_centro_custo",
        )
    )
    valores = defaultdict(lambda: ZERO)
    for lancamento in lancamentos:
        matriz = distribuir_classificacoes_por_rateios(lancamento)
        rateio_obra = next((r for r in lancamento.rateios_centro_custo.all() if r.centro_custo_id == obra.pk), None)
        if not rateio_obra:
            continue
        for classificacao in lancamento.classificacoes_contabeis.all():
            if classificacao.pk in ids_filtrados:
                valores[classificacao.plano_conta_id] += matriz[(classificacao.pk, rateio_obra.pk)]
    valores = {conta_id: moeda(valor) for conta_id, valor in valores.items()}
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
    queryset = LancamentoFinanceiroClassificacao.objects.filter(
        lancamento__empresa=empresa, plano_conta=conta,
    ).exclude(lancamento__status="CANCELADO").select_related("lancamento__pessoa", "plano_conta")
    competencia = "lancamento__data_competencia"
    emissao = "lancamento__data_emissao"
    if usar_fallback:
        queryset = queryset.annotate(
            data_referencia=Coalesce(competencia, emissao)
        ).filter(data_referencia__range=(data_inicial, data_final))
    else:
        queryset = queryset.filter(
            **{f"{competencia}__range": (data_inicial, data_final)}
        )

    ordem_data = "-data_referencia" if usar_fallback else "-lancamento__data_competencia"
    itens = []
    if obra:
        ids = RateioCentroCusto.objects.filter(centro_custo=obra,lancamento__empresa=empresa).values("lancamento_id")
        queryset = queryset.filter(lancamento_id__in=Subquery(ids))
        lancamentos = {l.pk:l for l in LancamentoFinanceiro.objects.filter(pk__in=Subquery(queryset.values("lancamento_id"))).prefetch_related("classificacoes_contabeis","rateios_centro_custo")}
    for item in queryset.order_by(ordem_data, "-id"):
        lancamento = item.lancamento
        valor_base = item.valor
        rateio = None
        if obra:
            lancamento_matriz = lancamentos[lancamento.pk]
            rateio = next((r for r in lancamento_matriz.rateios_centro_custo.all() if r.centro_custo_id==obra.pk),None)
            valor_base = distribuir_classificacoes_por_rateios(lancamento_matriz).get((item.pk,rateio.pk),ZERO) if rateio else ZERO
        valor = moeda(valor_base * sinal)
        data_referencia = (
            item.data_referencia if usar_fallback else lancamento.data_competencia
        )
        itens.append({
            "lancamento": lancamento,
            "classificacao": item,
            "plano_conta": item.plano_conta,
            "data_referencia": data_referencia,
            "valor": valor,
            "usou_fallback": lancamento.data_competencia is None,
        })
    return {
        "itens": itens,
        "total": moeda(sum((item["valor"] for item in itens), ZERO)),
    }


def _mes_seguinte(valor):
    return (valor.replace(day=28) + timedelta(days=4)).replace(day=1)


def _posicao_bancaria_dashboard(empresa, data_inicial, data_final):
    campo_decimal = DecimalField(max_digits=15, decimal_places=2)
    contas = list(
        ContaBancaria.objects.filter(empresa=empresa, ativa=True)
        .annotate(
            entradas_agregadas=Coalesce(
                Sum(
                    "movimentacoes_bancarias__valor",
                    filter=Q(movimentacoes_bancarias__tipo="ENTRADA"),
                ),
                Value(ZERO),
                output_field=campo_decimal,
            ),
            saidas_agregadas=Coalesce(
                Sum(
                    "movimentacoes_bancarias__valor",
                    filter=Q(movimentacoes_bancarias__tipo="SAIDA"),
                ),
                Value(ZERO),
                output_field=campo_decimal,
            ),
        )
        .order_by("banco", "agencia", "conta")
    )
    saldo_total = ZERO
    contas_negativas = 0
    for conta in contas:
        conta.saldo_dashboard = moeda(
            conta.saldo_inicial
            + conta.entradas_agregadas
            - conta.saidas_agregadas
        )
        saldo_total += conta.saldo_dashboard
        if conta.saldo_dashboard < ZERO:
            contas_negativas += 1

    movimentos = MovimentacaoBancaria.objects.filter(
        conta_bancaria__empresa=empresa,
        conta_bancaria__ativa=True,
        data__range=(data_inicial, data_final),
    ).exclude(origem="TRANSFERENCIA")
    agregados = movimentos.aggregate(
        entradas=Sum("valor", filter=Q(tipo="ENTRADA")),
        saidas=Sum("valor", filter=Q(tipo="SAIDA")),
    )
    return {
        "contas": contas,
        "saldo_total": moeda(saldo_total),
        "entradas_periodo": moeda(agregados["entradas"]),
        "saidas_periodo": moeda(agregados["saidas"]),
        "contas_negativas": contas_negativas,
    }


def _titulos_dashboard(
    empresa,
    tipo,
    data_inicial,
    data_final,
    hoje,
    obra=None,
):
    parcelas = list(
        ParcelaFinanceira.objects.filter(
            lancamento__empresa=empresa,
            lancamento__tipo=tipo,
        )
        .exclude(status="CANCELADA")
        .exclude(lancamento__status="CANCELADO")
        .select_related("lancamento__pessoa", "lancamento__plano_conta")
        .prefetch_related(
            "baixas",
            "lancamento__rateios_centro_custo",
        )
        .order_by("vencimento", "id")
    )
    total_aberto = ZERO
    vencido = ZERO
    a_vencer = ZERO
    previsto = ZERO
    proximos = []
    vencendo_sete_dias = 0
    fim_alerta = hoje + timedelta(days=7)
    inicio_previsao = max(hoje, data_inicial)

    for parcela in parcelas:
        baixado = sum((baixa.valor for baixa in parcela.baixas.all()), ZERO)
        saldo = max(parcela.valor - baixado, ZERO)
        if saldo <= ZERO:
            continue
        rateios = list(parcela.lancamento.rateios_centro_custo.all())
        if obra:
            rateio_obra = next(
                (rateio for rateio in rateios if rateio.centro_custo_id == obra.pk),
                None,
            )
            if not rateio_obra:
                continue
            saldo = distribuir_valor_rateios(saldo, rateios).get(
                rateio_obra.pk, ZERO
            )
            if saldo <= ZERO:
                continue

        parcela.saldo_dashboard = moeda(saldo)
        total_aberto += saldo
        if parcela.vencimento < hoje:
            vencido += saldo
        else:
            a_vencer += saldo
            if len(proximos) < 5:
                proximos.append(parcela)
        if hoje <= parcela.vencimento <= fim_alerta:
            vencendo_sete_dias += 1
        if inicio_previsao <= parcela.vencimento <= data_final:
            previsto += saldo

    realizado = ZERO
    baixas_periodo = BaixaFinanceira.objects.filter(
        parcela__lancamento__empresa=empresa,
        parcela__lancamento__tipo=tipo,
        data__range=(data_inicial, data_final),
    ).exclude(parcela__lancamento__status="CANCELADO")
    if obra:
        baixas_periodo = baixas_periodo.select_related(
            "parcela__lancamento"
        ).prefetch_related("parcela__lancamento__rateios_centro_custo")
        for baixa in baixas_periodo:
            rateios = list(baixa.parcela.lancamento.rateios_centro_custo.all())
            rateio_obra = next(
                (rateio for rateio in rateios if rateio.centro_custo_id == obra.pk),
                None,
            )
            if rateio_obra:
                realizado += distribuir_valor_rateios(
                    baixa.valor_movimento, rateios
                ).get(rateio_obra.pk, ZERO)
    else:
        realizado = (
            baixas_periodo.aggregate(total=Sum("valor"))["total"] or ZERO
        )
        ajustes = baixas_periodo.aggregate(
            juros=Sum("juros"), multa=Sum("multa"), desconto=Sum("desconto")
        )
        realizado += (
            (ajustes["juros"] or ZERO)
            + (ajustes["multa"] or ZERO)
            - (ajustes["desconto"] or ZERO)
        )

    return {
        "em_aberto": moeda(total_aberto),
        "vencido": moeda(vencido),
        "a_vencer": moeda(a_vencer),
        "realizado_periodo": moeda(realizado),
        "previsto": moeda(previsto),
        "proximos": proximos,
        "vencendo_sete_dias": vencendo_sete_dias,
        "parcelas": parcelas,
    }


def _fluxo_mensal_dashboard(
    empresa,
    data_inicial,
    data_final,
    hoje,
    saldo_atual,
    obra=None,
):
    meses = defaultdict(
        lambda: {
            "entradas_realizadas": ZERO,
            "saidas_realizadas": ZERO,
            "entradas_previstas": ZERO,
            "saidas_previstas": ZERO,
        }
    )

    if obra:
        baixas = (
            BaixaFinanceira.objects.filter(
                parcela__lancamento__empresa=empresa,
                data__range=(data_inicial, data_final),
            )
            .exclude(parcela__lancamento__status="CANCELADO")
            .select_related("parcela__lancamento")
            .prefetch_related("parcela__lancamento__rateios_centro_custo")
        )
        for baixa in baixas:
            rateios = list(baixa.parcela.lancamento.rateios_centro_custo.all())
            rateio = next(
                (item for item in rateios if item.centro_custo_id == obra.pk), None
            )
            if not rateio:
                continue
            valor = distribuir_valor_rateios(
                baixa.valor_movimento, rateios
            ).get(rateio.pk, ZERO)
            chave = baixa.data.replace(day=1)
            campo = (
                "entradas_realizadas"
                if baixa.parcela.lancamento.tipo == "RECEBER"
                else "saidas_realizadas"
            )
            meses[chave][campo] += valor
    else:
        realizados = (
            MovimentacaoBancaria.objects.filter(
                conta_bancaria__empresa=empresa,
                conta_bancaria__ativa=True,
                data__range=(data_inicial, data_final),
            )
            .exclude(origem="TRANSFERENCIA")
            .values("data", "tipo")
            .annotate(total=Sum("valor"))
        )
        for item in realizados:
            campo = (
                "entradas_realizadas"
                if item["tipo"] == "ENTRADA"
                else "saidas_realizadas"
            )
            meses[item["data"].replace(day=1)][campo] += item["total"]

    inicio_previsao = max(hoje, data_inicial)
    parcelas = (
        ParcelaFinanceira.objects.filter(
            lancamento__empresa=empresa,
            vencimento__range=(inicio_previsao, data_final),
        )
        .exclude(status="CANCELADA")
        .exclude(lancamento__status="CANCELADO")
        .select_related("lancamento")
        .prefetch_related("baixas", "lancamento__rateios_centro_custo")
    )
    for parcela in parcelas:
        saldo = max(
            parcela.valor
            - sum((baixa.valor for baixa in parcela.baixas.all()), ZERO),
            ZERO,
        )
        if obra:
            rateios = list(parcela.lancamento.rateios_centro_custo.all())
            rateio = next(
                (item for item in rateios if item.centro_custo_id == obra.pk), None
            )
            if not rateio:
                continue
            saldo = distribuir_valor_rateios(saldo, rateios).get(rateio.pk, ZERO)
        campo = (
            "entradas_previstas"
            if parcela.lancamento.tipo == "RECEBER"
            else "saidas_previstas"
        )
        meses[parcela.vencimento.replace(day=1)][campo] += saldo

    resultado = []
    atual = data_inicial.replace(day=1)
    ultimo = data_final.replace(day=1)
    saldo_projetado = saldo_atual
    while atual <= ultimo:
        item = meses[atual]
        saldo_projetado += (
            item["entradas_previstas"] - item["saidas_previstas"]
        )
        resultado.append({
            "rotulo": atual.strftime("%m/%Y"),
            **{chave: float(moeda(valor)) for chave, valor in item.items()},
            "saldo_projetado": float(moeda(saldo_projetado)),
        })
        atual = _mes_seguinte(atual)
    return resultado


def _obras_dashboard(empresa, data_inicial, data_final, dre, obra=None):
    contas, por_id = _mapa_contas_dre()
    receitas_financeiras = next(
        (conta for conta in contas if conta.codigo == "4.02"), None
    )
    despesas_financeiras = next(
        (conta for conta in contas if conta.codigo == "6.09"), None
    )
    rateios = (
        RateioCentroCusto.objects.filter(
            centro_custo__empresa=empresa,
            lancamento__empresa=empresa,
        )
        .exclude(lancamento__status="CANCELADO")
        .annotate(
            data_referencia=Coalesce(
                "lancamento__data_competencia", "lancamento__data_emissao"
            )
        )
        .filter(data_referencia__range=(data_inicial, data_final))
        .select_related("centro_custo", "lancamento")
        .prefetch_related("lancamento__classificacoes_contabeis__plano_conta","lancamento__rateios_centro_custo")
    )
    if obra:
        rateios = rateios.filter(centro_custo=obra)

    por_obra = {}
    total_apropriado = ZERO
    for rateio in rateios:
        dados = por_obra.setdefault(
            rateio.centro_custo_id,
            {
                "obra": rateio.centro_custo,
                "receitas": ZERO,
                "custos_despesas": ZERO,
                "resultado": ZERO,
            },
        )
        total_apropriado += abs(rateio.valor)
        matriz = distribuir_classificacoes_por_rateios(rateio.lancamento)
        for classificacao in rateio.lancamento.classificacoes_contabeis.all():
            conta = classificacao.plano_conta
            if not conta.aceita_lancamento: continue
            secao = _secao_conta_dre(conta,por_id,receitas_financeiras.pk if receitas_financeiras else None,despesas_financeiras.pk if despesas_financeiras else None)
            sinal = Decimal("-1") if conta.conta_redutora else Decimal("1")
            valor = matriz[(classificacao.pk,rateio.pk)] * sinal
            if secao in ("receitas_operacionais", "receitas_financeiras"):
                dados["receitas"] += valor; dados["resultado"] += valor
            else:
                dados["custos_despesas"] += valor; dados["resultado"] -= valor

    ranking = []
    for dados in por_obra.values():
        dados["receitas"] = moeda(dados["receitas"])
        dados["custos_despesas"] = moeda(dados["custos_despesas"])
        dados["resultado"] = moeda(dados["resultado"])
        dados["margem"] = (
            moeda(dados["resultado"] * Decimal("100") / dados["receitas"])
            if dados["receitas"] else None
        )
        ranking.append(dados)
    ranking.sort(
        key=lambda item: (-item["resultado"], item["obra"].codigo)
    )

    resumo = dre["resumo"]
    base_dre = sum(
        abs(resumo[chave])
        for chave in (
            "receitas_operacionais", "custos", "despesas_operacionais",
            "receitas_financeiras", "despesas_financeiras",
        )
    )
    return {
        "ativas": CentroCusto.objects.filter(empresa=empresa, ativo=True).count(),
        "receitas": moeda(sum((item["receitas"] for item in ranking), ZERO)),
        "custos_despesas": moeda(
            sum((item["custos_despesas"] for item in ranking), ZERO)
        ),
        "resultado": moeda(sum((item["resultado"] for item in ranking), ZERO)),
        "cobertura": (
            moeda(total_apropriado * Decimal("100") / base_dre)
            if base_dre else None
        ),
        "ranking": ranking[:5],
    }


def calcular_dashboard_financeiro(
    empresa,
    data_inicial,
    data_final,
    obra=None,
    hoje=None,
):
    hoje = hoje or timezone.localdate()
    bancos = _posicao_bancaria_dashboard(empresa, data_inicial, data_final)
    receber = _titulos_dashboard(
        empresa, "RECEBER", data_inicial, data_final, hoje, obra
    )
    pagar = _titulos_dashboard(
        empresa, "PAGAR", data_inicial, data_final, hoje, obra
    )
    saldo_projetado = bancos["saldo_total"] + receber["previsto"] - pagar["previsto"]
    dre = calcular_dre(
        empresa,
        data_inicial,
        data_final,
        obra=obra,
        usar_fallback=True,
    )
    obras = _obras_dashboard(empresa, data_inicial, data_final, dre, obra)

    pendentes_qs = MovimentoOFX.objects.filter(
        conta_bancaria__empresa=empresa,
        status="PENDENTE",
    )
    importacoes_recentes = ImportacaoOFX.objects.filter(
        conta_bancaria__empresa=empresa,
        criado_em__gte=timezone.now() - timedelta(days=30),
    ).select_related("conta_bancaria")
    conciliacao = {
        "pendentes": pendentes_qs.count(),
        "contas_com_pendencias": pendentes_qs.values(
            "conta_bancaria_id"
        ).distinct().count(),
        "importacoes_recentes": importacoes_recentes.count(),
        "ultima_importacao": importacoes_recentes.order_by("-criado_em").first(),
    }

    alertas = []
    if pagar["vencido"]:
        alertas.append({"tipo": "PAGAR", "texto": "Contas a pagar vencidas"})
    if receber["vencido"]:
        alertas.append({"tipo": "RECEBER", "texto": "Contas a receber vencidas"})
    vencendo = pagar["vencendo_sete_dias"] + receber["vencendo_sete_dias"]
    if vencendo:
        alertas.append({"tipo": "VENCIMENTO", "texto": "Títulos vencendo nos próximos 7 dias"})
    if bancos["contas_negativas"]:
        alertas.append({"tipo": "BANCO", "texto": "Contas bancárias com saldo negativo"})
    if conciliacao["pendentes"]:
        alertas.append({"tipo": "OFX", "texto": "Movimentos OFX pendentes"})

    entradas_realizadas = (
        receber["realizado_periodo"]
        if obra else bancos["entradas_periodo"]
    )
    saidas_realizadas = (
        pagar["realizado_periodo"]
        if obra else bancos["saidas_periodo"]
    )
    return {
        "posicao_bancaria": bancos,
        "receber": receber,
        "pagar": pagar,
        "fluxo": {
            "entradas_realizadas": entradas_realizadas,
            "saidas_realizadas": saidas_realizadas,
            "saldo_liquido": moeda(entradas_realizadas - saidas_realizadas),
            "entradas_previstas": receber["previsto"],
            "saidas_previstas": pagar["previsto"],
            "saldo_projetado": moeda(saldo_projetado),
            "grafico": _fluxo_mensal_dashboard(
                empresa, data_inicial, data_final, hoje,
                bancos["saldo_total"], obra,
            ),
        },
        "dre": dre,
        "obras": obras,
        "conciliacao": conciliacao,
        "alertas": alertas,
    }


def calcular_aging(empresa, tipo, data_base=None):
    """Resume principal em aberto sem confundir encargos de baixa com o título."""
    from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
    from django.db.models.functions import Coalesce

    data_base = data_base or timezone.localdate()
    qs = ParcelaFinanceira.objects.filter(
        lancamento__empresa=empresa,
        lancamento__tipo=tipo,
    ).exclude(status="CANCELADA").exclude(lancamento__status="CANCELADO").annotate(
        baixado=Coalesce(Sum("baixas__valor"), Value(Decimal("0.00")), output_field=DecimalField()),
    ).annotate(
        saldo_calculado=ExpressionWrapper(F("valor") - F("baixado"), output_field=DecimalField(max_digits=15, decimal_places=2)),
    ).filter(saldo_calculado__gt=0).select_related("lancamento__pessoa")
    faixas = {"a_vencer": Decimal("0.00"), "vencido_1_30": Decimal("0.00"), "vencido_31_60": Decimal("0.00"), "vencido_61_90": Decimal("0.00"), "vencido_mais_90": Decimal("0.00")}
    linhas = []
    for parcela in qs.order_by("vencimento", "pk"):
        atraso = (data_base - parcela.vencimento).days
        chave = "a_vencer" if atraso <= 0 else "vencido_1_30" if atraso <= 30 else "vencido_31_60" if atraso <= 60 else "vencido_61_90" if atraso <= 90 else "vencido_mais_90"
        faixas[chave] += parcela.saldo_calculado
        linhas.append({"parcela": parcela, "dias_atraso": max(atraso, 0), "faixa": chave, "saldo": parcela.saldo_calculado})
    total = sum(faixas.values(), Decimal("0.00"))
    return {"tipo": tipo, "data_base": data_base, "faixas": faixas, "total": total, "linhas": linhas}


def calcular_fluxo_projetado(empresa, data_inicial, data_final, agrupamento="DIARIO"):
    from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
    from django.db.models.functions import Coalesce, TruncMonth, TruncWeek

    contas = ContaBancaria.objects.filter(empresa=empresa, ativa=True)
    saldo = contas.aggregate(total=Coalesce(Sum("saldo_inicial"), Value(Decimal("0.00")), output_field=DecimalField()))["total"]
    movs = MovimentacaoBancaria.objects.filter(conta_bancaria__in=contas).values("tipo").annotate(total=Sum("valor"))
    for mov in movs:
        saldo += mov["total"] if mov["tipo"] == "ENTRADA" else -mov["total"]
    parcelas = ParcelaFinanceira.objects.filter(lancamento__empresa=empresa, vencimento__range=(data_inicial, data_final)).exclude(status="CANCELADA").exclude(lancamento__status="CANCELADO").annotate(
        baixado=Coalesce(Sum("baixas__valor"), Value(Decimal("0.00")), output_field=DecimalField()),
        saldo_aberto=ExpressionWrapper(F("valor") - F("baixado"), output_field=DecimalField(max_digits=15, decimal_places=2)),
    ).filter(saldo_aberto__gt=0)
    saldo_atual = saldo
    mapa = {}
    for parcela in parcelas.select_related("lancamento").order_by("vencimento", "pk"):
        if agrupamento == "MENSAL":
            periodo = parcela.vencimento.replace(day=1)
        elif agrupamento == "SEMANAL":
            periodo = parcela.vencimento - timedelta(days=parcela.vencimento.weekday())
        else:
            periodo = parcela.vencimento
        linha = mapa.setdefault(periodo, {"periodo": periodo, "entradas": Decimal("0.00"), "saidas": Decimal("0.00")})
        linha["entradas" if parcela.lancamento.tipo == "RECEBER" else "saidas"] += parcela.saldo_aberto
    linhas = []
    for linha in mapa.values():
        saldo += linha["entradas"] - linha["saidas"]
        linha["saldo"] = saldo
        linhas.append(linha)
    return {"saldo_atual": saldo_atual, "linhas": linhas, "saldo_final": saldo, "agrupamento": agrupamento}
