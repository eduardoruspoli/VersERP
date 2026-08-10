from django.contrib import admin

from .models import Pessoa


@admin.register(Pessoa)
class PessoaAdmin(admin.ModelAdmin):

    list_display = (
        "razao_social",
        "nome_fantasia",
        "tipo_pessoa",
        "classificacao",
        "cpf_cnpj",
        "cidade",
        "estado",
        "ativo",
    )

    list_filter = (
        "tipo_pessoa",
        "classificacao",
        "ativo",
        "estado",
    )

    search_fields = (
        "razao_social",
        "nome_fantasia",
        "cpf_cnpj",
        "email",
    )

    ordering = ("razao_social",)