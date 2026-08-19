from django.urls import path

from . import views

app_name = "comercial"
urlpatterns = [
    path("propostas/", views.proposta_lista, name="proposta_lista"),
    path("propostas/nova/", views.proposta_criar, name="proposta_criar"),
    path("propostas/<int:pk>/", views.proposta_detalhe, name="proposta_detalhe"),
    path("revisoes/<int:pk>/editar/", views.revisao_editar, name="revisao_editar"),
    path("revisoes/<int:pk>/itens/novo/", views.item_adicionar, name="item_adicionar"),
    path("revisoes/<int:pk>/linhas/novo/", views.linha_adicionar, name="linha_adicionar"),
    path("revisoes/<int:pk>/tributos/novo/", views.tributo_adicionar, name="tributo_adicionar"),
    path("propostas/<int:pk>/enviar/", views.proposta_enviar, name="proposta_enviar"),
    path("propostas/<int:pk>/nova-revisao/", views.revisao_nova, name="revisao_nova"),
    path("revisoes/<int:pk>/documento/", views.documento_publico, name="documento_publico"),
]
