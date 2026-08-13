from django.urls import path

from . import views


app_name = "financeiro"


urlpatterns = [
    # -------------------------------------------------
    # FINANCEIRO
    # -------------------------------------------------

    path(
        "",
        views.financeiro_index,
        name="index",
    ),


    # -------------------------------------------------
    # CONTAS A PAGAR
    # -------------------------------------------------

    path(
        "contas-a-pagar/",
        views.contas_pagar,
        name="contas_pagar",
    ),

    path(
        "contas-a-pagar/nova/",
        views.nova_conta_pagar,
        name="nova_conta_pagar",
    ),

    path(
        "contas-a-pagar/<int:pk>/",
        views.detalhe_conta_pagar,
        name="detalhe_conta_pagar",
    ),

    path(
        "contas-a-pagar/<int:pk>/editar/",
        views.editar_conta_pagar,
        name="editar_conta_pagar",
    ),

    path(
        "parcelas/<int:pk>/baixar/",
        views.baixar_parcela,
        name="baixar_parcela",
    ),


    # -------------------------------------------------
    # CONTAS A RECEBER
    # -------------------------------------------------

    path(
        "contas-a-receber/",
        views.contas_receber,
        name="contas_receber",
    ),

    path(
        "contas-a-receber/nova/",
        views.nova_conta_receber,
        name="nova_conta_receber",
    ),

    path(
        "contas-a-receber/<int:pk>/",
        views.detalhe_conta_receber,
        name="detalhe_conta_receber",
    ),

    path(
        "contas-a-receber/<int:pk>/editar/",
        views.editar_conta_receber,
        name="editar_conta_receber",
    ),

    path(
        "parcelas/<int:pk>/receber/",
        views.receber_parcela,
        name="receber_parcela",
    ),


    # -------------------------------------------------
    # CONTAS BANCÁRIAS
    # -------------------------------------------------

    path(
        "contas-bancarias/",
        views.contas_bancarias,
        name="contas_bancarias",
    ),

    path(
        "contas-bancarias/<int:pk>/",
        views.detalhe_conta_bancaria,
        name="detalhe_conta_bancaria",
    ),
]