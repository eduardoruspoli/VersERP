from django.urls import path

from . import views

app_name = "comercial"
urlpatterns = [
    path("propostas/", views.proposta_lista, name="proposta_lista"),
    path("propostas/relatorio/", views.relatorio_propostas, name="relatorio_propostas"),
    path("propostas/nova/", views.proposta_criar, name="proposta_criar"),
    path("propostas/<int:pk>/", views.proposta_detalhe, name="proposta_detalhe"),
    path("propostas/<int:pk>/acompanhamento/", views.proposta_acompanhamento, name="proposta_acompanhamento"),
    path("revisoes/<int:pk>/editar/", views.revisao_editar, name="revisao_editar"),
    path("revisoes/<int:pk>/itens/novo/", views.item_adicionar, name="item_adicionar"),
    path("itens/<int:pk>/editar/", views.item_editar, name="item_editar"),
    path("itens/<int:pk>/excluir/", views.item_excluir, name="item_excluir"),
    path("revisoes/<int:pk>/linhas/novo/", views.linha_adicionar, name="linha_adicionar"),
    path("revisoes/<int:pk>/tributos/novo/", views.tributo_adicionar, name="tributo_adicionar"),
    path("propostas/<int:pk>/enviar/", views.proposta_enviar, name="proposta_enviar"),
    path("propostas/<int:pk>/nova-revisao/", views.revisao_nova, name="revisao_nova"),
    path("propostas/<int:pk>/negociar/", views.proposta_negociar, name="proposta_negociar"),
    path("propostas/<int:pk>/aprovar/", views.proposta_aprovar, name="proposta_aprovar"),
    path("propostas/<int:pk>/<str:acao>/motivo/", views.proposta_motivo, name="proposta_motivo"),
    path("revisoes/<int:pk>/documento/", views.documento_publico, name="documento_publico"),
    path("revisoes/<int:pk>/pdf/", views.proposta_pdf, name="proposta_pdf"),
    path("propostas/<int:pk>/previsto-realizado/", views.previsto_realizado, name="previsto_realizado"),
]
