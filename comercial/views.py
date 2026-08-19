from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render

from .forms import MotivoStatusForm, PropostaCriacaoForm, PropostaItemForm, PropostaLinhaPublicaForm, PropostaRevisaoForm, PropostaTributoForm
from .models import Proposta, PropostaRevisao
from .services import aprovar_proposta, calcular_precificacao, cancelar_proposta, colocar_em_negociacao, criar_nova_revisao, criar_proposta, enviar_proposta, montar_contexto_publico_proposta, rejeitar_proposta


@login_required
def proposta_lista(request):
    propostas = Proposta.objects.select_related("empresa", "cliente").all()
    busca = request.GET.get("q", "").strip()
    if busca:
        propostas = propostas.filter(Q(codigo__icontains=busca) | Q(cliente__razao_social__icontains=busca))
    return render(request, "comercial/proposta_lista.html", {"propostas": propostas, "busca": busca})


@login_required
def proposta_criar(request):
    form = PropostaCriacaoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        proposta, _ = criar_proposta(usuario=request.user, **form.cleaned_data)
        messages.success(request, "Proposta criada.")
        return redirect("comercial:proposta_detalhe", pk=proposta.pk)
    return render(request, "comercial/formulario.html", {"form": form, "titulo": "Nova proposta"})


def _revisao_atual(proposta):
    return get_object_or_404(PropostaRevisao, proposta=proposta, numero=proposta.revisao_atual)


@login_required
def proposta_detalhe(request, pk):
    proposta = get_object_or_404(Proposta.objects.select_related("empresa", "cliente", "centro_custo", "revisao_aprovada"), pk=pk)
    revisao = _revisao_atual(proposta)
    try:
        calculo = calcular_precificacao(revisao)
    except ValidationError as erro:
        calculo = {"erro": erro.messages[0]}
    return render(request, "comercial/proposta_detalhe.html", {"proposta": proposta, "revisao": revisao, "calculo": calculo, "historico": proposta.historico_status.select_related("usuario")})


@login_required
def revisao_editar(request, pk):
    revisao = get_object_or_404(PropostaRevisao, pk=pk, congelada=False)
    form = PropostaRevisaoForm(request.POST or None, instance=revisao)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Revisão atualizada.")
        return redirect("comercial:proposta_detalhe", pk=revisao.proposta_id)
    return render(request, "comercial/formulario.html", {"form": form, "titulo": f"Editar {revisao}"})


def _adicionar(request, pk, form_class, titulo):
    revisao = get_object_or_404(PropostaRevisao, pk=pk, congelada=False)
    form = form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        objeto = form.save(commit=False)
        objeto.revisao = revisao
        objeto.save()
        messages.success(request, "Registro adicionado.")
        return redirect("comercial:proposta_detalhe", pk=revisao.proposta_id)
    return render(request, "comercial/formulario.html", {"form": form, "titulo": titulo})


@login_required
def item_adicionar(request, pk): return _adicionar(request, pk, PropostaItemForm, "Adicionar item interno")


@login_required
def linha_adicionar(request, pk): return _adicionar(request, pk, PropostaLinhaPublicaForm, "Adicionar linha pública")


@login_required
def tributo_adicionar(request, pk): return _adicionar(request, pk, PropostaTributoForm, "Adicionar tributo")


@login_required
def proposta_enviar(request, pk):
    if request.method != "POST": return HttpResponseBadRequest()
    revisao = _revisao_atual(get_object_or_404(Proposta, pk=pk))
    try:
        enviar_proposta(revisao, request.user)
        messages.success(request, "Revisão enviada e congelada.")
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    return redirect("comercial:proposta_detalhe", pk=pk)


@login_required
def revisao_nova(request, pk):
    if request.method != "POST": return HttpResponseBadRequest()
    proposta = get_object_or_404(Proposta, pk=pk)
    try:
        criar_nova_revisao(_revisao_atual(proposta), request.user)
        messages.success(request, "Nova revisão criada.")
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    return redirect("comercial:proposta_detalhe", pk=pk)


def _executar_acao(request, pk, acao, sucesso):
    if request.method != "POST":
        return HttpResponseBadRequest()
    proposta = get_object_or_404(Proposta, pk=pk)
    try:
        acao(proposta, request.user)
        messages.success(request, sucesso)
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    return redirect("comercial:proposta_detalhe", pk=pk)


@login_required
def proposta_negociar(request, pk):
    return _executar_acao(request, pk, colocar_em_negociacao, "Proposta colocada em negociação.")


@login_required
def proposta_aprovar(request, pk):
    return _executar_acao(request, pk, aprovar_proposta, "Proposta aprovada e obra criada.")


@login_required
def proposta_motivo(request, pk, acao):
    proposta = get_object_or_404(Proposta, pk=pk)
    if acao not in {"rejeitar", "cancelar"}:
        return HttpResponseBadRequest()
    form = MotivoStatusForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        servico = rejeitar_proposta if acao == "rejeitar" else cancelar_proposta
        try:
            servico(proposta, request.user, form.cleaned_data["motivo"])
            messages.success(request, "Status da proposta atualizado.")
            return redirect("comercial:proposta_detalhe", pk=pk)
        except ValidationError as erro:
            form.add_error(None, " ".join(erro.messages))
    return render(request, "comercial/formulario.html", {"form": form, "titulo": f"{acao.title()} proposta {proposta.codigo}"})


@login_required
def documento_publico(request, pk):
    revisao = get_object_or_404(PropostaRevisao.objects.prefetch_related("linhas_publicas"), pk=pk)
    return render(request, "comercial/documento_publico.html", {"documento": montar_contexto_publico_proposta(revisao)})
