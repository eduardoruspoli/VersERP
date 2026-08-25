from django.urls import path

from . import views


app_name = "core"


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("relatorios/",views.relatorios,name="relatorios"),
    path("pendencias/",views.pendencias,name="pendencias"),
    path("configuracoes/",views.configuracoes,name="configuracoes"),
    path("configuracoes/usuarios/",views.usuarios_lista,name="usuarios_lista"),
    path("configuracoes/usuarios/<int:pk>/",views.usuario_editar,name="usuario_editar"),
    path("configuracoes/perfis/",views.grupos_lista,name="grupos_lista"),
    path("configuracoes/perfis/<int:pk>/",views.grupo_editar,name="grupo_editar"),
    path("configuracoes/empresas/", views.empresas_lista, name="empresas_lista"),
    path("configuracoes/empresas/nova/", views.empresa_nova, name="empresa_nova"),
    path("configuracoes/empresas/<int:pk>/", views.empresa_editar, name="empresa_editar"),
    path("configuracoes/feriados/", views.feriados_lista, name="feriados_lista"),
    path("configuracoes/feriados/novo/", views.feriado_novo, name="feriado_novo"),
    path("configuracoes/feriados/<int:pk>/", views.feriado_editar, name="feriado_editar"),
    path("configuracoes/modelos-proposta/", views.modelos_proposta_lista, name="modelos_proposta_lista"),
    path("configuracoes/modelos-proposta/novo/", views.modelo_proposta_novo, name="modelo_proposta_novo"),
    path("configuracoes/modelos-proposta/<int:pk>/", views.modelo_proposta_editar, name="modelo_proposta_editar"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
]
