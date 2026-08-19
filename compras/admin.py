from django.contrib import admin

from .models import HistoricoSolicitacaoCompra, SolicitacaoCompra, SolicitacaoCompraItem


class SolicitacaoCompraItemInline(admin.TabularInline):
    model = SolicitacaoCompraItem
    extra = 0


@admin.register(SolicitacaoCompra)
class SolicitacaoCompraAdmin(admin.ModelAdmin):
    list_display = ("identificacao", "empresa", "obra", "solicitante", "data_solicitacao", "prioridade", "status")
    list_filter = ("empresa", "prioridade", "status")
    inlines = (SolicitacaoCompraItemInline,)


admin.site.register(HistoricoSolicitacaoCompra)
