from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from comercial.models import PropostaItem
from financeiro.models import CentroCusto, Empresa, PlanoConta
from pessoas.models import Pessoa


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


class ProcessoCotacao(models.Model):
    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
        CONCLUIDA = "CONCLUIDA", "Concluída"
        CANCELADA = "CANCELADA", "Cancelada"

    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="processos_cotacao")
    responsavel = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="processos_cotacao_responsavel")
    data_abertura = models.DateField(default=timezone.localdate)
    data_limite = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RASCUNHO)
    observacao = models.TextField(blank=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="processos_cotacao_criados")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_abertura", "-id"]
        permissions = [
            ("realizar_cotacao", "Pode registrar cotações de fornecedores"),
            ("selecionar_fornecedor", "Pode selecionar fornecedor vencedor"),
            ("cancelar_cotacao", "Pode cancelar processo de cotação"),
        ]

    @property
    def identificacao(self):
        return f"COT-{self.pk:05d}" if self.pk else "Nova cotação"

    def __str__(self):
        return self.identificacao


class ProcessoCotacaoItem(models.Model):
    processo = models.ForeignKey(ProcessoCotacao, on_delete=models.CASCADE, related_name="itens")
    solicitacao_item = models.ForeignKey(SolicitacaoCompraItem, on_delete=models.PROTECT, related_name="itens_processo_cotacao")
    quantidade_cotada = models.DecimalField(max_digits=15, decimal_places=4)
    unidade = models.CharField(max_length=20)
    observacao = models.TextField(blank=True)
    nao_comprar = models.BooleanField(default=False)
    justificativa_nao_compra = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["processo", "solicitacao_item"], name="uq_item_solicitacao_por_processo_cotacao")]

    def clean(self):
        errors = {}
        if self.quantidade_cotada is not None and self.quantidade_cotada <= 0:
            errors["quantidade_cotada"] = "A quantidade cotada deve ser positiva."
        if self.solicitacao_item_id:
            solicitacao = self.solicitacao_item.solicitacao
            if solicitacao.empresa_id != self.processo.empresa_id:
                errors["solicitacao_item"] = "O item deve pertencer à mesma empresa do processo."
            if solicitacao.status not in {SolicitacaoCompra.Status.ABERTA, SolicitacaoCompra.Status.EM_COTACAO}:
                errors["solicitacao_item"] = "O item deve pertencer a uma solicitação aberta ou em cotação."
            if self.solicitacao_item.cancelado:
                errors["solicitacao_item"] = "Item cancelado não pode entrar em cotação."
        if self.nao_comprar and not self.justificativa_nao_compra.strip():
            errors["justificativa_nao_compra"] = "Informe a justificativa para não comprar o item."
        if self.processo_id and ProcessoCotacao.objects.filter(pk=self.processo_id, status__in=[ProcessoCotacao.Status.CONCLUIDA, ProcessoCotacao.Status.CANCELADA]).exists():
            errors["processo"] = "O processo está congelado."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(); return super().save(*args, **kwargs)


class CotacaoFornecedor(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        RECEBIDA = "RECEBIDA", "Recebida"
        INVALIDADA = "INVALIDADA", "Invalidada"
        CANCELADA = "CANCELADA", "Cancelada"

    processo = models.ForeignKey(ProcessoCotacao, on_delete=models.CASCADE, related_name="cotacoes_fornecedor")
    fornecedor = models.ForeignKey(Pessoa, on_delete=models.PROTECT, related_name="cotacoes_compras")
    nome_contato = models.CharField(max_length=150, blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    data_cotacao = models.DateField(default=timezone.localdate)
    validade = models.DateField(null=True, blank=True)
    prazo_entrega = models.CharField(max_length=150, blank=True)
    condicao_pagamento = models.TextField(blank=True)
    tipo_frete = models.CharField(max_length=50, blank=True)
    valor_frete = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    desconto_global = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    impostos_globais = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    impostos_compoem_custo = models.BooleanField(default=True)
    outras_despesas = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    disponibilidade = models.CharField(max_length=150, blank=True)
    observacao = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDENTE)
    registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cotacoes_fornecedor_registradas")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fornecedor__razao_social", "id"]
        constraints = [models.UniqueConstraint(fields=["processo", "fornecedor"], name="uq_fornecedor_por_processo_cotacao")]

    def clean(self):
        errors = {}
        if self.fornecedor_id and (not self.fornecedor.ativo or self.fornecedor.classificacao not in {Pessoa.Classificacao.FORNECEDOR, Pessoa.Classificacao.AMBOS}):
            errors["fornecedor"] = "Selecione um fornecedor ativo."
        for campo in ("valor_frete", "desconto_global", "impostos_globais", "outras_despesas"):
            if getattr(self, campo) < 0: errors[campo] = "O valor não pode ser negativo."
        if self.processo_id and ProcessoCotacao.objects.filter(pk=self.processo_id, status__in=[ProcessoCotacao.Status.CONCLUIDA, ProcessoCotacao.Status.CANCELADA]).exists():
            errors["processo"] = "O processo está congelado."
        if errors: raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(); return super().save(*args, **kwargs)


class CotacaoFornecedorItem(models.Model):
    cotacao = models.ForeignKey(CotacaoFornecedor, on_delete=models.CASCADE, related_name="itens")
    processo_item = models.ForeignKey(ProcessoCotacaoItem, on_delete=models.PROTECT, related_name="ofertas")
    quantidade_ofertada = models.DecimalField(max_digits=15, decimal_places=4)
    unidade = models.CharField(max_length=20)
    preco_unitario = models.DecimalField(max_digits=15, decimal_places=4)
    preco_total = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=0)
    desconto_item = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    impostos_item = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    prazo_item = models.CharField(max_length=150, blank=True)
    disponivel = models.BooleanField(default=True)
    marca_modelo = models.CharField(max_length=150, blank=True)
    observacao = models.TextField(blank=True)

    class Meta:
        ordering = ["processo_item", "cotacao"]
        constraints = [models.UniqueConstraint(fields=["cotacao", "processo_item"], name="uq_oferta_item_por_fornecedor")]

    def clean(self):
        errors = {}
        if self.processo_item_id and self.cotacao_id and self.processo_item.processo_id != self.cotacao.processo_id:
            errors["processo_item"] = "A oferta deve pertencer ao mesmo processo da cotação."
        if self.quantidade_ofertada is not None and self.quantidade_ofertada <= 0: errors["quantidade_ofertada"] = "Informe quantidade positiva."
        if self.preco_unitario is not None and self.preco_unitario < 0: errors["preco_unitario"] = "O preço não pode ser negativo."
        if self.desconto_item < 0 or self.impostos_item < 0: errors["desconto_item"] = "Desconto e impostos não podem ser negativos."
        if self.cotacao_id and ProcessoCotacao.objects.filter(pk=self.cotacao.processo_id, status__in=[ProcessoCotacao.Status.CONCLUIDA, ProcessoCotacao.Status.CANCELADA]).exists(): errors["cotacao"] = "O processo está congelado."
        self.preco_total = (self.quantidade_ofertada * self.preco_unitario).quantize(Decimal("0.01")) if self.quantidade_ofertada is not None and self.preco_unitario is not None else 0
        if errors: raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(); return super().save(*args, **kwargs)


class EscolhaCotacaoItem(models.Model):
    processo_item = models.OneToOneField(ProcessoCotacaoItem, on_delete=models.CASCADE, related_name="escolha")
    oferta_escolhida = models.ForeignKey(CotacaoFornecedorItem, on_delete=models.PROTECT, related_name="escolhas")
    escolhido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="escolhas_cotacao")
    escolhido_em = models.DateTimeField(auto_now_add=True)
    justificativa = models.TextField(blank=True)
    era_menor_preco = models.BooleanField(default=False)
    observacao = models.TextField(blank=True)

    def __str__(self): return f"{self.processo_item} — {self.oferta_escolhida.cotacao.fornecedor}"


class HistoricoProcessoCotacao(models.Model):
    processo = models.ForeignKey(ProcessoCotacao, on_delete=models.CASCADE, related_name="historico")
    status_anterior = models.CharField(max_length=20, blank=True)
    status_novo = models.CharField(max_length=20, choices=ProcessoCotacao.Status.choices)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta: ordering = ["-criado_em", "-id"]

    def get_status_anterior_display(self): return dict(ProcessoCotacao.Status.choices).get(self.status_anterior, self.status_anterior)


class PedidoCompra(models.Model):
    class Origem(models.TextChoices):
        COTACAO = "COTACAO", "Cotação"
        DIRETA = "DIRETA", "Direta"
        EMERGENCIAL = "EMERGENCIAL", "Emergencial"
    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        AGUARDANDO_APROVACAO = "AGUARDANDO_APROVACAO", "Aguardando aprovação"
        APROVADO = "APROVADO", "Aprovado"
        ENVIADO_FORNECEDOR = "ENVIADO_FORNECEDOR", "Enviado ao fornecedor"
        REJEITADO = "REJEITADO", "Rejeitado"
        CANCELADO = "CANCELADO", "Cancelado"
        PARCIALMENTE_RECEBIDO = "PARCIALMENTE_RECEBIDO", "Parcialmente recebido"
        RECEBIDO = "RECEBIDO", "Recebido"

    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="pedidos_compra")
    fornecedor = models.ForeignKey(Pessoa, on_delete=models.PROTECT, related_name="pedidos_compra_fornecedor")
    origem = models.CharField(max_length=15, choices=Origem.choices)
    justificativa_origem = models.TextField(blank=True)
    nome_vendedor_fornecedor_snapshot = models.CharField(max_length=150, blank=True)
    telefone_vendedor_snapshot = models.CharField(max_length=30, blank=True)
    email_vendedor_snapshot = models.EmailField(blank=True)
    numero_pedido_versatile = models.CharField(max_length=80)
    numero_pedido_fornecedor = models.CharField(max_length=80, blank=True)
    data_pedido = models.DateField(default=timezone.localdate)
    condicao_pagamento = models.TextField()
    prazo_entrega = models.CharField(max_length=150)
    tipo_frete = models.CharField(max_length=50, blank=True)
    transportadora = models.ForeignKey(Pessoa, on_delete=models.PROTECT, null=True, blank=True, related_name="pedidos_compra_transportadora")
    transportadora_nome_snapshot = models.CharField(max_length=200, blank=True)
    transportadora_documento_snapshot = models.CharField(max_length=30, blank=True)
    transportadora_contato_snapshot = models.CharField(max_length=100, blank=True)
    dados_bancarios = models.TextField(blank=True)
    instrucoes_entrega = models.TextField(blank=True)
    observacoes = models.TextField(blank=True)
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    frete = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    impostos = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    outras_despesas = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    responsavel_nome_snapshot = models.CharField(max_length=150, blank=True)
    responsavel_cargo_snapshot = models.CharField(max_length=100, blank=True)
    assinatura_textual = models.TextField(blank=True)
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.RASCUNHO)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pedidos_compra_criados")
    aprovado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="pedidos_compra_aprovados")
    aprovado_em = models.DateTimeField(null=True, blank=True)
    enviado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="pedidos_compra_enviados")
    enviado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_pedido", "-id"]
        constraints = [models.UniqueConstraint(fields=["empresa", "numero_pedido_versatile"], name="uq_numero_pedido_compra_empresa")]
        permissions = [("criar_pedido", "Pode criar pedido de compra"), ("aprovar_pedido", "Pode aprovar pedido de compra"), ("rejeitar_pedido", "Pode rejeitar pedido de compra"), ("cancelar_pedido", "Pode cancelar pedido de compra"), ("enviar_pedido", "Pode enviar pedido ao fornecedor"), ("view_custos_compra", "Pode visualizar custos de compras")]

    def clean(self):
        errors = {}
        self.numero_pedido_versatile = " ".join((self.numero_pedido_versatile or "").split())
        if not self.numero_pedido_versatile: errors["numero_pedido_versatile"] = "Informe o número do pedido Versatile."
        if self.fornecedor_id and (not self.fornecedor.ativo or self.fornecedor.classificacao not in {Pessoa.Classificacao.FORNECEDOR, Pessoa.Classificacao.AMBOS}): errors["fornecedor"] = "Selecione um fornecedor ativo."
        if self.origem in {self.Origem.DIRETA, self.Origem.EMERGENCIAL} and not self.justificativa_origem.strip(): errors["justificativa_origem"] = "Informe a justificativa para compra direta ou emergencial."
        if self.transportadora_id:
            self.transportadora_nome_snapshot = self.transportadora_nome_snapshot or str(self.transportadora)
            self.transportadora_documento_snapshot = self.transportadora_documento_snapshot or self.transportadora.cpf_cnpj
            self.transportadora_contato_snapshot = self.transportadora_contato_snapshot or self.transportadora.telefone or self.transportadora.email
        for campo in ("frete", "desconto", "impostos", "outras_despesas"):
            if getattr(self, campo, 0) < 0: errors[campo] = "O valor não pode ser negativo."
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values("status").first()
            if original and original["status"] in {self.Status.APROVADO, self.Status.ENVIADO_FORNECEDOR, self.Status.REJEITADO, self.Status.CANCELADO, self.Status.PARCIALMENTE_RECEBIDO, self.Status.RECEBIDO}: errors["status"] = "O pedido está congelado."
        if errors: raise ValidationError(errors)

    def save(self, *args, **kwargs): self.full_clean(); return super().save(*args, **kwargs)
    def __str__(self): return self.numero_pedido_versatile or "Novo pedido"


class PedidoCompraItem(models.Model):
    pedido = models.ForeignKey(PedidoCompra, on_delete=models.CASCADE, related_name="itens")
    escolha_cotacao_item = models.OneToOneField(EscolhaCotacaoItem, on_delete=models.PROTECT, null=True, blank=True, related_name="pedido_item")
    solicitacao_item = models.ForeignKey(SolicitacaoCompraItem, on_delete=models.PROTECT, null=True, blank=True, related_name="itens_pedido_compra")
    proposta_item = models.ForeignKey(PropostaItem, on_delete=models.PROTECT, null=True, blank=True, related_name="itens_pedido_compra")
    proposta_codigo_snapshot = models.CharField(max_length=80, blank=True)
    descricao_mercadoria = models.CharField(max_length=250)
    quantidade = models.DecimalField(max_digits=15, decimal_places=4)
    unidade = models.CharField(max_length=20)
    valor_unitario = models.DecimalField(max_digits=15, decimal_places=4)
    valor_bruto = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    desconto = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    impostos = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    frete_alocado = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    outras_despesas_alocadas = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    custo_total = models.DecimalField(max_digits=15, decimal_places=2, default=0, editable=False)
    plano_conta = models.ForeignKey(PlanoConta, on_delete=models.PROTECT, null=True, blank=True, related_name="itens_pedido_compra")
    observacao = models.TextField(blank=True)
    ordem = models.PositiveIntegerField(default=0)
    class Meta: ordering = ["ordem", "id"]
    def clean(self):
        errors={}
        if self.quantidade is not None and self.quantidade <= 0: errors["quantidade"]="Informe quantidade positiva."
        if self.valor_unitario is not None and self.valor_unitario < 0: errors["valor_unitario"]="O valor não pode ser negativo."
        if self.solicitacao_item_id and self.pedido_id and self.solicitacao_item.solicitacao.empresa_id != self.pedido.empresa_id: errors["solicitacao_item"]="O item da solicitação deve pertencer à empresa do pedido."
        if self.proposta_item_id and self.pedido_id and self.proposta_item.revisao.proposta.empresa_id != self.pedido.empresa_id: errors["proposta_item"]="O item da proposta deve pertencer à empresa do pedido."
        if self.escolha_cotacao_item_id and self.pedido_id:
            oferta=self.escolha_cotacao_item.oferta_escolhida
            if oferta.cotacao.fornecedor_id != self.pedido.fornecedor_id or oferta.cotacao.processo.empresa_id != self.pedido.empresa_id: errors["escolha_cotacao_item"]="A escolha deve pertencer ao fornecedor e à empresa do pedido."
        if self.pedido_id and PedidoCompra.objects.filter(pk=self.pedido_id).exclude(status__in=[PedidoCompra.Status.RASCUNHO, PedidoCompra.Status.AGUARDANDO_APROVACAO]).exists(): errors["pedido"]="O pedido está congelado."
        if errors: raise ValidationError(errors)
    def save(self,*args,**kwargs): self.full_clean(); return super().save(*args,**kwargs)


class PedidoItemAlocacaoObra(models.Model):
    pedido_item = models.ForeignKey(PedidoCompraItem, on_delete=models.CASCADE, related_name="alocacoes")
    obra = models.ForeignKey(CentroCusto, on_delete=models.PROTECT, related_name="alocacoes_pedido_compra")
    solicitacao_item = models.ForeignKey(SolicitacaoCompraItem, on_delete=models.PROTECT, null=True, blank=True, related_name="alocacoes_pedido_compra")
    proposta_item = models.ForeignKey(PropostaItem, on_delete=models.PROTECT, null=True, blank=True, related_name="alocacoes_pedido_compra")
    quantidade = models.DecimalField(max_digits=15, decimal_places=4)
    valor = models.DecimalField(max_digits=15, decimal_places=2)
    tipo_origem = models.CharField(max_length=20, choices=SolicitacaoCompraItem.TipoOrigem.choices)
    observacao = models.TextField(blank=True)
    def clean(self):
        errors={}
        if self.quantidade is not None and self.quantidade <= 0: errors["quantidade"]="Informe quantidade positiva."
        if self.valor is not None and self.valor < 0: errors["valor"]="O valor não pode ser negativo."
        if self.obra_id and self.pedido_item_id:
            if self.obra.empresa_id != self.pedido_item.pedido.empresa_id: errors["obra"]="A obra deve pertencer à empresa do pedido."
            if not self.obra.ativo and not self.pk: errors["obra"]="Obra inativa não pode receber nova alocação."
        if self.pedido_item_id and PedidoCompra.objects.filter(pk=self.pedido_item.pedido_id).exclude(status=PedidoCompra.Status.RASCUNHO).exists(): errors["pedido_item"]="As alocações estão congeladas."
        if errors: raise ValidationError(errors)
    def save(self,*args,**kwargs): self.full_clean(); return super().save(*args,**kwargs)


class HistoricoPedidoCompra(models.Model):
    pedido = models.ForeignKey(PedidoCompra, on_delete=models.CASCADE, related_name="historico")
    status_anterior = models.CharField(max_length=25, blank=True)
    status_novo = models.CharField(max_length=25, choices=PedidoCompra.Status.choices)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["-criado_em","-id"]
    def get_status_anterior_display(self): return dict(PedidoCompra.Status.choices).get(self.status_anterior,self.status_anterior)


class RecebimentoCompra(models.Model):
    class Status(models.TextChoices):
        RASCUNHO="RASCUNHO","Rascunho"
        CONFIRMADO="CONFIRMADO","Confirmado"
        CANCELADO="CANCELADO","Cancelado"
    pedido=models.ForeignKey(PedidoCompra,on_delete=models.PROTECT,related_name="recebimentos")
    data_recebimento=models.DateField(default=timezone.localdate)
    responsavel=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="recebimentos_compra_responsavel")
    numero_documento=models.CharField(max_length=100,blank=True)
    observacao=models.TextField(blank=True)
    status=models.CharField(max_length=15,choices=Status.choices,default=Status.RASCUNHO)
    criado_por=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="recebimentos_compra_criados")
    confirmado_por=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,blank=True,related_name="recebimentos_compra_confirmados")
    confirmado_em=models.DateTimeField(null=True,blank=True)
    cancelado_por=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,blank=True,related_name="recebimentos_compra_cancelados")
    cancelado_em=models.DateTimeField(null=True,blank=True)
    motivo_cancelamento=models.TextField(blank=True)
    criado_em=models.DateTimeField(auto_now_add=True)
    atualizado_em=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=["-data_recebimento","-id"]
        permissions=[("registrar_recebimento","Pode registrar recebimento de compra"),("cancelar_recebimento","Pode cancelar recebimento confirmado"),("resolver_divergencia_recebimento","Pode resolver divergência de recebimento")]
    @property
    def identificacao(self): return f"REC-{self.pk:05d}" if self.pk else "Novo recebimento"
    def clean(self):
        if self.pedido_id and self.pedido.status not in {PedidoCompra.Status.APROVADO,PedidoCompra.Status.ENVIADO_FORNECEDOR,PedidoCompra.Status.PARCIALMENTE_RECEBIDO} and not self.pk: raise ValidationError({"pedido":"Este pedido não permite recebimento."})
        if self.pk and type(self).objects.filter(pk=self.pk).exclude(status=self.Status.RASCUNHO).exists(): raise ValidationError({"status":"O recebimento confirmado ou cancelado é imutável."})
    def save(self,*args,**kwargs): self.full_clean(); return super().save(*args,**kwargs)
    def __str__(self): return f"{self.identificacao} — {self.pedido}"


class RecebimentoCompraItem(models.Model):
    recebimento=models.ForeignKey(RecebimentoCompra,on_delete=models.CASCADE,related_name="itens")
    pedido_item=models.ForeignKey(PedidoCompraItem,on_delete=models.PROTECT,related_name="itens_recebimento")
    quantidade_recebida=models.DecimalField(max_digits=15,decimal_places=4)
    quantidade_aceita=models.DecimalField(max_digits=15,decimal_places=4)
    quantidade_rejeitada=models.DecimalField(max_digits=15,decimal_places=4,default=0)
    observacao=models.TextField(blank=True)
    possui_divergencia=models.BooleanField(default=False)
    class Meta:
        ordering=["id"]
        constraints=[models.UniqueConstraint(fields=["recebimento","pedido_item"],name="uq_item_por_recebimento_compra")]
    def clean(self):
        errors={}
        for campo in ("quantidade_recebida","quantidade_aceita","quantidade_rejeitada"):
            if getattr(self,campo,None) is not None and getattr(self,campo)<0: errors[campo]="A quantidade não pode ser negativa."
        if self.quantidade_aceita is not None and self.quantidade_rejeitada is not None and self.quantidade_recebida is not None and self.quantidade_aceita+self.quantidade_rejeitada>self.quantidade_recebida: errors["quantidade_recebida"]="Aceito mais rejeitado não pode superar o recebido."
        if self.pedido_item_id and self.recebimento_id and self.pedido_item.pedido_id!=self.recebimento.pedido_id: errors["pedido_item"]="O item deve pertencer ao pedido do recebimento."
        if self.recebimento_id and RecebimentoCompra.objects.filter(pk=self.recebimento_id).exclude(status=RecebimentoCompra.Status.RASCUNHO).exists(): errors["recebimento"]="O recebimento está congelado."
        if errors: raise ValidationError(errors)
    def save(self,*args,**kwargs): self.full_clean(); return super().save(*args,**kwargs)


class DivergenciaRecebimento(models.Model):
    class Tipo(models.TextChoices):
        QUANTIDADE_MENOR="QUANTIDADE_MENOR","Quantidade menor"
        QUANTIDADE_MAIOR="QUANTIDADE_MAIOR","Quantidade maior"
        MATERIAL_INCORRETO="MATERIAL_INCORRETO","Material incorreto"
        DANIFICADO="DANIFICADO","Danificado"
        PRECO_DIVERGENTE="PRECO_DIVERGENTE","Preço divergente"
        OUTRO="OUTRO","Outro"
    recebimento_item=models.ForeignKey(RecebimentoCompraItem,on_delete=models.PROTECT,related_name="divergencias")
    tipo=models.CharField(max_length=25,choices=Tipo.choices)
    descricao=models.TextField()
    quantidade_afetada=models.DecimalField(max_digits=15,decimal_places=4,null=True,blank=True)
    resolvida=models.BooleanField(default=False)
    resolvida_por=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,blank=True,related_name="divergencias_recebimento_resolvidas")
    resolvida_em=models.DateTimeField(null=True,blank=True)
    solucao=models.TextField(blank=True)
    criado_em=models.DateTimeField(auto_now_add=True)
    def clean(self):
        if self.quantidade_afetada is not None and self.quantidade_afetada<0: raise ValidationError({"quantidade_afetada":"A quantidade não pode ser negativa."})
        if self.resolvida and (not self.resolvida_por_id or not self.resolvida_em or not self.solucao.strip()): raise ValidationError("Informe usuário, data e solução da divergência.")
    def save(self,*args,**kwargs):
        self.full_clean(); resultado=super().save(*args,**kwargs)
        RecebimentoCompraItem.objects.filter(pk=self.recebimento_item_id).update(possui_divergencia=True)
        return resultado


def _normalizar_identificador(valor):
    return "".join((valor or "").upper().split())


def _normalizar_chave_fiscal(valor):
    return "".join(c for c in (valor or "").upper() if c.isalnum())


class DocumentoCompra(models.Model):
    class Tipo(models.TextChoices):
        NOTA_FISCAL="NOTA_FISCAL","Nota Fiscal"
        FATURA="FATURA","Fatura"
        BOLETO="BOLETO","Boleto/cobrança"
        RECIBO="RECIBO","Recibo"
        OUTRO="OUTRO","Outro"
    class Status(models.TextChoices):
        RASCUNHO="RASCUNHO","Rascunho"
        EM_CONFERENCIA="EM_CONFERENCIA","Em conferência"
        CONFERIDO="CONFERIDO","Conferido"
        DIVERGENTE="DIVERGENTE","Divergente"
        CANCELADO="CANCELADO","Cancelado"
    empresa=models.ForeignKey(Empresa,on_delete=models.PROTECT,related_name="documentos_compra")
    fornecedor=models.ForeignKey(Pessoa,on_delete=models.PROTECT,related_name="documentos_compra")
    tipo=models.CharField(max_length=20,choices=Tipo.choices)
    numero=models.CharField(max_length=100)
    numero_normalizado=models.CharField(max_length=100,editable=False)
    serie=models.CharField(max_length=50,blank=True)
    serie_normalizada=models.CharField(max_length=50,blank=True,editable=False)
    chave_fiscal=models.CharField(max_length=100,blank=True)
    data_emissao=models.DateField()
    data_entrada=models.DateField(default=timezone.localdate)
    valor_bruto=models.DecimalField(max_digits=15,decimal_places=2)
    desconto=models.DecimalField(max_digits=15,decimal_places=2,default=0)
    frete=models.DecimalField(max_digits=15,decimal_places=2,default=0)
    impostos=models.DecimalField(max_digits=15,decimal_places=2,default=0)
    outras_despesas=models.DecimalField(max_digits=15,decimal_places=2,default=0)
    valor_total=models.DecimalField(max_digits=15,decimal_places=2,default=0,editable=False)
    condicao_pagamento=models.TextField(blank=True)
    observacoes=models.TextField(blank=True)
    status=models.CharField(max_length=20,choices=Status.choices,default=Status.RASCUNHO)
    criado_por=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="documentos_compra_criados")
    enviado_conferencia_por=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,blank=True,related_name="documentos_compra_enviados_conferencia")
    enviado_conferencia_em=models.DateTimeField(null=True,blank=True)
    conferido_por=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,blank=True,related_name="documentos_compra_conferidos")
    conferido_em=models.DateTimeField(null=True,blank=True)
    cancelado_por=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,blank=True,related_name="documentos_compra_cancelados")
    cancelado_em=models.DateTimeField(null=True,blank=True)
    motivo_cancelamento=models.TextField(blank=True)
    criado_em=models.DateTimeField(auto_now_add=True)
    atualizado_em=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=["-data_emissao","-id"]
        constraints=[
            models.UniqueConstraint(fields=["empresa","fornecedor","tipo","numero_normalizado","serie_normalizada"],name="uq_documento_compra_identificacao"),
            models.UniqueConstraint(fields=["chave_fiscal"],condition=~models.Q(chave_fiscal=""),name="uq_documento_compra_chave_fiscal"),
        ]
        permissions=[("conferir_documento_compra","Pode conferir documento de compra"),("resolver_divergencia_documento","Pode resolver divergência de documento"),("cancelar_documento_compra","Pode cancelar documento de compra"),("view_valores_documento_compra","Pode visualizar valores de documento de compra")]
    @property
    def identificacao(self): return f"{self.get_tipo_display()} {self.numero}{('/'+self.serie) if self.serie else ''}"
    def clean(self):
        errors={}; self.numero=" ".join((self.numero or "").split()); self.serie=" ".join((self.serie or "").split()); self.numero_normalizado=_normalizar_identificador(self.numero); self.serie_normalizada=_normalizar_identificador(self.serie); self.chave_fiscal=_normalizar_chave_fiscal(self.chave_fiscal)
        if not self.numero_normalizado: errors["numero"]="Informe o número do documento."
        if self.fornecedor_id and (not self.fornecedor.ativo or self.fornecedor.classificacao not in {Pessoa.Classificacao.FORNECEDOR,Pessoa.Classificacao.AMBOS}): errors["fornecedor"]="Selecione um fornecedor ativo."
        for campo in ("valor_bruto","desconto","frete","impostos","outras_despesas"):
            if getattr(self,campo,None) is not None and getattr(self,campo)<0: errors[campo]="O valor não pode ser negativo."
        if all(getattr(self,c,None) is not None for c in ("valor_bruto","desconto","frete","impostos","outras_despesas")): self.valor_total=(self.valor_bruto-self.desconto+self.frete+self.impostos+self.outras_despesas).quantize(Decimal("0.01"))
        if self.valor_total<0: errors["valor_total"]="O total não pode ser negativo."
        if self.pk and type(self).objects.filter(pk=self.pk).exclude(status=self.Status.RASCUNHO).exists(): errors["status"]="Somente documentos em rascunho podem ser editados."
        if errors: raise ValidationError(errors)
    def save(self,*args,**kwargs): self.full_clean(); return super().save(*args,**kwargs)
    def __str__(self): return self.identificacao


class DocumentoCompraItem(models.Model):
    documento=models.ForeignKey(DocumentoCompra,on_delete=models.CASCADE,related_name="itens")
    pedido_item=models.ForeignKey(PedidoCompraItem,on_delete=models.PROTECT,null=True,blank=True,related_name="itens_documento_compra")
    descricao_snapshot=models.CharField(max_length=250)
    quantidade_faturada=models.DecimalField(max_digits=15,decimal_places=4)
    unidade=models.CharField(max_length=20)
    valor_unitario_faturado=models.DecimalField(max_digits=15,decimal_places=4)
    valor_bruto=models.DecimalField(max_digits=15,decimal_places=2,default=0,editable=False)
    desconto=models.DecimalField(max_digits=15,decimal_places=2,default=0)
    frete_alocado=models.DecimalField(max_digits=15,decimal_places=2,default=0)
    impostos=models.DecimalField(max_digits=15,decimal_places=2,default=0)
    outras_despesas=models.DecimalField(max_digits=15,decimal_places=2,default=0)
    total=models.DecimalField(max_digits=15,decimal_places=2,default=0,editable=False)
    plano_conta=models.ForeignKey(PlanoConta,on_delete=models.PROTECT,related_name="itens_documento_compra")
    observacao=models.TextField(blank=True)
    ordem=models.PositiveIntegerField(default=0)
    class Meta: ordering=["ordem","id"]
    def clean(self):
        errors={}
        if self.quantidade_faturada is not None and self.quantidade_faturada<=0: errors["quantidade_faturada"]="Informe quantidade positiva."
        if self.valor_unitario_faturado is not None and self.valor_unitario_faturado<0: errors["valor_unitario_faturado"]="O valor não pode ser negativo."
        for campo in ("desconto","frete_alocado","impostos","outras_despesas"):
            if getattr(self,campo,None) is not None and getattr(self,campo)<0: errors[campo]="O valor não pode ser negativo."
        if self.pedido_item_id and self.documento_id:
            if self.pedido_item.pedido.empresa_id!=self.documento.empresa_id: errors["pedido_item"]="O item do pedido deve pertencer à empresa do documento."
            if self.pedido_item.pedido.fornecedor_id!=self.documento.fornecedor_id: errors["pedido_item"]="O item do pedido deve pertencer ao fornecedor do documento."
        if self.plano_conta_id and (not self.plano_conta.ativo or self.plano_conta.estrutural or not self.plano_conta.aceita_lancamento or self.plano_conta.tipo not in {"CUSTO","DESPESA"}): errors["plano_conta"]="Selecione uma conta analítica ativa de custo ou despesa."
        if self.documento_id and self.documento.status!=DocumentoCompra.Status.RASCUNHO: errors["documento"]="Os itens estão congelados."
        if self.quantidade_faturada is not None and self.valor_unitario_faturado is not None:
            self.valor_bruto=(self.quantidade_faturada*self.valor_unitario_faturado).quantize(Decimal("0.01")); self.total=(self.valor_bruto-self.desconto+self.frete_alocado+self.impostos+self.outras_despesas).quantize(Decimal("0.01"))
            if self.total<0: errors["total"]="O total do item não pode ser negativo."
        if errors: raise ValidationError(errors)
    def save(self,*args,**kwargs): self.full_clean(); return super().save(*args,**kwargs)


class DocumentoCompraPedido(models.Model):
    documento=models.ForeignKey(DocumentoCompra,on_delete=models.CASCADE,related_name="vinculos_pedidos")
    pedido=models.ForeignKey(PedidoCompra,on_delete=models.PROTECT,related_name="vinculos_documentos")
    criado_em=models.DateTimeField(auto_now_add=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["documento","pedido"],name="uq_documento_compra_pedido")]
    def clean(self):
        errors={}
        if self.documento_id and self.pedido_id:
            if self.documento.empresa_id!=self.pedido.empresa_id: errors["pedido"]="O pedido deve pertencer à empresa do documento."
            if self.documento.fornecedor_id!=self.pedido.fornecedor_id: errors["pedido"]="O pedido deve pertencer ao fornecedor do documento."
        if self.documento_id and self.documento.status!=DocumentoCompra.Status.RASCUNHO: errors["documento"]="Os vínculos estão congelados."
        if errors: raise ValidationError(errors)
    def save(self,*args,**kwargs): self.full_clean(); return super().save(*args,**kwargs)


class DocumentoCompraItemRecebimento(models.Model):
    documento_item=models.ForeignKey(DocumentoCompraItem,on_delete=models.CASCADE,related_name="vinculos_recebimentos")
    recebimento_item=models.ForeignKey(RecebimentoCompraItem,on_delete=models.PROTECT,related_name="vinculos_documentos")
    quantidade_vinculada=models.DecimalField(max_digits=15,decimal_places=4)
    criado_em=models.DateTimeField(auto_now_add=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["documento_item","recebimento_item"],name="uq_documento_item_recebimento")]
    def clean(self):
        errors={}
        if self.quantidade_vinculada is not None and self.quantidade_vinculada<=0: errors["quantidade_vinculada"]="Informe quantidade positiva."
        if self.documento_item_id and self.recebimento_item_id:
            if self.recebimento_item.recebimento.status!=RecebimentoCompra.Status.CONFIRMADO: errors["recebimento_item"]="Use um recebimento confirmado."
            if self.documento_item.pedido_item_id and self.documento_item.pedido_item_id!=self.recebimento_item.pedido_item_id: errors["recebimento_item"]="O recebimento deve corresponder ao item do pedido."
            if self.recebimento_item.pedido_item.pedido.empresa_id!=self.documento_item.documento.empresa_id or self.recebimento_item.pedido_item.pedido.fornecedor_id!=self.documento_item.documento.fornecedor_id: errors["recebimento_item"]="O recebimento deve pertencer à empresa e fornecedor do documento."
            usado=type(self).objects.filter(recebimento_item=self.recebimento_item).exclude(pk=self.pk).aggregate(total=models.Sum("quantidade_vinculada"))["total"] or Decimal("0")
            if self.quantidade_vinculada is not None and usado+self.quantidade_vinculada>self.recebimento_item.quantidade_aceita: errors["quantidade_vinculada"]="A quantidade vinculada supera a quantidade aceita disponível."
        if self.documento_item_id and self.documento_item.documento.status!=DocumentoCompra.Status.RASCUNHO: errors["documento_item"]="Os vínculos estão congelados."
        if errors: raise ValidationError(errors)
    def save(self,*args,**kwargs): self.full_clean(); return super().save(*args,**kwargs)


class DivergenciaDocumentoCompra(models.Model):
    class Tipo(models.TextChoices):
        QUANTIDADE_MAIOR="QUANTIDADE_MAIOR","Quantidade maior"
        QUANTIDADE_MENOR="QUANTIDADE_MENOR","Quantidade menor"
        PRECO="PRECO","Preço divergente"
        FRETE="FRETE","Frete divergente"
        DESCONTO="DESCONTO","Desconto divergente"
        IMPOSTO="IMPOSTO","Imposto divergente"
        DOCUMENTO_DUPLICADO="DOCUMENTO_DUPLICADO","Documento duplicado"
        ITEM_SEM_VINCULO="ITEM_SEM_VINCULO","Item sem pedido/recebimento"
        OUTRO="OUTRO","Outro"
    documento=models.ForeignKey(DocumentoCompra,on_delete=models.PROTECT,related_name="divergencias")
    documento_item=models.ForeignKey(DocumentoCompraItem,on_delete=models.PROTECT,null=True,blank=True,related_name="divergencias")
    tipo=models.CharField(max_length=25,choices=Tipo.choices)
    descricao=models.TextField()
    quantidade_afetada=models.DecimalField(max_digits=15,decimal_places=4,null=True,blank=True)
    valor_afetado=models.DecimalField(max_digits=15,decimal_places=2,null=True,blank=True)
    bloqueante=models.BooleanField(default=True)
    automatica=models.BooleanField(default=False)
    resolvida=models.BooleanField(default=False)
    resolvida_por=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,blank=True,related_name="divergencias_documento_resolvidas")
    resolvida_em=models.DateTimeField(null=True,blank=True)
    solucao=models.TextField(blank=True)
    criado_em=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["resolvida","id"]
    def clean(self):
        if self.documento_item_id and self.documento_item.documento_id!=self.documento_id: raise ValidationError({"documento_item":"O item deve pertencer ao documento."})
        if self.resolvida and (not self.resolvida_por_id or not self.resolvida_em or not self.solucao.strip()): raise ValidationError("Informe responsável, data e solução.")
    def save(self,*args,**kwargs): self.full_clean(); return super().save(*args,**kwargs)


class DocumentoCompraParcela(models.Model):
    documento=models.ForeignKey(DocumentoCompra,on_delete=models.CASCADE,related_name="parcelas")
    numero=models.PositiveIntegerField()
    vencimento=models.DateField()
    valor=models.DecimalField(max_digits=15,decimal_places=2)
    observacao=models.TextField(blank=True)
    parcela_financeira=models.OneToOneField("financeiro.ParcelaFinanceira",on_delete=models.PROTECT,null=True,blank=True,related_name="parcela_documento_compra")
    criado_em=models.DateTimeField(auto_now_add=True)
    atualizado_em=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=["numero","vencimento"]
        constraints=[models.UniqueConstraint(fields=["documento","numero"],name="uq_parcela_documento_compra")]
        permissions=[("view_preview_financeiro_documento","Pode visualizar preview financeiro de documento")]
    def clean(self):
        errors={}
        if self.numero is not None and self.numero<=0: errors["numero"]="O número da parcela deve ser maior que zero."
        if self.valor is not None and self.valor<=0: errors["valor"]="O valor da parcela deve ser maior que zero."
        if self.pk and type(self).objects.filter(pk=self.pk,parcela_financeira__isnull=False).exists(): errors["parcela_financeira"]="A parcela integrada ao Financeiro está congelada."
        if self.documento_id and self.documento.parcelas.filter(parcela_financeira__isnull=False).exclude(pk=self.pk).exists(): errors["documento"]="As parcelas do documento integrado estão congeladas."
        if errors: raise ValidationError(errors)
    def save(self,*args,**kwargs): self.full_clean(); return super().save(*args,**kwargs)
    def delete(self,*args,**kwargs):
        if self.parcela_financeira_id or self.documento.parcelas.filter(parcela_financeira__isnull=False).exists(): raise ValidationError("As parcelas do documento integrado estão congeladas.")
        return super().delete(*args,**kwargs)
    def __str__(self): return f"{self.documento} — parcela {self.numero}"
