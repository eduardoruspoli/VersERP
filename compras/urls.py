from django.urls import path

from . import views

app_name = "compras"

urlpatterns = [
    path("cotacoes/", views.cotacao_lista, name="cotacao_lista"),
    path("cotacoes/nova/", views.cotacao_criar, name="cotacao_criar"),
    path("cotacoes/<int:pk>/", views.cotacao_detalhe, name="cotacao_detalhe"),
    path("cotacoes/<int:pk>/iniciar/", views.cotacao_iniciar, name="cotacao_iniciar"),
    path("cotacoes/<int:pk>/fornecedor/", views.cotacao_fornecedor, name="cotacao_fornecedor"),
    path("cotacoes/<int:pk>/fornecedor/<int:cotacao_pk>/editar/", views.cotacao_fornecedor, name="cotacao_fornecedor_editar"),
    path("cotacoes/fornecedor/<int:fornecedor_pk>/oferta/", views.cotacao_oferta, name="cotacao_oferta"),
    path("cotacoes/fornecedor/<int:fornecedor_pk>/oferta/<int:oferta_pk>/editar/", views.cotacao_oferta, name="cotacao_oferta_editar"),
    path("cotacoes/<int:pk>/mapa/", views.cotacao_mapa, name="cotacao_mapa"),
    path("cotacoes/<int:pk>/mapa/<int:item_pk>/selecionar/", views.cotacao_selecionar, name="cotacao_selecionar"),
    path("cotacoes/<int:pk>/concluir/", views.cotacao_concluir, name="cotacao_concluir"),
    path("cotacoes/<int:pk>/cancelar/", views.cotacao_cancelar, name="cotacao_cancelar"),
    path("solicitacoes/", views.solicitacao_lista, name="solicitacao_lista"),
    path("solicitacoes/nova/", views.solicitacao_criar, name="solicitacao_criar"),
    path("solicitacoes/<int:pk>/", views.solicitacao_detalhe, name="solicitacao_detalhe"),
    path("solicitacoes/<int:pk>/editar/", views.solicitacao_editar, name="solicitacao_editar"),
    path("solicitacoes/<int:pk>/abrir/", views.solicitacao_abrir, name="solicitacao_abrir"),
    path("solicitacoes/<int:pk>/cancelar/", views.solicitacao_cancelar, name="solicitacao_cancelar"),
    path("obras/<int:obra_id>/itens-previstos/", views.itens_previstos_obra, name="itens_previstos_obra"),
]
