from django.contrib import admin

from .models import (CotacaoFornecedor, CotacaoFornecedorItem, EscolhaCotacaoItem,
                     HistoricoProcessoCotacao, HistoricoSolicitacaoCompra,
                     HistoricoPedidoCompra, PedidoCompra, PedidoCompraItem, PedidoItemAlocacaoObra,
                     ProcessoCotacao, ProcessoCotacaoItem, SolicitacaoCompra, SolicitacaoCompraItem)


class SolicitacaoCompraItemInline(admin.TabularInline):
    model = SolicitacaoCompraItem
    extra = 0


@admin.register(SolicitacaoCompra)
class SolicitacaoCompraAdmin(admin.ModelAdmin):
    list_display = ("identificacao", "empresa", "obra", "solicitante", "data_solicitacao", "prioridade", "status")
    list_filter = ("empresa", "prioridade", "status")
    inlines = (SolicitacaoCompraItemInline,)


admin.site.register(HistoricoSolicitacaoCompra)
admin.site.register([ProcessoCotacao, ProcessoCotacaoItem, CotacaoFornecedor,
                     CotacaoFornecedorItem, EscolhaCotacaoItem, HistoricoProcessoCotacao,
                     PedidoCompra, PedidoCompraItem, PedidoItemAlocacaoObra, HistoricoPedidoCompra])
