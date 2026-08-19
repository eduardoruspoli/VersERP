from django.contrib import admin

from .models import ModeloConteudoProposta, Proposta, PropostaItem, PropostaLinhaPublica, PropostaRevisao, PropostaTributo

admin.site.register([ModeloConteudoProposta, Proposta, PropostaRevisao, PropostaItem, PropostaTributo, PropostaLinhaPublica])
