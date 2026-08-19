from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import login, logout
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group
from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from financeiro.models import Empresa

from .access import empresas_usuario
from .forms import GrupoForm, UsuarioAdministracaoForm
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
    return render(request,"core/usuarios_lista.html",{"usuarios":usuarios})


@login_required
@permission_required("core.gerenciar_acessos",raise_exception=True)
def usuario_editar(request,pk):
    usuario=get_object_or_404(get_user_model(),pk=pk); form=UsuarioAdministracaoForm(request.POST or None,instance=usuario)
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
        sincronizar_perfis_padrao(); messages.success(request,"Perfis padrão sincronizados."); return redirect("core:grupos_lista")
    return render(request,"core/grupos_lista.html",{"grupos":Group.objects.annotate(total_usuarios=Count("user"),total_permissoes=Count("permissions",distinct=True)).order_by("name")})


@login_required
@permission_required("core.gerenciar_acessos",raise_exception=True)
def grupo_editar(request,pk):
    grupo=get_object_or_404(Group,pk=pk); form=GrupoForm(request.POST or None,instance=grupo)
    if form.is_valid(): form.save(); messages.success(request,"Perfil atualizado."); return redirect("core:grupos_lista")
    return render(request,"core/formulario.html",{"form":form,"titulo":f"Perfil {grupo.name}","voltar":"core:grupos_lista"})

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

            if proxima_url:
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
