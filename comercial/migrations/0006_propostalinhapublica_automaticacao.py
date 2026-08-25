from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("comercial", "0005_propostaitem_margem_formacao"),
    ]

    operations = [
        migrations.AddField(
            model_name="propostalinhapublica",
            name="oculta_manual",
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name="propostalinhapublica",
            name="origem_automatica",
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name="propostalinhapublica",
            name="valor_automatico",
            field=models.BooleanField(default=False, editable=False),
        ),
    ]
