from django import forms

from .models import LancamentoFinanceiro


class LancamentoFinanceiroForm(forms.ModelForm):

    condicao_pagamento = forms.ChoiceField(
        label="Condição de pagamento",
        choices=[
            ("AVISTA", "À vista"),
            ("PARCELADO", "Parcelado"),
        ],
        initial="AVISTA",
        widget=forms.Select(
            attrs={"class": "form-select"}
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
        widget=forms.DateInput(
            attrs={
                "class": "form-control",
                "type": "date",
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
            "condicao_pagamento",
            "quantidade_parcelas",
            "primeiro_vencimento",
        ]

        widgets = {
            "empresa": forms.Select(
                attrs={"class": "form-select"}
            ),
            "pessoa": forms.Select(
                attrs={"class": "form-select"}
            ),
            "descricao": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Descrição do lançamento",
                }
            ),
            "numero_documento": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "NF, boleto, contrato...",
                }
            ),
            "data_emissao": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "data_competencia": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "valor_total": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0.01",
                }
            ),
            "plano_conta": forms.Select(
                attrs={"class": "form-select"}
            ),
            "observacoes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                }
            ),
        }