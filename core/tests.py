from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from financeiro.models import Empresa
from pessoas.models import Pessoa
from comercial.models import Proposta
from .access import empresas_usuario, pode_acessar_empresa
from .models import UsuarioEmpresa


class AcessoEmpresaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="limitado", password="teste123")
        self.empresa = Empresa.objects.create(razao_social="Empresa autorizada", cnpj="70.000.000/0001-01")
        self.outra = Empresa.objects.create(razao_social="Empresa bloqueada", cnpj="70.000.000/0001-02")

    def test_usuario_sem_empresa_nao_recebe_escopo(self):
        self.assertFalse(empresas_usuario(self.usuario).exists())

    def test_usuario_uma_e_multiplas_empresas(self):
        UsuarioEmpresa.objects.create(usuario=self.usuario, empresa=self.empresa)
        self.assertTrue(pode_acessar_empresa(self.usuario, self.empresa))
        self.assertFalse(pode_acessar_empresa(self.usuario, self.outra))
        UsuarioEmpresa.objects.create(usuario=self.usuario, empresa=self.outra)
        self.assertEqual(empresas_usuario(self.usuario).count(), 2)

    def test_superusuario_acessa_todas(self):
        administrador = get_user_model().objects.create_superuser(username="admin", password="teste123")
        self.assertEqual(empresas_usuario(administrador).count(), 2)

    def test_post_empresa_nao_autorizada_e_bloqueado(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post("/comercial/propostas/nova/", {"empresa": self.outra.pk})
        self.assertEqual(resposta.status_code, 403)

    def test_dashboard_e_url_nao_vazam_outra_empresa(self):
        UsuarioEmpresa.objects.create(usuario=self.usuario, empresa=self.empresa)
        self.usuario.user_permissions.add(Permission.objects.get(content_type__app_label="comercial", codename="view_proposta"))
        cliente = Pessoa.objects.create(razao_social="Cliente dashboard")
        permitida = Proposta.objects.create(empresa=self.empresa, cliente=cliente, codigo="VERS8101", numero_sequencial=8101)
        bloqueada = Proposta.objects.create(empresa=self.outra, cliente=cliente, codigo="VERS8102", numero_sequencial=8102)
        self.client.force_login(self.usuario)
        with CaptureQueriesContext(connection) as consultas:
            resposta = self.client.get(reverse("core:dashboard"))
        self.assertContains(resposta, permitida.codigo)
        self.assertNotContains(resposta, bloqueada.codigo)
        self.assertLessEqual(len(consultas), 30)
        self.assertEqual(self.client.get(reverse("comercial:proposta_detalhe", args=[bloqueada.pk])).status_code, 403)

    def test_configuracoes_exigem_permissao(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(reverse("core:configuracoes")).status_code, 403)
