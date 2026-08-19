from django.urls import path

from . import views

app_name = "compras"

urlpatterns = [
    path("solicitacoes/", views.solicitacao_lista, name="solicitacao_lista"),
    path("solicitacoes/nova/", views.solicitacao_criar, name="solicitacao_criar"),
    path("solicitacoes/<int:pk>/", views.solicitacao_detalhe, name="solicitacao_detalhe"),
    path("solicitacoes/<int:pk>/editar/", views.solicitacao_editar, name="solicitacao_editar"),
    path("solicitacoes/<int:pk>/abrir/", views.solicitacao_abrir, name="solicitacao_abrir"),
    path("solicitacoes/<int:pk>/cancelar/", views.solicitacao_cancelar, name="solicitacao_cancelar"),
    path("obras/<int:obra_id>/itens-previstos/", views.itens_previstos_obra, name="itens_previstos_obra"),
]
