import re

from django.db import models


class Pessoa(models.Model):

    class TipoPessoa(models.TextChoices):
        FISICA = "PF", "Pessoa Física"
        JURIDICA = "PJ", "Pessoa Jurídica"

    class Classificacao(models.TextChoices):
        CLIENTE = "CLIENTE", "Cliente"
        FORNECEDOR = "FORNECEDOR", "Fornecedor"
        AMBOS = "AMBOS", "Cliente e Fornecedor"

    tipo_pessoa = models.CharField(
        max_length=2,
        choices=TipoPessoa.choices,
        default=TipoPessoa.JURIDICA,
        verbose_name="Tipo de pessoa",
    )

    classificacao = models.CharField(
        max_length=15,
        choices=Classificacao.choices,
        default=Classificacao.CLIENTE,
        verbose_name="Classificação",
    )

    razao_social = models.CharField(
        max_length=200,
        verbose_name="Razão social / Nome",
    )

    nome_fantasia = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Nome fantasia",
    )

    cpf_cnpj = models.CharField(
        max_length=18,
        blank=True,
        verbose_name="CPF / CNPJ",
    )

    inscricao_estadual = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Inscrição estadual",
    )

    email = models.EmailField(
        blank=True,
        verbose_name="E-mail",
    )

    telefone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Telefone",
    )

    whatsapp = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="WhatsApp",
    )

    cep = models.CharField(
        max_length=9,
        blank=True,
        verbose_name="CEP",
    )

    endereco = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Endereço",
    )

    numero = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Número",
    )

    complemento = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Complemento",
    )

    bairro = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Bairro",
    )

    cidade = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Cidade",
    )

    estado = models.CharField(
        max_length=2,
        blank=True,
        verbose_name="Estado",
    )

    observacoes = models.TextField(
        blank=True,
        verbose_name="Observações",
    )

    ativo = models.BooleanField(
        default=True,
        verbose_name="Ativo",
    )

    criado_em = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Criado em",
    )

    atualizado_em = models.DateTimeField(
        auto_now=True,
        verbose_name="Atualizado em",
    )

    @property
    def cpf_cnpj_formatado(self):
        documento = re.sub(r"\D", "", self.cpf_cnpj or "")

        if len(documento) == 11:
            return (
                f"{documento[:3]}."
                f"{documento[3:6]}."
                f"{documento[6:9]}-"
                f"{documento[9:]}"
            )

        if len(documento) == 14:
            return (
                f"{documento[:2]}."
                f"{documento[2:5]}."
                f"{documento[5:8]}/"
                f"{documento[8:12]}-"
                f"{documento[12:]}"
            )

        return self.cpf_cnpj


    class Meta:
        verbose_name = "Pessoa"
        verbose_name_plural = "Pessoas"
        ordering = ["razao_social"]

    def __str__(self):
        return self.razao_social