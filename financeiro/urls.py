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


    # -------------------------------------------------
    # CONCILIAÇÃO BANCÁRIA
    # -------------------------------------------------

    path(
        "conciliacao/",
        views.conciliacao_bancaria,
        name="conciliacao_bancaria",
    ),

    path(
        "conciliacao/importar/",
        views.importar_ofx,
        name="importar_ofx",
    ),

    path(
        "conciliacao/importacoes/<int:pk>/",
        views.detalhe_importacao_ofx,
        name="detalhe_importacao_ofx",
    ),

    path(
        "conciliacao/movimentos/<int:pk>/buscar/",
        views.buscar_movimento_ofx,
        name="buscar_movimento_ofx",
    ),

    path(
        "conciliacao/movimentos/<int:pk>/criar-lancamento/",
        views.criar_lancamento_movimento_ofx,
        name="criar_lancamento_movimento_ofx",
    ),

    path(
        "conciliacao/movimentos/<int:pk>/baixar-parcela/<int:parcela_pk>/",
        views.baixar_parcela_movimento_ofx,
        name="baixar_parcela_movimento_ofx",
    ),

    path(
        "conciliacao/movimentos/<int:pk>/conciliar/<int:baixa_pk>/",
        views.conciliar_movimento_ofx,
        name="conciliar_movimento_ofx",
    ),

    path(
        "conciliacao/movimentos/<int:pk>/ignorar/",
        views.ignorar_movimento_ofx,
        name="ignorar_movimento_ofx",
    ),

    path(
        "conciliacao/movimentos/<int:pk>/reabrir/",
        views.reabrir_movimento_ofx,
        name="reabrir_movimento_ofx",
    ),
]