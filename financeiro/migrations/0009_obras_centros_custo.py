import django.db.models.deletion
from django.db import migrations, models


def vincular_centros_a_empresa(apps, schema_editor):
    CentroCusto = apps.get_model("financeiro", "CentroCusto")
    Empresa = apps.get_model("financeiro", "Empresa")

    if not CentroCusto.objects.filter(empresa__isnull=True).exists():
        return

    empresa = (
        Empresa.objects.filter(principal=True).first()
        or Empresa.objects.first()
    )

    if empresa is None:
        raise RuntimeError(
            "Não existe empresa para vincular aos centros de custo atuais."
        )

    CentroCusto.objects.filter(empresa__isnull=True).update(
        empresa=empresa
    )


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0008_plano_contas_padrao"),
        ("pessoas", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="centrocusto",
            name="cliente",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="obras_centro_custo",
                to="pessoas.pessoa",
                verbose_name="Cliente",
            ),
        ),
        migrations.AddField(
            model_name="centrocusto",
            name="empresa",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="centros_custo",
                to="financeiro.empresa",
                verbose_name="Empresa",
            ),
        ),
        migrations.RunPython(
            vincular_centros_a_empresa,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="centrocusto",
            name="empresa",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="centros_custo",
                to="financeiro.empresa",
                verbose_name="Empresa",
            ),
        ),
        migrations.AlterField(
            model_name="centrocusto",
            name="codigo",
            field=models.CharField(
                max_length=30,
                verbose_name="Código",
            ),
        ),
        migrations.AlterModelOptions(
            name="centrocusto",
            options={
                "ordering": ["empresa", "codigo"],
                "verbose_name": "Centro de custo",
                "verbose_name_plural": "Centros de custo",
            },
        ),
        migrations.AddConstraint(
            model_name="centrocusto",
            constraint=models.UniqueConstraint(
                fields=("empresa", "codigo"),
                name="unique_centro_custo_por_empresa",
            ),
        ),
    ]
