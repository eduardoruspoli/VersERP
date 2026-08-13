from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum


class Empresa(models.Model):
    razao_social = models.CharField(
        "Razão social",
        max_length=200,
    )

    nome_fantasia = models.CharField(
        "Nome fantasia",
        max_length=200,
        blank=True,
    )

    cnpj = models.CharField(
        "CNPJ",
        max_length=18,
        unique=True,
    )

    inscricao_estadual = models.CharField(
        "Inscrição estadual",
        max_length=20,
        blank=True,
    )

    inscricao_municipal = models.CharField(
        "Inscrição municipal",
        max_length=20,
        blank=True,
    )

    email = models.EmailField(
        "E-mail",
        blank=True,
    )

    telefone = models.CharField(
        "Telefone",
        max_length=20,
        blank=True,
    )

    ativa = models.BooleanField(
        "Ativa",
        default=True,
    )

    principal = models.BooleanField(
        "Empresa principal",
        default=False,
    )

    criado_em = models.DateTimeField(
        "Criado em",
        auto_now_add=True,
    )

    atualizado_em = models.DateTimeField(
        "Atualizado em",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        ordering = ["razao_social"]

    def __str__(self):
        return self.nome_fantasia or self.razao_social


class ContaBancaria(models.Model):
    TIPO_CHOICES = [
        ("CORRENTE", "Conta corrente"),
        ("POUPANCA", "Poupança"),
        ("PAGAMENTO", "Conta de pagamento"),
        ("CAIXA", "Caixa"),
    ]

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="contas_bancarias",
        verbose_name="Empresa",
    )

    banco = models.CharField(
        "Banco",
        max_length=100,
    )

    codigo_banco = models.CharField(
        "Código do banco",
        max_length=10,
        blank=True,
    )

    agencia = models.CharField(
        "Agência",
        max_length=20,
        blank=True,
    )

    conta = models.CharField(
        "Conta",
        max_length=30,
        blank=True,
    )

    tipo = models.CharField(
        "Tipo de conta",
        max_length=20,
        choices=TIPO_CHOICES,
        default="CORRENTE",
    )

    descricao = models.CharField(
        "Descrição",
        max_length=100,
        blank=True,
    )

    saldo_inicial = models.DecimalField(
        "Saldo inicial",
        max_digits=15,
        decimal_places=2,
        default=0,
    )

    data_saldo_inicial = models.DateField(
        "Data do saldo inicial",
        null=True,
        blank=True,
    )

    ativa = models.BooleanField(
        "Ativa",
        default=True,
    )

    criado_em = models.DateTimeField(
        "Criado em",
        auto_now_add=True,
    )

    atualizado_em = models.DateTimeField(
        "Atualizado em",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Conta bancária"
        verbose_name_plural = "Contas bancárias"
        ordering = ["empresa", "banco", "agencia", "conta"]

    @property
    def total_entradas(self):
        total = Decimal("0.00")

        baixas = self.baixas_financeiras.select_related(
            "parcela__lancamento"
        )

        for baixa in baixas:
            if baixa.parcela.lancamento.tipo == "RECEBER":
                total += baixa.valor_movimento

        return total


    @property
    def total_saidas(self):
        total = Decimal("0.00")

        baixas = self.baixas_financeiras.select_related(
            "parcela__lancamento"
        )

        for baixa in baixas:
            if baixa.parcela.lancamento.tipo == "PAGAR":
                total += baixa.valor_movimento

        return total


    @property
    def saldo_atual(self):
        return (
            self.saldo_inicial
            + self.total_entradas
            - self.total_saidas
        )

    def __str__(self):
        partes = [self.banco]

        if self.agencia:
            partes.append(f"Ag. {self.agencia}")

        if self.conta:
            partes.append(f"Conta {self.conta}")

        return " - ".join(partes)

class PlanoConta(models.Model):
    TIPO_CHOICES = [
        ("RECEITA", "Receita"),
        ("DESPESA", "Despesa"),
    ]

    codigo = models.CharField(
        "Código",
        max_length=20,
        unique=True,
    )

    nome = models.CharField(
        "Nome",
        max_length=150,
    )

    tipo = models.CharField(
        "Tipo",
        max_length=10,
        choices=TIPO_CHOICES,
    )

    conta_pai = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="subcontas",
        verbose_name="Conta superior",
    )

    aceita_lancamento = models.BooleanField(
        "Aceita lançamento",
        default=True,
    )

    ativo = models.BooleanField(
        "Ativo",
        default=True,
    )

    criado_em = models.DateTimeField(
        "Criado em",
        auto_now_add=True,
    )

    atualizado_em = models.DateTimeField(
        "Atualizado em",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Conta do plano de contas"
        verbose_name_plural = "Plano de contas"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.nome}"


class CentroCusto(models.Model):
    codigo = models.CharField(
        "Código",
        max_length=30,
        unique=True,
    )

    nome = models.CharField(
        "Nome",
        max_length=150,
    )

    descricao = models.TextField(
        "Descrição",
        blank=True,
    )

    ativo = models.BooleanField(
        "Ativo",
        default=True,
    )

    criado_em = models.DateTimeField(
        "Criado em",
        auto_now_add=True,
    )

    atualizado_em = models.DateTimeField(
        "Atualizado em",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Centro de custo"
        verbose_name_plural = "Centros de custo"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.nome}"


class LancamentoFinanceiro(models.Model):
    TIPO_CHOICES = [
        ("PAGAR", "Conta a pagar"),
        ("RECEBER", "Conta a receber"),
    ]

    ORIGEM_CHOICES = [
        ("MANUAL", "Manual"),
        ("FISCAL", "Documento fiscal"),
        ("COMERCIAL", "Comercial"),
        ("CONCILIACAO", "Conciliação bancária"),
    ]

    STATUS_CHOICES = [
        ("ABERTO", "Em aberto"),
        ("PARCIAL", "Parcialmente liquidado"),
        ("LIQUIDADO", "Liquidado"),
        ("CANCELADO", "Cancelado"),
    ]

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="lancamentos_financeiros",
        verbose_name="Empresa",
    )

    pessoa = models.ForeignKey(
        "pessoas.Pessoa",
        on_delete=models.PROTECT,
        related_name="lancamentos_financeiros",
        verbose_name="Cliente / Fornecedor",
    )

    tipo = models.CharField(
        "Tipo",
        max_length=10,
        choices=TIPO_CHOICES,
    )

    origem = models.CharField(
        "Origem",
        max_length=15,
        choices=ORIGEM_CHOICES,
        default="MANUAL",
    )

    descricao = models.CharField(
        "Descrição",
        max_length=250,
    )

    numero_documento = models.CharField(
        "Número do documento",
        max_length=50,
        blank=True,
    )

    data_emissao = models.DateField(
        "Data de emissão",
        null=True,
        blank=True,
    )

    data_competencia = models.DateField(
        "Data de competência",
        null=True,
        blank=True,
    )

    valor_total = models.DecimalField(
        "Valor total",
        max_digits=15,
        decimal_places=2,
    )

    plano_conta = models.ForeignKey(
        PlanoConta,
        on_delete=models.PROTECT,
        related_name="lancamentos",
        verbose_name="Plano de contas",
    )

    status = models.CharField(
        "Status",
        max_length=15,
        choices=STATUS_CHOICES,
        default="ABERTO",
    )

    observacoes = models.TextField(
        "Observações",
        blank=True,
    )

    criado_em = models.DateTimeField(
        "Criado em",
        auto_now_add=True,
    )

    atualizado_em = models.DateTimeField(
        "Atualizado em",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Lançamento financeiro"
        verbose_name_plural = "Lançamentos financeiros"
        ordering = ["-data_emissao", "-id"]

    def clean(self):
        super().clean()

        errors = {}

        if self.valor_total is not None and self.valor_total <= Decimal("0.00"):
            errors["valor_total"] = "O valor total deve ser maior que zero."

        if self.plano_conta_id:
            if not self.plano_conta.ativo:
                errors["plano_conta"] = (
                    "Não é possível utilizar uma conta inativa do plano de contas."
                )

            elif not self.plano_conta.aceita_lancamento:
                errors["plano_conta"] = (
                    "Esta conta do plano de contas não aceita lançamentos."
                )

            elif (
                self.tipo == "PAGAR"
                and self.plano_conta.tipo != "DESPESA"
            ):
                errors["plano_conta"] = (
                    "Uma conta a pagar deve utilizar uma conta de despesa."
                )

            elif (
                self.tipo == "RECEBER"
                and self.plano_conta.tipo != "RECEITA"
            ):
                errors["plano_conta"] = (
                    "Uma conta a receber deve utilizar uma conta de receita."
                )

        if errors:
            raise ValidationError(errors)

    def atualizar_status(self):
        if self.status == "CANCELADO":
            return

        parcelas = self.parcelas.all()

        if not parcelas.exists():
            novo_status = "ABERTO"

        elif parcelas.filter(status="PARCIAL").exists():
            novo_status = "PARCIAL"

        elif parcelas.filter(status="ABERTA").exists():
            if parcelas.filter(status="LIQUIDADA").exists():
                novo_status = "PARCIAL"
            else:
                novo_status = "ABERTO"

        elif parcelas.exclude(
            status__in=["LIQUIDADA", "CANCELADA"]
        ).exists():
            novo_status = "PARCIAL"

        else:
            novo_status = "LIQUIDADO"

        if self.status != novo_status:
            LancamentoFinanceiro.objects.filter(
                pk=self.pk
            ).update(status=novo_status)

            self.status = novo_status    

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.descricao}"


class RateioCentroCusto(models.Model):
    lancamento = models.ForeignKey(
        LancamentoFinanceiro,
        on_delete=models.CASCADE,
        related_name="rateios_centro_custo",
        verbose_name="Lançamento",
    )

    centro_custo = models.ForeignKey(
        CentroCusto,
        on_delete=models.PROTECT,
        related_name="rateios_financeiros",
        verbose_name="Centro de custo",
    )

    valor = models.DecimalField(
        "Valor",
        max_digits=15,
        decimal_places=2,
    )

    criado_em = models.DateTimeField(
        "Criado em",
        auto_now_add=True,
    )

    atualizado_em = models.DateTimeField(
        "Atualizado em",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Rateio por centro de custo"
        verbose_name_plural = "Rateios por centro de custo"
        ordering = ["centro_custo"]
        constraints = [
            models.UniqueConstraint(
                fields=["lancamento", "centro_custo"],
                name="unique_centro_custo_por_lancamento",
            ),
        ]

    def clean(self):
        super().clean()

        if self.valor is not None and self.valor <= Decimal("0.00"):
            raise ValidationError({
                "valor": "O valor do rateio deve ser maior que zero."
            })

        if self.centro_custo_id and not self.centro_custo.ativo:
            raise ValidationError({
                "centro_custo": (
                    "Não é possível utilizar um centro de custo inativo."
                )
            })

    def __str__(self):
        return (
            f"{self.lancamento} - "
            f"{self.centro_custo} - "
            f"R$ {self.valor}"
        )


class ParcelaFinanceira(models.Model):
    STATUS_CHOICES = [
        ("ABERTA", "Em aberto"),
        ("PARCIAL", "Parcialmente liquidada"),
        ("LIQUIDADA", "Liquidada"),
        ("CANCELADA", "Cancelada"),
    ]

    lancamento = models.ForeignKey(
        LancamentoFinanceiro,
        on_delete=models.PROTECT,
        related_name="parcelas",
        verbose_name="Lançamento",
    )

    numero = models.PositiveIntegerField(
        "Número da parcela",
    )

    vencimento = models.DateField(
        "Vencimento",
    )

    valor = models.DecimalField(
        "Valor",
        max_digits=15,
        decimal_places=2,
    )

    status = models.CharField(
        "Status",
        max_length=15,
        choices=STATUS_CHOICES,
        default="ABERTA",
    )

    observacoes = models.TextField(
        "Observações",
        blank=True,
    )

    criado_em = models.DateTimeField(
        "Criado em",
        auto_now_add=True,
    )

    atualizado_em = models.DateTimeField(
        "Atualizado em",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Parcela financeira"
        verbose_name_plural = "Parcelas financeiras"
        ordering = ["vencimento", "numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["lancamento", "numero"],
                name="unique_parcela_por_lancamento",
            ),
        ]

    def clean(self):
        super().clean()

        if self.valor is not None and self.valor <= Decimal("0.00"):
            raise ValidationError({
                "valor": "O valor da parcela deve ser maior que zero."
            })


    @property
    def total_baixado(self):
        return (
            self.baixas.aggregate(total=Sum("valor"))["total"]
            or Decimal("0.00")
        )


    @property
    def saldo(self):
        return self.valor - self.total_baixado


    def atualizar_status(self):
        if self.status == "CANCELADA":
            return

        total_baixado = self.total_baixado

        if total_baixado <= Decimal("0.00"):
            novo_status = "ABERTA"

        elif total_baixado < self.valor:
            novo_status = "PARCIAL"

        else:
            novo_status = "LIQUIDADA"

        if self.status != novo_status:
            ParcelaFinanceira.objects.filter(
                pk=self.pk
            ).update(status=novo_status)

            self.status = novo_status

    def __str__(self):
        return (
            f"{self.lancamento} - "
            f"Parcela {self.numero}"
        )


class BaixaFinanceira(models.Model):
    parcela = models.ForeignKey(
        ParcelaFinanceira,
        on_delete=models.PROTECT,
        related_name="baixas",
        verbose_name="Parcela",
    )

    conta_bancaria = models.ForeignKey(
        ContaBancaria,
        on_delete=models.PROTECT,
        related_name="baixas_financeiras",
        verbose_name="Conta bancária",
    )

    data = models.DateField(
        "Data da baixa",
    )

    valor = models.DecimalField(
        "Valor",
        max_digits=15,
        decimal_places=2,
    )

    juros = models.DecimalField(
        "Juros",
        max_digits=15,
        decimal_places=2,
        default=0,
    )

    multa = models.DecimalField(
        "Multa",
        max_digits=15,
        decimal_places=2,
        default=0,
    )

    desconto = models.DecimalField(
        "Desconto",
        max_digits=15,
        decimal_places=2,
        default=0,
    )

    observacoes = models.TextField(
        "Observações",
        blank=True,
    )

    criado_em = models.DateTimeField(
        "Criado em",
        auto_now_add=True,
    )

    atualizado_em = models.DateTimeField(
        "Atualizado em",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Baixa financeira"
        verbose_name_plural = "Baixas financeiras"
        ordering = ["-data", "-id"]

    def clean(self):
        super().clean()

        errors = {}

        for campo in ("valor", "juros", "multa", "desconto"):
            valor = getattr(self, campo)

            if valor is not None and valor < Decimal("0.00"):
                errors[campo] = "O valor não pode ser negativo."

        if self.valor is not None and self.valor <= Decimal("0.00"):
            errors["valor"] = "O valor da baixa deve ser maior que zero."

        if (
            self.parcela_id
            and self.conta_bancaria_id
            and self.parcela.lancamento.empresa_id
            != self.conta_bancaria.empresa_id
        ):
            errors["conta_bancaria"] = (
                "A conta bancária deve pertencer à mesma empresa "
                "do lançamento financeiro."
            )

        if self.parcela_id and self.valor is not None:
            outras_baixas = self.parcela.baixas.all()

            if self.pk:
                outras_baixas = outras_baixas.exclude(pk=self.pk)

            total_outras_baixas = (
                outras_baixas.aggregate(total=Sum("valor"))["total"]
                or Decimal("0.00")
            )

            saldo_disponivel = (
                self.parcela.valor - total_outras_baixas
            )

            if self.valor > saldo_disponivel:
                errors["valor"] = (
                    f"O valor da baixa não pode ultrapassar "
                    f"o saldo da parcela de R$ {saldo_disponivel:.2f}."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()

        super().save(*args, **kwargs)

        self.parcela.atualizar_status()
        self.parcela.lancamento.atualizar_status()


    @property
    def valor_movimento(self):
        return (
            self.valor
            + self.juros
            + self.multa
            - self.desconto
    )

    def __str__(self):
        return (
            f"{self.parcela} - "
            f"R$ {self.valor}"
        )