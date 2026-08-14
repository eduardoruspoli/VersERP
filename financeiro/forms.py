from decimal import Decimal

from django import forms
from django.forms import formset_factory

from .models import (
    BaixaFinanceira,
    ContaBancaria,
    LancamentoFinanceiro,
    PlanoConta,
)


class DecimalBRField(forms.DecimalField):
    """
    Campo decimal que aceita valores no padrão brasileiro.

    Exemplos aceitos:
    1000
    1000,00
    1.000,00
    12500,50
    12.500,50
    3000.00
    """

    def to_python(self, value):
        if isinstance(value, str):
            value = value.strip()

            if value:
                value = (
                    value
                    .replace("R$", "")
                    .replace(" ", "")
                )

            if "," in value:
                value = (
                    value
                    .replace(".", "")
                    .replace(",", ".")
                )

        return super().to_python(value)


class LancamentoFinanceiroForm(forms.ModelForm):

    condicao_pagamento = forms.ChoiceField(
        label="Condição de pagamento",
        choices=[
            ("AVISTA", "À vista"),
            ("PARCELADO", "Parcelado"),
        ],
        initial="AVISTA",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    quantidade_parcelas = forms.IntegerField(
        label="Quantidade de parcelas",
        min_value=1,
        initial=1,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "min": "1",
            }
        ),
    )

    primeiro_vencimento = forms.DateField(
        label="Primeiro vencimento",
        input_formats=[
            "%Y-%m-%d",
        ],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={
                "class": "form-control",
                "type": "date",
            },
        ),
    )

    valor_total = DecimalBRField(
        label="Valor total",
        max_digits=15,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.TextInput(
            attrs={
                "class": (
                    "form-control "
                    "campo-moeda"
                ),
                "inputmode": "decimal",
                "autocomplete": "off",
            }
        ),
    )

    class Meta:
        model = LancamentoFinanceiro

        fields = [
            "empresa",
            "pessoa",
            "descricao",
            "numero_documento",
            "data_emissao",
            "data_competencia",
            "valor_total",
            "plano_conta",
            "observacoes",
        ]

        widgets = {
            "empresa": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "pessoa": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "descricao": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Descrição do lançamento"
                    ),
                }
            ),

            "numero_documento": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "NF, boleto, contrato..."
                    ),
                }
            ),

            "data_emissao": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "class": "form-control",
                    "type": "date",
                },
            ),

            "data_competencia": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "class": "form-control",
                    "type": "date",
                },
            ),

            "plano_conta": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "observacoes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                }
            ),
        }

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.fields[
            "data_emissao"
        ].input_formats = [
            "%Y-%m-%d",
        ]

        self.fields[
            "data_competencia"
        ].input_formats = [
            "%Y-%m-%d",
        ]


class ParcelaForm(forms.Form):

    numero = forms.IntegerField(
        widget=forms.HiddenInput()
    )

    vencimento = forms.DateField(
        label="Vencimento",
        input_formats=[
            "%Y-%m-%d",
        ],
        widget=forms.DateInput(
            format="%Y-%m-%d",
            attrs={
                "class": "form-control",
                "type": "date",
            },
        ),
    )

    valor = DecimalBRField(
        label="Valor",
        max_digits=15,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.TextInput(
            attrs={
                "class": (
                    "form-control "
                    "parcela-valor "
                    "campo-moeda"
                ),
                "inputmode": "decimal",
                "autocomplete": "off",
            }
        ),
    )


ParcelaFormSet = formset_factory(
    ParcelaForm,
    extra=0,
)


class BaixaFinanceiraForm(forms.ModelForm):

    valor = DecimalBRField(
        label="Valor principal",
        max_digits=15,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.TextInput(
            attrs={
                "class": (
                    "form-control "
                    "campo-moeda"
                ),
                "inputmode": "decimal",
                "autocomplete": "off",
            }
        ),
    )

    juros = DecimalBRField(
        label="Juros",
        max_digits=15,
        decimal_places=2,
        min_value=Decimal("0.00"),
        initial=Decimal("0.00"),
        widget=forms.TextInput(
            attrs={
                "class": (
                    "form-control "
                    "campo-moeda"
                ),
                "inputmode": "decimal",
                "autocomplete": "off",
            }
        ),
    )

    multa = DecimalBRField(
        label="Multa",
        max_digits=15,
        decimal_places=2,
        min_value=Decimal("0.00"),
        initial=Decimal("0.00"),
        widget=forms.TextInput(
            attrs={
                "class": (
                    "form-control "
                    "campo-moeda"
                ),
                "inputmode": "decimal",
                "autocomplete": "off",
            }
        ),
    )

    desconto = DecimalBRField(
        label="Desconto",
        max_digits=15,
        decimal_places=2,
        min_value=Decimal("0.00"),
        initial=Decimal("0.00"),
        widget=forms.TextInput(
            attrs={
                "class": (
                    "form-control "
                    "campo-moeda"
                ),
                "inputmode": "decimal",
                "autocomplete": "off",
            }
        ),
    )

    class Meta:
        model = BaixaFinanceira

        fields = [
            "conta_bancaria",
            "data",
            "valor",
            "juros",
            "multa",
            "desconto",
            "observacoes",
        ]

        widgets = {
            "conta_bancaria": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "data": forms.DateInput(
                format="%Y-%m-%d",
                attrs={
                    "class": "form-control",
                    "type": "date",
                },
            ),

            "observacoes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                }
            ),
        }

    def __init__(
        self,
        *args,
        empresa=None,
        saldo=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.fields[
            "data"
        ].input_formats = [
            "%Y-%m-%d",
        ]

        if empresa is not None:
            self.fields[
                "conta_bancaria"
            ].queryset = (
                ContaBancaria.objects
                .filter(
                    empresa=empresa,
                    ativa=True,
                )
                .order_by(
                    "banco",
                    "agencia",
                    "conta",
                )
            )

        if (
            saldo is not None
            and not self.is_bound
        ):
            self.fields[
                "valor"
            ].initial = saldo

        if not self.is_bound:
            self.fields[
                "juros"
            ].initial = Decimal(
                "0.00"
            )

            self.fields[
                "multa"
            ].initial = Decimal(
                "0.00"
            )

            self.fields[
                "desconto"
            ].initial = Decimal(
                "0.00"
            )


class ImportacaoOFXForm(forms.Form):

    conta_bancaria = forms.ModelChoiceField(
        label="Conta bancária",
        queryset=ContaBancaria.objects.none(),
        empty_label="Selecione a conta bancária",
        widget=forms.Select(
            attrs={
                "class": "form-select",
            }
        ),
    )

    arquivo = forms.FileField(
        label="Arquivo OFX",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": ".ofx,application/x-ofx",
            }
        ),
        help_text=(
            "Selecione o arquivo .ofx "
            "exportado pelo internet banking."
        ),
    )

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.fields[
            "conta_bancaria"
        ].queryset = (
            ContaBancaria.objects
            .filter(
                ativa=True
            )
            .select_related(
                "empresa"
            )
            .order_by(
                "empresa",
                "banco",
                "agencia",
                "conta",
            )
        )

    def clean_arquivo(self):
        arquivo = self.cleaned_data[
            "arquivo"
        ]

        nome = (
            arquivo.name
            or ""
        ).lower()

        if not nome.endswith(".ofx"):
            raise forms.ValidationError(
                "Selecione um arquivo com extensão .ofx."
            )

        if arquivo.size <= 0:
            raise forms.ValidationError(
                "O arquivo OFX está vazio."
            )

        limite = (
            10 * 1024 * 1024
        )

        if arquivo.size > limite:
            raise forms.ValidationError(
                "O arquivo OFX deve possuir no máximo 10 MB."
            )

        return arquivo

class CriarLancamentoOFXForm(forms.ModelForm):

    class Meta:
        model = LancamentoFinanceiro

        fields = [
            "pessoa",
            "descricao",
            "numero_documento",
            "plano_conta",
            "observacoes",
        ]

        widgets = {
            "pessoa": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "descricao": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "numero_documento": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "plano_conta": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "observacoes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                }
            ),
        }

    def __init__(
        self,
        *args,
        tipo=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        if tipo == "PAGAR":
            self.fields[
                "pessoa"
            ].label = "Fornecedor"

            tipo_plano = "DESPESA"

        else:
            self.fields[
                "pessoa"
            ].label = "Cliente"

            tipo_plano = "RECEITA"

        if tipo is not None:
            self.fields[
                "plano_conta"
            ].queryset = (
                PlanoConta.objects
                .filter(
                    tipo=tipo_plano,
                    ativo=True,
                    aceita_lancamento=True,
                )
                .order_by(
                    "codigo"
                )
            )