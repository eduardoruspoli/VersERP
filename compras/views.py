from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import MotivoCancelamentoForm, SolicitacaoCompraForm, SolicitacaoCompraItemFormSet
from .models import SolicitacaoCompra
from .services import abrir_solicitacao, cancelar_solicitacao


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
