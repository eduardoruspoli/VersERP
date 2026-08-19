from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from financeiro.models import Empresa

from .forms import (CompetenciaForm, ConferenciaForm, ContratoForm,
                    DadosBancariosForm, EventoForm, FuncionarioForm, JornadaDiaForm,
                    JornadaForm, MarcacaoForm, MotivoForm, OcorrenciaForm,
                    RetornoForm, ValeForm)
from .models import (CompetenciaPonto, ConferenciaFolha, EventoFolha, Funcionario,
                     Jornada, RetornoContabilidade, ValeAdiantamento)
from .services import (apurar_competencia, atualizar_conferencia,
                       calcular_previas_empresa, comparar_retorno,
                       fechar_competencia, gerar_parcelas_vale,
                       reabrir_competencia)


def _empresa(request):
    empresas = Empresa.objects.filter(ativa=True)
    empresa_id = request.GET.get("empresa") or request.POST.get("empresa")
    empresa = empresas.filter(pk=empresa_id).first() if empresa_id else empresas.filter(principal=True).first() or empresas.first()
    return empresa, empresas


def _render_form(request, form, titulo, voltar, template="rh/formulario.html"):
    return render(request, template, {"form":form,"titulo":titulo,"voltar":voltar})


@login_required
@permission_required("rh.view_rh", raise_exception=True)
def dashboard(request):
    empresa, empresas = _empresa(request)
    funcionarios = Funcionario.objects.filter(empresa=empresa) if empresa else Funcionario.objects.none()
    competencias = CompetenciaPonto.objects.filter(funcionario__empresa=empresa) if empresa else CompetenciaPonto.objects.none()
    contexto = {"empresa":empresa,"empresas":empresas,
        "ativos":funcionarios.filter(situacao=Funcionario.Situacao.ATIVO).count(),
        "afastados":funcionarios.filter(situacao=Funcionario.Situacao.AFASTADO).count(),
        "ferias":funcionarios.filter(situacao=Funcionario.Situacao.FERIAS).count(),
        "pontos_pendentes":competencias.exclude(status=CompetenciaPonto.Status.FECHADO).count(),
        "bh_negativo":competencias.filter(saldo_final_minutos__lt=0).count(),
        "horas_100":competencias.filter(horas_100_minutos__gt=0).exclude(status=CompetenciaPonto.Status.FECHADO).count(),
        "eventos_pendentes":EventoFolha.objects.filter(empresa=empresa,status=EventoFolha.Status.PENDENTE).count() if empresa else 0,
        "divergencias":ConferenciaFolha.objects.filter(retorno__funcionario__empresa=empresa,status=ConferenciaFolha.Status.DIVERGENTE).count() if empresa else 0}
    return render(request,"rh/dashboard.html",contexto)


@login_required
@permission_required("rh.view_funcionario", raise_exception=True)
def funcionario_lista(request):
    empresa, empresas = _empresa(request)
    qs=Funcionario.objects.filter(empresa=empresa).select_related("pessoa") if empresa else Funcionario.objects.none()
    busca=request.GET.get("q","").strip()
    if busca: qs=qs.filter(Q(pessoa__razao_social__icontains=busca)|Q(matricula__icontains=busca))
    return render(request,"rh/funcionario_lista.html",{"funcionarios":qs,"empresa":empresa,"empresas":empresas,"busca":busca})


@login_required
@permission_required("rh.add_funcionario", raise_exception=True)
def funcionario_criar(request):
    empresa,_=_empresa(request); form=FuncionarioForm(request.POST or None,empresa=empresa)
    if form.is_valid():
        obj=form.save(); messages.success(request,"Funcionário cadastrado."); return redirect("rh:funcionario_detalhe",pk=obj.pk)
    return _render_form(request,form,"Novo funcionário","rh:funcionario_lista")


@login_required
@permission_required("rh.view_funcionario", raise_exception=True)
def funcionario_detalhe(request,pk):
    empresa,_=_empresa(request); obj=get_object_or_404(Funcionario.objects.select_related("pessoa","empresa"),pk=pk,empresa=empresa)
    return render(request,"rh/funcionario_detalhe.html",{"funcionario":obj,"pode_remuneracao":request.user.has_perm("rh.view_remuneracao"),"pode_banco":request.user.has_perm("rh.view_dados_bancarios")})


@login_required
@permission_required("rh.change_funcionario", raise_exception=True)
def funcionario_editar(request,pk):
    empresa,_=_empresa(request); obj=get_object_or_404(Funcionario,pk=pk,empresa=empresa); form=FuncionarioForm(request.POST or None,instance=obj,empresa=empresa)
    if form.is_valid(): form.save(); messages.success(request,"Cadastro atualizado."); return redirect("rh:funcionario_detalhe",pk=pk)
    return _render_form(request,form,"Editar funcionário","rh:funcionario_lista")


@login_required
@permission_required(("rh.view_dados_bancarios", "rh.change_funcionario"), raise_exception=True)
def dados_bancarios(request,pk):
    empresa,_=_empresa(request); obj=get_object_or_404(Funcionario,pk=pk,empresa=empresa); form=DadosBancariosForm(request.POST or None,instance=obj)
    if form.is_valid(): form.save(); messages.success(request,"Dados bancários atualizados."); return redirect("rh:funcionario_detalhe",pk=pk)
    return _render_form(request,form,"Dados bancários","rh:funcionario_lista")


@login_required
@permission_required("rh.change_remuneracao", raise_exception=True)
def contrato_criar(request,funcionario_id):
    empresa,_=_empresa(request); funcionario=get_object_or_404(Funcionario,pk=funcionario_id,empresa=empresa); form=ContratoForm(request.POST or None)
    if form.is_valid(): obj=form.save(commit=False); obj.funcionario=funcionario; obj.criado_por=request.user; obj.save(); messages.success(request,"Condição contratual registrada."); return redirect("rh:funcionario_detalhe",pk=funcionario.pk)
    return _render_form(request,form,"Nova condição contratual","rh:funcionario_lista")


@login_required
@permission_required("rh.change_funcionario", raise_exception=True)
def jornada_criar(request,funcionario_id):
    empresa,_=_empresa(request); funcionario=get_object_or_404(Funcionario,pk=funcionario_id,empresa=empresa); form=JornadaForm(request.POST or None)
    if form.is_valid(): obj=form.save(commit=False); obj.funcionario=funcionario; obj.criado_por=request.user; obj.save(); return redirect("rh:funcionario_detalhe",pk=funcionario.pk)
    return _render_form(request,form,"Nova jornada","rh:funcionario_lista")


@login_required
@permission_required("rh.change_funcionario", raise_exception=True)
def jornada_dia_criar(request,jornada_id):
    empresa,_=_empresa(request); jornada=get_object_or_404(Jornada,pk=jornada_id,funcionario__empresa=empresa); form=JornadaDiaForm(request.POST or None)
    if form.is_valid(): obj=form.save(commit=False); obj.jornada=jornada; obj.full_clean(); obj.save(); return redirect("rh:funcionario_detalhe",pk=jornada.funcionario_id)
    return _render_form(request,form,"Configurar dia da jornada","rh:funcionario_lista")


@login_required
@permission_required("rh.view_competenciaponto", raise_exception=True)
def competencia_lista(request):
    empresa,empresas=_empresa(request); qs=CompetenciaPonto.objects.filter(funcionario__empresa=empresa).select_related("funcionario__pessoa") if empresa else CompetenciaPonto.objects.none()
    return render(request,"rh/competencia_lista.html",{"competencias":qs,"empresa":empresa,"empresas":empresas})


@login_required
@permission_required("rh.add_competenciaponto", raise_exception=True)
def competencia_criar(request):
    empresa,_=_empresa(request); form=CompetenciaForm(request.POST or None,empresa=empresa)
    if form.is_valid(): obj=form.save(); return redirect("rh:competencia_detalhe",pk=obj.pk)
    return _render_form(request,form,"Nova competência","rh:competencia_lista")


@login_required
@permission_required("rh.view_competenciaponto", raise_exception=True)
def competencia_detalhe(request,pk):
    empresa,_=_empresa(request); obj=get_object_or_404(CompetenciaPonto.objects.select_related("funcionario__pessoa").prefetch_related("apuracoes"),pk=pk,funcionario__empresa=empresa)
    return render(request,"rh/competencia_detalhe.html",{"competencia":obj})


@login_required
@permission_required("rh.ajustar_ponto", raise_exception=True)
def marcacao_criar(request,funcionario_id):
    empresa,_=_empresa(request); funcionario=get_object_or_404(Funcionario,pk=funcionario_id,empresa=empresa); form=MarcacaoForm(request.POST or None,funcionario=funcionario)
    if form.is_valid(): obj=form.save(commit=False); obj.funcionario=funcionario; obj.usuario_responsavel=request.user; obj.save(); return redirect("rh:funcionario_detalhe",pk=funcionario.pk)
    return _render_form(request,form,"Registrar marcação","rh:funcionario_lista")


@login_required
@permission_required("rh.ajustar_ponto", raise_exception=True)
def ocorrencia_criar(request,funcionario_id):
    empresa,_=_empresa(request); funcionario=get_object_or_404(Funcionario,pk=funcionario_id,empresa=empresa); form=OcorrenciaForm(request.POST or None)
    if form.is_valid(): obj=form.save(commit=False); obj.funcionario=funcionario; obj.usuario=request.user; obj.save(); return redirect("rh:funcionario_detalhe",pk=funcionario.pk)
    return _render_form(request,form,"Registrar ocorrência","rh:funcionario_lista")


@login_required
@permission_required("rh.ajustar_ponto", raise_exception=True)
def competencia_apurar(request,pk):
    if request.method!="POST": return redirect("rh:competencia_detalhe",pk=pk)
    empresa,_=_empresa(request); obj=get_object_or_404(CompetenciaPonto,pk=pk,funcionario__empresa=empresa)
    try: apurar_competencia(obj,request.user); messages.success(request,"Competência apurada.")
    except ValidationError as erro: messages.error(request," ".join(erro.messages))
    return redirect("rh:competencia_detalhe",pk=pk)


@login_required
@permission_required("rh.fechar_ponto", raise_exception=True)
def competencia_fechar(request,pk):
    if request.method=="POST":
        empresa,_=_empresa(request); obj=get_object_or_404(CompetenciaPonto,pk=pk,funcionario__empresa=empresa)
        try: fechar_competencia(obj,request.user); messages.success(request,"Competência fechada.")
        except ValidationError as erro: messages.error(request," ".join(erro.messages))
    return redirect("rh:competencia_detalhe",pk=pk)


@login_required
@permission_required("rh.reabrir_ponto", raise_exception=True)
def competencia_reabrir(request,pk):
    empresa,_=_empresa(request); obj=get_object_or_404(CompetenciaPonto,pk=pk,funcionario__empresa=empresa); form=MotivoForm(request.POST or None)
    if form.is_valid(): reabrir_competencia(obj,request.user,form.cleaned_data["motivo"]); return redirect("rh:competencia_detalhe",pk=pk)
    return _render_form(request,form,"Reabrir competência","rh:competencia_lista")


@login_required
@permission_required("rh.view_eventofolha", raise_exception=True)
def evento_lista(request):
    empresa,empresas=_empresa(request); qs=EventoFolha.objects.filter(empresa=empresa).select_related("funcionario__pessoa") if empresa else EventoFolha.objects.none()
    return render(request,"rh/evento_lista.html",{"eventos":qs,"empresa":empresa,"empresas":empresas})


@login_required
@permission_required("rh.lancar_evento_folha", raise_exception=True)
def evento_criar(request):
    empresa,_=_empresa(request); form=EventoForm(request.POST or None,empresa=empresa)
    if form.is_valid(): obj=form.save(commit=False); obj.empresa=empresa; obj.origem="MANUAL"; obj.criado_por=request.user; obj.save(); return redirect("rh:evento_lista")
    return _render_form(request,form,"Novo evento","rh:evento_lista")


@login_required
@permission_required("rh.view_valeadiantamento", raise_exception=True)
def vale_lista(request):
    empresa,empresas=_empresa(request); qs=ValeAdiantamento.objects.filter(funcionario__empresa=empresa).select_related("funcionario__pessoa").prefetch_related("parcelas") if empresa else ValeAdiantamento.objects.none()
    return render(request,"rh/vale_lista.html",{"vales":qs,"empresa":empresa,"empresas":empresas})


@login_required
@permission_required("rh.add_valeadiantamento", raise_exception=True)
def vale_criar(request):
    empresa,_=_empresa(request); form=ValeForm(request.POST or None,empresa=empresa)
    if form.is_valid(): obj=form.save(commit=False); obj.criado_por=request.user; obj.save(); gerar_parcelas_vale(obj,form.cleaned_data["competencia_inicial"]); return redirect("rh:vale_lista")
    return _render_form(request,form,"Novo vale/adiantamento","rh:vale_lista")


@login_required
@permission_required("rh.view_remuneracao", raise_exception=True)
def pre_fechamento(request):
    empresa,empresas=_empresa(request); texto=request.GET.get("competencia") or date.today().strftime("%Y-%m"); competencia=date.fromisoformat(texto+"-01")
    previas=calcular_previas_empresa(empresa,competencia) if empresa else []
    return render(request,"rh/pre_fechamento.html",{"previas":previas,"empresa":empresa,"empresas":empresas,"competencia":texto})


@login_required
@permission_required("rh.registrar_retorno_contabilidade", raise_exception=True)
def retorno_criar(request):
    empresa,_=_empresa(request); form=RetornoForm(request.POST or None,empresa=empresa)
    if form.is_valid(): obj=form.save(commit=False); obj.registrado_por=request.user; obj.save(); return redirect("rh:conferencia",pk=obj.pk)
    return _render_form(request,form,"Retorno da contabilidade","rh:dashboard")


@login_required
@permission_required("rh.conferir_folha", raise_exception=True)
def conferencia(request,pk):
    empresa,_=_empresa(request); retorno=get_object_or_404(RetornoContabilidade,pk=pk,funcionario__empresa=empresa); atual=getattr(retorno,"conferencia",None); form=ConferenciaForm(request.POST or None,instance=atual)
    if form.is_valid(): atualizar_conferencia(retorno,form.cleaned_data["status"],form.cleaned_data["justificativa"],request.user); return redirect("rh:conferencia",pk=pk)
    contexto=comparar_retorno(retorno); contexto["form"]=form
    return render(request,"rh/conferencia.html",contexto)
