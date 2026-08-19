import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q, Sum
from django.utils import timezone

from .models import (ApuracaoDiaria, CompetenciaPonto, ConferenciaFolha,
                     ContratoFuncionario, EventoFolha, Feriado, HistoricoRH,
                     Jornada, MarcacaoPonto, OcorrenciaPonto,
                     RetornoContabilidade, ValeAdiantamento, ValeParcela,
                     Funcionario)

CENTAVO = Decimal("0.01")


def _exigir(usuario, permissao):
    if usuario and not usuario.has_perm(f"rh.{permissao}"):
        raise PermissionDenied


def primeiro_dia_mes(valor):
    return valor.replace(day=1)


def somar_meses(valor, meses):
    indice = valor.year * 12 + valor.month - 1 + meses
    return date(indice // 12, indice % 12 + 1, 1)


def contrato_vigente(funcionario, data_referencia):
    contrato = funcionario.contratos.filter(inicio_vigencia__lte=data_referencia).filter(
        Q(fim_vigencia__isnull=True) | Q(fim_vigencia__gte=data_referencia)
    ).order_by("-inicio_vigencia").first()
    if not contrato:
        raise ValidationError("Não existe condição contratual vigente para a data informada.")
    return contrato


def jornada_vigente(funcionario, data_referencia):
    return funcionario.jornadas.filter(inicio_vigencia__lte=data_referencia).filter(
        Q(fim_vigencia__isnull=True) | Q(fim_vigencia__gte=data_referencia)
    ).prefetch_related("dias").order_by("-inicio_vigencia").first()


def minutos_trabalhados(marcacoes):
    horarios = [m.horario for m in marcacoes if m.ativa]
    if len(horarios) % 2:
        raise ValidationError("A quantidade de marcações ativas do dia deve ser par.")
    total = 0
    for indice in range(0, len(horarios), 2):
        inicio = datetime.combine(date.min, horarios[indice])
        fim = datetime.combine(date.min, horarios[indice + 1])
        if fim < inicio:
            fim += timedelta(days=1)
        total += int((fim - inicio).total_seconds() // 60)
    return total


def apurar_dia(funcionario, data_referencia):
    jornada = jornada_vigente(funcionario, data_referencia)
    configuracao = jornada.dias.filter(dia_semana=data_referencia.weekday()).first() if jornada else None
    previsto = configuracao.minutos_previstos if configuracao and configuracao.trabalha else 0
    marcacoes = funcionario.marcacoes.filter(data=data_referencia, ativa=True).order_by("horario", "id")
    trabalhado = minutos_trabalhados(marcacoes)
    ocorrencias = funcionario.ocorrencias_ponto.filter(data_inicio__lte=data_referencia).filter(
        Q(data_fim__isnull=True, data_inicio=data_referencia) | Q(data_fim__gte=data_referencia)
    )
    abonado = ocorrencias.filter(tipo__in=[OcorrenciaPonto.Tipo.ABONO, OcorrenciaPonto.Tipo.ATESTADO]).exists()
    minutos_abonados = ocorrencias.aggregate(total=Sum("minutos_abonados"))["total"] or 0
    feriado = Feriado.objects.filter(empresa=funcionario.empresa, data=data_referencia).exists()
    especial = data_referencia.weekday() == 6 or feriado
    horas_100 = trabalhado if especial else 0
    credito = debito = 0
    if not especial:
        diferenca = trabalhado + minutos_abonados - previsto
        credito = max(diferenca, 0)
        debito = max(-diferenca, 0)
    return {
        "minutos_previstos": previsto,
        "minutos_trabalhados": trabalhado,
        "credito_bh_minutos": credito,
        "debito_bh_minutos": debito,
        "horas_100_minutos": horas_100,
        "adicional_noturno_minutos": 0,
        "falta": previsto > 0 and trabalhado == 0 and not abonado,
        "abonado": abonado,
    }


def calcular_valor_horas(minutos, valor_hora, multiplicador=Decimal("1")):
    return (Decimal(minutos) / Decimal(60) * valor_hora * multiplicador).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def calcular_horas_100(competencia):
    contrato = contrato_vigente(competencia.funcionario, competencia.competencia)
    return calcular_valor_horas(competencia.horas_100_minutos, contrato.valor_hora, Decimal("2"))


def calcular_desconto_bh_negativo(competencia):
    if competencia.saldo_final_minutos >= 0:
        return Decimal("0.00")
    contrato = contrato_vigente(competencia.funcionario, competencia.competencia)
    return calcular_valor_horas(abs(competencia.saldo_final_minutos), contrato.valor_hora)


def saldo_anterior(funcionario, competencia):
    anterior = funcionario.competencias_ponto.filter(competencia__lt=competencia, status=CompetenciaPonto.Status.FECHADO).order_by("-competencia").first()
    return anterior.saldo_final_minutos if anterior else 0


@transaction.atomic
def apurar_competencia(competencia, usuario=None):
    competencia = CompetenciaPonto.objects.select_for_update().select_related("funcionario__empresa").get(pk=competencia.pk)
    if competencia.status == CompetenciaPonto.Status.FECHADO:
        raise ValidationError("Competência fechada não pode ser recalculada.")
    ultimo = calendar.monthrange(competencia.competencia.year, competencia.competencia.month)[1]
    totais = {"credito_bh_minutos": 0, "debito_bh_minutos": 0, "horas_100_minutos": 0}
    for dia in range(1, ultimo + 1):
        data_referencia = competencia.competencia.replace(day=dia)
        dados = apurar_dia(competencia.funcionario, data_referencia)
        ApuracaoDiaria.objects.update_or_create(competencia=competencia, data=data_referencia, defaults=dados)
        for chave in totais:
            totais[chave] += dados[chave]
    competencia.saldo_anterior_minutos = saldo_anterior(competencia.funcionario, competencia.competencia)
    competencia.creditos_minutos = totais["credito_bh_minutos"]
    competencia.debitos_minutos = totais["debito_bh_minutos"]
    competencia.horas_100_minutos = totais["horas_100_minutos"]
    competencia.saldo_final_minutos = competencia.saldo_anterior_minutos + competencia.creditos_minutos - competencia.debitos_minutos + competencia.ajustes_minutos
    competencia.status = CompetenciaPonto.Status.APURADO
    competencia.save()
    HistoricoRH.objects.create(empresa=competencia.funcionario.empresa, funcionario=competencia.funcionario, tipo="APURACAO_PONTO", referencia=str(competencia.pk), descricao=f"Competência {competencia.competencia:%m/%Y} apurada.", usuario=usuario)
    return competencia


def sincronizar_eventos_automaticos(competencia, usuario=None):
    valor_100 = calcular_horas_100(competencia)
    desconto = calcular_desconto_bh_negativo(competencia)
    especificacoes = [
        ("HORA_100", EventoFolha.Natureza.PROVENTO, competencia.horas_100_minutos, valor_100),
        ("DESCONTO_BH", EventoFolha.Natureza.DESCONTO, abs(min(competencia.saldo_final_minutos, 0)), desconto),
    ]
    eventos = []
    for tipo, natureza, minutos, valor in especificacoes:
        chave = f"COMPETENCIA:{competencia.pk}:{tipo}"
        if valor == 0:
            EventoFolha.objects.filter(empresa=competencia.funcionario.empresa, chave_origem=chave).delete()
            continue
        evento, _ = EventoFolha.objects.update_or_create(
            empresa=competencia.funcionario.empresa, chave_origem=chave,
            defaults={"funcionario": competencia.funcionario, "competencia": competencia.competencia,
                      "tipo": tipo, "descricao": dict(EventoFolha.TIPOS)[tipo], "natureza": natureza,
                      "quantidade": (Decimal(minutos) / Decimal(60)).quantize(Decimal("0.0001")),
                      "unidade": EventoFolha.Unidade.HORAS, "valor": valor, "origem": "FECHAMENTO_PONTO",
                      "criado_por": usuario, "status": EventoFolha.Status.PENDENTE},
        )
        eventos.append(evento)
    return eventos


@transaction.atomic
def fechar_competencia(competencia, usuario):
    _exigir(usuario, "fechar_ponto")
    competencia = CompetenciaPonto.objects.select_for_update().get(pk=competencia.pk)
    if competencia.status not in {CompetenciaPonto.Status.APURADO, CompetenciaPonto.Status.REABERTO}:
        raise ValidationError("A competência precisa estar apurada ou reaberta para ser fechada.")
    sincronizar_eventos_automaticos(competencia, usuario)
    competencia.status = CompetenciaPonto.Status.FECHADO
    competencia.fechado_por = usuario
    competencia.fechado_em = timezone.now()
    competencia.save()
    HistoricoRH.objects.create(empresa=competencia.funcionario.empresa, funcionario=competencia.funcionario, tipo="FECHAMENTO_PONTO", referencia=str(competencia.pk), descricao="Competência fechada.", usuario=usuario)
    return competencia


@transaction.atomic
def reabrir_competencia(competencia, usuario, motivo):
    _exigir(usuario, "reabrir_ponto")
    if not motivo.strip():
        raise ValidationError("Informe o motivo da reabertura.")
    competencia = CompetenciaPonto.objects.select_for_update().get(pk=competencia.pk)
    if competencia.status != CompetenciaPonto.Status.FECHADO:
        raise ValidationError("Somente competência fechada pode ser reaberta.")
    competencia.status = CompetenciaPonto.Status.REABERTO
    competencia.save(update_fields=["status", "atualizado_em"])
    HistoricoRH.objects.create(empresa=competencia.funcionario.empresa, funcionario=competencia.funcionario, tipo="REABERTURA_PONTO", referencia=str(competencia.pk), descricao=motivo, usuario=usuario)
    return competencia


@transaction.atomic
def gerar_parcelas_vale(vale, competencia_inicial):
    vale = ValeAdiantamento.objects.select_for_update().get(pk=vale.pk)
    if vale.parcelas.exists():
        return list(vale.parcelas.all())
    total_centavos = int((vale.valor_total * 100).to_integral_value(rounding=ROUND_HALF_UP))
    base, resto = divmod(total_centavos, vale.quantidade_parcelas)
    parcelas = []
    for indice in range(vale.quantidade_parcelas):
        centavos = base + (1 if indice >= vale.quantidade_parcelas - resto else 0)
        parcelas.append(ValeParcela(vale=vale, numero=indice + 1, competencia=somar_meses(primeiro_dia_mes(competencia_inicial), indice), valor=Decimal(centavos) / 100))
    ValeParcela.objects.bulk_create(parcelas)
    return parcelas


def calcular_previa_funcionario(funcionario, competencia):
    competencia = primeiro_dia_mes(competencia)
    contratos_cache = getattr(funcionario, "contratos_vigentes_cache", None)
    contrato = contratos_cache[0] if contratos_cache is not None and contratos_cache else contrato_vigente(funcionario, competencia)
    pontos_cache = getattr(funcionario, "pontos_competencia_cache", None)
    ponto = pontos_cache[0] if pontos_cache else None if pontos_cache is not None else funcionario.competencias_ponto.filter(competencia=competencia).first()
    eventos_cache = getattr(funcionario, "eventos_competencia_cache", None)
    eventos = eventos_cache if eventos_cache is not None else funcionario.eventos_folha.filter(competencia=competencia).exclude(status=EventoFolha.Status.CANCELADO)
    proventos = sum((e.valor for e in eventos if e.natureza == EventoFolha.Natureza.PROVENTO), Decimal("0.00"))
    descontos = sum((e.valor for e in eventos if e.natureza == EventoFolha.Natureza.DESCONTO), Decimal("0.00"))
    return {"funcionario": funcionario, "contrato": contrato, "ponto": ponto, "eventos": eventos,
            "proventos_controlados": proventos, "descontos_controlados": descontos,
            "liquido_gerencial": (contrato.salario_base + proventos - descontos).quantize(CENTAVO)}


def calcular_previas_empresa(empresa, competencia):
    competencia = primeiro_dia_mes(competencia)
    contratos = ContratoFuncionario.objects.filter(inicio_vigencia__lte=competencia).filter(
        Q(fim_vigencia__isnull=True) | Q(fim_vigencia__gte=competencia)
    ).order_by("-inicio_vigencia")
    pontos = CompetenciaPonto.objects.filter(competencia=competencia)
    eventos = EventoFolha.objects.filter(competencia=competencia).exclude(status=EventoFolha.Status.CANCELADO)
    funcionarios = Funcionario.objects.filter(empresa=empresa).exclude(situacao=Funcionario.Situacao.DESLIGADO).select_related("pessoa").prefetch_related(
        Prefetch("contratos", queryset=contratos, to_attr="contratos_vigentes_cache"),
        Prefetch("competencias_ponto", queryset=pontos, to_attr="pontos_competencia_cache"),
        Prefetch("eventos_folha", queryset=eventos, to_attr="eventos_competencia_cache"),
    )
    return [calcular_previa_funcionario(funcionario, competencia) for funcionario in funcionarios if funcionario.contratos_vigentes_cache]


def comparar_retorno(retorno):
    previa = calcular_previa_funcionario(retorno.funcionario, retorno.competencia)
    por_tipo = {e.tipo: e.valor for e in previa["eventos"]}
    itens = [
        {"nome": "Horas 100%", "esperado": por_tipo.get("HORA_100", Decimal("0.00")), "informado": retorno.horas_extras},
        {"nome": "Desconto BH", "esperado": por_tipo.get("DESCONTO_BH", Decimal("0.00")), "informado": retorno.faltas_descontos},
        {"nome": "INSS", "esperado": None, "informado": retorno.inss},
        {"nome": "IRRF", "esperado": None, "informado": retorno.irrf},
    ]
    for item in itens:
        item["diferenca"] = None if item["esperado"] is None or item["informado"] is None else (item["informado"] - item["esperado"]).quantize(CENTAVO)
    return {"previa": previa, "retorno": retorno, "itens": itens}


@transaction.atomic
def atualizar_conferencia(retorno, status, justificativa, usuario):
    _exigir(usuario, "conferir_folha")
    retorno = RetornoContabilidade.objects.select_for_update().get(pk=retorno.pk)
    conferencia, _ = ConferenciaFolha.objects.select_for_update().get_or_create(retorno=retorno)
    conferencia.status = status
    conferencia.justificativa = justificativa
    conferencia.usuario = usuario
    conferencia.conferido_em = timezone.now()
    conferencia.full_clean()
    conferencia.save()
    HistoricoRH.objects.create(empresa=retorno.funcionario.empresa, funcionario=retorno.funcionario, tipo="CONFERENCIA_FOLHA", referencia=str(retorno.pk), descricao=f"Conferência: {conferencia.get_status_display()}. {justificativa}", usuario=usuario)
    return conferencia
