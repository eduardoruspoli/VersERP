from django.conf import settings
from django.db import models


class UsuarioEmpresa(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vinculos_empresas")
    empresa = models.ForeignKey("financeiro.Empresa", on_delete=models.CASCADE, related_name="usuarios_autorizados")
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="acessos_empresariais_criados")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["usuario__username", "empresa__razao_social"]
        constraints = [models.UniqueConstraint(fields=["usuario", "empresa"], name="uq_usuario_empresa")]
        permissions = [
            ("view_configuracoes", "Pode acessar a Central de Configurações"),
            ("gerenciar_acessos", "Pode gerenciar usuários, perfis e empresas autorizadas"),
        ]

    def __str__(self):
        return f"{self.usuario} — {self.empresa}"


class AuditoriaAcesso(models.Model):
    usuario_alvo = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="auditorias_acesso_recebidas")
    usuario_responsavel = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="auditorias_acesso_realizadas")
    acao = models.CharField(max_length=40)
    descricao = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
