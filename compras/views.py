from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (CotacaoFornecedorForm, CotacaoFornecedorItemForm, GerarPedidosCotacaoForm,
                    MotivoCancelamentoForm, PedidoCompraForm, PedidoCompraItemForm,
                    PedidoItemAlocacaoForm, ProcessoCotacaoForm, SolicitacaoCompraForm,
                    SolicitacaoCompraItemFormSet)
from .models import (CotacaoFornecedor, CotacaoFornecedorItem, ProcessoCotacao,
                     ProcessoCotacaoItem, PedidoCompra, PedidoCompraItem,
                     PedidoItemAlocacaoObra, SolicitacaoCompra)
from .services import (abrir_solicitacao, cancelar_processo_cotacao, cancelar_solicitacao,
                       cancelar_pedido, concluir_processo_cotacao, enviar_pedido,
                       gerar_pedidos_da_cotacao, iniciar_processo_cotacao,
                       montar_mapa_comparativo, recalcular_pedido, rejeitar_pedido,
                       selecionar_oferta, submeter_pedido, aprovar_pedido)


@login_required
@permission_required("compras.view_solicitacaocompra", raise_exception=True)
def solicitacao_lista(request):
    solicitacoes = SolicitacaoCompra.objects.select_related("empresa", "obra", "solicitante").annotate(quantidade_itens=Count("itens", filter=Q(itens__cancelado=False)))
    empresa = request.GET.get("empresa")
    status = request.GET.get("status")
    if empresa:
        solicitacoes = solicitacoes.filter(empresa_id=empresa)
    if status:
        solicitacoes = solicitacoes.filter(status=status)
    return render(request, "compras/solicitacao_lista.html", {"solicitacoes": solicitacoes, "status_choices": SolicitacaoCompra.Status.choices})


def _obra_do_form(request, instance=None):
    obra_id = request.POST.get("obra") if request.method == "POST" else request.GET.get("obra")
    if obra_id:
        from financeiro.models import CentroCusto
        return CentroCusto.objects.filter(pk=obra_id).first()
    return instance.obra if instance and instance.pk else None


def _salvar_solicitacao(request, instance=None):
    instance = instance or SolicitacaoCompra(solicitante=request.user, criado_por=request.user)
    obra = _obra_do_form(request, instance)
    form = SolicitacaoCompraForm(request.POST or None, instance=instance)
    formset = SolicitacaoCompraItemFormSet(request.POST or None, instance=instance, obra=obra)
    if request.method == "POST" and form.is_valid():
        instance = form.save(commit=False)
        instance.solicitante_id = instance.solicitante_id or request.user.pk
        instance.criado_por_id = instance.criado_por_id or request.user.pk
        formset.instance = instance
        if formset.is_valid():
            with transaction.atomic():
                instance.save()
                formset.save()
            messages.success(request, "Solicitação de compra salva em rascunho.")
            return redirect("compras:solicitacao_detalhe", pk=instance.pk)
    return render(request, "compras/solicitacao_formulario.html", {"form": form, "formset": formset, "solicitacao": instance})


@login_required
@permission_required("compras.add_solicitacaocompra", raise_exception=True)
def solicitacao_criar(request):
    return _salvar_solicitacao(request)


@login_required
@permission_required("compras.change_solicitacaocompra", raise_exception=True)
def solicitacao_editar(request, pk):
    solicitacao = get_object_or_404(SolicitacaoCompra, pk=pk)
    if solicitacao.status != SolicitacaoCompra.Status.RASCUNHO:
        messages.error(request, "Somente solicitações em rascunho podem ser editadas.")
        return redirect("compras:solicitacao_detalhe", pk=pk)
    return _salvar_solicitacao(request, solicitacao)


@login_required
@permission_required("compras.view_solicitacaocompra", raise_exception=True)
def solicitacao_detalhe(request, pk):
    solicitacao = get_object_or_404(SolicitacaoCompra.objects.select_related("empresa", "obra", "solicitante", "obra__proposta_origem"), pk=pk)
    return render(request, "compras/solicitacao_detalhe.html", {"solicitacao": solicitacao, "itens": solicitacao.itens.select_related("proposta_item", "plano_conta_previsto"), "historico": solicitacao.historico.select_related("usuario")})


@login_required
def solicitacao_abrir(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest()
    solicitacao = get_object_or_404(SolicitacaoCompra, pk=pk)
    try:
        abrir_solicitacao(solicitacao, request.user)
        messages.success(request, "Solicitação aberta.")
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    return redirect("compras:solicitacao_detalhe", pk=pk)


@login_required
def solicitacao_cancelar(request, pk):
    solicitacao = get_object_or_404(SolicitacaoCompra, pk=pk)
    form = MotivoCancelamentoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            cancelar_solicitacao(solicitacao, request.user, form.cleaned_data["motivo"])
            messages.success(request, "Solicitação cancelada.")
            return redirect("compras:solicitacao_detalhe", pk=pk)
        except ValidationError as erro:
            form.add_error(None, " ".join(erro.messages))
    return render(request, "compras/cancelar_formulario.html", {"form": form, "solicitacao": solicitacao})


@login_required
@permission_required("compras.add_solicitacaocompra", raise_exception=True)
def itens_previstos_obra(request, obra_id):
    from comercial.models import PropostaItem
    from financeiro.models import CentroCusto

    obra = get_object_or_404(CentroCusto.objects.select_related("proposta_origem"), pk=obra_id, ativo=True)
    proposta = getattr(obra, "proposta_origem", None)
    itens = []
    if proposta and proposta.revisao_aprovada_id:
        itens = list(PropostaItem.objects.filter(revisao_id=proposta.revisao_aprovada_id).values("id", "descricao", "quantidade", "unidade", "custo_unitario"))
    return JsonResponse({"itens": itens})


@login_required
@permission_required("compras.view_processocotacao", raise_exception=True)
def cotacao_lista(request):
    qs = ProcessoCotacao.objects.select_related("empresa", "responsavel").annotate(total_itens=Count("itens", distinct=True), total_fornecedores=Count("cotacoes_fornecedor", distinct=True))
    for campo in ("empresa", "status", "responsavel"):
        if request.GET.get(campo): qs = qs.filter(**{f"{campo}_id" if campo != "status" else campo: request.GET[campo]})
    if request.GET.get("obra"): qs = qs.filter(itens__solicitacao_item__solicitacao__obra_id=request.GET["obra"])
    if request.GET.get("fornecedor"): qs = qs.filter(cotacoes_fornecedor__fornecedor_id=request.GET["fornecedor"])
    return render(request, "compras/cotacao_lista.html", {"processos": qs.distinct(), "status_choices": ProcessoCotacao.Status.choices})


@login_required
@permission_required("compras.add_processocotacao", raise_exception=True)
def cotacao_criar(request):
    processo = ProcessoCotacao(criado_por=request.user, responsavel=request.user)
    form = ProcessoCotacaoForm(request.POST or None, instance=processo)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            processo = form.save(); itens = form.cleaned_data["itens_solicitacao"]
            for item in itens: ProcessoCotacaoItem.objects.create(processo=processo, solicitacao_item=item, quantidade_cotada=item.quantidade, unidade=item.unidade)
        messages.success(request, "Processo de cotação criado.")
        return redirect("compras:cotacao_detalhe", pk=processo.pk)
    return render(request, "compras/cotacao_formulario.html", {"form":form})


@login_required
@permission_required("compras.view_processocotacao", raise_exception=True)
def cotacao_detalhe(request, pk):
    processo = get_object_or_404(ProcessoCotacao.objects.select_related("empresa","responsavel"), pk=pk)
    return render(request, "compras/cotacao_detalhe.html", {"processo":processo, "itens":processo.itens.select_related("solicitacao_item__solicitacao__obra","solicitacao_item__solicitacao__obra__proposta_origem"), "fornecedores":processo.cotacoes_fornecedor.select_related("fornecedor").prefetch_related("itens"), "historico":processo.historico.select_related("usuario")})


@login_required
@permission_required("compras.realizar_cotacao", raise_exception=True)
def cotacao_fornecedor(request, pk, cotacao_pk=None):
    processo = get_object_or_404(ProcessoCotacao, pk=pk)
    instancia = get_object_or_404(CotacaoFornecedor, pk=cotacao_pk, processo=processo) if cotacao_pk else None
    form = CotacaoFornecedorForm(request.POST or None, instance=instancia)
    if request.method == "POST" and form.is_valid():
        obj=form.save(commit=False); obj.processo=processo; obj.registrada_por=request.user; obj.save()
        return redirect("compras:cotacao_detalhe", pk=pk)
    return render(request,"compras/cotacao_fornecedor_formulario.html",{"form":form,"processo":processo})


@login_required
@permission_required("compras.realizar_cotacao", raise_exception=True)
def cotacao_oferta(request, fornecedor_pk, oferta_pk=None):
    cotacao = get_object_or_404(CotacaoFornecedor.objects.select_related("processo"), pk=fornecedor_pk)
    instancia = get_object_or_404(CotacaoFornecedorItem, pk=oferta_pk, cotacao=cotacao) if oferta_pk else None
    form = CotacaoFornecedorItemForm(request.POST or None, instance=instancia, cotacao=cotacao)
    if request.method == "POST" and form.is_valid():
        obj=form.save(commit=False); obj.cotacao=cotacao; obj.save(); return redirect("compras:cotacao_detalhe", pk=cotacao.processo_id)
    return render(request,"compras/cotacao_oferta_formulario.html",{"form":form,"cotacao":cotacao})


@login_required
@permission_required("compras.view_processocotacao", raise_exception=True)
def cotacao_mapa(request, pk):
    processo=get_object_or_404(ProcessoCotacao,pk=pk)
    return render(request,"compras/cotacao_mapa.html",{"processo":processo,"linhas":montar_mapa_comparativo(processo)})


def _acao(request, pk, funcao, sucesso):
    if request.method != "POST": return HttpResponseBadRequest()
    processo=get_object_or_404(ProcessoCotacao,pk=pk)
    try: funcao(processo,request.user); messages.success(request,sucesso)
    except ValidationError as erro: messages.error(request," ".join(erro.messages))
    return redirect("compras:cotacao_detalhe",pk=pk)


@login_required
def cotacao_iniciar(request,pk): return _acao(request,pk,iniciar_processo_cotacao,"Cotação iniciada.")

@login_required
def cotacao_concluir(request,pk): return _acao(request,pk,concluir_processo_cotacao,"Cotação concluída.")

@login_required
def cotacao_cancelar(request,pk):
    if request.method != "POST": return HttpResponseBadRequest()
    return _acao(request,pk,lambda p,u: cancelar_processo_cotacao(p,u,request.POST.get("motivo", "")),"Cotação cancelada.")

@login_required
def cotacao_selecionar(request,pk,item_pk):
    if request.method != "POST": return HttpResponseBadRequest()
    processo=get_object_or_404(ProcessoCotacao,pk=pk); item=get_object_or_404(processo.itens,pk=item_pk); oferta=get_object_or_404(CotacaoFornecedorItem.objects.select_related("cotacao"),pk=request.POST.get("oferta"))
    try: selecionar_oferta(item,oferta,request.user,request.POST.get("justificativa",""),request.POST.get("observacao","")); messages.success(request,"Fornecedor selecionado.")
    except ValidationError as erro: messages.error(request," ".join(erro.messages))
    return redirect("compras:cotacao_mapa",pk=pk)


@login_required
@permission_required("compras.view_pedidocompra",raise_exception=True)
def pedido_lista(request):
    qs=PedidoCompra.objects.select_related("empresa","fornecedor","criado_por").annotate(total_itens=Count("itens",distinct=True),total_obras=Count("itens__alocacoes__obra",distinct=True))
    for campo in ("empresa","fornecedor","status","origem"):
        if request.GET.get(campo): qs=qs.filter(**{f"{campo}_id" if campo in {"empresa","fornecedor"} else campo:request.GET[campo]})
    return render(request,"compras/pedido_lista.html",{"pedidos":qs,"status_choices":PedidoCompra.Status.choices,"origem_choices":PedidoCompra.Origem.choices})


def _salvar_pedido(request,pedido=None):
    pedido=pedido or PedidoCompra(criado_por=request.user)
    form=PedidoCompraForm(request.POST or None,instance=pedido)
    if request.method=="POST" and form.is_valid():
        pedido=form.save(); messages.success(request,"Pedido salvo em rascunho."); return redirect("compras:pedido_detalhe",pk=pedido.pk)
    return render(request,"compras/pedido_formulario.html",{"form":form,"pedido":pedido})


@login_required
@permission_required(("compras.add_pedidocompra","compras.criar_pedido"),raise_exception=True)
def pedido_criar(request): return _salvar_pedido(request)

@login_required
@permission_required("compras.change_pedidocompra",raise_exception=True)
def pedido_editar(request,pk):
    pedido=get_object_or_404(PedidoCompra,pk=pk)
    if pedido.status!=PedidoCompra.Status.RASCUNHO: messages.error(request,"Somente rascunhos podem ser editados."); return redirect("compras:pedido_detalhe",pk=pk)
    return _salvar_pedido(request,pedido)

@login_required
@permission_required("compras.criar_pedido",raise_exception=True)
def pedido_gerar_cotacao(request,pk):
    processo=get_object_or_404(ProcessoCotacao,pk=pk,status=ProcessoCotacao.Status.CONCLUIDA)
    form=GerarPedidosCotacaoForm(request.POST or None,processo=processo)
    if request.method=="POST" and form.is_valid():
        numeros={int(k.split("_")[1]):v for k,v in form.cleaned_data.items()}
        try:
            pedidos=gerar_pedidos_da_cotacao(processo,numeros,request.user); messages.success(request,f"{len(pedidos)} pedido(s) gerado(s).")
            return redirect("compras:pedido_lista")
        except ValidationError as erro: form.add_error(None," ".join(erro.messages))
    return render(request,"compras/pedido_gerar_cotacao.html",{"form":form,"processo":processo})

@login_required
@permission_required("compras.view_pedidocompra",raise_exception=True)
def pedido_detalhe(request,pk):
    pedido=get_object_or_404(PedidoCompra.objects.select_related("empresa","fornecedor","transportadora","aprovado_por","enviado_por"),pk=pk)
    itens=pedido.itens.select_related("plano_conta").prefetch_related("alocacoes__obra")
    return render(request,"compras/pedido_detalhe.html",{"pedido":pedido,"itens":itens,"historico":pedido.historico.select_related("usuario")})

@login_required
@permission_required("compras.change_pedidocompra",raise_exception=True)
def pedido_item(request,pk,item_pk=None):
    pedido=get_object_or_404(PedidoCompra,pk=pk,status=PedidoCompra.Status.RASCUNHO)
    instancia=get_object_or_404(PedidoCompraItem,pk=item_pk,pedido=pedido) if item_pk else None
    form=PedidoCompraItemForm(request.POST or None,instance=instancia,pedido=pedido)
    if request.method=="POST" and form.is_valid():
        item=form.save(commit=False); item.pedido=pedido; item.save(); recalcular_pedido(pedido); return redirect("compras:pedido_detalhe",pk=pk)
    return render(request,"compras/pedido_item_formulario.html",{"form":form,"pedido":pedido})

@login_required
@permission_required("compras.change_pedidocompra",raise_exception=True)
def pedido_alocacao(request,pk,item_pk,alocacao_pk=None):
    pedido=get_object_or_404(PedidoCompra,pk=pk,status=PedidoCompra.Status.RASCUNHO); item=get_object_or_404(PedidoCompraItem,pk=item_pk,pedido=pedido)
    instancia=get_object_or_404(PedidoItemAlocacaoObra,pk=alocacao_pk,pedido_item=item) if alocacao_pk else None
    form=PedidoItemAlocacaoForm(request.POST or None,instance=instancia,pedido_item=item)
    if request.method=="POST" and form.is_valid():
        obj=form.save(commit=False); obj.pedido_item=item; obj.save(); return redirect("compras:pedido_detalhe",pk=pk)
    return render(request,"compras/pedido_alocacao_formulario.html",{"form":form,"pedido":pedido,"item":item})


def _acao_pedido(request,pk,funcao,sucesso,motivo=False):
    if request.method!="POST": return HttpResponseBadRequest()
    pedido=get_object_or_404(PedidoCompra,pk=pk)
    try:
        funcao(pedido,request.user,request.POST.get("motivo", "")) if motivo else funcao(pedido,request.user); messages.success(request,sucesso)
    except (ValidationError, PermissionDenied) as erro: messages.error(request," ".join(getattr(erro,"messages",[str(erro)])))
    return redirect("compras:pedido_detalhe",pk=pk)

@login_required
def pedido_submeter(request,pk): return _acao_pedido(request,pk,submeter_pedido,"Pedido enviado para aprovação.")
@login_required
def pedido_aprovar(request,pk): return _acao_pedido(request,pk,aprovar_pedido,"Pedido aprovado.")
@login_required
def pedido_rejeitar(request,pk): return _acao_pedido(request,pk,rejeitar_pedido,"Pedido rejeitado.",True)
@login_required
def pedido_cancelar(request,pk): return _acao_pedido(request,pk,cancelar_pedido,"Pedido cancelado.",True)
@login_required
def pedido_enviar(request,pk): return _acao_pedido(request,pk,enviar_pedido,"Envio ao fornecedor registrado.")

@login_required
@permission_required("compras.view_pedidocompra",raise_exception=True)
def pedido_imprimir(request,pk):
    pedido=get_object_or_404(PedidoCompra.objects.select_related("empresa","fornecedor"),pk=pk)
    return render(request,"compras/pedido_imprimir.html",{"pedido":pedido,"itens":pedido.itens.prefetch_related("alocacoes__obra")})
