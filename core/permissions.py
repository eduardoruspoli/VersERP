from django.contrib.auth.models import Group, Permission


PERFIS_PADRAO = {
    "Administrador": {"all": True},
    "Gerência": {
        "all": True,
        "exclude_codenames": {
            "view_remuneracao",
            "change_remuneracao",
            "view_dados_bancarios",
            "gerenciar_acessos",
        },
    },
    "Financeiro e Compras": {
        "apps": {"pessoas", "financeiro", "compras"},
    },
    "Comercial": {
        "apps": {"pessoas", "comercial"},
    },
    "RH": {
        "apps": {"pessoas", "rh"},
    },
    "RH restrito/Ponto": {
        "codenames": {
            "view_rh",
            "view_funcionario",
            "view_competenciaponto",
            "add_competenciaponto",
            "change_competenciaponto",
            "ajustar_ponto",
        },
    },
}

def sincronizar_perfis_padrao():
    resultado = []
    for nome, regra in PERFIS_PADRAO.items():
        grupo, criado = Group.objects.get_or_create(name=nome)
        if regra.get("all"):
            permissoes = Permission.objects.all()
        elif regra.get("apps"):
            permissoes = Permission.objects.filter(content_type__app_label__in=regra["apps"])
        elif regra.get("codenames"):
            permissoes = Permission.objects.filter(content_type__app_label="rh", codename__in=regra["codenames"])
        else:
            permissoes = Permission.objects.none()

        if regra.get("exclude_codenames"):
            permissoes = permissoes.exclude(codename__in=regra["exclude_codenames"])

        grupo.permissions.set(permissoes)
        resultado.append((grupo, criado, permissoes.count()))
    return resultado
