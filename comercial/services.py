from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from financeiro.models import CentroCusto

from .models import (
    ModeloConteudoProposta,
    Proposta,
    PropostaHistoricoStatus,
    PropostaItem,
    PropostaLinhaPublica,
    PropostaRevisao,
    PropostaTributo,
)

CENTAVO = Decimal("0.01")

TRANSICOES_PERMITIDAS = {
    Proposta.Status.RASCUNHO: {Proposta.Status.ENVIADA, Proposta.Status.CANCELADA},
    Proposta.Status.EM_REVISAO: {Proposta.Status.ENVIADA, Proposta.Status.CANCELADA},
    Proposta.Status.ENVIADA: {Proposta.Status.EM_NEGOCIACAO, Proposta.Status.APROVADA, Proposta.Status.REJEITADA, Proposta.Status.CANCELADA, Proposta.Status.EM_REVISAO},
    Proposta.Status.EM_NEGOCIACAO: {Proposta.Status.APROVADA, Proposta.Status.REJEITADA, Proposta.Status.CANCELADA, Proposta.Status.EM_REVISAO},
    Proposta.Status.APROVADA: {Proposta.Status.CANCELADA},
    Proposta.Status.REJEITADA: set(),
    Proposta.Status.CANCELADA: set(),
}


def _dinheiro(valor):
    return Decimal(valor or 0).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _validar_transicao(proposta, novo_status):
    if novo_status not in TRANSICOES_PERMITIDAS.get(proposta.status, set()):
        raise ValidationError(f"Não é permitido alterar a proposta de {proposta.get_status_display()} para {dict(Proposta.Status.choices)[novo_status]}.")


def _exigir_permissao(usuario, permissao):
    if not usuario or not usuario.has_perm(f"comercial.{permissao}"):
        raise PermissionDenied("Você não possui permissão para esta ação.")


def _registrar_status(proposta, novo_status, usuario, observacao=""):
    anterior = proposta.status
    _validar_transicao(proposta, novo_status)
    proposta.status = novo_status
    proposta.save(update_fields=["status", "atualizado_em"])
    PropostaHistoricoStatus.objects.create(proposta=proposta, status_anterior=anterior, status_novo=novo_status, usuario=usuario, observacao=observacao)


def calcular_precificacao(revisao):
    """Calcula exclusivamente a partir da composição interna da revisão."""
    custo = _dinheiro(revisao.itens.aggregate(total=Sum("custo_total"))["total"])
    aliquota = sum((t.percentual for t in revisao.tributos.all()), Decimal("0")) / Decimal("100")
    fator = revisao.percentual_formacao / Decimal("100")
    if aliquota >= 1:
        raise ValidationError("A soma dos tributos deve ser inferior a 100%.")

    if revisao.formacao_preco == PropostaRevisao.FormacaoPreco.MARKUP:
        preco = custo * (Decimal("1") + fator) / (Decimal("1") - aliquota)
    elif revisao.formacao_preco == PropostaRevisao.FormacaoPreco.MARGEM:
        if aliquota + fator >= 1:
            raise ValidationError("Margem e tributos juntos devem ser inferiores a 100%.")
        preco = custo / (Decimal("1") - aliquota - fator)
    else:
        preco = revisao.preco_venda_final
        if preco <= 0:
            raise ValidationError("Informe um preço de venda manual positivo.")

    preco = _dinheiro(preco)
    tributos = _dinheiro(preco * aliquota)
    resultado = _dinheiro(preco - custo - tributos)
    margem = (resultado / preco * 100).quantize(Decimal("0.01")) if preco else Decimal("0")
    markup = (resultado / custo * 100).quantize(Decimal("0.01")) if custo else Decimal("0")
    return {"custo_total": custo, "preco_final": preco, "tributos": tributos, "resultado": resultado, "margem": margem, "markup": markup}


def validar_fechamento_publico(revisao):
    total = _dinheiro(revisao.linhas_publicas.aggregate(total=Sum("valor_total"))["total"])
    preco = _dinheiro(revisao.preco_venda_final)
    if total != preco:
        raise ValidationError(f"As linhas públicas totalizam R$ {total} e devem fechar em R$ {preco}.")
    return total


@transaction.atomic
def criar_proposta(*, empresa, cliente, nome_servico, usuario=None, modelo=None, **dados_revisao):
    from financeiro.models import Empresa

    Empresa.objects.select_for_update().get(pk=empresa.pk)
    sequencial = (Proposta.objects.filter(empresa=empresa).aggregate(maximo=Max("numero_sequencial"))["maximo"] or 0) + 1
    proposta = Proposta(empresa=empresa, cliente=cliente, codigo=f"VERS{sequencial:04d}", numero_sequencial=sequencial, responsavel_interno=usuario)
    proposta.full_clean()
    proposta.save()
    if modelo is None:
        modelo = ModeloConteudoProposta.objects.filter(empresa=empresa, ativo=True, padrao=True).first()
    snapshot = {}
    if modelo:
        for campo in ("texto_introdutorio", "normas_procedimentos", "qualificacao_mao_obra", "obrigacoes_contratada", "observacoes_comerciais", "observacao_faturamento", "texto_impostos", "multa_juros_atraso", "regra_protesto", "rodape"):
            snapshot[campo] = getattr(modelo, campo)
    snapshot.update(dados_revisao)
    revisao = PropostaRevisao.objects.create(proposta=proposta, numero=0, modelo_conteudo=modelo, data_proposta=timezone.localdate(), nome_servico=nome_servico, criado_por=usuario, **snapshot)
    PropostaHistoricoStatus.objects.create(proposta=proposta, status_novo=proposta.status, usuario=usuario)
    return proposta, revisao


@transaction.atomic
def enviar_proposta(revisao, usuario=None):
    revisao = PropostaRevisao.objects.select_for_update().select_related("proposta__empresa", "proposta__cliente").get(pk=revisao.pk)
    if revisao.congelada:
        raise ValidationError("Esta revisão já foi enviada.")
    _validar_transicao(revisao.proposta, Proposta.Status.ENVIADA)
    calculo = calcular_precificacao(revisao)
    revisao.preco_venda_final = calculo["preco_final"]
    validar_fechamento_publico(revisao)
    revisao.valida_ate = revisao.data_proposta + timedelta(days=revisao.validade_dias)
    revisao.empresa_nome_snapshot = revisao.proposta.empresa.nome_fantasia or revisao.proposta.empresa.razao_social
    revisao.empresa_documento_snapshot = revisao.proposta.empresa.cnpj
    revisao.cliente_nome_snapshot = revisao.proposta.cliente.nome_fantasia or revisao.proposta.cliente.razao_social
    revisao.cliente_documento_snapshot = revisao.proposta.cliente.cpf_cnpj
    revisao.enviada_em = timezone.now()
    revisao.congelada = True
    revisao.save()
    _registrar_status(revisao.proposta, Proposta.Status.ENVIADA, usuario)
    return revisao


@transaction.atomic
def criar_nova_revisao(revisao, usuario=None):
    origem = PropostaRevisao.objects.select_for_update().get(pk=revisao.pk)
    if not origem.congelada:
        raise ValidationError("Envie a revisão atual antes de criar uma nova.")
    proposta = origem.proposta
    _validar_transicao(proposta, Proposta.Status.EM_REVISAO)
    novo_numero = (proposta.revisoes.aggregate(maximo=Max("numero"))["maximo"] or 0) + 1
    campos = [f.name for f in PropostaRevisao._meta.fields if f.name not in {"id", "numero", "congelada", "enviada_em", "criado_em", "criado_por", "empresa_nome_snapshot", "empresa_documento_snapshot", "cliente_nome_snapshot", "cliente_documento_snapshot"}]
    dados = {campo: getattr(origem, campo) for campo in campos if campo != "proposta"}
    nova = PropostaRevisao.objects.create(proposta=proposta, numero=novo_numero, congelada=False, enviada_em=None, criado_por=usuario, **dados)
    for classe, relacionamento in ((PropostaItem, "itens"), (PropostaTributo, "tributos"), (PropostaLinhaPublica, "linhas_publicas")):
        for objeto in getattr(origem, relacionamento).all():
            objeto.pk = None
            objeto.revisao = nova
            objeto.save()
    proposta.revisao_atual = novo_numero
    proposta.save(update_fields=["revisao_atual", "atualizado_em"])
    _registrar_status(proposta, Proposta.Status.EM_REVISAO, usuario, f"Criada revisão {novo_numero}.")
    return nova


@transaction.atomic
def colocar_em_negociacao(proposta, usuario):
    proposta = Proposta.objects.select_for_update().get(pk=proposta.pk)
    revisao = proposta.revisoes.get(numero=proposta.revisao_atual)
    if not revisao.congelada:
        raise ValidationError("A revisão atual precisa estar enviada e congelada.")
    _registrar_status(proposta, Proposta.Status.EM_NEGOCIACAO, usuario)
    return proposta


@transaction.atomic
def aprovar_proposta(proposta, usuario):
    _exigir_permissao(usuario, "aprovar_proposta")
    _exigir_permissao(usuario, "criar_obra_proposta")
    proposta = Proposta.objects.select_for_update().select_related("empresa", "cliente", "centro_custo").get(pk=proposta.pk)
    _validar_transicao(proposta, Proposta.Status.APROVADA)
    revisao = proposta.revisoes.select_for_update().get(numero=proposta.revisao_atual)
    if not revisao.congelada or not revisao.enviada_em:
        raise ValidationError("Somente uma revisão enviada e congelada pode ser aprovada.")
    if revisao.preco_venda_final <= 0:
        raise ValidationError("O valor final da revisão deve ser positivo.")
    if not revisao.valida_ate or revisao.valida_ate < timezone.localdate():
        raise ValidationError("A revisão está fora da validade e não pode ser aprovada.")
    if proposta.centro_custo_id:
        raise ValidationError("Esta proposta já possui uma obra vinculada.")
    if CentroCusto.objects.select_for_update().filter(empresa=proposta.empresa, codigo=proposta.codigo).exists():
        raise ValidationError(f"Já existe uma obra com o código {proposta.codigo} nesta empresa. A aprovação foi bloqueada sem realizar vínculo automático.")
    obra = CentroCusto.objects.create(empresa=proposta.empresa, cliente=proposta.cliente, codigo=proposta.codigo, nome=revisao.nome_servico, descricao=f"Obra criada a partir da proposta {proposta.codigo}, revisão {revisao.numero}.", ativo=True)
    proposta.centro_custo = obra
    proposta.revisao_aprovada = revisao
    proposta.aprovada_por = usuario
    proposta.aprovada_em = timezone.now()
    proposta.save(update_fields=["centro_custo", "revisao_aprovada", "aprovada_por", "aprovada_em", "atualizado_em"])
    _registrar_status(proposta, Proposta.Status.APROVADA, usuario, f"Obra {obra.codigo} criada e vinculada.")
    return proposta, obra


@transaction.atomic
def rejeitar_proposta(proposta, usuario, motivo):
    _exigir_permissao(usuario, "rejeitar_proposta")
    if not (motivo or "").strip():
        raise ValidationError("Informe o motivo da rejeição.")
    proposta = Proposta.objects.select_for_update().get(pk=proposta.pk)
    _registrar_status(proposta, Proposta.Status.REJEITADA, usuario, motivo.strip())
    return proposta


@transaction.atomic
def cancelar_proposta(proposta, usuario, motivo):
    _exigir_permissao(usuario, "cancelar_proposta")
    if not (motivo or "").strip():
        raise ValidationError("Informe o motivo do cancelamento.")
    proposta = Proposta.objects.select_for_update().get(pk=proposta.pk)
    _registrar_status(proposta, Proposta.Status.CANCELADA, usuario, motivo.strip())
    return proposta


def montar_contexto_publico_proposta(revisao):
    """Allowlist pública: nunca retorna models nem campos internos."""
    materiais, servicos = [], []
    for linha in revisao.linhas_publicas.all():
        dado = {"descricao": linha.descricao, "quantidade": linha.quantidade, "unidade": linha.unidade, "valor_unitario": linha.valor_unitario, "valor_total": linha.valor_total, "observacao": linha.observacao}
        (materiais if linha.grupo == PropostaLinhaPublica.Grupo.MATERIAL else servicos).append(dado)
    subtotal_materiais = _dinheiro(sum((x["valor_total"] for x in materiais), Decimal("0")))
    subtotal_servicos = _dinheiro(sum((x["valor_total"] for x in servicos), Decimal("0")))
    return {
        "cabecalho": {"empresa": revisao.empresa_nome_snapshot or revisao.proposta.empresa.nome_fantasia or revisao.proposta.empresa.razao_social, "documento_empresa": revisao.empresa_documento_snapshot or revisao.proposta.empresa.cnpj, "data": revisao.data_proposta, "cliente": revisao.cliente_nome_snapshot or revisao.proposta.cliente.razao_social, "documento_cliente": revisao.cliente_documento_snapshot or revisao.proposta.cliente.cpf_cnpj, "aos_cuidados_de": revisao.aos_cuidados_de, "numero": revisao.proposta.codigo, "revisao": revisao.numero, "servico": revisao.nome_servico},
        "blocos": {"texto_introdutorio": revisao.texto_introdutorio if revisao.exibir_texto_introdutorio else "", "escopo_incluido": revisao.escopo_incluido, "nao_incluso": revisao.nao_incluso, "normas_procedimentos": revisao.normas_procedimentos if revisao.exibir_normas_procedimentos else "", "qualificacao_mao_obra": revisao.qualificacao_mao_obra if revisao.exibir_qualificacao_mao_obra else "", "obrigacoes_contratada": revisao.obrigacoes_contratada if revisao.exibir_obrigacoes_contratada else "", "observacoes_comerciais": revisao.observacoes_comerciais if revisao.exibir_observacoes_comerciais else ""},
        "materiais": materiais, "servicos": servicos,
        "valores": {"subtotal_materiais": subtotal_materiais, "subtotal_servicos": subtotal_servicos, "total": _dinheiro(revisao.preco_venda_final)},
        "condicoes": {"faturamento": revisao.observacao_faturamento, "impostos": revisao.texto_impostos, "prazo": revisao.prazo_entrega, "frete": revisao.tipo_frete, "pagamento": revisao.condicao_pagamento, "dados_bancarios": revisao.dados_bancarios, "multa_juros": revisao.multa_juros_atraso, "protesto": revisao.regra_protesto, "validade": revisao.valida_ate},
        "responsavel": {"nome": revisao.responsavel_nome, "cargo": revisao.responsavel_cargo, "assinatura": revisao.assinatura_textual}, "rodape": revisao.rodape,
    }
