from django.urls import path
from . import views

app_name="rh"
urlpatterns=[
    path("",views.dashboard,name="dashboard"),
    path("funcionarios/",views.funcionario_lista,name="funcionario_lista"),
    path("funcionarios/novo/",views.funcionario_criar,name="funcionario_criar"),
    path("funcionarios/<int:pk>/",views.funcionario_detalhe,name="funcionario_detalhe"),
    path("funcionarios/<int:pk>/editar/",views.funcionario_editar,name="funcionario_editar"),
    path("funcionarios/<int:pk>/banco/",views.dados_bancarios,name="dados_bancarios"),
    path("funcionarios/<int:funcionario_id>/contratos/novo/",views.contrato_criar,name="contrato_criar"),
    path("funcionarios/<int:funcionario_id>/jornadas/nova/",views.jornada_criar,name="jornada_criar"),
    path("jornadas/<int:jornada_id>/dias/novo/",views.jornada_dia_criar,name="jornada_dia_criar"),
    path("funcionarios/<int:funcionario_id>/marcacoes/nova/",views.marcacao_criar,name="marcacao_criar"),
    path("funcionarios/<int:funcionario_id>/ocorrencias/nova/",views.ocorrencia_criar,name="ocorrencia_criar"),
    path("ponto/",views.competencia_lista,name="competencia_lista"),
    path("ponto/nova/",views.competencia_criar,name="competencia_criar"),
    path("ponto/<int:pk>/",views.competencia_detalhe,name="competencia_detalhe"),
    path("ponto/<int:pk>/apurar/",views.competencia_apurar,name="competencia_apurar"),
    path("ponto/<int:pk>/fechar/",views.competencia_fechar,name="competencia_fechar"),
    path("ponto/<int:pk>/reabrir/",views.competencia_reabrir,name="competencia_reabrir"),
    path("eventos/",views.evento_lista,name="evento_lista"),path("eventos/novo/",views.evento_criar,name="evento_criar"),
    path("vales/",views.vale_lista,name="vale_lista"),path("vales/novo/",views.vale_criar,name="vale_criar"),
    path("pre-fechamento/",views.pre_fechamento,name="pre_fechamento"),
    path("retorno/novo/",views.retorno_criar,name="retorno_criar"),
    path("conferencia/<int:pk>/",views.conferencia,name="conferencia"),
]
