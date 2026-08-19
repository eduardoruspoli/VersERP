from django.contrib.auth.models import Group, Permission


PERFIS_PADRAO = {
    "Administrador": {"apps": {"core", "pessoas", "financeiro", "comercial", "compras", "rh"}},
    "Diretoria/Gerência": {"apps": {"pessoas", "financeiro", "comercial", "compras", "rh"}},
    "Financeiro": {"apps": {"pessoas", "financeiro"}},
    "Comercial": {"apps": {"pessoas", "comercial"}},
    "Compras": {"apps": {"pessoas", "compras"}},
    "RH": {"apps": {"pessoas", "rh"}},
    "RH restrito/Ponto": {"codenames": {"view_rh", "view_funcionario", "view_competenciaponto", "add_competenciaponto", "change_competenciaponto", "ajustar_ponto"}},
}

SENSIVE_EXCLUDED_FROM_BROAD = {
    "view_remuneracao", "change_remuneracao", "view_dados_bancarios",
    "aprovar_pedido", "integrar_documento_financeiro", "estornar_documento_financeiro",
    "reabrir_ponto", "conferir_folha", "gerenciar_acessos",
}


def sincronizar_perfis_padrao():
    resultado = []
    for nome, regra in PERFIS_PADRAO.items():
        grupo, criado = Group.objects.get_or_create(name=nome)
        permissoes = Permission.objects.none()
        if regra.get("apps"):
            permissoes = Permission.objects.filter(content_type__app_label__in=regra["apps"])
            if nome != "Administrador":
                permissoes = permissoes.exclude(codename__in=SENSIVE_EXCLUDED_FROM_BROAD)
        elif regra.get("codenames"):
            permissoes = Permission.objects.filter(content_type__app_label="rh", codename__in=regra["codenames"])
        grupo.permissions.set(permissoes)
        resultado.append((grupo, criado, permissoes.count()))
    return resultado
