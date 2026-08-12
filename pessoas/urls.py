from django.urls import path

from . import views


app_name = "pessoas"


urlpatterns = [
    path("", views.lista_pessoas, name="lista"),

    path("nova/", views.nova_pessoa, name="nova"),

    path(
        "consultar-cnpj/",
        views.consultar_cnpj,
        name="consultar_cnpj",
    ),

    path(
        "<int:pk>/editar/",
        views.editar_pessoa,
        name="editar",
    ),

    path(
            "<int:pk>/",
            views.detalhe_pessoa,
            name="detalhe",
        ),

    path(
        "<int:pk>/status/",
        views.alterar_status_pessoa,
        name="alterar_status",
    ),
]

