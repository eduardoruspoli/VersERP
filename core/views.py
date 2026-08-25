from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import login, logout
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group
from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from financeiro.models import Empresa
from rh.models import Feriado
from comercial.models import ModeloConteudoProposta

from .access import empresas_usuario
from .forms import (EmpresaConfiguracaoForm, FeriadoConfiguracaoForm, GrupoForm,
                    ModeloPropostaConfiguracaoForm, UsuarioAdministracaoForm)
from .models import AuditoriaAcesso, UsuarioEmpresa
from .permissions import sincronizar_perfis_padrao
from .services import indicadores_dashboard, pendencias_usuario

# Create your views here.

@login_required
def dashboard(request):
    return render(request,"core/dashboard.html",{"indicadores":indicadores_dashboard(request.user)})


@login_required
def relatorios(request):
    return render(request,"core/relatorios.html")


@login_required
def pendencias(request):
    return render(request,"core/pendencias.html",{"pendencias":pendencias_usuario(request.user)})


@login_required
@permission_required("core.view_configuracoes",raise_exception=True)
def configuracoes(request):
    return render(request,"core/configuracoes.html",{"empresas":empresas_usuario(request.user)})


@login_required
@permission_required("core.gerenciar_acessos",raise_exception=True)
def usuarios_lista(request):
    usuarios=get_user_model().objects.prefetch_related("groups","vinculos_empresas__empresa").order_by("username")
    if not request.user.is_superuser:
        usuarios = usuarios.filter(vinculos_empresas__empresa__in=empresas_usuario(request.user), is_superuser=False).exclude(pk=request.user.pk).distinct()
    return render(request,"core/usuarios_lista.html",{"usuarios":usuarios})


@login_required
@permission_required("core.gerenciar_acessos",raise_exception=True)
def usuario_editar(request,pk):
    usuario=get_object_or_404(get_user_model(),pk=pk)
    if not request.user.is_superuser:
        autorizado = usuario.vinculos_empresas.filter(empresa__in=empresas_usuario(request.user)).exists()
        if usuario.is_superuser or usuario.pk == request.user.pk or not autorizado:
            raise PermissionDenied("Usuário fora do escopo de administração.")
    form=UsuarioAdministracaoForm(request.POST or None,instance=usuario,ator=request.user)
    if form.is_valid():
        with transaction.atomic():
            usuario=form.save(); usuario.groups.set(form.cleaned_data["grupos"])
            anteriores=set(usuario.vinculos_empresas.values_list("empresa_id",flat=True)); novos=set(form.cleaned_data["empresas"].values_list("pk",flat=True))
            usuario.vinculos_empresas.exclude(empresa_id__in=novos).delete()
            for empresa_id in novos-anteriores: UsuarioEmpresa.objects.create(usuario=usuario,empresa_id=empresa_id,criado_por=request.user)
            AuditoriaAcesso.objects.create(usuario_alvo=usuario,usuario_responsavel=request.user,acao="ATUALIZAR_ACESSO",descricao=f"Grupos e empresas atualizados: {sorted(novos)}")
        messages.success(request,"Acessos atualizados."); return redirect("core:usuarios_lista")
    return render(request,"core/formulario.html",{"form":form,"titulo":f"Acessos de {usuario}","voltar":"core:usuarios_lista"})


@login_required
@permission_required("core.gerenciar_acessos",raise_exception=True)
def grupos_lista(request):
    if request.method=="POST" and request.POST.get("sincronizar"):
        if not request.user.is_superuser:
            raise PermissionDenied("Somente superusuários podem sincronizar perfis padrão.")
        sincronizar_perfis_padrao(); messages.success(request,"Perfis padrão sincronizados."); return redirect("core:grupos_lista")
    return render(request,"core/grupos_lista.html",{"grupos":Group.objects.annotate(total_usuarios=Count("user"),total_permissoes=Count("permissions",distinct=True)).order_by("name")})


@login_required
@permission_required("core.gerenciar_acessos",raise_exception=True)
def grupo_editar(request,pk):
    grupo=get_object_or_404(Group,pk=pk)
    if not request.user.is_superuser:
        permissoes_grupo = {f"{p.content_type.app_label}.{p.codename}" for p in grupo.permissions.select_related("content_type")}
        if not permissoes_grupo.issubset(request.user.get_all_permissions()):
            raise PermissionDenied("Perfil contém permissões fora do seu escopo.")
    form=GrupoForm(request.POST or None,instance=grupo,ator=request.user)
    if form.is_valid(): form.save(); messages.success(request,"Perfil atualizado."); return redirect("core:grupos_lista")
    return render(request,"core/formulario.html",{"form":form,"titulo":f"Perfil {grupo.name}","voltar":"core:grupos_lista"})


def _config_form(request, form_class, titulo, voltar, instance=None, **kwargs):
    form = form_class(request.POST or None, instance=instance, **kwargs)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Cadastro salvo.")
        return redirect(voltar)
    return render(request, "core/configuracao_formulario.html", {"form": form, "titulo": titulo, "voltar": voltar})


@login_required
@permission_required("financeiro.view_empresa", raise_exception=True)
def empresas_lista(request):
    empresas = empresas_usuario(request.user).order_by("razao_social")
    return render(request, "core/configuracao_lista.html", {"titulo": "Empresas", "objetos": empresas, "novo_url": "core:empresa_nova", "editar_url": "core:empresa_editar", "colunas": [("Razão social", "razao_social"), ("CNPJ", "cnpj"), ("Ativa", "ativa")]})


@login_required
@permission_required("financeiro.add_empresa", raise_exception=True)
def empresa_nova(request):
    return _config_form(request, EmpresaConfiguracaoForm, "Nova empresa", "core:empresas_lista")


@login_required
@permission_required("financeiro.change_empresa", raise_exception=True)
def empresa_editar(request, pk):
    empresa = get_object_or_404(empresas_usuario(request.user), pk=pk)
    return _config_form(request, EmpresaConfiguracaoForm, "Editar empresa", "core:empresas_lista", instance=empresa)


@login_required
@permission_required("rh.view_feriado", raise_exception=True)
def feriados_lista(request):
    objetos = Feriado.objects.filter(empresa__in=empresas_usuario(request.user)).select_related("empresa")
    return render(request, "core/feriados_lista.html", {"objetos": objetos})


@login_required
@permission_required("rh.add_feriado", raise_exception=True)
def feriado_novo(request):
    return _config_form(request, FeriadoConfiguracaoForm, "Novo feriado", "core:feriados_lista", usuario=request.user)


@login_required
@permission_required("rh.change_feriado", raise_exception=True)
def feriado_editar(request, pk):
    objeto = get_object_or_404(Feriado, pk=pk, empresa__in=empresas_usuario(request.user))
    return _config_form(request, FeriadoConfiguracaoForm, "Editar feriado", "core:feriados_lista", instance=objeto, usuario=request.user)


@login_required
@permission_required("comercial.view_modeloconteudoproposta", raise_exception=True)
def modelos_proposta_lista(request):
    objetos = ModeloConteudoProposta.objects.filter(empresa__in=empresas_usuario(request.user)).select_related("empresa")
    return render(request, "core/modelos_proposta_lista.html", {"objetos": objetos})


@login_required
@permission_required("comercial.add_modeloconteudoproposta", raise_exception=True)
def modelo_proposta_novo(request):
    return _config_form(request, ModeloPropostaConfiguracaoForm, "Novo modelo de proposta", "core:modelos_proposta_lista", usuario=request.user)


@login_required
@permission_required("comercial.change_modeloconteudoproposta", raise_exception=True)
def modelo_proposta_editar(request, pk):
    objeto = get_object_or_404(ModeloConteudoProposta, pk=pk, empresa__in=empresas_usuario(request.user))
    return _config_form(request, ModeloPropostaConfiguracaoForm, "Editar modelo de proposta", "core:modelos_proposta_lista", instance=objeto, usuario=request.user)

def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    if request.method == "POST":
        form = AuthenticationForm(
            request,
            data=request.POST,
        )

        if form.is_valid():
            usuario = form.get_user()
            login(request, usuario)

            proxima_url = request.GET.get("next")

            if proxima_url and url_has_allowed_host_and_scheme(
                proxima_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(proxima_url)

            return redirect("core:dashboard")

    else:
        form = AuthenticationForm(request)

    return render(
        request,
        "core/login.html",
        {
            "form": form,
        },
    )


def logout_view(request):
    if request.method == "POST":
        logout(request)

    return redirect("core:login")
