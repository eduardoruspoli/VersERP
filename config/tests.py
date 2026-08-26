import os
import subprocess
import sys
import tempfile

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
        "VERSERP_LOG_DIR",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "DB_HOST",
        "DB_PORT",
    }

    def executar_settings(self, incluir_diretorios_producao=True, **variaveis):
        ambiente = os.environ.copy()
        for nome in self.variaveis:
            ambiente.pop(nome, None)
        ambiente.update(variaveis)
        if (
            ambiente.get("VERSERP_ENV") == "production"
            and incluir_diretorios_producao
        ):
            ambiente.setdefault("VERSERP_LOG_DIR", tempfile.gettempdir())
        return subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import config.settings as s; "
                    "print(s.DEBUG, s.ALLOWED_HOSTS, s.SECURE_SSL_REDIRECT, "
                    "hasattr(s, 'SECURE_PROXY_SSL_HEADER')); "
                    "print(s.DATABASES['default']); "
                    "print(getattr(s, 'VERSERP_LOG_DIR', None)); "
                    "print(getattr(s, 'LOGGING', None))"
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
        self.assertIn("django.db.backends.sqlite3", resultado.stdout)
        self.assertIn("None\n", resultado.stdout)

    def test_producao_exige_diretorio_de_logs(self):
        resultado = self.executar_settings(
            incluir_diretorios_producao=False,
            VERSERP_ENV="production",
            DJANGO_SECRET_KEY="chave-ficticia-segura-para-teste-com-mais-de-cinquenta-caracteres",
            DJANGO_ALLOWED_HOSTS="erp.example.test",
            DB_NAME="verserp_teste",
            DB_USER="usuario_teste",
            DB_PASSWORD="senha-ficticia",
            DB_HOST="postgres.example.test",
        )

        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("VERSERP_LOG_DIR", resultado.stderr)

    def test_producao_aceita_diretorio_de_logs_e_configura_logging(self):
        with tempfile.TemporaryDirectory() as diretorio:
            resultado = self.executar_settings(
                incluir_diretorios_producao=False,
                VERSERP_ENV="production",
                DJANGO_SECRET_KEY="chave-ficticia-segura-para-teste-com-mais-de-cinquenta-caracteres",
                DJANGO_ALLOWED_HOSTS="erp.example.test",
                DB_NAME="verserp_teste",
                DB_USER="usuario_teste",
                DB_PASSWORD="senha-ficticia",
                DB_HOST="postgres.example.test",
                VERSERP_LOG_DIR=diretorio,
            )

        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn(diretorio, resultado.stdout)
        self.assertIn("RotatingFileHandler", resultado.stdout)
        self.assertIn("verserp.log", resultado.stdout)
        self.assertIn("'level': 'WARNING'", resultado.stdout)

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
            DB_NAME="verserp_teste",
            DB_USER="usuario_teste",
            DB_PASSWORD="senha-ficticia",
            DB_HOST="postgres.example.test",
        )

        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("False", resultado.stdout)
        self.assertIn("True False", resultado.stdout)

    def test_producao_exige_variaveis_obrigatorias_do_postgresql(self):
        base = {
            "VERSERP_ENV": "production",
            "DJANGO_SECRET_KEY": (
                "chave-ficticia-segura-para-teste-com-mais-de-cinquenta-caracteres"
            ),
            "DJANGO_ALLOWED_HOSTS": "erp.example.test",
            "DB_NAME": "verserp_teste",
            "DB_USER": "usuario_teste",
            "DB_PASSWORD": "senha-ficticia",
            "DB_HOST": "postgres.example.test",
        }
        for variavel in ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST"):
            with self.subTest(variavel=variavel):
                dados = base.copy()
                dados.pop(variavel)
                resultado = self.executar_settings(**dados)
                self.assertNotEqual(resultado.returncode, 0)
                self.assertIn(variavel, resultado.stderr)

    def test_producao_monta_postgresql_com_porta_padrao(self):
        resultado = self.executar_settings(
            VERSERP_ENV="production",
            DJANGO_SECRET_KEY="chave-ficticia-segura-para-teste-com-mais-de-cinquenta-caracteres",
            DJANGO_ALLOWED_HOSTS="erp.example.test",
            DB_NAME="verserp_teste",
            DB_USER="usuario_teste",
            DB_PASSWORD="senha-ficticia",
            DB_HOST="postgres.example.test",
        )

        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("django.db.backends.postgresql", resultado.stdout)
        self.assertIn("'NAME': 'verserp_teste'", resultado.stdout)
        self.assertIn("'USER': 'usuario_teste'", resultado.stdout)
        self.assertIn("'HOST': 'postgres.example.test'", resultado.stdout)
        self.assertIn("'PORT': '5432'", resultado.stdout)

    def test_producao_respeita_porta_postgresql_informada(self):
        resultado = self.executar_settings(
            VERSERP_ENV="production",
            DJANGO_SECRET_KEY="chave-ficticia-segura-para-teste-com-mais-de-cinquenta-caracteres",
            DJANGO_ALLOWED_HOSTS="erp.example.test",
            DB_NAME="verserp_teste",
            DB_USER="usuario_teste",
            DB_PASSWORD="senha-ficticia",
            DB_HOST="postgres.example.test",
            DB_PORT="55432",
        )

        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("'PORT': '55432'", resultado.stdout)
