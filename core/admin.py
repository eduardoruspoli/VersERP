from django.contrib import admin

from .models import AuditoriaAcesso, UsuarioEmpresa

admin.site.register([UsuarioEmpresa, AuditoriaAcesso])
