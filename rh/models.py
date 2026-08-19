from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from financeiro.models import Empresa
from pessoas.models import Pessoa


class Funcionario(models.Model):
    class Situacao(models.TextChoices):
        ATIVO = "ATIVO", "Ativo"
        AFASTADO = "AFASTADO", "Afastado"
        FERIAS = "FERIAS", "Férias"
        DESLIGADO = "DESLIGADO", "Desligado"

    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="funcionarios")
    pessoa = models.ForeignKey(Pessoa, on_delete=models.PROTECT, related_name="vinculos_funcionais")
    matricula = models.CharField(max_length=30, blank=True)
    nome_apresentacao = models.CharField(max_length=200, blank=True)
    cargo_atual = models.CharField(max_length=120)
    data_admissao = models.DateField()
    data_desligamento = models.DateField(null=True, blank=True)
    situacao = models.CharField(max_length=15, choices=Situacao.choices, default=Situacao.ATIVO)
    banco = models.CharField(max_length=100, blank=True)
    agencia = models.CharField(max_length=20, blank=True)
    conta = models.CharField(max_length=30, blank=True)
    chave_pix = models.CharField(max_length=150, blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["pessoa__razao_social"]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "pessoa"], name="uq_funcionario_empresa_pessoa"),
            models.UniqueConstraint(fields=["empresa", "matricula"], condition=~models.Q(matricula=""), name="uq_funcionario_empresa_matricula"),
        ]
        permissions = [
            ("view_rh", "Pode acessar o RH"),
            ("view_remuneracao", "Pode visualizar remuneração"),
            ("change_remuneracao", "Pode alterar remuneração"),
            ("ajustar_ponto", "Pode lançar e ajustar ponto"),
            ("fechar_ponto", "Pode fechar competência de ponto"),
            ("reabrir_ponto", "Pode reabrir competência de ponto"),
            ("lancar_evento_folha", "Pode lançar eventos de folha"),
            ("fechar_folha_gerencial", "Pode fechar folha gerencial"),
            ("registrar_retorno_contabilidade", "Pode registrar retorno da contabilidade"),
            ("conferir_folha", "Pode conferir folha"),
            ("view_dados_bancarios", "Pode visualizar dados bancários de funcionário"),
        ]

    def clean(self):
        if self.data_desligamento and self.data_desligamento < self.data_admissao:
            raise ValidationError({"data_desligamento": "O desligamento não pode ser anterior à admissão."})
        if self.situacao == self.Situacao.DESLIGADO and not self.data_desligamento:
            raise ValidationError({"data_desligamento": "Informe a data de desligamento."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def nome(self):
        return self.nome_apresentacao or self.pessoa.razao_social

    def __str__(self):
        return self.nome


class ContratoFuncionario(models.Model):
    funcionario = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name="contratos")
    inicio_vigencia = models.DateField()
    fim_vigencia = models.DateField(null=True, blank=True)
    salario_base = models.DecimalField(max_digits=15, decimal_places=2)
    divisor_salarial = models.PositiveIntegerField(default=220)
    carga_semanal_minutos = models.PositiveIntegerField(default=2640)
    cargo = models.CharField(max_length=120, blank=True)
    observacao = models.TextField(blank=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-inicio_vigencia"]

    def clean(self):
        if self.salario_base <= 0 or self.divisor_salarial <= 0:
            raise ValidationError("Salário e divisor devem ser positivos.")
        if self.fim_vigencia and self.fim_vigencia < self.inicio_vigencia:
            raise ValidationError({"fim_vigencia": "Fim anterior ao início da vigência."})
        if self.funcionario_id:
            conflito = type(self).objects.filter(funcionario=self.funcionario).exclude(pk=self.pk).filter(
                models.Q(fim_vigencia__isnull=True) | models.Q(fim_vigencia__gte=self.inicio_vigencia)
            )
            if self.fim_vigencia:
                conflito = conflito.filter(inicio_vigencia__lte=self.fim_vigencia)
            if conflito.exists():
                raise ValidationError("Existe outra condição contratual sobreposta a esta vigência.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def valor_hora(self):
        return (self.salario_base / Decimal(self.divisor_salarial)).quantize(Decimal("0.0001"))


class Jornada(models.Model):
    funcionario = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name="jornadas")
    nome = models.CharField(max_length=100, default="Jornada padrão")
    inicio_vigencia = models.DateField()
    fim_vigencia = models.DateField(null=True, blank=True)
    observacao = models.TextField(blank=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-inicio_vigencia"]

    def clean(self):
        if self.fim_vigencia and self.fim_vigencia < self.inicio_vigencia:
            raise ValidationError({"fim_vigencia": "Fim anterior ao início."})
        if self.funcionario_id:
            conflito = type(self).objects.filter(funcionario=self.funcionario).exclude(pk=self.pk).filter(
                models.Q(fim_vigencia__isnull=True) | models.Q(fim_vigencia__gte=self.inicio_vigencia)
            )
            if self.fim_vigencia:
                conflito = conflito.filter(inicio_vigencia__lte=self.fim_vigencia)
            if conflito.exists():
                raise ValidationError("Existe outra jornada sobreposta a esta vigência.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class JornadaDia(models.Model):
    jornada = models.ForeignKey(Jornada, on_delete=models.CASCADE, related_name="dias")
    dia_semana = models.PositiveSmallIntegerField(choices=[(0,"Segunda"),(1,"Terça"),(2,"Quarta"),(3,"Quinta"),(4,"Sexta"),(5,"Sábado"),(6,"Domingo")])
    trabalha = models.BooleanField(default=True)
    entrada = models.TimeField(null=True, blank=True)
    saida_intervalo = models.TimeField(null=True, blank=True)
    retorno_intervalo = models.TimeField(null=True, blank=True)
    saida = models.TimeField(null=True, blank=True)
    minutos_previstos = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["dia_semana"]
        constraints = [models.UniqueConstraint(fields=["jornada", "dia_semana"], name="uq_jornada_dia")]

    def clean(self):
        if self.trabalha and self.minutos_previstos <= 0:
            raise ValidationError({"minutos_previstos": "Informe a carga diária em minutos."})


class Feriado(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="feriados_rh")
    data = models.DateField()
    nome = models.CharField(max_length=150)
    localidade = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["data"]
        constraints = [models.UniqueConstraint(fields=["empresa", "data"], name="uq_feriado_empresa_data")]


class CompetenciaPonto(models.Model):
    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        APURADO = "APURADO", "Apurado"
        FECHADO = "FECHADO", "Fechado"
        REABERTO = "REABERTO", "Reaberto"

    funcionario = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name="competencias_ponto")
    competencia = models.DateField(help_text="Primeiro dia do mês")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RASCUNHO)
    saldo_anterior_minutos = models.IntegerField(default=0)
    creditos_minutos = models.PositiveIntegerField(default=0)
    debitos_minutos = models.PositiveIntegerField(default=0)
    ajustes_minutos = models.IntegerField(default=0)
    saldo_final_minutos = models.IntegerField(default=0)
    horas_100_minutos = models.PositiveIntegerField(default=0)
    observacoes = models.TextField(blank=True)
    fechado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="competencias_rh_fechadas")
    fechado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-competencia", "funcionario"]
        constraints = [models.UniqueConstraint(fields=["funcionario", "competencia"], name="uq_competencia_funcionario_mes")]

    def clean(self):
        if self.competencia and self.competencia.day != 1:
            raise ValidationError({"competencia": "Use o primeiro dia do mês para identificar a competência."})

    def save(self,*args,**kwargs): self.full_clean(); return super().save(*args,**kwargs)


class MarcacaoPonto(models.Model):
    class Origem(models.TextChoices):
        RELOGIO = "RELOGIO", "Relógio"
        MANUAL = "MANUAL", "Manual"
        IMPORTADO = "IMPORTADO", "Importado"
        PRE_ASSINALADO = "PRE_ASSINALADO", "Pré-assinalado"

    funcionario = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name="marcacoes")
    data = models.DateField()
    horario = models.TimeField()
    origem = models.CharField(max_length=15, choices=Origem.choices)
    observacao = models.TextField(blank=True)
    ativa = models.BooleanField(default=True)
    substitui = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="correcoes")
    usuario_responsavel = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["data", "horario", "id"]

    def clean(self):
        if self.substitui_id and self.substitui.funcionario_id != self.funcionario_id:
            raise ValidationError({"substitui": "A marcação corrigida deve pertencer ao mesmo funcionário."})
        if self.funcionario_id and self.data and CompetenciaPonto.objects.filter(funcionario=self.funcionario,competencia=self.data.replace(day=1),status=CompetenciaPonto.Status.FECHADO).exists():
            raise ValidationError("Não é possível alterar marcações de uma competência fechada.")

    def save(self,*args,**kwargs): self.full_clean(); return super().save(*args,**kwargs)


class OcorrenciaPonto(models.Model):
    class Tipo(models.TextChoices):
        FALTA = "FALTA", "Falta"
        ATESTADO = "ATESTADO", "Atestado"
        AFASTAMENTO = "AFASTAMENTO", "Afastamento"
        ABONO = "ABONO", "Abono"
        ATRASO_JUSTIFICADO = "ATRASO_JUSTIFICADO", "Atraso justificado"
        AJUSTE_PONTO = "AJUSTE_PONTO", "Ajuste de ponto"
        OUTRO = "OUTRO", "Outro"

    funcionario = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name="ocorrencias_ponto")
    data_inicio = models.DateField()
    data_fim = models.DateField(null=True, blank=True)
    tipo = models.CharField(max_length=22, choices=Tipo.choices)
    descricao = models.CharField(max_length=200)
    observacao = models.TextField(blank=True)
    minutos_abonados = models.PositiveIntegerField(default=0)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.data_fim and self.data_fim < self.data_inicio:
            raise ValidationError({"data_fim": "Fim anterior ao início."})

    def save(self,*args,**kwargs): self.full_clean(); return super().save(*args,**kwargs)


class ApuracaoDiaria(models.Model):
    competencia = models.ForeignKey(CompetenciaPonto, on_delete=models.CASCADE, related_name="apuracoes")
    data = models.DateField()
    minutos_previstos = models.PositiveIntegerField(default=0)
    minutos_trabalhados = models.PositiveIntegerField(default=0)
    credito_bh_minutos = models.PositiveIntegerField(default=0)
    debito_bh_minutos = models.PositiveIntegerField(default=0)
    horas_100_minutos = models.PositiveIntegerField(default=0)
    adicional_noturno_minutos = models.PositiveIntegerField(default=0)
    falta = models.BooleanField(default=False)
    abonado = models.BooleanField(default=False)
    observacoes = models.TextField(blank=True)

    class Meta:
        ordering = ["data"]
        constraints = [models.UniqueConstraint(fields=["competencia", "data"], name="uq_apuracao_competencia_data")]


class HistoricoRH(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="historicos_rh")
    funcionario = models.ForeignKey(Funcionario, on_delete=models.PROTECT, null=True, blank=True, related_name="historicos")
    tipo = models.CharField(max_length=50)
    referencia = models.CharField(max_length=100, blank=True)
    descricao = models.TextField()
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]


class EventoFolha(models.Model):
    class Natureza(models.TextChoices):
        PROVENTO = "PROVENTO", "Provento"
        DESCONTO = "DESCONTO", "Desconto"
        INFORMATIVO = "INFORMATIVO", "Informativo"
    class Unidade(models.TextChoices):
        VALOR = "VALOR", "Valor"
        HORAS = "HORAS", "Horas"
        DIAS = "DIAS", "Dias"
        OUTRO = "OUTRO", "Outro"
    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        CONFERIDO = "CONFERIDO", "Conferido"
        CANCELADO = "CANCELADO", "Cancelado"

    TIPOS = [(x, x.replace("_", " ").title()) for x in ("ADIANTAMENTO", "FALTA", "ATESTADO", "BENEFICIO", "PREMIO", "ABONO", "ADICIONAL_NOTURNO", "HORA_100", "DESCONTO_BH", "VALE_TRANSPORTE", "OUTROS")]
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="eventos_folha")
    funcionario = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name="eventos_folha")
    competencia = models.DateField()
    data_evento = models.DateField(null=True, blank=True)
    tipo = models.CharField(max_length=30, choices=TIPOS)
    descricao = models.CharField(max_length=200)
    natureza = models.CharField(max_length=12, choices=Natureza.choices)
    quantidade = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    unidade = models.CharField(max_length=10, choices=Unidade.choices, default=Unidade.VALOR)
    valor = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0"))
    origem = models.CharField(max_length=30, default="MANUAL")
    chave_origem = models.CharField(max_length=100, blank=True)
    observacao = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDENTE)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-competencia", "funcionario", "tipo"]
        constraints = [models.UniqueConstraint(fields=["empresa", "chave_origem"], condition=~models.Q(chave_origem=""), name="uq_evento_empresa_chave_origem")]

    def clean(self):
        if self.funcionario_id and self.empresa_id != self.funcionario.empresa_id:
            raise ValidationError("Empresa e funcionário do evento são incompatíveis.")

    def save(self,*args,**kwargs): self.full_clean(); return super().save(*args,**kwargs)


class ValeAdiantamento(models.Model):
    class Status(models.TextChoices):
        ATIVO = "ATIVO", "Ativo"
        QUITADO = "QUITADO", "Quitado"
        CANCELADO = "CANCELADO", "Cancelado"
    funcionario = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name="vales")
    data = models.DateField()
    descricao = models.CharField(max_length=200)
    valor_total = models.DecimalField(max_digits=15, decimal_places=2)
    quantidade_parcelas = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ATIVO)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.valor_total <= 0 or self.quantidade_parcelas <= 0:
            raise ValidationError("Valor e quantidade de parcelas devem ser positivos.")

    def save(self,*args,**kwargs): self.full_clean(); return super().save(*args,**kwargs)

    @property
    def saldo(self):
        return sum((p.valor for p in self.parcelas.exclude(status=ValeParcela.Status.DESCONTADA)), Decimal("0.00"))


class ValeParcela(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        DESCONTADA = "DESCONTADA", "Descontada"
        CANCELADA = "CANCELADA", "Cancelada"
    vale = models.ForeignKey(ValeAdiantamento, on_delete=models.CASCADE, related_name="parcelas")
    numero = models.PositiveIntegerField()
    competencia = models.DateField()
    valor = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDENTE)

    class Meta:
        ordering = ["numero"]
        constraints = [models.UniqueConstraint(fields=["vale", "numero"], name="uq_vale_numero_parcela")]


class RetornoContabilidade(models.Model):
    funcionario = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name="retornos_contabilidade")
    competencia = models.DateField()
    salario_holerite = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    inss = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    irrf = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    beneficios = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    horas_extras = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    adicional_noturno = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    faltas_descontos = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    premio_abono = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    outros = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    liquido_informado = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    observacao = models.TextField(blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["funcionario", "competencia"], name="uq_retorno_funcionario_competencia")]


class ConferenciaFolha(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        CONFERIDO = "CONFERIDO", "Conferido"
        DIVERGENTE = "DIVERGENTE", "Divergente"
        JUSTIFICADO = "JUSTIFICADO", "Justificado"
    retorno = models.OneToOneField(RetornoContabilidade, on_delete=models.CASCADE, related_name="conferencia")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDENTE)
    justificativa = models.TextField(blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    conferido_em = models.DateTimeField(null=True, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.status == self.Status.JUSTIFICADO and not self.justificativa.strip():
            raise ValidationError({"justificativa": "Informe a justificativa da divergência."})
