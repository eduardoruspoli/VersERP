from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0011_alter_lancamentofinanceiroclassificacao_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="empresa",
            name="bairro",
            field=models.CharField(blank=True, max_length=100, verbose_name="Bairro"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="cep",
            field=models.CharField(blank=True, max_length=9, verbose_name="CEP"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="cidade",
            field=models.CharField(blank=True, max_length=100, verbose_name="Cidade"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="complemento",
            field=models.CharField(blank=True, max_length=100, verbose_name="Complemento"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="endereco",
            field=models.CharField(blank=True, max_length=200, verbose_name="Logradouro"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="estado",
            field=models.CharField(blank=True, max_length=2, verbose_name="UF"),
        ),
        migrations.AddField(
            model_name="empresa",
            name="numero",
            field=models.CharField(blank=True, max_length=20, verbose_name="Número"),
        ),
    ]
