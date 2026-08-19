from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import HistoricoSolicitacaoCompra, SolicitacaoCompra


def _exigir(usuario, permissao):
    if not usuario or not usuario.has_perm(f"compras.{permissao}"):
        raise PermissionDenied("Você não possui permissão para esta ação.")


def _alterar_status(solicitacao, novo_status, usuario, observacao=""):
    permitidas = {
        SolicitacaoCompra.Status.RASCUNHO: {SolicitacaoCompra.Status.ABERTA, SolicitacaoCompra.Status.CANCELADA},
        SolicitacaoCompra.Status.ABERTA: {SolicitacaoCompra.Status.CANCELADA},
    }
    if novo_status not in permitidas.get(solicitacao.status, set()):
        raise ValidationError(f"Transição inválida de {solicitacao.get_status_display()} para {dict(SolicitacaoCompra.Status.choices)[novo_status]}.")
    anterior = solicitacao.status
    SolicitacaoCompra.objects.filter(pk=solicitacao.pk).update(status=novo_status)
    solicitacao.status = novo_status
    HistoricoSolicitacaoCompra.objects.create(solicitacao=solicitacao, status_anterior=anterior, status_novo=novo_status, usuario=usuario, observacao=observacao)


@transaction.atomic
def abrir_solicitacao(solicitacao, usuario):
    _exigir(usuario, "change_solicitacaocompra")
    solicitacao = SolicitacaoCompra.objects.select_for_update().get(pk=solicitacao.pk)
    if not solicitacao.itens.filter(cancelado=False).exists():
        raise ValidationError("Inclua ao menos um item ativo antes de abrir a solicitação.")
    _alterar_status(solicitacao, SolicitacaoCompra.Status.ABERTA, usuario)
    return solicitacao


@transaction.atomic
def cancelar_solicitacao(solicitacao, usuario, motivo):
    _exigir(usuario, "cancelar_solicitacao")
    if not (motivo or "").strip():
        raise ValidationError("Informe o motivo do cancelamento.")
    solicitacao = SolicitacaoCompra.objects.select_for_update().get(pk=solicitacao.pk)
    _alterar_status(solicitacao, SolicitacaoCompra.Status.CANCELADA, usuario, motivo.strip())
    return solicitacao
