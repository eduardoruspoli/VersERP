from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from financeiro.models import ContaBancaria, Empresa, PlanoConta
from pessoas.models import Pessoa


class ModeloConteudoProposta(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="modelos_proposta")
    nome = models.CharField(max_length=120)
    ativo = models.BooleanField(default=True)
    padrao = models.BooleanField(default=False)
    texto_introdutorio = models.TextField(blank=True)
    normas_procedimentos = models.TextField(blank=True)
    qualificacao_mao_obra = models.TextField(blank=True)
    obrigacoes_contratada = models.TextField(blank=True)
    observacoes_comerciais = models.TextField(blank=True)
    observacao_faturamento = models.TextField(blank=True)
    texto_impostos = models.TextField(blank=True)
    multa_juros_atraso = models.TextField(blank=True)
    regra_protesto = models.TextField(blank=True)
    rodape = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["empresa", "nome"]
        constraints = [models.UniqueConstraint(fields=["empresa", "nome"], name="uq_modelo_proposta_empresa_nome")]

    def __str__(self):
        return self.nome


class Proposta(models.Model):
    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        EM_REVISAO = "EM_REVISAO", "Em revisão"
        ENVIADA = "ENVIADA", "Enviada"
        EM_NEGOCIACAO = "EM_NEGOCIACAO", "Em negociação"
        APROVADA = "APROVADA", "Aprovada"
        REJEITADA = "REJEITADA", "Rejeitada"
        CANCELADA = "CANCELADA", "Cancelada"

    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="propostas")
    cliente = models.ForeignKey(Pessoa, on_delete=models.PROTECT, related_name="propostas_cliente")
    codigo = models.CharField(max_length=20)
    numero_sequencial = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RASCUNHO)
    revisao_atual = models.PositiveIntegerField(default=0)
    centro_custo = models.OneToOneField("financeiro.CentroCusto", on_delete=models.PROTECT, null=True, blank=True, related_name="proposta_origem")
    responsavel_interno = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="propostas_responsavel")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "codigo"], name="uq_proposta_empresa_codigo"),
            models.UniqueConstraint(fields=["empresa", "numero_sequencial"], name="uq_proposta_empresa_numero"),
        ]

    def clean(self):
        if self.cliente_id and (not self.cliente.ativo or self.cliente.classificacao not in {Pessoa.Classificacao.CLIENTE, Pessoa.Classificacao.AMBOS}):
            raise ValidationError({"cliente": "Selecione um cliente ativo."})

    def __str__(self):
        return self.codigo


class PropostaRevisao(models.Model):
    class FormacaoPreco(models.TextChoices):
        MARKUP = "MARKUP", "Markup"
        MARGEM = "MARGEM", "Margem"
        MANUAL = "MANUAL", "Preço manual"

    proposta = models.ForeignKey(Proposta, on_delete=models.CASCADE, related_name="revisoes")
    numero = models.PositiveIntegerField(default=0)
    modelo_conteudo = models.ForeignKey(ModeloConteudoProposta, on_delete=models.SET_NULL, null=True, blank=True)
    data_proposta = models.DateField()
    nome_servico = models.CharField(max_length=250)
    aos_cuidados_de = models.CharField(max_length=150, blank=True)
    escopo_incluido = models.TextField(blank=True)
    nao_incluso = models.TextField(blank=True)
    prazo_entrega = models.CharField(max_length=200, blank=True)
    tipo_frete = models.CharField(max_length=100, blank=True)
    condicao_pagamento = models.TextField(blank=True)
    validade_dias = models.PositiveIntegerField(default=15)
    valida_ate = models.DateField(null=True, blank=True)
    texto_introdutorio = models.TextField(blank=True)
    exibir_texto_introdutorio = models.BooleanField(default=True)
    normas_procedimentos = models.TextField(blank=True)
    exibir_normas_procedimentos = models.BooleanField(default=True)
    qualificacao_mao_obra = models.TextField(blank=True)
    exibir_qualificacao_mao_obra = models.BooleanField(default=True)
    obrigacoes_contratada = models.TextField(blank=True)
    exibir_obrigacoes_contratada = models.BooleanField(default=True)
    observacoes_comerciais = models.TextField(blank=True)
    exibir_observacoes_comerciais = models.BooleanField(default=True)
    observacao_faturamento = models.TextField(blank=True)
    texto_impostos = models.TextField(blank=True)
    multa_juros_atraso = models.TextField(blank=True)
    regra_protesto = models.TextField(blank=True)
    dados_bancarios = models.TextField(blank=True)
    conta_bancaria_pagamento = models.ForeignKey(ContaBancaria, on_delete=models.PROTECT, null=True, blank=True)
    responsavel_nome = models.CharField(max_length=150, blank=True)
    responsavel_cargo = models.CharField(max_length=100, blank=True)
    assinatura_textual = models.CharField(max_length=200, blank=True)
    rodape = models.TextField(blank=True)
    observacoes_internas = models.TextField(blank=True)
    formacao_preco = models.CharField(max_length=10, choices=FormacaoPreco.choices, default=FormacaoPreco.MARKUP)
    percentual_formacao = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0"))
    preco_venda_final = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0"))
    congelada = models.BooleanField(default=False)
    enviada_em = models.DateTimeField(null=True, blank=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    empresa_nome_snapshot = models.CharField(max_length=200, blank=True)
    empresa_documento_snapshot = models.CharField(max_length=30, blank=True)
    cliente_nome_snapshot = models.CharField(max_length=200, blank=True)
    cliente_documento_snapshot = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["proposta", "-numero"]
        constraints = [models.UniqueConstraint(fields=["proposta", "numero"], name="uq_proposta_revisao_numero")]

    def __str__(self):
        return f"{self.proposta.codigo} - Rev. {self.numero}"

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk, congelada=True).exists():
            raise ValidationError("A revisão enviada está congelada.")
        self.full_clean()
        return super().save(*args, **kwargs)


class ProtegidoPorCongelamento(models.Model):
    class Meta:
        abstract = True

    def clean(self):
        if self.revisao_id and PropostaRevisao.objects.filter(pk=self.revisao_id, congelada=True).exists():
            raise ValidationError("A revisão enviada está congelada.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if PropostaRevisao.objects.filter(pk=self.revisao_id, congelada=True).exists():
            raise ValidationError("A revisão enviada está congelada.")
        return super().delete(*args, **kwargs)


class PropostaItem(ProtegidoPorCongelamento):
    class Tipo(models.TextChoices):
        MATERIAL = "MATERIAL", "Material"
        MAO_OBRA = "MAO_OBRA", "Mão de obra"
        SERVICO_TERCEIRO = "SERVICO_TERCEIRO", "Serviço de terceiro"
        FRETE = "FRETE", "Frete"
        LOCACAO_EQUIPAMENTO = "LOCACAO_EQUIPAMENTO", "Locação/equipamento"
        OUTROS = "OUTROS", "Outros"

    revisao = models.ForeignKey(PropostaRevisao, on_delete=models.CASCADE, related_name="itens")
    ordem = models.PositiveIntegerField(default=0)
    tipo = models.CharField(max_length=25, choices=Tipo.choices)
    descricao = models.CharField(max_length=250)
    quantidade = models.DecimalField(max_digits=15, decimal_places=4, default=Decimal("1"))
    unidade = models.CharField(max_length=20, default="UN")
    fornecedor = models.ForeignKey(Pessoa, on_delete=models.PROTECT, null=True, blank=True, related_name="itens_proposta_fornecidos")
    custo_unitario = models.DecimalField(max_digits=15, decimal_places=4)
    custo_total = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=Decimal("0"))
    plano_conta = models.ForeignKey(PlanoConta, on_delete=models.PROTECT, null=True, blank=True, related_name="itens_proposta")
    observacoes_internas = models.TextField(blank=True)

    class Meta:
        ordering = ["ordem", "id"]

    def clean(self):
        super().clean()
        if self.quantidade <= 0 or self.custo_unitario < 0:
            raise ValidationError("Quantidade deve ser positiva e custo não pode ser negativo.")
        if self.fornecedor_id and self.fornecedor.classificacao not in {Pessoa.Classificacao.FORNECEDOR, Pessoa.Classificacao.AMBOS}:
            raise ValidationError({"fornecedor": "Selecione um fornecedor válido."})
        if self.plano_conta_id and (self.plano_conta.estrutural or not self.plano_conta.aceita_lancamento or self.plano_conta.tipo not in {"CUSTO", "DESPESA"}):
            raise ValidationError({"plano_conta": "Use uma conta analítica de custo ou despesa."})
        self.custo_total = (self.quantidade * self.custo_unitario).quantize(Decimal("0.01"))


class PropostaTributo(ProtegidoPorCongelamento):
    revisao = models.ForeignKey(PropostaRevisao, on_delete=models.CASCADE, related_name="tributos")
    nome = models.CharField(max_length=100)
    percentual = models.DecimalField(max_digits=7, decimal_places=4)

    def clean(self):
        super().clean()
        if self.percentual < 0 or self.percentual >= 100:
            raise ValidationError({"percentual": "Informe um percentual entre 0 e 100."})


class PropostaLinhaPublica(ProtegidoPorCongelamento):
    class Grupo(models.TextChoices):
        MATERIAL = "MATERIAL", "Materiais"
        SERVICO = "SERVICO", "Serviços"

    revisao = models.ForeignKey(PropostaRevisao, on_delete=models.CASCADE, related_name="linhas_publicas")
    ordem = models.PositiveIntegerField(default=0)
    grupo = models.CharField(max_length=10, choices=Grupo.choices)
    descricao = models.CharField(max_length=250)
    quantidade = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    unidade = models.CharField(max_length=20, blank=True)
    valor_unitario = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    valor_total = models.DecimalField(max_digits=15, decimal_places=2)
    observacao = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ["grupo", "ordem", "id"]

    def clean(self):
        super().clean()
        if self.valor_total < 0:
            raise ValidationError({"valor_total": "O valor não pode ser negativo."})


class PropostaHistoricoStatus(models.Model):
    proposta = models.ForeignKey(Proposta, on_delete=models.CASCADE, related_name="historico_status")
    status_anterior = models.CharField(max_length=20, blank=True)
    status_novo = models.CharField(max_length=20, choices=Proposta.Status.choices)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    observacao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
