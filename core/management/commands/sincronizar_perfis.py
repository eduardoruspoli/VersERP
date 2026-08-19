from django.core.management.base import BaseCommand

from core.permissions import sincronizar_perfis_padrao


class Command(BaseCommand):
    help = "Cria ou sincroniza os perfis padrão do VersERP de forma idempotente."

    def handle(self, *args, **options):
        for grupo, criado, quantidade in sincronizar_perfis_padrao():
            estado = "criado" if criado else "sincronizado"
            self.stdout.write(self.style.SUCCESS(f"{grupo.name}: {estado}, {quantidade} permissões."))
