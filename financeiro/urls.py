from django.urls import path

from . import views


app_name = "financeiro"


urlpatterns = [
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
]