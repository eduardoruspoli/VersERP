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
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
]
