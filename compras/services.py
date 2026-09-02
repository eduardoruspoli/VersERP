from django.core.exceptions import PermissionDenied, ValidationError
from calendar import monthrange
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (
    CotacaoFornecedor, DocumentoCompra, DocumentoCompraItem, DocumentoCompraItemRecebimento,
    DocumentoCompraParcela, IntegracaoDocumentoFinanceiro,
    DocumentoCompraPedido, DivergenciaDocumentoCompra, EscolhaCotacaoItem,
    HistoricoPedidoCompra, HistoricoProcessoCotacao,
    DivergenciaRecebimento, HistoricoSolicitacaoCompra, PedidoCompra, PedidoCompraItem,
    PedidoItemAlocacaoObra, RecebimentoCompra, RecebimentoCompraItem,
    ProcessoCotacao, SolicitacaoCompra, SolicitacaoCompraItem,
)


def _exigir(usuario, permissao):
    if not usuario or not usuario.has_perm(f"compras.{permissao}"):
        raise PermissionDenied("Você não possui permissão para esta ação.")


def _alterar_status(solicitacao, novo_status, usuario, observacao=""):
    permitidas = {
        SolicitacaoCompra.Status.RASCUNHO: {SolicitacaoCompra.Status.ABERTA, SolicitacaoCompra.Status.CANCELADA},
        SolicitacaoCompra.Status.ABERTA: {SolicitacaoCompra.Status.CANCELADA},
    }
    if novo_status not in permitidas.get(solicitacao.status, set()):
        raise ValidationError(f"Transição inválida de {solicitacao.get_status_display()} para {dict(SolicitacaoCompra.Status.choices)[novo_status]}.")
    anterior = solicitacao.status
    SolicitacaoCompra.objects.filter(pk=solicitacao.pk).update(status=novo_status)
    solicitacao.status = novo_status
    HistoricoSolicitacaoCompra.objects.create(solicitacao=solicitacao, status_anterior=anterior, status_novo=novo_status, usuario=usuario, observacao=observacao)


@transaction.atomic
def abrir_solicitacao(solicitacao, usuario):
    _exigir(usuario, "change_solicitacaocompra")
    solicitacao = SolicitacaoCompra.objects.select_for_update().get(pk=solicitacao.pk)
    if not solicitacao.itens.filter(cancelado=False).exists():
        raise ValidationError("Inclua ao menos um item ativo antes de abrir a solicitação.")
    _alterar_status(solicitacao, SolicitacaoCompra.Status.ABERTA, usuario)
    return solicitacao


@transaction.atomic
def cancelar_solicitacao(solicitacao, usuario, motivo):
    _exigir(usuario, "cancelar_solicitacao")
    if not (motivo or "").strip():
        raise ValidationError("Informe o motivo do cancelamento.")
    solicitacao = SolicitacaoCompra.objects.select_for_update().get(pk=solicitacao.pk)
    _alterar_status(solicitacao, SolicitacaoCompra.Status.CANCELADA, usuario, motivo.strip())
    return solicitacao


CENTAVO = Decimal("0.01")


def _ratear_centavos(valor, ofertas):
    valor = Decimal(valor or 0).quantize(CENTAVO, ROUND_HALF_UP)
    ofertas = list(ofertas)
    if not ofertas or not valor:
        return {oferta.pk: Decimal("0.00") for oferta in ofertas}
    pesos = {oferta.pk: max(Decimal(oferta.preco_total), Decimal("0")) for oferta in ofertas}
    total = sum(pesos.values(), Decimal("0"))
    if not total:
        pesos = {oferta.pk: Decimal("1") for oferta in ofertas}; total = Decimal(len(ofertas))
    resultado = {oferta.pk: (valor * pesos[oferta.pk] / total).quantize(CENTAVO, ROUND_DOWN) for oferta in ofertas}
    diferenca = valor - sum(resultado.values(), Decimal("0"))
    centavos = int((diferenca / CENTAVO).to_integral_value())
    ordem = sorted(ofertas, key=lambda o: (-pesos[o.pk], o.pk))
    passo = CENTAVO if centavos > 0 else -CENTAVO
    for indice in range(abs(centavos)):
        resultado[ordem[indice % len(ordem)].pk] += passo
    return resultado


def calcular_custos_cotacao(cotacao):
    ofertas = list(cotacao.itens.filter(disponivel=True).select_related("processo_item"))
    parcelas = {
        "frete": _ratear_centavos(cotacao.valor_frete, ofertas),
        "desconto": _ratear_centavos(cotacao.desconto_global, ofertas),
        "impostos": _ratear_centavos(cotacao.impostos_globais if cotacao.impostos_compoem_custo else 0, ofertas),
        "outras": _ratear_centavos(cotacao.outras_despesas, ofertas),
    }
    return {
        oferta.pk: {
            "oferta": oferta,
            "frete_rateado": parcelas["frete"][oferta.pk],
            "desconto_global_rateado": parcelas["desconto"][oferta.pk],
            "impostos_globais_rateados": parcelas["impostos"][oferta.pk],
            "outras_despesas_rateadas": parcelas["outras"][oferta.pk],
            "custo_efetivo": (oferta.preco_total - oferta.desconto_item + oferta.impostos_item
                + parcelas["frete"][oferta.pk] - parcelas["desconto"][oferta.pk]
                + parcelas["impostos"][oferta.pk] + parcelas["outras"][oferta.pk]).quantize(CENTAVO),
        } for oferta in ofertas
    }


def montar_mapa_comparativo(processo):
    custos = {}
    for cotacao in processo.cotacoes_fornecedor.filter(status=CotacaoFornecedor.Status.RECEBIDA).prefetch_related("itens"):
        custos.update(calcular_custos_cotacao(cotacao))
    hoje = timezone.localdate()
    linhas = []
    for item in processo.itens.select_related("solicitacao_item__solicitacao__obra").prefetch_related("ofertas__cotacao__fornecedor"):
        ofertas = []
        for oferta in item.ofertas.all():
            info = custos.get(oferta.pk)
            vencida = bool(oferta.cotacao.validade and oferta.cotacao.validade < hoje)
            if info:
                ofertas.append({**info, "vencida": vencida, "elegivel": oferta.disponivel and not vencida})
        elegiveis = [o for o in ofertas if o["elegivel"]]
        menor_preco = min((o["oferta"].preco_total for o in elegiveis), default=None)
        menor_custo = min((o["custo_efetivo"] for o in elegiveis), default=None)
        for oferta in ofertas:
            oferta["menor_preco"] = oferta["elegivel"] and oferta["oferta"].preco_total == menor_preco
            oferta["menor_custo"] = oferta["elegivel"] and oferta["custo_efetivo"] == menor_custo
        linhas.append({"item": item, "ofertas": ofertas, "menor_preco": menor_preco, "menor_custo": menor_custo})
    return linhas


@transaction.atomic
def iniciar_processo_cotacao(processo, usuario):
    _exigir(usuario, "change_processocotacao")
    processo = ProcessoCotacao.objects.select_for_update().get(pk=processo.pk)
    if processo.status != ProcessoCotacao.Status.RASCUNHO:
        raise ValidationError("Somente processos em rascunho podem ser iniciados.")
    if not processo.itens.exists(): raise ValidationError("Inclua ao menos um item.")
    anterior = processo.status
    ProcessoCotacao.objects.filter(pk=processo.pk).update(status=ProcessoCotacao.Status.EM_ANDAMENTO)
    processo.status = ProcessoCotacao.Status.EM_ANDAMENTO
    HistoricoProcessoCotacao.objects.create(processo=processo, status_anterior=anterior, status_novo=processo.status, usuario=usuario)
    solicitacao_ids = SolicitacaoCompra.objects.filter(
        itens__itens_processo_cotacao__processo=processo
    ).values_list("pk", flat=True).distinct()
    solicitacoes = SolicitacaoCompra.objects.select_for_update().filter(
        pk__in=solicitacao_ids
    )
    for solicitacao in solicitacoes:
        if solicitacao.status == SolicitacaoCompra.Status.ABERTA:
            SolicitacaoCompra.objects.filter(pk=solicitacao.pk).update(status=SolicitacaoCompra.Status.EM_COTACAO)
            HistoricoSolicitacaoCompra.objects.create(solicitacao=solicitacao, status_anterior=SolicitacaoCompra.Status.ABERTA, status_novo=SolicitacaoCompra.Status.EM_COTACAO, usuario=usuario, observacao=f"Incluída em {processo.identificacao}.")
    return processo


@transaction.atomic
def selecionar_oferta(processo_item, oferta, usuario, justificativa="", observacao=""):
    _exigir(usuario, "selecionar_fornecedor")
    processo = ProcessoCotacao.objects.select_for_update().get(pk=processo_item.processo_id)
    if processo.status != ProcessoCotacao.Status.EM_ANDAMENTO: raise ValidationError("O processo não está em andamento.")
    if oferta.processo_item_id != processo_item.pk or oferta.cotacao.processo_id != processo.pk: raise ValidationError("A oferta não pertence a este item e processo.")
    if oferta.cotacao.status != CotacaoFornecedor.Status.RECEBIDA or not oferta.disponivel: raise ValidationError("A oferta não está disponível para escolha.")
    if oferta.cotacao.validade and oferta.cotacao.validade < timezone.localdate(): raise ValidationError("A cotação está vencida.")
    linha = next(l for l in montar_mapa_comparativo(processo) if l["item"].pk == processo_item.pk)
    escolhida = next(o for o in linha["ofertas"] if o["oferta"].pk == oferta.pk)
    if escolhida["custo_efetivo"] != linha["menor_custo"] and not justificativa.strip():
        raise ValidationError("Justifique a escolha que não possui o menor custo efetivo.")
    escolha, _ = EscolhaCotacaoItem.objects.update_or_create(processo_item=processo_item, defaults={
        "oferta_escolhida": oferta, "escolhido_por": usuario, "justificativa": justificativa.strip(),
        "era_menor_preco": escolhida["menor_preco"], "observacao": observacao.strip(),
    })
    return escolha


@transaction.atomic
def concluir_processo_cotacao(processo, usuario):
    _exigir(usuario, "change_processocotacao")
    processo = ProcessoCotacao.objects.select_for_update().get(pk=processo.pk)
    if processo.status != ProcessoCotacao.Status.EM_ANDAMENTO: raise ValidationError("Somente processos em andamento podem ser concluídos.")
    pendentes = [i for i in processo.itens.all() if not i.nao_comprar and not hasattr(i, "escolha")]
    if pendentes: raise ValidationError("Todos os itens devem ter fornecedor escolhido ou justificativa de não compra.")
    ProcessoCotacao.objects.filter(pk=processo.pk).update(status=ProcessoCotacao.Status.CONCLUIDA)
    HistoricoProcessoCotacao.objects.create(processo=processo, status_anterior=processo.status, status_novo=ProcessoCotacao.Status.CONCLUIDA, usuario=usuario)
    processo.status = ProcessoCotacao.Status.CONCLUIDA
    return processo


@transaction.atomic
def cancelar_processo_cotacao(processo, usuario, motivo):
    _exigir(usuario, "cancelar_cotacao")
    if not motivo.strip(): raise ValidationError("Informe o motivo do cancelamento.")
    referencia = processo
    processo = ProcessoCotacao.objects.select_for_update().get(pk=processo.pk)
    if processo.status not in {ProcessoCotacao.Status.RASCUNHO, ProcessoCotacao.Status.EM_ANDAMENTO}: raise ValidationError("Este processo não pode ser cancelado.")
    anterior = processo.status
    ProcessoCotacao.objects.filter(pk=processo.pk).update(status=ProcessoCotacao.Status.CANCELADA)
    HistoricoProcessoCotacao.objects.create(processo=processo, status_anterior=anterior, status_novo=ProcessoCotacao.Status.CANCELADA, usuario=usuario, observacao=motivo.strip())
    processo.status = ProcessoCotacao.Status.CANCELADA
    referencia.status = processo.status
    return processo


def recalcular_pedido(pedido):
    itens = list(pedido.itens.order_by("ordem", "id"))
    for item in itens:
        item.valor_bruto = (item.quantidade * item.valor_unitario).quantize(CENTAVO, ROUND_HALF_UP)
    class Parcela:
        def __init__(self, item): self.pk=item.pk; self.preco_total=item.valor_bruto
    parcelas=[Parcela(i) for i in itens]
    fretes=_ratear_centavos(pedido.frete,parcelas); descontos=_ratear_centavos(pedido.desconto,parcelas)
    impostos=_ratear_centavos(pedido.impostos,parcelas); outras=_ratear_centavos(pedido.outras_despesas,parcelas)
    for item in itens:
        item.desconto=descontos[item.pk]; item.impostos=impostos[item.pk]
        item.frete_alocado=fretes[item.pk]; item.outras_despesas_alocadas=outras[item.pk]
        item.custo_total=(item.valor_bruto-item.desconto+item.impostos+item.frete_alocado+item.outras_despesas_alocadas).quantize(CENTAVO)
        PedidoCompraItem.objects.filter(pk=item.pk).update(valor_bruto=item.valor_bruto,desconto=item.desconto,impostos=item.impostos,frete_alocado=item.frete_alocado,outras_despesas_alocadas=item.outras_despesas_alocadas,custo_total=item.custo_total)
    subtotal=sum((i.valor_bruto for i in itens),Decimal("0.00"))
    total=sum((i.custo_total for i in itens),Decimal("0.00"))
    PedidoCompra.objects.filter(pk=pedido.pk).update(subtotal=subtotal,total=total)
    pedido.subtotal=subtotal; pedido.total=total
    return pedido


def validar_alocacoes_pedido(pedido):
    erros=[]
    for item in pedido.itens.prefetch_related("alocacoes"):
        alocacoes=list(item.alocacoes.all())
        if any(a.obra.empresa_id != pedido.empresa_id for a in alocacoes): erros.append(f"O item {item.descricao_mercadoria} possui obra de outra empresa.")
        qtd=sum((a.quantidade for a in alocacoes),Decimal("0"))
        valor=sum((a.valor for a in alocacoes),Decimal("0"))
        if qtd != item.quantidade or valor != item.custo_total:
            erros.append(f"O item {item.descricao_mercadoria} não fecha quantidade e valor nas obras.")
    if erros: raise ValidationError(erros)


@transaction.atomic
def gerar_pedidos_da_cotacao(processo, numeros_por_fornecedor, usuario):
    _exigir(usuario,"criar_pedido")
    processo=ProcessoCotacao.objects.select_for_update().get(pk=processo.pk)
    if processo.status != ProcessoCotacao.Status.CONCLUIDA: raise ValidationError("A cotação deve estar concluída.")
    escolhas=list(EscolhaCotacaoItem.objects.filter(processo_item__processo=processo).select_related("oferta_escolhida__cotacao__fornecedor","oferta_escolhida__processo_item__solicitacao_item__solicitacao__obra__proposta_origem","oferta_escolhida__processo_item__solicitacao_item__proposta_item"))
    if not escolhas: raise ValidationError("A cotação não possui escolhas para gerar pedidos.")
    if EscolhaCotacaoItem.objects.filter(pk__in=[e.pk for e in escolhas],pedido_item__isnull=False).exists(): raise ValidationError("Já existe pedido para uma ou mais escolhas desta cotação.")
    grupos={}
    for escolha in escolhas: grupos.setdefault(escolha.oferta_escolhida.cotacao.fornecedor_id,[]).append(escolha)
    pedidos=[]
    for fornecedor_id, grupo in grupos.items():
        numero=(numeros_por_fornecedor.get(fornecedor_id) or numeros_por_fornecedor.get(str(fornecedor_id)) or "").strip()
        if not numero: raise ValidationError("Informe o número Versatile de cada pedido.")
        cotacao=grupo[0].oferta_escolhida.cotacao
        pedido=PedidoCompra.objects.create(empresa=processo.empresa,fornecedor=cotacao.fornecedor,origem=PedidoCompra.Origem.COTACAO,numero_pedido_versatile=numero,nome_vendedor_fornecedor_snapshot=cotacao.nome_contato,telefone_vendedor_snapshot=cotacao.telefone,email_vendedor_snapshot=cotacao.email,condicao_pagamento=cotacao.condicao_pagamento,prazo_entrega=cotacao.prazo_entrega,tipo_frete=cotacao.tipo_frete,frete=cotacao.valor_frete,desconto=cotacao.desconto_global+sum((e.oferta_escolhida.desconto_item for e in grupo),Decimal("0")),impostos=(cotacao.impostos_globais if cotacao.impostos_compoem_custo else Decimal("0"))+sum((e.oferta_escolhida.impostos_item for e in grupo),Decimal("0")),outras_despesas=cotacao.outras_despesas,responsavel_nome_snapshot=usuario.get_full_name() or usuario.get_username(),criado_por=usuario)
        for ordem,escolha in enumerate(grupo,1):
            oferta=escolha.oferta_escolhida; si=escolha.processo_item.solicitacao_item; proposta=getattr(si.solicitacao.obra,"proposta_origem",None)
            item=PedidoCompraItem.objects.create(pedido=pedido,escolha_cotacao_item=escolha,solicitacao_item=si,proposta_item=si.proposta_item,proposta_codigo_snapshot=proposta.codigo if proposta else "",descricao_mercadoria=si.descricao,quantidade=oferta.quantidade_ofertada,unidade=oferta.unidade,valor_unitario=oferta.preco_unitario,plano_conta=si.plano_conta_previsto,observacao=oferta.observacao,ordem=ordem)
            PedidoItemAlocacaoObra.objects.create(pedido_item=item,obra=si.solicitacao.obra,solicitacao_item=si,proposta_item=si.proposta_item,quantidade=item.quantidade,valor=0,tipo_origem=si.tipo_origem)
        recalcular_pedido(pedido)
        for item in pedido.itens.all(): PedidoItemAlocacaoObra.objects.filter(pedido_item=item).update(valor=item.custo_total)
        pedidos.append(pedido)
    return pedidos


def _mudar_pedido(pedido,usuario,novo_status,permissao,observacao=""):
    _exigir(usuario,permissao)
    permitidas={PedidoCompra.Status.RASCUNHO:{PedidoCompra.Status.AGUARDANDO_APROVACAO},PedidoCompra.Status.AGUARDANDO_APROVACAO:{PedidoCompra.Status.APROVADO,PedidoCompra.Status.REJEITADO},PedidoCompra.Status.APROVADO:{PedidoCompra.Status.ENVIADO_FORNECEDOR,PedidoCompra.Status.CANCELADO},PedidoCompra.Status.ENVIADO_FORNECEDOR:{PedidoCompra.Status.CANCELADO}}
    if novo_status not in permitidas.get(pedido.status,set()): raise ValidationError("Transição de status inválida.")
    anterior=pedido.status
    atualizacoes={"status":novo_status}
    if novo_status==PedidoCompra.Status.APROVADO: atualizacoes.update(aprovado_por=usuario,aprovado_em=timezone.now())
    if novo_status==PedidoCompra.Status.ENVIADO_FORNECEDOR: atualizacoes.update(enviado_por=usuario,enviado_em=timezone.now())
    PedidoCompra.objects.filter(pk=pedido.pk).update(**atualizacoes)
    for campo,valor in atualizacoes.items(): setattr(pedido,campo,valor)
    HistoricoPedidoCompra.objects.create(pedido=pedido,status_anterior=anterior,status_novo=novo_status,usuario=usuario,observacao=observacao)
    return pedido


@transaction.atomic
def submeter_pedido(pedido,usuario):
    _exigir(usuario,"change_pedidocompra")
    pedido=PedidoCompra.objects.select_for_update().get(pk=pedido.pk); recalcular_pedido(pedido)
    if not pedido.itens.exists() or pedido.total<=0: raise ValidationError("O pedido deve possuir itens e total positivo.")
    validar_alocacoes_pedido(pedido)
    return _mudar_pedido(pedido,usuario,PedidoCompra.Status.AGUARDANDO_APROVACAO,"change_pedidocompra")


@transaction.atomic
def aprovar_pedido(pedido,usuario):
    _exigir(usuario,"aprovar_pedido")
    pedido=PedidoCompra.objects.select_for_update().select_related("fornecedor").get(pk=pedido.pk); recalcular_pedido(pedido)
    if not pedido.numero_pedido_versatile.strip() or not pedido.fornecedor.ativo or not pedido.condicao_pagamento.strip() or not pedido.prazo_entrega.strip(): raise ValidationError("Número, fornecedor ativo, condição de pagamento e prazo são obrigatórios.")
    if pedido.total<=0: raise ValidationError("O total deve ser positivo.")
    validar_alocacoes_pedido(pedido)
    return _mudar_pedido(pedido,usuario,PedidoCompra.Status.APROVADO,"aprovar_pedido")


@transaction.atomic
def rejeitar_pedido(pedido,usuario,motivo):
    _exigir(usuario,"rejeitar_pedido")
    if not motivo.strip(): raise ValidationError("Informe o motivo da rejeição.")
    pedido=PedidoCompra.objects.select_for_update().get(pk=pedido.pk)
    return _mudar_pedido(pedido,usuario,PedidoCompra.Status.REJEITADO,"rejeitar_pedido",motivo.strip())


@transaction.atomic
def cancelar_pedido(pedido,usuario,motivo):
    _exigir(usuario,"cancelar_pedido")
    if not motivo.strip(): raise ValidationError("Informe o motivo do cancelamento.")
    pedido=PedidoCompra.objects.select_for_update().get(pk=pedido.pk)
    return _mudar_pedido(pedido,usuario,PedidoCompra.Status.CANCELADO,"cancelar_pedido",motivo.strip())


@transaction.atomic
def enviar_pedido(pedido,usuario):
    _exigir(usuario,"enviar_pedido")
    pedido=PedidoCompra.objects.select_for_update().get(pk=pedido.pk)
    return _mudar_pedido(pedido,usuario,PedidoCompra.Status.ENVIADO_FORNECEDOR,"enviar_pedido")


def quantidades_recebimento_pedido(pedido):
    acumuladas=dict(RecebimentoCompraItem.objects.filter(recebimento__pedido=pedido,recebimento__status=RecebimentoCompra.Status.CONFIRMADO).values_list("pedido_item_id").annotate(total=Sum("quantidade_aceita")))
    return {item.pk:{"pedida":item.quantidade,"recebida":acumuladas.get(item.pk,Decimal("0")),"pendente":item.quantidade-acumuladas.get(item.pk,Decimal("0"))} for item in pedido.itens.all()}


def _recalcular_status_recebimento_pedido(pedido,usuario,observacao):
    quantidades=quantidades_recebimento_pedido(pedido)
    recebida=sum((v["recebida"] for v in quantidades.values()),Decimal("0"))
    completo=bool(quantidades) and all(v["pendente"]==0 for v in quantidades.values())
    origem_recebimento=pedido.historico.filter(status_novo__in=[PedidoCompra.Status.PARCIALMENTE_RECEBIDO,PedidoCompra.Status.RECEBIDO],status_anterior__in=[PedidoCompra.Status.APROVADO,PedidoCompra.Status.ENVIADO_FORNECEDOR]).order_by("-id").values_list("status_anterior",flat=True).first()
    base=origem_recebimento or (PedidoCompra.Status.ENVIADO_FORNECEDOR if pedido.enviado_em else PedidoCompra.Status.APROVADO)
    novo=PedidoCompra.Status.RECEBIDO if completo else (PedidoCompra.Status.PARCIALMENTE_RECEBIDO if recebida>0 else base)
    if pedido.status!=novo:
        anterior=pedido.status; PedidoCompra.objects.filter(pk=pedido.pk).update(status=novo); pedido.status=novo
        HistoricoPedidoCompra.objects.create(pedido=pedido,status_anterior=anterior,status_novo=novo,usuario=usuario,observacao=observacao)
    return pedido


@transaction.atomic
def confirmar_recebimento(recebimento,usuario):
    _exigir(usuario,"registrar_recebimento")
    recebimento=RecebimentoCompra.objects.select_for_update().select_related("pedido").get(pk=recebimento.pk)
    pedido=PedidoCompra.objects.select_for_update().get(pk=recebimento.pedido_id)
    if recebimento.status!=RecebimentoCompra.Status.RASCUNHO: raise ValidationError("Somente recebimentos em rascunho podem ser confirmados.")
    if pedido.status not in {PedidoCompra.Status.APROVADO,PedidoCompra.Status.ENVIADO_FORNECEDOR,PedidoCompra.Status.PARCIALMENTE_RECEBIDO}: raise ValidationError("O pedido não permite novos recebimentos.")
    itens=list(recebimento.itens.select_related("pedido_item"))
    if not itens: raise ValidationError("Inclua ao menos um item no recebimento.")
    PedidoCompraItem.objects.select_for_update().filter(pedido=pedido).count()
    acumuladas=quantidades_recebimento_pedido(pedido)
    for item in itens:
        if item.quantidade_aceita+item.quantidade_rejeitada>item.quantidade_recebida: raise ValidationError("Quantidade aceita mais rejeitada supera a recebida.")
        if item.quantidade_aceita>acumuladas[item.pedido_item_id]["pendente"]: raise ValidationError(f"A quantidade aceita de {item.pedido_item.descricao_mercadoria} supera a pendência do pedido.")
    if not any(i.quantidade_recebida>0 for i in itens): raise ValidationError("Informe ao menos uma quantidade recebida.")
    agora=timezone.now(); RecebimentoCompra.objects.filter(pk=recebimento.pk).update(status=RecebimentoCompra.Status.CONFIRMADO,confirmado_por=usuario,confirmado_em=agora)
    recebimento.status=RecebimentoCompra.Status.CONFIRMADO; recebimento.confirmado_por=usuario; recebimento.confirmado_em=agora
    _recalcular_status_recebimento_pedido(pedido,usuario,f"Confirmação do {recebimento.identificacao}.")
    return recebimento


@transaction.atomic
def cancelar_recebimento(recebimento,usuario,motivo):
    _exigir(usuario,"cancelar_recebimento")
    if not motivo.strip(): raise ValidationError("Informe o motivo do cancelamento.")
    referencia=recebimento
    recebimento=RecebimentoCompra.objects.select_for_update().select_related("pedido").get(pk=recebimento.pk)
    pedido=PedidoCompra.objects.select_for_update().get(pk=recebimento.pedido_id)
    if recebimento.status!=RecebimentoCompra.Status.CONFIRMADO: raise ValidationError("Somente recebimentos confirmados podem ser cancelados.")
    agora=timezone.now(); RecebimentoCompra.objects.filter(pk=recebimento.pk).update(status=RecebimentoCompra.Status.CANCELADO,cancelado_por=usuario,cancelado_em=agora,motivo_cancelamento=motivo.strip())
    recebimento.status=RecebimentoCompra.Status.CANCELADO; recebimento.cancelado_por=usuario; recebimento.cancelado_em=agora; recebimento.motivo_cancelamento=motivo.strip()
    referencia.status=recebimento.status; referencia.cancelado_por=usuario; referencia.cancelado_em=agora; referencia.motivo_cancelamento=motivo.strip()
    _recalcular_status_recebimento_pedido(pedido,usuario,f"Cancelamento do {recebimento.identificacao}: {motivo.strip()}")
    return recebimento


@transaction.atomic
def resolver_divergencia(divergencia,usuario,solucao):
    _exigir(usuario,"resolver_divergencia_recebimento")
    if not solucao.strip(): raise ValidationError("Informe a solução da divergência.")
    referencia=divergencia
    divergencia=DivergenciaRecebimento.objects.select_for_update().get(pk=divergencia.pk)
    if divergencia.resolvida: raise ValidationError("A divergência já foi resolvida.")
    agora=timezone.now(); DivergenciaRecebimento.objects.filter(pk=divergencia.pk).update(resolvida=True,resolvida_por=usuario,resolvida_em=agora,solucao=solucao.strip())
    divergencia.resolvida=True; divergencia.resolvida_por=usuario; divergencia.resolvida_em=agora; divergencia.solucao=solucao.strip()
    referencia.resolvida=True; referencia.resolvida_por=usuario; referencia.resolvida_em=agora; referencia.solucao=solucao.strip()
    return divergencia


QUANTIDADE = Decimal("0.0001")


def _ratear_quantidade(valor, alocacoes):
    valor=Decimal(valor or 0).quantize(QUANTIDADE,ROUND_DOWN); alocacoes=list(alocacoes)
    if not alocacoes: return {}
    total=sum((a.quantidade for a in alocacoes),Decimal("0"))
    if not total: return {a.pk:Decimal("0") for a in alocacoes}
    resultado={a.pk:(valor*a.quantidade/total).quantize(QUANTIDADE,ROUND_DOWN) for a in alocacoes}
    restante=valor-sum(resultado.values(),Decimal("0")); passos=int((restante/QUANTIDADE).to_integral_value())
    ordem=sorted(alocacoes,key=lambda a:(-a.quantidade,a.pk))
    for indice in range(passos): resultado[ordem[indice%len(ordem)].pk]+=QUANTIDADE
    return resultado


def calcular_previsto_comprado(obra, *, tipo_origem="", status_pedido="", plano_conta_id=None, somente_divergencias=False):
    """Compara compras da obra com a revisão aprovada, sem persistir derivados."""
    from django.db.models import Prefetch
    proposta=getattr(obra,"proposta_origem",None)
    if not proposta or not proposta.revisao_aprovada_id:
        return {"disponivel":False,"motivo":"A obra não possui proposta com revisão aprovada.","obra":obra}
    previstos=list(proposta.revisao_aprovada.itens.select_related("plano_conta").order_by("ordem","id"))
    if plano_conta_id: previstos=[p for p in previstos if p.plano_conta_id==int(plano_conta_id)]
    solicitacoes=list(SolicitacaoCompraItem.objects.filter(solicitacao__obra=obra,cancelado=False).select_related("solicitacao","proposta_item"))
    solicitadas={}
    for item in solicitacoes:
        if item.proposta_item_id: solicitadas[item.proposta_item_id]=solicitadas.get(item.proposta_item_id,Decimal("0"))+item.quantidade
    status_validos=[PedidoCompra.Status.APROVADO,PedidoCompra.Status.ENVIADO_FORNECEDOR,PedidoCompra.Status.PARCIALMENTE_RECEBIDO,PedidoCompra.Status.RECEBIDO]
    itens_recebidos=RecebimentoCompraItem.objects.filter(recebimento__status=RecebimentoCompra.Status.CONFIRMADO).select_related("recebimento")
    pedidos_qs=PedidoCompraItem.objects.filter(pedido__status__in=status_validos,alocacoes__obra=obra).select_related("pedido__fornecedor","solicitacao_item","proposta_item").prefetch_related("alocacoes",Prefetch("itens_recebimento",queryset=itens_recebidos),"itens_recebimento__divergencias").distinct()
    if status_pedido: pedidos_qs=pedidos_qs.filter(pedido__status=status_pedido)
    itens_pedido=list(pedidos_qs)
    compras_previstas={p.pk:[] for p in previstos}; nao_previstos=[]; substituicoes=[]; pedidos_relacionados={}
    total_comprado=Decimal("0"); total_recebido=Decimal("0"); pedidos_pendentes=set(); alertas=[]
    for item in itens_pedido:
        alocacoes=list(item.alocacoes.all()); alocacao=next((a for a in alocacoes if a.obra_id==obra.pk),None)
        if not alocacao or (tipo_origem and alocacao.tipo_origem!=tipo_origem): continue
        aceita_total=sum((r.quantidade_aceita for r in item.itens_recebimento.all()),Decimal("0"))
        recebidas_rateadas=_ratear_quantidade(aceita_total,alocacoes); quantidade_recebida=recebidas_rateadas.get(alocacao.pk,Decimal("0"))
        valor_recebido=(alocacao.valor*quantidade_recebida/alocacao.quantidade).quantize(CENTAVO,ROUND_HALF_UP) if alocacao.quantidade else Decimal("0")
        divergencias_abertas=sum(1 for r in item.itens_recebimento.all() for d in r.divergencias.all() if not d.resolvida)
        dado={"pedido_item":item,"alocacao":alocacao,"quantidade":alocacao.quantidade,"valor":alocacao.valor,"quantidade_recebida":quantidade_recebida,"valor_recebido":valor_recebido,"pendente_recebimento":max(alocacao.quantidade-quantidade_recebida,Decimal("0")),"divergencias_abertas":divergencias_abertas}
        if somente_divergencias and not (divergencias_abertas or alocacao.tipo_origem in {SolicitacaoCompraItem.TipoOrigem.SUBSTITUICAO,SolicitacaoCompraItem.TipoOrigem.NAO_PREVISTO}): continue
        total_comprado+=alocacao.valor; total_recebido+=valor_recebido
        if dado["pendente_recebimento"]>0: pedidos_pendentes.add(item.pedido_id)
        pedidos_relacionados[item.pedido_id]=item.pedido
        if alocacao.proposta_item_id in compras_previstas: compras_previstas[alocacao.proposta_item_id].append(dado)
        if alocacao.tipo_origem==SolicitacaoCompraItem.TipoOrigem.SUBSTITUICAO: substituicoes.append(dado)
        elif not alocacao.proposta_item_id: nao_previstos.append(dado)
    linhas=[]
    for previsto in previstos:
        compras=compras_previstas.get(previsto.pk,[]); qtd_comprada=sum((c["quantidade"] for c in compras),Decimal("0")); valor_comprado=sum((c["valor"] for c in compras),Decimal("0")); qtd_recebida=sum((c["quantidade_recebida"] for c in compras),Decimal("0")); valor_recebido=sum((c["valor_recebido"] for c in compras),Decimal("0")); qtd_solicitada=solicitadas.get(previsto.pk,Decimal("0"))
        linha={"previsto":previsto,"quantidade_solicitada":qtd_solicitada,"quantidade_comprada":qtd_comprada,"quantidade_recebida":qtd_recebida,"pendente_compra":max(previsto.quantidade-qtd_comprada,Decimal("0")),"diferenca_quantidade":qtd_comprada-previsto.quantidade,"pendente_recebimento":max(qtd_comprada-qtd_recebida,Decimal("0")),"valor_comprado":valor_comprado,"valor_recebido":valor_recebido,"custo_medio":(valor_comprado/qtd_comprada).quantize(Decimal("0.0001"),ROUND_HALF_UP) if qtd_comprada else None,"diferenca_financeira":valor_comprado-previsto.custo_total,"percentual_comprado":(qtd_comprada/previsto.quantidade*100).quantize(CENTAVO) if previsto.quantidade else None,"compras":compras,"alertas":[]}
        if not compras: linha["situacao"]="NAO_COMPRADO"; linha["alertas"].append("Item previsto sem compra")
        elif qtd_comprada<previsto.quantidade: linha["situacao"]="PARCIAL"; linha["alertas"].append("Compra parcial")
        else: linha["situacao"]="COMPRADO"
        if qtd_comprada>previsto.quantidade: linha["alertas"].append("Quantidade acima do previsto")
        if valor_comprado>previsto.custo_total: linha["alertas"].append("Custo acima do previsto")
        if linha["pendente_recebimento"]>0: linha["alertas"].append("Recebimento pendente")
        if any(c["divergencias_abertas"] for c in compras): linha["alertas"].append("Divergência de recebimento aberta")
        linhas.append(linha); alertas.extend(f"{previsto.descricao}: {a}." for a in linha["alertas"])
    for item in nao_previstos: alertas.append(f"Compra não prevista: {item['pedido_item'].descricao_mercadoria}.")
    for item in substituicoes: alertas.append(f"Substituição: {item['pedido_item'].descricao_mercadoria}.")
    previsto_total=sum((p.custo_total for p in previstos),Decimal("0")); solicitado_valor=sum((s.quantidade*(s.custo_unitario_previsto_snapshot or Decimal("0"))) for s in solicitacoes)
    resumo={"custo_previsto":previsto_total,"valor_solicitado":solicitado_valor,"valor_comprado":total_comprado,"valor_recebido":total_recebido,"economia_estouro":previsto_total-total_comprado,"compras_nao_previstas":sum((x["valor"] for x in nao_previstos),Decimal("0")),"itens_sem_compra":sum(1 for x in linhas if not x["compras"]),"pedidos_pendentes_recebimento":len(pedidos_pendentes),"percentual_orcamento_comprado":(total_comprado/previsto_total*100).quantize(CENTAVO) if previsto_total else None,"percentual_comprado_recebido":(total_recebido/total_comprado*100).quantize(CENTAVO) if total_comprado else None}
    return {"disponivel":True,"obra":obra,"proposta":proposta,"revisao":proposta.revisao_aprovada,"resumo":resumo,"itens_previstos":linhas,"nao_previstos":nao_previstos,"substituicoes":substituicoes,"pedidos":list(pedidos_relacionados.values()),"alertas":alertas}


def validar_fechamento_documento(documento):
    itens=list(documento.itens.all())
    if not itens: raise ValidationError("Inclua ao menos um item no documento.")
    campos={"valor_bruto":"valor_bruto","desconto":"desconto","frete":"frete_alocado","impostos":"impostos","outras_despesas":"outras_despesas","valor_total":"total"}
    erros=[]
    for cabecalho,item_campo in campos.items():
        soma=sum((getattr(i,item_campo) for i in itens),Decimal("0")).quantize(CENTAVO)
        if soma!=getattr(documento,cabecalho): erros.append(f"A soma de {cabecalho.replace('_',' ')} dos itens ({soma}) não fecha com o documento ({getattr(documento,cabecalho)}).")
    pedidos_itens={i.pedido_item.pedido_id for i in itens if i.pedido_item_id}; pedidos_vinculados=set(documento.vinculos_pedidos.values_list("pedido_id",flat=True))
    if pedidos_itens-pedidos_vinculados: erros.append("Todos os pedidos dos itens devem estar vinculados ao documento.")
    if erros: raise ValidationError(erros)


@transaction.atomic
def vincular_recebimento_documento(documento_item,recebimento_item,quantidade):
    documento_item=DocumentoCompraItem.objects.select_for_update().select_related("documento").get(pk=documento_item.pk)
    recebimento_item=RecebimentoCompraItem.objects.select_for_update().select_related("recebimento","pedido_item__pedido").get(pk=recebimento_item.pk)
    if documento_item.documento.status!=DocumentoCompra.Status.RASCUNHO: raise ValidationError("Somente documentos em rascunho aceitam vínculos.")
    existente=DocumentoCompraItemRecebimento.objects.filter(documento_item=documento_item,recebimento_item=recebimento_item).first()
    usado=DocumentoCompraItemRecebimento.objects.filter(recebimento_item=recebimento_item).exclude(pk=getattr(existente,"pk",None)).aggregate(total=Sum("quantidade_vinculada"))["total"] or Decimal("0")
    quantidade=Decimal(quantidade)
    if quantidade<=0 or usado+quantidade>recebimento_item.quantidade_aceita: raise ValidationError("A quantidade vinculada deve ser positiva e não pode superar o saldo aceito.")
    objeto=existente or DocumentoCompraItemRecebimento(documento_item=documento_item,recebimento_item=recebimento_item)
    objeto.quantidade_vinculada=quantidade; objeto.save(); return objeto


def _criar_divergencia(documento,item,tipo,descricao,quantidade=None,valor=None):
    existente=DivergenciaDocumentoCompra.objects.filter(documento=documento,documento_item=item,tipo=tipo,automatica=True).order_by("-id").first()
    if existente: return existente
    return DivergenciaDocumentoCompra.objects.create(documento=documento,documento_item=item,tipo=tipo,descricao=descricao,quantidade_afetada=quantidade,valor_afetado=valor,bloqueante=True,automatica=True)


@transaction.atomic
def detectar_divergencias_documento(documento,usuario):
    documento=DocumentoCompra.objects.select_for_update().get(pk=documento.pk)
    for item in documento.itens.select_related("pedido_item").prefetch_related("vinculos_recebimentos"):
        pedido_item=item.pedido_item; vinculado=sum((v.quantidade_vinculada for v in item.vinculos_recebimentos.all()),Decimal("0"))
        if not pedido_item or not item.vinculos_recebimentos.exists():
            _criar_divergencia(documento,item,DivergenciaDocumentoCompra.Tipo.ITEM_SEM_VINCULO,"Item sem pedido ou recebimento confirmado vinculado.")
            continue
        if item.quantidade_faturada>vinculado: _criar_divergencia(documento,item,DivergenciaDocumentoCompra.Tipo.QUANTIDADE_MAIOR,"Quantidade faturada maior que a quantidade recebida vinculada.",item.quantidade_faturada-vinculado)
        elif item.quantidade_faturada<vinculado: _criar_divergencia(documento,item,DivergenciaDocumentoCompra.Tipo.QUANTIDADE_MENOR,"Quantidade faturada menor que a quantidade recebida vinculada.",vinculado-item.quantidade_faturada)
        if item.valor_unitario_faturado!=pedido_item.valor_unitario: _criar_divergencia(documento,item,DivergenciaDocumentoCompra.Tipo.PRECO,"Preço faturado diferente do preço negociado.",valor=(item.valor_unitario_faturado-pedido_item.valor_unitario).quantize(CENTAVO))
        proporcao=item.quantidade_faturada/pedido_item.quantidade if pedido_item.quantidade else Decimal("0")
        comparacoes=(("frete_alocado","frete_alocado",DivergenciaDocumentoCompra.Tipo.FRETE),("desconto","desconto",DivergenciaDocumentoCompra.Tipo.DESCONTO),("impostos","impostos",DivergenciaDocumentoCompra.Tipo.IMPOSTO))
        for campo_doc,campo_pedido,tipo in comparacoes:
            esperado=(getattr(pedido_item,campo_pedido)*proporcao).quantize(CENTAVO,ROUND_HALF_UP); informado=getattr(item,campo_doc)
            if informado!=esperado: _criar_divergencia(documento,item,tipo,f"{tipo.label} em relação ao pedido proporcional.",valor=informado-esperado)
    return documento.divergencias.filter(resolvida=False)


def _atualizar_status_documento(documento,status,usuario,**campos):
    valores={"status":status,**campos}; DocumentoCompra.objects.filter(pk=documento.pk).update(**valores)
    documento.status=status
    for campo,valor in campos.items(): setattr(documento,campo,valor)
    return documento


@transaction.atomic
def iniciar_conferencia_documento(documento,usuario):
    _exigir(usuario,"conferir_documento_compra")
    documento=DocumentoCompra.objects.select_for_update().get(pk=documento.pk)
    if documento.status!=DocumentoCompra.Status.RASCUNHO: raise ValidationError("Somente documentos em rascunho podem entrar em conferência.")
    validar_fechamento_documento(documento); agora=timezone.now()
    return _atualizar_status_documento(documento,DocumentoCompra.Status.EM_CONFERENCIA,usuario,enviado_conferencia_por=usuario,enviado_conferencia_em=agora)


@transaction.atomic
def concluir_conferencia_documento(documento,usuario):
    _exigir(usuario,"conferir_documento_compra")
    documento=DocumentoCompra.objects.select_for_update().get(pk=documento.pk)
    if documento.status!=DocumentoCompra.Status.EM_CONFERENCIA: raise ValidationError("O documento não está em conferência.")
    validar_fechamento_documento(documento); abertas=detectar_divergencias_documento(documento,usuario).filter(bloqueante=True).exists()
    if abertas: return _atualizar_status_documento(documento,DocumentoCompra.Status.DIVERGENTE,usuario)
    agora=timezone.now(); return _atualizar_status_documento(documento,DocumentoCompra.Status.CONFERIDO,usuario,conferido_por=usuario,conferido_em=agora)


@transaction.atomic
def reabrir_conferencia_documento(documento,usuario):
    _exigir(usuario,"conferir_documento_compra"); documento=DocumentoCompra.objects.select_for_update().get(pk=documento.pk)
    if documento.status!=DocumentoCompra.Status.DIVERGENTE: raise ValidationError("Somente documentos divergentes podem retornar à conferência.")
    return _atualizar_status_documento(documento,DocumentoCompra.Status.EM_CONFERENCIA,usuario)


@transaction.atomic
def resolver_divergencia_documento(divergencia,usuario,solucao):
    _exigir(usuario,"resolver_divergencia_documento")
    if not solucao.strip(): raise ValidationError("Informe a solução da divergência.")
    referencia=divergencia; divergencia=DivergenciaDocumentoCompra.objects.select_for_update().get(pk=divergencia.pk)
    if divergencia.resolvida: raise ValidationError("A divergência já foi resolvida.")
    agora=timezone.now(); DivergenciaDocumentoCompra.objects.filter(pk=divergencia.pk).update(resolvida=True,resolvida_por=usuario,resolvida_em=agora,solucao=solucao.strip())
    referencia.resolvida=True; referencia.resolvida_por=usuario; referencia.resolvida_em=agora; referencia.solucao=solucao.strip(); return referencia


@transaction.atomic
def cancelar_documento_compra(documento,usuario,motivo):
    _exigir(usuario,"cancelar_documento_compra")
    if not motivo.strip(): raise ValidationError("Informe o motivo do cancelamento.")
    documento=DocumentoCompra.objects.select_for_update().get(pk=documento.pk)
    if documento.status==DocumentoCompra.Status.CANCELADO: raise ValidationError("O documento já está cancelado.")
    agora=timezone.now(); return _atualizar_status_documento(documento,DocumentoCompra.Status.CANCELADO,usuario,cancelado_por=usuario,cancelado_em=agora,motivo_cancelamento=motivo.strip())


def _ratear_valor_por_pesos(total,pesos,chave=lambda item:item):
    """Distribui um valor monetário por pesos, fechando centavos por ordem estável."""
    total=Decimal(total).quantize(CENTAVO,ROUND_HALF_UP); pesos=[(obj,Decimal(peso)) for obj,peso in pesos if Decimal(peso)>0]
    soma=sum((peso for _,peso in pesos),Decimal("0"))
    if not pesos or soma<=0: return {}
    brutos={obj:total*peso/soma for obj,peso in pesos}
    resultado={obj:valor.quantize(CENTAVO,ROUND_DOWN) for obj,valor in brutos.items()}
    centavos=int(((total-sum(resultado.values(),Decimal("0")))/CENTAVO).to_integral_value())
    ordem=sorted(pesos,key=lambda par:(brutos[par[0]]-resultado[par[0]],chave(par[0])),reverse=True)
    for indice in range(centavos): resultado[ordem[indice%len(ordem)][0]]+=CENTAVO
    return resultado


def _somar_meses(data_base,meses):
    indice=data_base.month-1+meses; ano=data_base.year+indice//12; mes=indice%12+1
    return data_base.replace(year=ano,month=mes,day=min(data_base.day,monthrange(ano,mes)[1]))


@transaction.atomic
def gerar_parcelas_documento(documento,usuario,quantidade=1,intervalo_dias=30,primeiro_dias=0):
    _exigir(usuario,"add_documentocompraparcela")
    documento=DocumentoCompra.objects.select_for_update().get(pk=documento.pk)
    if quantidade<=0: raise ValidationError("A quantidade de parcelas deve ser maior que zero.")
    if documento.parcelas.filter(parcela_financeira__isnull=False).exists(): raise ValidationError("As parcelas integradas ao Financeiro estão congeladas.")
    DocumentoCompraParcela.objects.filter(documento=documento).delete()
    valores=_ratear_valor_por_pesos(documento.valor_total,[(numero,Decimal("1")) for numero in range(1,quantidade+1)])
    base=documento.data_emissao or documento.data_entrada
    parcelas=[]
    for numero in range(1,quantidade+1):
        dias=primeiro_dias+(numero-1)*intervalo_dias
        vencimento=_somar_meses(base,dias//30) if intervalo_dias==30 and primeiro_dias%30==0 else base+timedelta(days=dias)
        parcelas.append(DocumentoCompraParcela(documento=documento,numero=numero,vencimento=vencimento,valor=valores[numero]))
    DocumentoCompraParcela.objects.bulk_create(parcelas)
    return list(documento.parcelas.all())


def validar_parcelas_documento(documento):
    parcelas=list(documento.parcelas.order_by("numero")); total=sum((p.valor for p in parcelas),Decimal("0"))
    motivos=[]
    if not parcelas: motivos.append("Defina ao menos uma parcela.")
    if any(p.valor<=0 for p in parcelas): motivos.append("Todas as parcelas devem possuir valor positivo.")
    if total!=documento.valor_total: motivos.append(f"As parcelas totalizam R$ {total:.2f}, mas o documento totaliza R$ {documento.valor_total:.2f}.")
    return parcelas,total,motivos


def montar_preview_financeiro_documento(documento):
    """Monta dados neutros e somente leitura; não persiste objetos financeiros."""
    documento=DocumentoCompra.objects.select_related("empresa","fornecedor").prefetch_related(
        "parcelas","divergencias","itens__plano_conta","itens__pedido_item__pedido",
        "itens__pedido_item__alocacoes__obra",
    ).get(pk=documento.pk)
    motivos=[]; itens=list(documento.itens.all())
    if documento.status!=DocumentoCompra.Status.CONFERIDO: motivos.append("O documento ainda não está conferido.")
    if documento.valor_total<=0: motivos.append("O valor total deve ser maior que zero.")
    if not documento.fornecedor_id or not documento.fornecedor.ativo or documento.fornecedor.classificacao not in {"FORNECEDOR","AMBOS"}: motivos.append("O fornecedor é inválido ou está inativo.")
    if documento.divergencias.filter(bloqueante=True,resolvida=False).exists(): motivos.append("Existem divergências bloqueantes não resolvidas.")
    parcelas,total_parcelas,motivos_parcelas=validar_parcelas_documento(documento); motivos.extend(motivos_parcelas)

    classificacoes={}
    for item in itens:
        conta=item.plano_conta
        if not conta: motivos.append(f"O item {item.descricao_snapshot} não possui classificação contábil."); continue
        if not conta.ativo or conta.estrutural or not conta.aceita_lancamento or conta.tipo not in {"CUSTO","DESPESA"}: motivos.append(f"A conta {conta.codigo} do item {item.descricao_snapshot} é inválida para integração.")
        atual=classificacoes.setdefault(conta.pk,{"plano_conta":conta,"valor":Decimal("0")}); atual["valor"]+=item.total
    classificacoes=list(classificacoes.values()); total_classificacoes=sum((c["valor"] for c in classificacoes),Decimal("0"))
    if total_classificacoes!=documento.valor_total: motivos.append("As classificações contábeis não fecham com o valor total do documento.")

    rateios={}; itens_sem_rateio=[]
    for item in itens:
        pedido=item.pedido_item
        if not pedido: itens_sem_rateio.append(item); continue
        if pedido.pedido.empresa_id!=documento.empresa_id: motivos.append(f"O pedido do item {item.descricao_snapshot} pertence a outra empresa.")
        alocacoes=list(pedido.alocacoes.all())
        distribuicao=_ratear_valor_por_pesos(item.total,[(a,a.quantidade) for a in alocacoes],chave=lambda a:a.pk)
        if not distribuicao: itens_sem_rateio.append(item); continue
        for alocacao,valor in distribuicao.items():
            if alocacao.obra.empresa_id!=documento.empresa_id: motivos.append(f"A obra {alocacao.obra.codigo} pertence a outra empresa.")
            atual=rateios.setdefault(alocacao.obra_id,{"obra":alocacao.obra,"valor":Decimal("0")}); atual["valor"]+=valor
    if itens_sem_rateio: motivos.append("Há itens sem alocação de obra válida.")
    rateios=list(rateios.values()); total_rateios=sum((r["valor"] for r in rateios),Decimal("0"))
    if total_rateios!=documento.valor_total: motivos.append("Os rateios por obra não fecham com o valor total do documento.")

    # Mantém ordem e mensagens determinísticas para HTML, testes e futuras exportações.
    motivos=list(dict.fromkeys(motivos))
    return {"documento":documento,"pronto":not motivos,"motivos":motivos,"competencia":documento.data_emissao or documento.data_entrada,
        "lancamento":{"tipo":"PAGAR","origem":"FISCAL","pessoa":documento.fornecedor,"descricao":f"{documento.identificacao} — {documento.fornecedor}","numero_documento":documento.numero,"valor_total":documento.valor_total},
        "classificacoes":classificacoes,"total_classificacoes":total_classificacoes,"parcelas":parcelas,"total_parcelas":total_parcelas,
        "rateios":rateios,"total_rateios":total_rateios}


@transaction.atomic
def integrar_documento_financeiro(documento, usuario):
    """Persiste, de forma idempotente, o contrato validado pelo preview financeiro."""
    _exigir(usuario, "integrar_documento_financeiro")
    documento = DocumentoCompra.objects.select_for_update().get(pk=documento.pk)
    existente = IntegracaoDocumentoFinanceiro.objects.select_related("lancamento").filter(documento=documento).first()
    if existente:
        return existente
    preview = montar_preview_financeiro_documento(documento)
    if not preview["pronto"]:
        raise ValidationError(preview["motivos"])
    from financeiro.models import LancamentoFinanceiro, ParcelaFinanceira, RateioCentroCusto
    from financeiro.services import salvar_classificacoes_lancamento
    lancamento = LancamentoFinanceiro.objects.create(
        empresa=documento.empresa, pessoa=documento.fornecedor, tipo="PAGAR",
        origem="FISCAL", descricao=f"Documento de compra {documento.identificacao} - {documento.fornecedor}",
        numero_documento=documento.numero, data_emissao=documento.data_emissao,
        data_competencia=preview["competencia"], valor_total=documento.valor_total,
        plano_conta=None, status="ABERTO", observacoes=f"Origem: Documento de Compra #{documento.pk}",
    )
    salvar_classificacoes_lancamento(lancamento, preview["classificacoes"])
    for parcela_documento in preview["parcelas"]:
        parcela = ParcelaFinanceira.objects.create(
            lancamento=lancamento, numero=parcela_documento.numero,
            vencimento=parcela_documento.vencimento, valor=parcela_documento.valor,
            observacoes=parcela_documento.observacao,
        )
        DocumentoCompraParcela.objects.filter(pk=parcela_documento.pk).update(parcela_financeira=parcela)
    RateioCentroCusto.objects.bulk_create([
        RateioCentroCusto(lancamento=lancamento, centro_custo=item["obra"], valor=item["valor"])
        for item in preview["rateios"]
    ])
    integracao = IntegracaoDocumentoFinanceiro.objects.create(
        documento=documento, lancamento=lancamento,
        chave_idempotencia=f"DOCUMENTO-COMPRA:{documento.pk}", integrado_por=usuario,
        observacao="Integração criada a partir do preview financeiro conferido.",
    )
    DocumentoCompra.objects.filter(pk=documento.pk).update(status=DocumentoCompra.Status.INTEGRADO_FINANCEIRO)
    documento.status=DocumentoCompra.Status.INTEGRADO_FINANCEIRO
    return integracao


@transaction.atomic
def estornar_documento_financeiro(documento, usuario, motivo):
    _exigir(usuario, "estornar_documento_financeiro")
    if not (motivo or "").strip(): raise ValidationError("Informe o motivo do estorno.")
    documento=DocumentoCompra.objects.select_for_update().get(pk=documento.pk)
    try: integracao=IntegracaoDocumentoFinanceiro.objects.select_for_update().select_related("lancamento").get(documento=documento)
    except IntegracaoDocumentoFinanceiro.DoesNotExist: raise ValidationError("O documento não possui integração financeira.")
    if integracao.status==IntegracaoDocumentoFinanceiro.Status.ESTORNADO: return integracao
    lancamento=integracao.lancamento
    if lancamento.parcelas.filter(baixas__isnull=False).exists():
        conciliada=lancamento.parcelas.filter(baixas__movimentos_ofx_conciliados__isnull=False).exists()
        if conciliada: raise ValidationError("Desfaça a conciliação OFX antes de estornar a integração.")
        raise ValidationError("Estorne as baixas financeiras antes de estornar a integração.")
    lancamento.parcelas.update(status="CANCELADA")
    type(lancamento).objects.filter(pk=lancamento.pk).update(status="CANCELADO")
    agora=timezone.now()
    IntegracaoDocumentoFinanceiro.objects.filter(pk=integracao.pk).update(
        status=IntegracaoDocumentoFinanceiro.Status.ESTORNADO, estornado_por=usuario,
        estornado_em=agora, observacao=f"{integracao.observacao}\nEstorno: {motivo}".strip(),
    )
    DocumentoCompra.objects.filter(pk=documento.pk).update(
        status=DocumentoCompra.Status.CANCELADO, cancelado_por=usuario,
        cancelado_em=agora, motivo_cancelamento=motivo,
    )
    integracao.refresh_from_db(); return integracao
