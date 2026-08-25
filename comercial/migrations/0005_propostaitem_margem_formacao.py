from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("comercial", "0004_proposta_observacao_importacao_proposta_origem_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="propostaitem",
            name="margem_formacao",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Percentual somado ao valor unitário do fornecedor. Ex.: R$ 125,00 + 86% = R$ 232,50.",
                max_digits=7,
                null=True,
                verbose_name="Margem de formação (%)",
            ),
        ),
        migrations.AlterField(
            model_name="propostaitem",
            name="custo_unitario",
            field=models.DecimalField(decimal_places=4, max_digits=15, verbose_name="Valor unitário fornecedor"),
        ),
    ]
