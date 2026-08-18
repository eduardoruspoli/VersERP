from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "financeiro",
            "0006_popular_movimentacoes_bancarias",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="planoconta",
            name="codigo",
            field=models.CharField(
                max_length=30,
                unique=True,
                verbose_name="Código",
            ),
        ),
        migrations.AlterField(
            model_name="planoconta",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("ATIVO", "Ativo"),
                    ("PASSIVO", "Passivo"),
                    (
                        "PATRIMONIO_LIQUIDO",
                        "Patrimônio Líquido",
                    ),
                    ("RECEITA", "Receita"),
                    ("CUSTO", "Custo"),
                    ("DESPESA", "Despesa"),
                ],
                max_length=25,
                verbose_name="Grupo contábil",
            ),
        ),
        migrations.AddField(
            model_name="planoconta",
            name="natureza",
            field=models.CharField(
                choices=[
                    ("DEVEDORA", "Devedora"),
                    ("CREDORA", "Credora"),
                ],
                default="DEVEDORA",
                max_length=10,
                verbose_name="Natureza contábil",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="planoconta",
            name="estrutural",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Identifica contas-base da estrutura "
                    "contábil do VersERP."
                ),
                verbose_name="Conta estrutural",
            ),
        ),
    ]