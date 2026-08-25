import os
import subprocess
import sys

from django.test import SimpleTestCase


class ConfiguracaoAmbienteTests(SimpleTestCase):
    variaveis = {
        "VERSERP_ENV",
        "DJANGO_SECRET_KEY",
        "DJANGO_DEBUG",
        "DJANGO_ALLOWED_HOSTS",
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "DJANGO_SECURE_HSTS_SECONDS",
        "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
        "DJANGO_SECURE_HSTS_PRELOAD",
        "DJANGO_TRUST_X_FORWARDED_PROTO",
    }

    def executar_settings(self, **variaveis):
        ambiente = os.environ.copy()
        for nome in self.variaveis:
            ambiente.pop(nome, None)
        ambiente.update(variaveis)
        return subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import config.settings as s; "
                    "print(s.DEBUG, s.ALLOWED_HOSTS, s.SECURE_SSL_REDIRECT, "
                    "hasattr(s, 'SECURE_PROXY_SSL_HEADER'))"
                ),
            ],
            cwd=os.getcwd(),
            env=ambiente,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_desenvolvimento_mantem_defaults_locais(self):
        resultado = self.executar_settings()

        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("True", resultado.stdout)
        self.assertIn("127.0.0.1", resultado.stdout)
        self.assertIn("False False", resultado.stdout)

    def test_producao_exige_secret_key(self):
        resultado = self.executar_settings(
            VERSERP_ENV="production",
            DJANGO_ALLOWED_HOSTS="erp.example.test",
        )

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", resultado.stderr)

    def test_producao_rejeita_debug_ativo(self):
        resultado = self.executar_settings(
            VERSERP_ENV="production",
            DJANGO_SECRET_KEY="chave-ficticia-segura-para-teste-com-mais-de-cinquenta-caracteres",
            DJANGO_DEBUG="true",
            DJANGO_ALLOWED_HOSTS="erp.example.test",
        )

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("DJANGO_DEBUG", resultado.stderr)

    def test_producao_exige_hosts_explicitos(self):
        configuracao = {
            "VERSERP_ENV": "production",
            "DJANGO_SECRET_KEY": (
                "chave-ficticia-segura-para-teste-com-mais-de-cinquenta-caracteres"
            ),
        }
        for hosts in ("", "*"):
            with self.subTest(hosts=hosts):
                resultado = self.executar_settings(
                    **configuracao,
                    DJANGO_ALLOWED_HOSTS=hosts,
                )
                self.assertNotEqual(resultado.returncode, 0)
                self.assertIn("DJANGO_ALLOWED_HOSTS", resultado.stderr)

    def test_producao_ativa_seguranca_sem_presumir_proxy(self):
        resultado = self.executar_settings(
            VERSERP_ENV="production",
            DJANGO_SECRET_KEY="chave-ficticia-segura-para-teste-com-mais-de-cinquenta-caracteres",
            DJANGO_ALLOWED_HOSTS="erp.example.test",
            DJANGO_CSRF_TRUSTED_ORIGINS="https://erp.example.test",
        )

        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("False", resultado.stdout)
        self.assertIn("True False", resultado.stdout)
