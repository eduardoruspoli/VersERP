from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from financeiro.models import Empresa


def empresas_usuario(usuario, *, ativas=None):
    queryset = Empresa.objects.all()
    if not usuario.is_authenticated:
        return queryset.none()
    if not usuario.is_superuser:
        queryset = queryset.filter(usuarios_autorizados__usuario=usuario)
    if ativas is not None:
        queryset = queryset.filter(ativa=ativas)
    return queryset.distinct()


def ids_empresas_usuario(usuario):
    return empresas_usuario(usuario).values_list("pk", flat=True)


def pode_acessar_empresa(usuario, empresa_ou_id):
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True
    empresa_id = getattr(empresa_ou_id, "pk", empresa_ou_id)
    return usuario.vinculos_empresas.filter(empresa_id=empresa_id).exists()


def exigir_empresa(usuario, empresa_ou_id):
    if not pode_acessar_empresa(usuario, empresa_ou_id):
        raise PermissionDenied("Você não possui acesso a esta empresa.")
    return empresa_ou_id


def empresa_request(request, *, obrigatoria=True, ativas=None):
    empresas = empresas_usuario(request.user, ativas=ativas)
    empresa_id = request.GET.get("empresa") or request.POST.get("empresa")
    if empresa_id:
        return get_object_or_404(empresas, pk=empresa_id), empresas
    empresa = empresas.filter(principal=True).first() or empresas.first()
    if obrigatoria and not empresa:
        raise PermissionDenied("Nenhuma empresa foi autorizada para este usuário.")
    return empresa, empresas


def filtrar_empresas(queryset, usuario, lookup="empresa"):
    if usuario.is_superuser:
        return queryset
    return queryset.filter(**{f"{lookup}__in": ids_empresas_usuario(usuario)})


def objeto_empresa_ou_404(queryset, usuario, *, lookup="empresa", **filtros):
    return get_object_or_404(filtrar_empresas(queryset, usuario, lookup), **filtros)


def acesso_empresa(get_empresa):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            exigir_empresa(request.user, get_empresa(request, *args, **kwargs))
            return view(request, *args, **kwargs)
        return wrapper
    return decorator
