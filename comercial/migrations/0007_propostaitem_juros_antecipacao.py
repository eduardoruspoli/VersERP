from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("comercial", "0006_propostalinhapublica_automaticacao"),
    ]

    operations = [
        migrations.AddField(
            model_name="propostaitem",
            name="prazo_antecipacao_dias",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Ex.: 90 dias = 3 meses comerciais; 180 dias = 6 meses.",
                null=True,
                verbose_name="Prazo de antecipação (dias)",
            ),
        ),
        migrations.AddField(
            model_name="propostaitem",
            name="taxa_juros_mensal",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Usada somente em Juros de antecipação. Padrão comercial: 2,40% ao mês.",
                max_digits=7,
                null=True,
                verbose_name="Taxa mensal de antecipação (%)",
            ),
        ),
        migrations.AlterField(
            model_name="propostaitem",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("MATERIAL", "Material"),
                    ("MAO_OBRA", "Mão de obra"),
                    ("SERVICO_TERCEIRO", "Serviço de terceiro"),
                    ("JUROS_ANTECIPACAO", "Juros de antecipação"),
                    ("FRETE", "Frete"),
                    ("LOCACAO_EQUIPAMENTO", "Locação/equipamento"),
                    ("OUTROS", "Outros"),
                ],
                max_length=25,
            ),
        ),
    ]
