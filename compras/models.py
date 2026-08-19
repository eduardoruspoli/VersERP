from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from comercial.models import PropostaItem
from financeiro.models import CentroCusto, Empresa, PlanoConta


class SolicitacaoCompra(models.Model):
    class Prioridade(models.TextChoices):
        BAIXA = "BAIXA", "Baixa"
        NORMAL = "NORMAL", "Normal"
        ALTA = "ALTA", "Alta"
        URGENTE = "URGENTE", "Urgente"

    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        ABERTA = "ABERTA", "Aberta"
        EM_COTACAO = "EM_COTACAO", "Em cotação"
        PARCIALMENTE_ATENDIDA = "PARCIALMENTE_ATENDIDA", "Parcialmente atendida"
        ATENDIDA = "ATENDIDA", "Atendida"
        CANCELADA = "CANCELADA", "Cancelada"

    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="solicitacoes_compra")
    obra = models.ForeignKey(CentroCusto, on_delete=models.PROTECT, related_name="solicitacoes_compra")
    solicitante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="solicitacoes_compra")
    data_solicitacao = models.DateField(default=timezone.localdate)
    prioridade = models.CharField(max_length=10, choices=Prioridade.choices, default=Prioridade.NORMAL)
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.RASCUNHO)
    observacao = models.TextField(blank=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="solicitacoes_compra_criadas")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_solicitacao", "-id"]
        permissions = [("cancelar_solicitacao", "Pode cancelar solicitação de compra")]

    @property
    def identificacao(self):
        return f"SC-{self.pk:05d}" if self.pk else "Nova solicitação"

    def clean(self):
        errors = {}
        if self.obra_id:
            if self.empresa_id != self.obra.empresa_id:
                errors["obra"] = "A obra deve pertencer à mesma empresa da solicitação."
            if not self.obra.ativo:
                errors["obra"] = "Não é possível criar solicitação para uma obra inativa."
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values("empresa_id", "obra_id", "status").first()
            if original and original["status"] != self.Status.RASCUNHO:
                if original["empresa_id"] != self.empresa_id:
                    errors["empresa"] = "A empresa não pode ser alterada após a abertura."
                if original["obra_id"] != self.obra_id:
                    errors["obra"] = "A obra não pode ser alterada após a abertura."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.identificacao} — {self.obra}"


class SolicitacaoCompraItem(models.Model):
    class TipoOrigem(models.TextChoices):
        PREVISTO = "PREVISTO", "Previsto"
        SUBSTITUICAO = "SUBSTITUICAO", "Substituição"
        NAO_PREVISTO = "NAO_PREVISTO", "Não previsto"

    solicitacao = models.ForeignKey(SolicitacaoCompra, on_delete=models.CASCADE, related_name="itens")
    descricao = models.CharField(max_length=250)
    quantidade = models.DecimalField(max_digits=15, decimal_places=4)
    unidade = models.CharField(max_length=20)
    data_necessaria = models.DateField(null=True, blank=True)
    observacao = models.TextField(blank=True)
    proposta_item = models.ForeignKey(PropostaItem, on_delete=models.PROTECT, null=True, blank=True, related_name="itens_solicitacao_compra")
    tipo_origem = models.CharField(max_length=20, choices=TipoOrigem.choices, default=TipoOrigem.NAO_PREVISTO)
    descricao_prevista_snapshot = models.CharField(max_length=250, blank=True)
    quantidade_prevista_snapshot = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    unidade_prevista_snapshot = models.CharField(max_length=20, blank=True)
    custo_unitario_previsto_snapshot = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    plano_conta_previsto = models.ForeignKey(PlanoConta, on_delete=models.PROTECT, null=True, blank=True, related_name="itens_solicitacao_compra")
    descricao_item_substituido = models.CharField(max_length=250, blank=True)
    cancelado = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def clean(self):
        errors = {}
        if self.quantidade is not None and self.quantidade <= Decimal("0"):
            errors["quantidade"] = "A quantidade deve ser maior que zero."
        if self.solicitacao_id and not SolicitacaoCompra.objects.filter(pk=self.solicitacao_id, status=SolicitacaoCompra.Status.RASCUNHO).exists():
            errors["solicitacao"] = "Itens não podem ser alterados após a abertura da solicitação."
        if self.proposta_item_id:
            proposta = getattr(self.solicitacao.obra, "proposta_origem", None)
            if not proposta or not proposta.revisao_aprovada_id or self.proposta_item.revisao_id != proposta.revisao_aprovada_id:
                errors["proposta_item"] = "O item deve pertencer à revisão aprovada da proposta que originou a obra."
            if self.tipo_origem == self.TipoOrigem.NAO_PREVISTO:
                errors["tipo_origem"] = "Um item vinculado à proposta deve ser previsto ou substituição."
            if not self.pk:
                self.descricao_prevista_snapshot = self.proposta_item.descricao
                self.quantidade_prevista_snapshot = self.proposta_item.quantidade
                self.unidade_prevista_snapshot = self.proposta_item.unidade
                self.custo_unitario_previsto_snapshot = self.proposta_item.custo_unitario
                self.plano_conta_previsto = self.proposta_item.plano_conta
                if not self.descricao:
                    self.descricao = self.proposta_item.descricao
                if not self.unidade:
                    self.unidade = self.proposta_item.unidade
        else:
            if self.tipo_origem != self.TipoOrigem.NAO_PREVISTO:
                errors["proposta_item"] = "Informe o item previsto para registrar uma substituição ou origem prevista."
            self.tipo_origem = self.TipoOrigem.NAO_PREVISTO
            self.descricao_prevista_snapshot = ""
            self.quantidade_prevista_snapshot = None
            self.unidade_prevista_snapshot = ""
            self.custo_unitario_previsto_snapshot = None
            self.plano_conta_previsto = None
        if self.tipo_origem == self.TipoOrigem.SUBSTITUICAO and not self.descricao_item_substituido.strip():
            errors["descricao_item_substituido"] = "Informe a descrição do item substituído."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.proposta_item_id and not self.pk:
            self.descricao_prevista_snapshot = self.proposta_item.descricao
            self.quantidade_prevista_snapshot = self.proposta_item.quantidade
            self.unidade_prevista_snapshot = self.proposta_item.unidade
            self.custo_unitario_previsto_snapshot = self.proposta_item.custo_unitario
            self.plano_conta_previsto = self.proposta_item.plano_conta
            self.descricao = self.descricao or self.proposta_item.descricao
            self.unidade = self.unidade or self.proposta_item.unidade
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not SolicitacaoCompra.objects.filter(pk=self.solicitacao_id, status=SolicitacaoCompra.Status.RASCUNHO).exists():
            raise ValidationError("Itens não podem ser excluídos após a abertura da solicitação.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return self.descricao


class HistoricoSolicitacaoCompra(models.Model):
    solicitacao = models.ForeignKey(SolicitacaoCompra, on_delete=models.CASCADE, related_name="historico")
    status_anterior = models.CharField(max_length=25, blank=True)
    status_novo = models.CharField(max_length=25, choices=SolicitacaoCompra.Status.choices)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em", "-id"]

    def get_status_anterior_display(self):
        return dict(SolicitacaoCompra.Status.choices).get(self.status_anterior, self.status_anterior)
