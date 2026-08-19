from django.core.exceptions import PermissionDenied, ValidationError
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from .models import (
    CotacaoFornecedor, EscolhaCotacaoItem, HistoricoPedidoCompra, HistoricoProcessoCotacao,
    HistoricoSolicitacaoCompra, PedidoCompra, PedidoCompraItem, PedidoItemAlocacaoObra,
    ProcessoCotacao, SolicitacaoCompra,
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
    solicitacoes = SolicitacaoCompra.objects.select_for_update().filter(itens__itens_processo_cotacao__processo=processo).distinct()
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
    pedido=PedidoCompra.objects.select_for_update().get(pk=pedido.pk)
    return _mudar_pedido(pedido,usuario,PedidoCompra.Status.ENVIADO_FORNECEDOR,"enviar_pedido")
