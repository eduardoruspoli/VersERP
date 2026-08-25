from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Max, Min, Q, Sum
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (CotacaoFornecedorForm, CotacaoFornecedorItemForm, GerarPedidosCotacaoForm,
                    DivergenciaDocumentoForm, DivergenciaRecebimentoForm, DocumentoCompraForm,
                    DocumentoCompraItemForm, DocumentoCompraPedidoForm, DocumentoItemRecebimentoForm,
                    MotivoCancelamentoForm, PedidoCompraForm, PedidoCompraItemForm,
                    PedidoItemAlocacaoForm, ProcessoCotacaoForm, SolicitacaoCompraForm,
                    SolicitacaoCompraItemFormSet, RecebimentoCompraForm,
                    RecebimentoCompraItemFormSet, SolucaoDivergenciaForm,
                    PrevistoCompradoFiltroForm, SolucaoDivergenciaDocumentoForm)
from .forms import DocumentoCompraParcelaForm, GerarParcelasDocumentoForm
from .models import (CotacaoFornecedor, CotacaoFornecedorItem, ProcessoCotacao,
                     DivergenciaDocumentoCompra, DivergenciaRecebimento, DocumentoCompra,
                     DocumentoCompraItem, DocumentoCompraPedido, ProcessoCotacaoItem, PedidoCompra, PedidoCompraItem,
                     PedidoItemAlocacaoObra, SolicitacaoCompra)
from .models import DocumentoCompraParcela, IntegracaoDocumentoFinanceiro
from .models import RecebimentoCompra, RecebimentoCompraItem
from .services import (abrir_solicitacao, cancelar_processo_cotacao, cancelar_solicitacao,
                       cancelar_pedido, concluir_processo_cotacao, enviar_pedido,
                       gerar_pedidos_da_cotacao, iniciar_processo_cotacao,
                       montar_mapa_comparativo, recalcular_pedido, rejeitar_pedido,
                       selecionar_oferta, submeter_pedido, aprovar_pedido,
                       cancelar_recebimento, confirmar_recebimento,
                       quantidades_recebimento_pedido, resolver_divergencia,
                       calcular_previsto_comprado, cancelar_documento_compra,
                       concluir_conferencia_documento, iniciar_conferencia_documento,
                       reabrir_conferencia_documento, resolver_divergencia_documento,
                       validar_fechamento_documento, vincular_recebimento_documento)
from .services import (gerar_parcelas_documento, montar_preview_financeiro_documento,
                       integrar_documento_financeiro, estornar_documento_financeiro)
from core.access import ids_empresas_usuario
from financeiro.models import Empresa
from pessoas.models import Pessoa


@login_required
@permission_required(("compras.view_pedidocompra", "compras.view_custos_compra"), raise_exception=True)
def fornecedor_historico(request, pk):
    empresas = ids_empresas_usuario(request.user)
    fornecedor = get_object_or_404(Pessoa, pk=pk, pedidos_compra_fornecedor__empresa_id__in=empresas)
    pedidos = PedidoCompra.objects.filter(fornecedor=fornecedor, empresa_id__in=empresas).exclude(status=PedidoCompra.Status.CANCELADO).select_related("empresa").prefetch_related("itens", "recebimentos")
    resumo = pedidos.aggregate(total=Sum("total"), quantidade=Count("pk"), ultima_compra=Max("data_pedido"))
    itens = PedidoCompraItem.objects.filter(pedido__in=pedidos).values("descricao_mercadoria", "unidade").annotate(ultima_compra=Max("pedido__data_pedido"), menor_preco=Min("valor_unitario"), maior_preco=Max("valor_unitario"), quantidade=Sum("quantidade")).order_by("descricao_mercadoria")
    pendentes = pedidos.filter(status__in=[PedidoCompra.Status.APROVADO, PedidoCompra.Status.ENVIADO_FORNECEDOR, PedidoCompra.Status.PARCIALMENTE_RECEBIDO]).count()
    divergencias = DivergenciaDocumentoCompra.objects.filter(documento__fornecedor=fornecedor, documento__empresa_id__in=empresas, resolvida=False).count()
    return render(request, "compras/fornecedor_historico.html", {"fornecedor": fornecedor, "pedidos": pedidos[:50], "resumo": resumo, "itens": itens, "pendentes": pendentes, "divergencias": divergencias})


@login_required
@permission_required("compras.view_solicitacaocompra", raise_exception=True)
def solicitacao_lista(request):
    empresas = Empresa.objects.filter(pk__in=ids_empresas_usuario(request.user)).order_by("razao_social")
    solicitacoes = SolicitacaoCompra.objects.filter(empresa__in=empresas).select_related("empresa", "obra", "solicitante").annotate(quantidade_itens=Count("itens", filter=Q(itens__cancelado=False)))
    empresa = request.GET.get("empresa")
    status = request.GET.get("status")
    if empresa:
        if not empresas.filter(pk=empresa).exists():
            raise PermissionDenied("Empresa não autorizada para este usuário.")
        solicitacoes = solicitacoes.filter(empresa_id=empresa)
    if status:
        solicitacoes = solicitacoes.filter(status=status)
    return render(request, "compras/solicitacao_lista.html", {"solicitacoes": solicitacoes, "empresas": empresas, "status_choices": SolicitacaoCompra.Status.choices})


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
@permission_required("compras.change_solicitacaocompra", raise_exception=True)
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
@permission_required("compras.cancelar_solicitacao", raise_exception=True)
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

    obra = get_object_or_404(CentroCusto.objects.select_related("proposta_origem"), pk=obra_id, ativo=True, empresa_id__in=ids_empresas_usuario(request.user))
    proposta = getattr(obra, "proposta_origem", None)
    itens = []
    if proposta and proposta.revisao_aprovada_id:
        itens = list(PropostaItem.objects.filter(revisao_id=proposta.revisao_aprovada_id).values("id", "descricao", "quantidade", "unidade", "custo_unitario"))
    return JsonResponse({"itens": itens})


@login_required
@permission_required("compras.view_processocotacao", raise_exception=True)
def cotacao_lista(request):
    qs = ProcessoCotacao.objects.filter(empresa_id__in=ids_empresas_usuario(request.user)).select_related("empresa", "responsavel").annotate(total_itens=Count("itens", distinct=True), total_fornecedores=Count("cotacoes_fornecedor", distinct=True))
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
    cotacao = get_object_or_404(CotacaoFornecedor.objects.select_related("processo"), pk=fornecedor_pk, processo__empresa_id__in=ids_empresas_usuario(request.user))
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
@permission_required("compras.change_processocotacao", raise_exception=True)
def cotacao_iniciar(request,pk): return _acao(request,pk,iniciar_processo_cotacao,"Cotação iniciada.")

@login_required
@permission_required("compras.change_processocotacao", raise_exception=True)
def cotacao_concluir(request,pk): return _acao(request,pk,concluir_processo_cotacao,"Cotação concluída.")

@login_required
@permission_required("compras.cancelar_cotacao", raise_exception=True)
def cotacao_cancelar(request,pk):
    if request.method != "POST": return HttpResponseBadRequest()
    return _acao(request,pk,lambda p,u: cancelar_processo_cotacao(p,u,request.POST.get("motivo", "")),"Cotação cancelada.")

@login_required
@permission_required("compras.selecionar_fornecedor", raise_exception=True)
def cotacao_selecionar(request,pk,item_pk):
    if request.method != "POST": return HttpResponseBadRequest()
    processo=get_object_or_404(ProcessoCotacao,pk=pk); item=get_object_or_404(processo.itens,pk=item_pk); oferta=get_object_or_404(CotacaoFornecedorItem.objects.select_related("cotacao"),pk=request.POST.get("oferta"))
    try: selecionar_oferta(item,oferta,request.user,request.POST.get("justificativa",""),request.POST.get("observacao","")); messages.success(request,"Fornecedor selecionado.")
    except ValidationError as erro: messages.error(request," ".join(erro.messages))
    return redirect("compras:cotacao_mapa",pk=pk)


@login_required
@permission_required("compras.view_pedidocompra",raise_exception=True)
def pedido_lista(request):
    qs=PedidoCompra.objects.filter(empresa_id__in=ids_empresas_usuario(request.user)).select_related("empresa","fornecedor","criado_por").annotate(total_itens=Count("itens",distinct=True),total_obras=Count("itens__alocacoes__obra",distinct=True))
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
    processo=get_object_or_404(ProcessoCotacao,pk=pk,empresa_id__in=ids_empresas_usuario(request.user),status=ProcessoCotacao.Status.CONCLUIDA)
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
    itens=list(pedido.itens.select_related("plano_conta").prefetch_related("alocacoes__obra")); quantidades=quantidades_recebimento_pedido(pedido)
    for item in itens: item.quantidade_recebida_acumulada=quantidades[item.pk]["recebida"]; item.quantidade_pendente=quantidades[item.pk]["pendente"]
    return render(request,"compras/pedido_detalhe.html",{"pedido":pedido,"itens":itens,"historico":pedido.historico.select_related("usuario"),"recebimentos":pedido.recebimentos.select_related("responsavel")})

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
@permission_required("compras.change_pedidocompra", raise_exception=True)
def pedido_submeter(request,pk): return _acao_pedido(request,pk,submeter_pedido,"Pedido enviado para aprovação.")
@login_required
@permission_required("compras.aprovar_pedido", raise_exception=True)
def pedido_aprovar(request,pk): return _acao_pedido(request,pk,aprovar_pedido,"Pedido aprovado.")
@login_required
@permission_required("compras.rejeitar_pedido", raise_exception=True)
def pedido_rejeitar(request,pk): return _acao_pedido(request,pk,rejeitar_pedido,"Pedido rejeitado.",True)
@login_required
@permission_required("compras.cancelar_pedido", raise_exception=True)
def pedido_cancelar(request,pk): return _acao_pedido(request,pk,cancelar_pedido,"Pedido cancelado.",True)
@login_required
@permission_required("compras.enviar_pedido", raise_exception=True)
def pedido_enviar(request,pk): return _acao_pedido(request,pk,enviar_pedido,"Envio ao fornecedor registrado.")

@login_required
@permission_required(("compras.view_pedidocompra","compras.view_custos_compra"),raise_exception=True)
def pedido_imprimir(request,pk):
    pedido=get_object_or_404(PedidoCompra.objects.select_related("empresa","fornecedor"),pk=pk)
    return render(request,"compras/pedido_imprimir.html",{"pedido":pedido,"itens":pedido.itens.prefetch_related("alocacoes__obra")})


@login_required
@permission_required(("compras.view_pedidocompra","compras.view_custos_compra"),raise_exception=True)
def pedido_pdf(request,pk):
    from core.pdf import resposta_pdf
    permitidos=[PedidoCompra.Status.AGUARDANDO_APROVACAO,PedidoCompra.Status.APROVADO,PedidoCompra.Status.ENVIADO_FORNECEDOR,PedidoCompra.Status.PARCIALMENTE_RECEBIDO,PedidoCompra.Status.RECEBIDO]
    pedido=get_object_or_404(PedidoCompra.objects.select_related("empresa","fornecedor","transportadora"),pk=pk,status__in=permitidos)
    itens=pedido.itens.prefetch_related("alocacoes__obra")
    return resposta_pdf("compras/pedido_pdf.html",{"pedido":pedido,"itens":itens},f"pedido-{pedido.numero_pedido_versatile}.pdf")


@login_required
@permission_required(("compras.add_recebimentocompra","compras.registrar_recebimento"),raise_exception=True)
def recebimento_criar(request,pedido_pk):
    pedido=get_object_or_404(PedidoCompra,pk=pedido_pk,empresa_id__in=ids_empresas_usuario(request.user),status__in=[PedidoCompra.Status.APROVADO,PedidoCompra.Status.ENVIADO_FORNECEDOR,PedidoCompra.Status.PARCIALMENTE_RECEBIDO])
    recebimento=RecebimentoCompra(pedido=pedido,responsavel=request.user,criado_por=request.user)
    form=RecebimentoCompraForm(request.POST or None,instance=recebimento)
    if request.method=="POST" and form.is_valid():
        with transaction.atomic():
            recebimento=form.save(commit=False); recebimento.pedido=pedido; recebimento.criado_por=request.user; recebimento.save()
            for item in pedido.itens.all(): RecebimentoCompraItem.objects.create(recebimento=recebimento,pedido_item=item,quantidade_recebida=0,quantidade_aceita=0,quantidade_rejeitada=0)
        return redirect("compras:recebimento_editar",pk=recebimento.pk)
    return render(request,"compras/recebimento_formulario.html",{"form":form,"pedido":pedido})

@login_required
@permission_required("compras.change_recebimentocompra",raise_exception=True)
def recebimento_editar(request,pk):
    recebimento=get_object_or_404(RecebimentoCompra.objects.select_related("pedido"),pk=pk,status=RecebimentoCompra.Status.RASCUNHO)
    form=RecebimentoCompraForm(request.POST or None,instance=recebimento); formset=RecebimentoCompraItemFormSet(request.POST or None,instance=recebimento,pedido=recebimento.pedido)
    if request.method=="POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic(): form.save(); formset.save()
        messages.success(request,"Recebimento salvo em rascunho."); return redirect("compras:recebimento_detalhe",pk=pk)
    return render(request,"compras/recebimento_editar.html",{"form":form,"formset":formset,"recebimento":recebimento})

@login_required
@permission_required("compras.view_recebimentocompra",raise_exception=True)
def recebimento_detalhe(request,pk):
    recebimento=get_object_or_404(RecebimentoCompra.objects.select_related("pedido","responsavel","confirmado_por","cancelado_por"),pk=pk)
    acumuladas=quantidades_recebimento_pedido(recebimento.pedido); itens=list(recebimento.itens.select_related("pedido_item").prefetch_related("divergencias__resolvida_por"))
    for item in itens: item.recebida_acumulada=acumuladas[item.pedido_item_id]["recebida"]; item.pendente=acumuladas[item.pedido_item_id]["pendente"]
    return render(request,"compras/recebimento_detalhe.html",{"recebimento":recebimento,"itens":itens})

def _acao_recebimento(request,pk,funcao,sucesso,motivo=False):
    if request.method!="POST": return HttpResponseBadRequest()
    rec=get_object_or_404(RecebimentoCompra,pk=pk)
    try: funcao(rec,request.user,request.POST.get("motivo","")) if motivo else funcao(rec,request.user); messages.success(request,sucesso)
    except (ValidationError,PermissionDenied) as erro: messages.error(request," ".join(getattr(erro,"messages",[str(erro)])))
    return redirect("compras:recebimento_detalhe",pk=pk)

@login_required
@permission_required("compras.registrar_recebimento", raise_exception=True)
def recebimento_confirmar(request,pk): return _acao_recebimento(request,pk,confirmar_recebimento,"Recebimento confirmado.")
@login_required
@permission_required("compras.cancelar_recebimento", raise_exception=True)
def recebimento_cancelar(request,pk): return _acao_recebimento(request,pk,cancelar_recebimento,"Recebimento cancelado.",True)

@login_required
@permission_required("compras.registrar_recebimento",raise_exception=True)
def divergencia_criar(request,pk,item_pk):
    recebimento=get_object_or_404(RecebimentoCompra,pk=pk,pedido__empresa_id__in=ids_empresas_usuario(request.user)); item=get_object_or_404(RecebimentoCompraItem,pk=item_pk,recebimento=recebimento)
    form=DivergenciaRecebimentoForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        obj=form.save(commit=False); obj.recebimento_item=item; obj.save(); RecebimentoCompraItem.objects.filter(pk=item.pk).update(possui_divergencia=True); return redirect("compras:recebimento_detalhe",pk=pk)
    return render(request,"compras/divergencia_formulario.html",{"form":form,"recebimento":recebimento,"item":item})

@login_required
@permission_required("compras.resolver_divergencia_recebimento",raise_exception=True)
def divergencia_resolver(request,pk):
    divergencia=get_object_or_404(DivergenciaRecebimento.objects.select_related("recebimento_item__recebimento"),pk=pk); form=SolucaoDivergenciaForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        try: resolver_divergencia(divergencia,request.user,form.cleaned_data["solucao"]); return redirect("compras:recebimento_detalhe",pk=divergencia.recebimento_item.recebimento_id)
        except ValidationError as erro: form.add_error(None," ".join(erro.messages))
    return render(request,"compras/divergencia_resolver.html",{"form":form,"divergencia":divergencia})


@login_required
@permission_required("compras.view_pedidocompra",raise_exception=True)
def previsto_comprado(request,obra_pk=None):
    from financeiro.models import CentroCusto, Empresa
    dados=request.GET.copy()
    empresas = Empresa.objects.filter(pk__in=ids_empresas_usuario(request.user))
    if obra_pk:
        obra_url=get_object_or_404(CentroCusto,pk=obra_pk,empresa__in=empresas); dados.setdefault("empresa",str(obra_url.empresa_id)); dados.setdefault("obra",str(obra_url.pk))
    elif not dados.get("empresa"):
        principal=empresas.filter(principal=True,ativa=True).first() or empresas.filter(ativa=True).first()
        if principal: dados["empresa"]=str(principal.pk)
    form=PrevistoCompradoFiltroForm(dados or None,usuario=request.user)
    relatorio=None
    if form.is_valid():
        obra=form.cleaned_data["obra"]; proposta=form.cleaned_data.get("proposta")
        if proposta and proposta.centro_custo_id!=obra.pk: form.add_error("proposta","A proposta deve pertencer à obra selecionada.")
        else: relatorio=calcular_previsto_comprado(obra,tipo_origem=form.cleaned_data.get("tipo_origem", ""),status_pedido=form.cleaned_data.get("status", ""),plano_conta_id=getattr(form.cleaned_data.get("plano_conta"),"pk",None),somente_divergencias=form.cleaned_data.get("somente_divergencias",False))
    return render(request,"compras/previsto_comprado.html",{"form":form,"relatorio":relatorio})


@login_required
@permission_required("compras.view_pedidocompra",raise_exception=True)
def previsto_comprado_item(request,obra_pk,item_pk):
    from financeiro.models import CentroCusto
    obra=get_object_or_404(CentroCusto,pk=obra_pk,empresa_id__in=ids_empresas_usuario(request.user)); relatorio=calcular_previsto_comprado(obra); linha=next((x for x in relatorio.get("itens_previstos",[]) if x["previsto"].pk==item_pk),None)
    if not linha: return HttpResponseBadRequest("Item não pertence à revisão aprovada desta obra.")
    return render(request,"compras/previsto_comprado_item.html",{"relatorio":relatorio,"linha":linha})


@login_required
@permission_required("compras.view_documentocompra",raise_exception=True)
def documento_lista(request):
    qs=DocumentoCompra.objects.filter(empresa_id__in=ids_empresas_usuario(request.user)).select_related("empresa","fornecedor").annotate(total_itens=Count("itens",distinct=True),total_pedidos=Count("vinculos_pedidos",distinct=True),divergencias_abertas=Count("divergencias",filter=Q(divergencias__resolvida=False),distinct=True))
    for campo in ("empresa","fornecedor","tipo","status"):
        if request.GET.get(campo): qs=qs.filter(**{f"{campo}_id" if campo in {"empresa","fornecedor"} else campo:request.GET[campo]})
    return render(request,"compras/documento_lista.html",{"documentos":qs,"tipo_choices":DocumentoCompra.Tipo.choices,"status_choices":DocumentoCompra.Status.choices})


def _salvar_documento(request,documento=None):
    documento=documento or DocumentoCompra(criado_por=request.user); form=DocumentoCompraForm(request.POST or None,instance=documento)
    if request.method=="POST" and form.is_valid(): documento=form.save(); messages.success(request,"Documento salvo em rascunho."); return redirect("compras:documento_detalhe",pk=documento.pk)
    return render(request,"compras/documento_formulario.html",{"form":form,"documento":documento})

@login_required
@permission_required("compras.add_documentocompra",raise_exception=True)
def documento_criar(request): return _salvar_documento(request)

@login_required
@permission_required("compras.change_documentocompra",raise_exception=True)
def documento_editar(request,pk):
    documento=get_object_or_404(DocumentoCompra,pk=pk)
    if documento.status!=DocumentoCompra.Status.RASCUNHO: messages.error(request,"Somente rascunhos podem ser editados."); return redirect("compras:documento_detalhe",pk=pk)
    return _salvar_documento(request,documento)

@login_required
@permission_required("compras.view_documentocompra",raise_exception=True)
def documento_detalhe(request,pk):
    documento=get_object_or_404(DocumentoCompra.objects.select_related("empresa","fornecedor","conferido_por","cancelado_por","integracao_financeira__lancamento"),pk=pk)
    return render(request,"compras/documento_detalhe.html",{"documento":documento,"itens":documento.itens.select_related("pedido_item__pedido","plano_conta").prefetch_related("vinculos_recebimentos__recebimento_item__recebimento"),"pedidos":documento.vinculos_pedidos.select_related("pedido"),"divergencias":documento.divergencias.select_related("documento_item","resolvida_por")})

@login_required
@permission_required("compras.change_documentocompra",raise_exception=True)
def documento_item(request,pk,item_pk=None):
    documento=get_object_or_404(DocumentoCompra,pk=pk,status=DocumentoCompra.Status.RASCUNHO); instancia=get_object_or_404(DocumentoCompraItem,pk=item_pk,documento=documento) if item_pk else None
    form=DocumentoCompraItemForm(request.POST or None,instance=instancia,documento=documento)
    if request.method=="POST" and form.is_valid(): obj=form.save(commit=False); obj.documento=documento; obj.save(); return redirect("compras:documento_detalhe",pk=pk)
    return render(request,"compras/documento_item_formulario.html",{"form":form,"documento":documento})

@login_required
@permission_required("compras.change_documentocompra",raise_exception=True)
def documento_pedido(request,pk):
    documento=get_object_or_404(DocumentoCompra,pk=pk,status=DocumentoCompra.Status.RASCUNHO); form=DocumentoCompraPedidoForm(request.POST or None,documento=documento)
    if request.method=="POST" and form.is_valid(): obj=form.save(commit=False); obj.documento=documento; obj.save(); return redirect("compras:documento_detalhe",pk=pk)
    return render(request,"compras/documento_pedido_formulario.html",{"form":form,"documento":documento})

@login_required
@permission_required("compras.change_documentocompra",raise_exception=True)
def documento_recebimento(request,pk,item_pk):
    documento=get_object_or_404(DocumentoCompra,pk=pk,status=DocumentoCompra.Status.RASCUNHO); item=get_object_or_404(DocumentoCompraItem,pk=item_pk,documento=documento); form=DocumentoItemRecebimentoForm(request.POST or None,documento_item=item)
    if request.method=="POST" and form.is_valid():
        try: vincular_recebimento_documento(item,form.cleaned_data["recebimento_item"],form.cleaned_data["quantidade_vinculada"]); return redirect("compras:documento_detalhe",pk=pk)
        except ValidationError as erro: form.add_error(None," ".join(erro.messages))
    return render(request,"compras/documento_recebimento_formulario.html",{"form":form,"documento":documento,"item":item})


def _acao_documento(request,pk,funcao,sucesso,motivo=False):
    if request.method!="POST": return HttpResponseBadRequest()
    documento=get_object_or_404(DocumentoCompra,pk=pk)
    try: funcao(documento,request.user,request.POST.get("motivo","")) if motivo else funcao(documento,request.user); messages.success(request,sucesso)
    except (ValidationError,PermissionDenied) as erro: messages.error(request," ".join(getattr(erro,"messages",[str(erro)])))
    return redirect("compras:documento_detalhe",pk=pk)

@login_required
@permission_required("compras.conferir_documento_compra", raise_exception=True)
def documento_iniciar_conferencia(request,pk): return _acao_documento(request,pk,iniciar_conferencia_documento,"Documento enviado para conferência.")
@login_required
@permission_required("compras.conferir_documento_compra", raise_exception=True)
def documento_conferir(request,pk): return _acao_documento(request,pk,concluir_conferencia_documento,"Conferência concluída.")
@login_required
@permission_required("compras.conferir_documento_compra", raise_exception=True)
def documento_reabrir(request,pk): return _acao_documento(request,pk,reabrir_conferencia_documento,"Documento retornou à conferência.")
@login_required
@permission_required("compras.cancelar_documento_compra", raise_exception=True)
def documento_cancelar(request,pk): return _acao_documento(request,pk,cancelar_documento_compra,"Documento cancelado.",True)

@login_required
@permission_required("compras.conferir_documento_compra",raise_exception=True)
def documento_divergencia(request,pk):
    documento=get_object_or_404(DocumentoCompra,pk=pk); form=DivergenciaDocumentoForm(request.POST or None,documento=documento)
    if request.method=="POST" and form.is_valid(): obj=form.save(commit=False); obj.documento=documento; obj.save(); return redirect("compras:documento_detalhe",pk=pk)
    return render(request,"compras/documento_divergencia_formulario.html",{"form":form,"documento":documento})

@login_required
@permission_required("compras.resolver_divergencia_documento",raise_exception=True)
def documento_divergencia_resolver(request,pk):
    divergencia=get_object_or_404(DivergenciaDocumentoCompra,pk=pk); form=SolucaoDivergenciaDocumentoForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        try: resolver_divergencia_documento(divergencia,request.user,form.cleaned_data["solucao"]); return redirect("compras:documento_detalhe",pk=divergencia.documento_id)
        except ValidationError as erro: form.add_error(None," ".join(erro.messages))
    return render(request,"compras/documento_divergencia_resolver.html",{"form":form,"divergencia":divergencia})


@login_required
@permission_required("compras.add_documentocompraparcela",raise_exception=True)
def documento_parcelas_gerar(request,pk):
    documento=get_object_or_404(DocumentoCompra,pk=pk); form=GerarParcelasDocumentoForm(request.POST or None)
    if request.method=="POST" and form.is_valid():
        try:
            gerar_parcelas_documento(documento,request.user,form.cleaned_data["quantidade"],form.cleaned_data["intervalo_dias"],form.cleaned_data["primeiro_vencimento_dias"]); messages.success(request,"Parcelas geradas com fechamento exato."); return redirect("compras:documento_detalhe",pk=pk)
        except (ValidationError,PermissionDenied) as erro: form.add_error(None," ".join(getattr(erro,"messages",[str(erro)])))
    return render(request,"compras/documento_parcelas_gerar.html",{"form":form,"documento":documento})


def _salvar_parcela_documento(request,documento,parcela=None):
    form=DocumentoCompraParcelaForm(request.POST or None,instance=parcela,documento=documento)
    if request.method=="POST" and form.is_valid():
        obj=form.save(commit=False); obj.documento=documento
        try: obj.save(); messages.success(request,"Parcela salva."); return redirect("compras:documento_detalhe",pk=documento.pk)
        except ValidationError as erro: form.add_error(None," ".join(erro.messages))
    return render(request,"compras/documento_parcela_formulario.html",{"form":form,"documento":documento,"parcela":parcela})


@login_required
@permission_required("compras.add_documentocompraparcela",raise_exception=True)
def documento_parcela_criar(request,pk): return _salvar_parcela_documento(request,get_object_or_404(DocumentoCompra,pk=pk))


@login_required
@permission_required("compras.change_documentocompraparcela",raise_exception=True)
def documento_parcela_editar(request,pk,parcela_pk):
    documento=get_object_or_404(DocumentoCompra,pk=pk); parcela=get_object_or_404(DocumentoCompraParcela,pk=parcela_pk,documento=documento); return _salvar_parcela_documento(request,documento,parcela)


@login_required
@permission_required("compras.change_documentocompraparcela",raise_exception=True)
def documento_parcela_excluir(request,pk,parcela_pk):
    if request.method!="POST": return HttpResponseBadRequest()
    documento=get_object_or_404(DocumentoCompra,pk=pk); parcela=get_object_or_404(DocumentoCompraParcela,pk=parcela_pk,documento=documento)
    try: parcela.delete(); messages.success(request,"Parcela removida.")
    except ValidationError as erro: messages.error(request," ".join(erro.messages))
    return redirect("compras:documento_detalhe",pk=pk)


@login_required
@permission_required("compras.view_preview_financeiro_documento",raise_exception=True)
def documento_preview_financeiro(request,pk):
    documento=get_object_or_404(DocumentoCompra,pk=pk); preview=montar_preview_financeiro_documento(documento)
    return render(request,"compras/documento_preview_financeiro.html",{"preview":preview,"documento":preview["documento"]})


@login_required
@permission_required("compras.integrar_documento_financeiro",raise_exception=True)
def documento_integrar_financeiro(request,pk):
    if request.method!="POST": return HttpResponseBadRequest()
    documento=get_object_or_404(DocumentoCompra,pk=pk)
    try:
        integracao=integrar_documento_financeiro(documento,request.user)
        messages.success(request,f"Documento integrado à Conta a Pagar #{integracao.lancamento_id}.")
    except (ValidationError,PermissionDenied) as erro:
        messages.error(request," ".join(getattr(erro,"messages",[str(erro)])))
    return redirect("compras:documento_detalhe",pk=pk)


@login_required
@permission_required("compras.estornar_documento_financeiro",raise_exception=True)
def documento_estornar_financeiro(request,pk):
    if request.method!="POST": return HttpResponseBadRequest()
    documento=get_object_or_404(DocumentoCompra,pk=pk)
    try:
        estornar_documento_financeiro(documento,request.user,request.POST.get("motivo",""))
        messages.success(request,"Integração financeira estornada sem excluir o histórico.")
    except (ValidationError,PermissionDenied) as erro:
        messages.error(request," ".join(getattr(erro,"messages",[str(erro)])))
    return redirect("compras:documento_detalhe",pk=pk)
