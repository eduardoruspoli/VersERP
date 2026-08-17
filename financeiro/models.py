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
        return (
            self.movimentacoes_bancarias
            .filter(
                tipo="ENTRADA"
            )
            .aggregate(
                total=Sum("valor")
            )["total"]
            or Decimal("0.00")
        )


    @property
    def total_saidas(self):
        return (
            self.movimentacoes_bancarias
            .filter(
                tipo="SAIDA"
            )
            .aggregate(
                total=Sum("valor")
            )["total"]
            or Decimal("0.00")
        )


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


class TransferenciaBancaria(models.Model):
    STATUS_CHOICES = [
        ("EFETIVADA", "Efetivada"),
        ("CANCELADA", "Cancelada"),
    ]

    conta_origem = models.ForeignKey(
        ContaBancaria,
        on_delete=models.PROTECT,
        related_name="transferencias_enviadas",
        verbose_name="Conta de origem",
    )

    conta_destino = models.ForeignKey(
        ContaBancaria,
        on_delete=models.PROTECT,
        related_name="transferencias_recebidas",
        verbose_name="Conta de destino",
    )

    data = models.DateField(
        "Data da transferência",
    )

    valor = models.DecimalField(
        "Valor",
        max_digits=15,
        decimal_places=2,
    )

    documento = models.CharField(
        "Documento / referência",
        max_length=100,
        blank=True,
    )

    observacoes = models.TextField(
        "Observações",
        blank=True,
    )

    status = models.CharField(
        "Status",
        max_length=10,
        choices=STATUS_CHOICES,
        default="EFETIVADA",
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
        verbose_name = "Transferência bancária"
        verbose_name_plural = "Transferências bancárias"
        ordering = ["-data", "-id"]

    def clean(self):
        super().clean()

        errors = {}

        if (
            self.valor is not None
            and self.valor <= Decimal("0.00")
        ):
            errors["valor"] = (
                "O valor da transferência deve ser maior que zero."
            )

        if (
            self.conta_origem_id
            and self.conta_destino_id
            and self.conta_origem_id == self.conta_destino_id
        ):
            errors["conta_destino"] = (
                "A conta de destino deve ser diferente da conta de origem."
            )

        if (
            self.conta_origem_id
            and self.conta_destino_id
            and self.conta_origem.empresa_id
            != self.conta_destino.empresa_id
        ):
            errors["conta_destino"] = (
                "Nesta etapa, transferências só podem ocorrer entre "
                "contas bancárias da mesma empresa."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

        if self.status == "EFETIVADA":
            MovimentacaoBancaria.objects.update_or_create(
                transferencia=self,
                conta_bancaria=self.conta_origem,
                defaults={
                    "data": self.data,
                    "tipo": "SAIDA",
                    "origem": "TRANSFERENCIA",
                    "descricao": f"Transferência para {self.conta_destino}",
                    "documento": self.documento,
                    "valor": self.valor,
                },
            )
            MovimentacaoBancaria.objects.update_or_create(
                transferencia=self,
                conta_bancaria=self.conta_destino,
                defaults={
                    "data": self.data,
                    "tipo": "ENTRADA",
                    "origem": "TRANSFERENCIA",
                    "descricao": f"Transferência recebida de {self.conta_origem}",
                    "documento": self.documento,
                    "valor": self.valor,
                },
            )
        else:
            self.movimentacoes_bancarias.all().delete()

    @property
    def empresa(self):
        return self.conta_origem.empresa

    def __str__(self):
        return (
            f"{self.data:%d/%m/%Y} - "
            f"{self.conta_origem} → {self.conta_destino} - "
            f"R$ {self.valor}"
        )


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

        lancamento = self.parcela.lancamento
        recebimento = lancamento.tipo == "RECEBER"

        MovimentacaoBancaria.objects.update_or_create(
            baixa_financeira=self,
            defaults={
                "conta_bancaria": self.conta_bancaria,
                "data": self.data,
                "tipo": "ENTRADA" if recebimento else "SAIDA",
                "origem": "RECEBIMENTO" if recebimento else "PAGAMENTO",
                "descricao": lancamento.descricao,
                "documento": lancamento.numero_documento,
                "valor": self.valor_movimento,
            },
        )


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


class MovimentacaoBancaria(models.Model):
    TIPO_CHOICES = [
        ("ENTRADA", "Entrada"),
        ("SAIDA", "Saída"),
    ]

    ORIGEM_CHOICES = [
        ("PAGAMENTO", "Pagamento"),
        ("RECEBIMENTO", "Recebimento"),
        ("TRANSFERENCIA", "Transferência"),
        ("AJUSTE", "Ajuste"),
    ]

    conta_bancaria = models.ForeignKey(
        ContaBancaria,
        on_delete=models.PROTECT,
        related_name="movimentacoes_bancarias",
        verbose_name="Conta bancária",
    )

    data = models.DateField("Data")

    tipo = models.CharField(
        "Tipo",
        max_length=10,
        choices=TIPO_CHOICES,
    )

    origem = models.CharField(
        "Origem",
        max_length=20,
        choices=ORIGEM_CHOICES,
    )

    descricao = models.CharField(
        "Descrição",
        max_length=500,
        blank=True,
    )

    documento = models.CharField(
        "Documento / referência",
        max_length=100,
        blank=True,
    )

    valor = models.DecimalField(
        "Valor",
        max_digits=15,
        decimal_places=2,
    )

    baixa_financeira = models.OneToOneField(
        BaixaFinanceira,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="movimentacao_bancaria",
        verbose_name="Baixa financeira",
    )

    transferencia = models.ForeignKey(
        TransferenciaBancaria,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="movimentacoes_bancarias",
        verbose_name="Transferência bancária",
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
        verbose_name = "Movimentação bancária"
        verbose_name_plural = "Movimentações bancárias"
        ordering = ["-data", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["transferencia", "conta_bancaria"],
                name="unique_movimentacao_transferencia_conta",
            ),
        ]
        indexes = [
            models.Index(
                fields=["conta_bancaria", "data"],
                name="mov_banc_conta_data_idx",
            ),
        ]

    @property
    def valor_assinado(self):
        if self.tipo == "SAIDA":
            return -self.valor
        return self.valor

    def clean(self):
        super().clean()
        errors = {}

        if self.valor is not None and self.valor <= Decimal("0.00"):
            errors["valor"] = "O valor da movimentação deve ser maior que zero."

        if self.baixa_financeira_id and self.transferencia_id:
            errors["transferencia"] = (
                "A movimentação não pode estar vinculada simultaneamente "
                "a uma baixa e a uma transferência."
            )

        if self.baixa_financeira_id:
            baixa = self.baixa_financeira
            lancamento = baixa.parcela.lancamento

            if (
                self.conta_bancaria_id
                and self.conta_bancaria_id != baixa.conta_bancaria_id
            ):
                errors["conta_bancaria"] = (
                    "A conta deve ser a mesma da baixa financeira."
                )

            tipo_esperado = (
                "ENTRADA" if lancamento.tipo == "RECEBER" else "SAIDA"
            )
            origem_esperada = (
                "RECEBIMENTO" if lancamento.tipo == "RECEBER" else "PAGAMENTO"
            )

            if self.tipo != tipo_esperado:
                errors["tipo"] = "O tipo não corresponde à baixa financeira."

            if self.origem != origem_esperada:
                errors["origem"] = "A origem não corresponde à baixa financeira."

        if self.transferencia_id and self.conta_bancaria_id:
            transferencia = self.transferencia

            if transferencia.status != "EFETIVADA":
                errors["transferencia"] = (
                    "Não é possível movimentar uma transferência cancelada."
                )
            elif self.conta_bancaria_id == transferencia.conta_origem_id:
                if self.tipo != "SAIDA":
                    errors["tipo"] = (
                        "A conta de origem deve registrar uma saída."
                    )
            elif self.conta_bancaria_id == transferencia.conta_destino_id:
                if self.tipo != "ENTRADA":
                    errors["tipo"] = (
                        "A conta de destino deve registrar uma entrada."
                    )
            else:
                errors["conta_bancaria"] = (
                    "A conta não pertence à transferência."
                )

            if self.origem != "TRANSFERENCIA":
                errors["origem"] = (
                    "Movimentação vinculada a transferência deve ter "
                    "origem Transferência."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        sinal = "-" if self.tipo == "SAIDA" else "+"
        return (
            f"{self.data:%d/%m/%Y} - {self.conta_bancaria} - "
            f"{sinal} R$ {self.valor} - {self.descricao}"
        )

class ImportacaoOFX(models.Model):
    STATUS_CHOICES = [
        ("PROCESSANDO", "Processando"),
        ("CONCLUIDA", "Concluída"),
        ("ERRO", "Erro"),
    ]

    conta_bancaria = models.ForeignKey(
        ContaBancaria,
        on_delete=models.PROTECT,
        related_name="importacoes_ofx",
        verbose_name="Conta bancária",
    )

    nome_arquivo = models.CharField(
        "Nome do arquivo",
        max_length=255,
    )

    data_inicio = models.DateField(
        "Data inicial do extrato",
        null=True,
        blank=True,
    )

    data_fim = models.DateField(
        "Data final do extrato",
        null=True,
        blank=True,
    )

    status = models.CharField(
        "Status",
        max_length=20,
        choices=STATUS_CHOICES,
        default="PROCESSANDO",
    )

    mensagem_erro = models.TextField(
        "Mensagem de erro",
        blank=True,
    )

    criado_em = models.DateTimeField(
        "Importado em",
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "Importação OFX"
        verbose_name_plural = "Importações OFX"
        ordering = ["-criado_em", "-id"]

    @property
    def total_movimentos(self):
        return self.movimentos.count()

    @property
    def total_conciliados(self):
        return self.movimentos.filter(
            status="CONCILIADO"
        ).count()

    @property
    def total_pendentes(self):
        return self.movimentos.filter(
            status="PENDENTE"
        ).count()

    def __str__(self):
        return (
            f"{self.conta_bancaria} - "
            f"{self.nome_arquivo}"
        )


class MovimentoOFX(models.Model):
    TIPO_CHOICES = [
        ("ENTRADA", "Entrada"),
        ("SAIDA", "Saída"),
    ]

    STATUS_CHOICES = [
        ("PENDENTE", "Pendente"),
        ("CONCILIADO", "Conciliado"),
        ("IGNORADO", "Ignorado"),
    ]

    importacao = models.ForeignKey(
        ImportacaoOFX,
        on_delete=models.CASCADE,
        related_name="movimentos",
        verbose_name="Importação",
    )

    conta_bancaria = models.ForeignKey(
        ContaBancaria,
        on_delete=models.PROTECT,
        related_name="movimentos_ofx",
        verbose_name="Conta bancária",
    )

    identificador = models.CharField(
        "Identificador da transação",
        max_length=255,
    )

    data = models.DateField(
        "Data",
    )

    tipo = models.CharField(
        "Tipo",
        max_length=10,
        choices=TIPO_CHOICES,
    )

    valor = models.DecimalField(
        "Valor",
        max_digits=15,
        decimal_places=2,
    )

    descricao = models.CharField(
        "Descrição",
        max_length=500,
        blank=True,
    )

    documento = models.CharField(
        "Documento / referência",
        max_length=100,
        blank=True,
    )

    status = models.CharField(
        "Status",
        max_length=15,
        choices=STATUS_CHOICES,
        default="PENDENTE",
    )

    baixa_conciliada = models.ForeignKey(
        BaixaFinanceira,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimentos_ofx_conciliados",
        verbose_name="Baixa conciliada",
    )

    transferencia_conciliada = models.ForeignKey(
        TransferenciaBancaria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimentos_ofx_conciliados",
        verbose_name="Transferência conciliada",
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
        verbose_name = "Movimento OFX"
        verbose_name_plural = "Movimentos OFX"
        ordering = ["-data", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "conta_bancaria",
                    "identificador",
                ],
                name=(
                    "unique_movimento_ofx_"
                    "por_conta"
                ),
            ),
        ]

    @property
    def valor_assinado(self):
        if self.tipo == "SAIDA":
            return -self.valor

        return self.valor

    def clean(self):
        super().clean()

        errors = {}

        if (
            self.valor is not None
            and self.valor <= Decimal("0.00")
        ):
            errors["valor"] = (
                "O valor do movimento deve "
                "ser maior que zero."
            )

        if (
            self.importacao_id
            and self.conta_bancaria_id
            and self.importacao.conta_bancaria_id
            != self.conta_bancaria_id
        ):
            errors["conta_bancaria"] = (
                "A conta bancária do movimento "
                "deve ser a mesma da importação."
            )

        if (
            self.baixa_conciliada_id
            and self.conta_bancaria_id
            and self.baixa_conciliada.conta_bancaria_id
            != self.conta_bancaria_id
        ):
            errors["baixa_conciliada"] = (
                "A baixa conciliada deve pertencer "
                "à mesma conta bancária do extrato."
            )

        if (
            self.baixa_conciliada_id
            and self.transferencia_conciliada_id
        ):
            errors["transferencia_conciliada"] = (
                "O movimento OFX não pode estar conciliado "
                "simultaneamente com uma baixa e uma transferência."
            )

        if (
            self.transferencia_conciliada_id
            and self.conta_bancaria_id
        ):
            transferencia = self.transferencia_conciliada

            if transferencia.status != "EFETIVADA":
                errors["transferencia_conciliada"] = (
                    "Não é possível conciliar uma transferência cancelada."
                )

            elif (
                self.conta_bancaria_id
                == transferencia.conta_origem_id
            ):
                if self.tipo != "SAIDA":
                    errors["transferencia_conciliada"] = (
                        "Na conta de origem, a transferência deve "
                        "corresponder a uma saída no extrato."
                    )

            elif (
                self.conta_bancaria_id
                == transferencia.conta_destino_id
            ):
                if self.tipo != "ENTRADA":
                    errors["transferencia_conciliada"] = (
                        "Na conta de destino, a transferência deve "
                        "corresponder a uma entrada no extrato."
                    )

            else:
                errors["transferencia_conciliada"] = (
                    "A transferência não pertence à conta bancária "
                    "deste movimento OFX."
                )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        sinal = (
            "-"
            if self.tipo == "SAIDA"
            else "+"
        )

        return (
            f"{self.data:%d/%m/%Y} - "
            f"{sinal} R$ {self.valor} - "
            f"{self.descricao}"
        )