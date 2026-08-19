from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Exists, F, OuterRef, Q, Sum
from django.http import HttpResponse, HttpResponseBadRequest
import csv
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AcompanhamentoPropostaForm, MotivoStatusForm, PropostaCriacaoForm, PropostaItemForm, PropostaLinhaPublicaForm, PropostaRevisaoForm, PropostaTributoForm, RelatorioPropostasFiltroForm
from .models import Proposta, PropostaRevisao
from .services import aprovar_proposta, calcular_precificacao, calcular_previsto_realizado, cancelar_proposta, colocar_em_negociacao, criar_nova_revisao, criar_proposta, enviar_proposta, montar_contexto_publico_proposta, rejeitar_proposta
from core.access import filtrar_empresas, objeto_empresa_ou_404
from core.csv import linha_csv_segura


def _propostas(request):
    return filtrar_empresas(Proposta.objects.all(), request.user)


def _revisoes(request):
    return filtrar_empresas(PropostaRevisao.objects.all(), request.user, "proposta__empresa")


@login_required
@permission_required("comercial.view_proposta", raise_exception=True)
def proposta_lista(request):
    propostas = filtrar_empresas(Proposta.objects.select_related("empresa", "cliente"), request.user)
    busca = request.GET.get("q", "").strip()
    if busca:
        propostas = propostas.filter(Q(codigo__icontains=busca) | Q(cliente__razao_social__icontains=busca))
    return render(request, "comercial/proposta_lista.html", {"propostas": propostas, "busca": busca})


@login_required
@permission_required("comercial.add_proposta", raise_exception=True)
def proposta_criar(request):
    form = PropostaCriacaoForm(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        proposta, _ = criar_proposta(usuario=request.user, **form.cleaned_data)
        messages.success(request, "Proposta criada.")
        return redirect("comercial:proposta_detalhe", pk=proposta.pk)
    return render(request, "comercial/formulario.html", {"form": form, "titulo": "Nova proposta"})


def _revisao_atual(proposta):
    return get_object_or_404(PropostaRevisao, proposta=proposta, numero=proposta.revisao_atual)


@login_required
@permission_required("comercial.view_proposta", raise_exception=True)
def proposta_detalhe(request, pk):
    proposta = objeto_empresa_ou_404(Proposta.objects.select_related("empresa", "cliente", "centro_custo", "revisao_aprovada"), request.user, pk=pk)
    revisao = _revisao_atual(proposta)
    try:
        calculo = calcular_precificacao(revisao)
    except ValidationError as erro:
        calculo = {"erro": erro.messages[0]}
    return render(request, "comercial/proposta_detalhe.html", {"proposta": proposta, "revisao": revisao, "calculo": calculo, "historico": proposta.historico_status.select_related("usuario"), "contatos": proposta.historico_contatos.select_related("usuario")})


@login_required
@permission_required("comercial.change_proposta", raise_exception=True)
def proposta_acompanhamento(request, pk):
    proposta = objeto_empresa_ou_404(Proposta.objects.all(), request.user, pk=pk)
    form = AcompanhamentoPropostaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        contato = form.save(commit=False)
        contato.proposta = proposta
        contato.usuario = request.user
        contato.save()
        Proposta.objects.filter(pk=proposta.pk).update(proxima_acao=contato.proxima_acao, data_retorno=contato.data_retorno, acompanhamento=contato.descricao)
        messages.success(request, "Acompanhamento registrado.")
        return redirect("comercial:proposta_detalhe", pk=pk)
    return render(request, "comercial/formulario.html", {"form": form, "titulo": f"Acompanhar {proposta.codigo}"})


@login_required
@permission_required("comercial.change_propostarevisao", raise_exception=True)
def revisao_editar(request, pk):
    revisao = objeto_empresa_ou_404(PropostaRevisao, request.user, lookup="proposta__empresa", pk=pk, congelada=False)
    form = PropostaRevisaoForm(request.POST or None, instance=revisao)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Revisão atualizada.")
        return redirect("comercial:proposta_detalhe", pk=revisao.proposta_id)
    return render(request, "comercial/formulario.html", {"form": form, "titulo": f"Editar {revisao}"})


def _adicionar(request, pk, form_class, titulo):
    revisao = objeto_empresa_ou_404(PropostaRevisao, request.user, lookup="proposta__empresa", pk=pk, congelada=False)
    form = form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        objeto = form.save(commit=False)
        objeto.revisao = revisao
        objeto.save()
        messages.success(request, "Registro adicionado.")
        return redirect("comercial:proposta_detalhe", pk=revisao.proposta_id)
    return render(request, "comercial/formulario.html", {"form": form, "titulo": titulo})


@login_required
@permission_required("comercial.add_propostaitem", raise_exception=True)
def item_adicionar(request, pk): return _adicionar(request, pk, PropostaItemForm, "Adicionar item interno")


@login_required
@permission_required("comercial.add_propostalinhapublica", raise_exception=True)
def linha_adicionar(request, pk): return _adicionar(request, pk, PropostaLinhaPublicaForm, "Adicionar linha pública")


@login_required
@permission_required("comercial.add_propostatributo", raise_exception=True)
def tributo_adicionar(request, pk): return _adicionar(request, pk, PropostaTributoForm, "Adicionar tributo")


@login_required
@permission_required("comercial.change_proposta", raise_exception=True)
def proposta_enviar(request, pk):
    if request.method != "POST": return HttpResponseBadRequest()
    revisao = _revisao_atual(objeto_empresa_ou_404(Proposta.objects.all(), request.user, pk=pk))
    try:
        enviar_proposta(revisao, request.user)
        messages.success(request, "Revisão enviada e congelada.")
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    return redirect("comercial:proposta_detalhe", pk=pk)


@login_required
@permission_required(("comercial.change_proposta", "comercial.add_propostarevisao"), raise_exception=True)
def revisao_nova(request, pk):
    if request.method != "POST": return HttpResponseBadRequest()
    proposta = objeto_empresa_ou_404(Proposta.objects.all(), request.user, pk=pk)
    try:
        criar_nova_revisao(_revisao_atual(proposta), request.user)
        messages.success(request, "Nova revisão criada.")
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    return redirect("comercial:proposta_detalhe", pk=pk)


def _executar_acao(request, pk, acao, sucesso):
    if request.method != "POST":
        return HttpResponseBadRequest()
    proposta = objeto_empresa_ou_404(Proposta.objects.all(), request.user, pk=pk)
    try:
        acao(proposta, request.user)
        messages.success(request, sucesso)
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
    return redirect("comercial:proposta_detalhe", pk=pk)


@login_required
@permission_required("comercial.change_proposta", raise_exception=True)
def proposta_negociar(request, pk):
    return _executar_acao(request, pk, colocar_em_negociacao, "Proposta colocada em negociação.")


@login_required
@permission_required(("comercial.aprovar_proposta", "comercial.criar_obra_proposta"), raise_exception=True)
def proposta_aprovar(request, pk):
    return _executar_acao(request, pk, aprovar_proposta, "Proposta aprovada e obra criada.")


@login_required
def proposta_motivo(request, pk, acao):
    proposta = objeto_empresa_ou_404(Proposta.objects.all(), request.user, pk=pk)
    if acao not in {"rejeitar", "cancelar"}:
        return HttpResponseBadRequest()
    permissao = "comercial.rejeitar_proposta" if acao == "rejeitar" else "comercial.cancelar_proposta"
    if not request.user.has_perm(permissao):
        raise PermissionDenied
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
@permission_required("comercial.view_proposta", raise_exception=True)
def documento_publico(request, pk):
    revisao = objeto_empresa_ou_404(PropostaRevisao.objects.prefetch_related("linhas_publicas"), request.user, lookup="proposta__empresa", pk=pk)
    return render(request, "comercial/documento_publico.html", {"documento": montar_contexto_publico_proposta(revisao)})


@login_required
@permission_required("comercial.view_proposta", raise_exception=True)
def proposta_pdf(request, pk):
    from core.pdf import resposta_pdf
    revisao=objeto_empresa_ou_404(PropostaRevisao.objects.select_related("proposta__empresa","proposta__cliente").prefetch_related("linhas_publicas"),request.user,lookup="proposta__empresa",pk=pk)
    contexto={"documento":montar_contexto_publico_proposta(revisao)}
    return resposta_pdf("comercial/proposta_pdf.html",contexto,f"{revisao.proposta.codigo}-rev-{revisao.numero:02d}.pdf")


@login_required
@permission_required("comercial.view_proposta", raise_exception=True)
def relatorio_propostas(request):
    from financeiro.models import BaixaFinanceira, RateioCentroCusto
    form=RelatorioPropostasFiltroForm(request.GET or None,usuario=request.user)
    propostas=filtrar_empresas(Proposta.objects.filter(revisoes__numero=F("revisao_atual")).select_related("empresa","cliente","responsavel_interno","centro_custo"),request.user)
    if not form.is_valid():
        propostas=propostas.none()
    else:
        d=form.cleaned_data; propostas=propostas.filter(empresa=d["empresa"])
        if d.get("data_inicial"): propostas=propostas.filter(revisoes__data_proposta__gte=d["data_inicial"])
        if d.get("data_final"): propostas=propostas.filter(revisoes__data_proposta__lte=d["data_final"])
        if d.get("numero"): propostas=propostas.filter(codigo__icontains=d["numero"])
        if d.get("cliente"): propostas=propostas.filter(cliente=d["cliente"])
        if d.get("contato"): propostas=propostas.filter(revisoes__aos_cuidados_de__icontains=d["contato"])
        if d.get("responsavel"): propostas=propostas.filter(responsavel_interno=d["responsavel"])
        if d.get("status"): propostas=propostas.filter(status=d["status"])
        if d.get("busca"):
            texto=d["busca"]; propostas=propostas.filter(Q(codigo__icontains=texto)|Q(cliente__razao_social__icontains=texto)|Q(revisoes__nome_servico__icontains=texto)|Q(revisoes__observacoes_comerciais__icontains=texto))
    propostas=propostas.annotate(
        data_emissao_relatorio=F("revisoes__data_proposta"), contato_relatorio=F("revisoes__aos_cuidados_de"),
        servico_relatorio=F("revisoes__nome_servico"), valor_relatorio=F("revisoes__preco_venda_final"),
        observacao_relatorio=F("revisoes__observacoes_comerciais"),
        tem_receita=Exists(RateioCentroCusto.objects.filter(centro_custo_id=OuterRef("centro_custo_id"),lancamento__tipo="RECEBER").exclude(lancamento__status="CANCELADO")),
        tem_recebimento=Exists(BaixaFinanceira.objects.filter(parcela__lancamento__rateios_centro_custo__centro_custo_id=OuterRef("centro_custo_id"))),
    ).order_by("-data_emissao_relatorio","-pk")
    resumo=propostas.aggregate(quantidade=Count("pk"),valor_total=Sum("valor_relatorio"))
    por_status=list(propostas.values("status").annotate(quantidade=Count("pk"),valor=Sum("valor_relatorio")).order_by("status"))
    for item in por_status: item["label"]=dict(Proposta.Status.choices).get(item["status"],item["status"])
    if request.GET.get("formato") == "csv":
        resposta = HttpResponse(content_type="text/csv; charset=utf-8")
        resposta["Content-Disposition"] = 'attachment; filename="relatorio-propostas.csv"'
        resposta.write("\ufeff")
        writer = csv.writer(resposta, delimiter=";")
        writer.writerow(["Número", "Data", "Cliente", "Serviço", "Status", "Valor", "Responsável"])
        for proposta in propostas:
            writer.writerow(linha_csv_segura([proposta.codigo, proposta.data_emissao_relatorio.strftime("%d/%m/%Y"), proposta.cliente, proposta.servico_relatorio, proposta.get_status_display(), str(proposta.valor_relatorio).replace(".", ","), proposta.responsavel_interno or ""]))
        return resposta
    pagina=Paginator(propostas,50).get_page(request.GET.get("page"))
    return render(request,"comercial/relatorio_propostas.html",{"form":form,"pagina":pagina,"resumo":resumo,"por_status":por_status,"status_labels":dict(Proposta.Status.choices)})


@login_required
@permission_required("comercial.view_proposta", raise_exception=True)
def previsto_realizado(request, pk):
    proposta = objeto_empresa_ou_404(Proposta.objects.all(), request.user, pk=pk)
    relatorio = calcular_previsto_realizado(proposta)
    pagina = None
    if relatorio["disponivel"]:
        pagina = Paginator(relatorio["detalhes"], 20).get_page(request.GET.get("page"))
    return render(request, "comercial/previsto_realizado.html", {"proposta": proposta, "relatorio": relatorio, "pagina": pagina})
