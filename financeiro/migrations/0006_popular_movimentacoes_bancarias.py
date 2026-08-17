from decimal import Decimal

from django.db import migrations


def descricao_conta(conta):
    partes = [
        conta.banco,
    ]

    if conta.agencia:
        partes.append(
            f"Ag. {conta.agencia}"
        )

    if conta.conta:
        partes.append(
            f"Conta {conta.conta}"
        )

    return " - ".join(partes)


def popular_movimentacoes(
    apps,
    schema_editor,
):
    BaixaFinanceira = apps.get_model(
        "financeiro",
        "BaixaFinanceira",
    )

    TransferenciaBancaria = apps.get_model(
        "financeiro",
        "TransferenciaBancaria",
    )

    MovimentacaoBancaria = apps.get_model(
        "financeiro",
        "MovimentacaoBancaria",
    )

    # =========================================================
    # PAGAMENTOS E RECEBIMENTOS
    # =========================================================

    baixas = (
        BaixaFinanceira.objects
        .select_related(
            "conta_bancaria",
            "parcela",
            "parcela__lancamento",
        )
        .all()
    )

    for baixa in baixas:
        lancamento = (
            baixa
            .parcela
            .lancamento
        )

        valor = (
            (baixa.valor or Decimal("0.00"))
            + (baixa.juros or Decimal("0.00"))
            + (baixa.multa or Decimal("0.00"))
            - (baixa.desconto or Decimal("0.00"))
        )

        if lancamento.tipo == "RECEBER":
            tipo = "ENTRADA"
            origem = "RECEBIMENTO"

        else:
            tipo = "SAIDA"
            origem = "PAGAMENTO"

        MovimentacaoBancaria.objects.update_or_create(
            baixa_financeira_id=baixa.pk,
            defaults={
                "conta_bancaria_id": (
                    baixa.conta_bancaria_id
                ),
                "data": baixa.data,
                "tipo": tipo,
                "origem": origem,
                "descricao": (
                    lancamento.descricao
                    or ""
                ),
                "documento": (
                    lancamento.numero_documento
                    or ""
                ),
                "valor": valor,
            },
        )

    # =========================================================
    # TRANSFERÊNCIAS BANCÁRIAS
    # =========================================================

    transferencias = (
        TransferenciaBancaria.objects
        .select_related(
            "conta_origem",
            "conta_destino",
        )
        .filter(
            status="EFETIVADA",
        )
    )

    for transferencia in transferencias:
        conta_origem = (
            transferencia.conta_origem
        )

        conta_destino = (
            transferencia.conta_destino
        )

        origem_texto = descricao_conta(
            conta_origem
        )

        destino_texto = descricao_conta(
            conta_destino
        )

        # -----------------------------------------------------
        # SAÍDA NA CONTA DE ORIGEM
        # -----------------------------------------------------

        MovimentacaoBancaria.objects.update_or_create(
            transferencia_id=(
                transferencia.pk
            ),
            conta_bancaria_id=(
                conta_origem.pk
            ),
            defaults={
                "data": transferencia.data,
                "tipo": "SAIDA",
                "origem": "TRANSFERENCIA",
                "descricao": (
                    f"Transferência para "
                    f"{destino_texto}"
                ),
                "documento": (
                    transferencia.documento
                    or ""
                ),
                "valor": transferencia.valor,
            },
        )

        # -----------------------------------------------------
        # ENTRADA NA CONTA DE DESTINO
        # -----------------------------------------------------

        MovimentacaoBancaria.objects.update_or_create(
            transferencia_id=(
                transferencia.pk
            ),
            conta_bancaria_id=(
                conta_destino.pk
            ),
            defaults={
                "data": transferencia.data,
                "tipo": "ENTRADA",
                "origem": "TRANSFERENCIA",
                "descricao": (
                    f"Transferência recebida de "
                    f"{origem_texto}"
                ),
                "documento": (
                    transferencia.documento
                    or ""
                ),
                "valor": transferencia.valor,
            },
        )


def remover_movimentacoes(
    apps,
    schema_editor,
):
    MovimentacaoBancaria = apps.get_model(
        "financeiro",
        "MovimentacaoBancaria",
    )

    MovimentacaoBancaria.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        (
            "financeiro",
            "0005_movimentacaobancaria",
        ),
    ]

    operations = [
        migrations.RunPython(
            popular_movimentacoes,
            remover_movimentacoes,
        ),
    ]