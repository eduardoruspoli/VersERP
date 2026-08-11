import re

from django import forms

from .models import Pessoa


class PessoaForm(forms.ModelForm):

    class Meta:
        model = Pessoa

        fields = [
            "tipo_pessoa",
            "classificacao",
            "razao_social",
            "nome_fantasia",
            "cpf_cnpj",
            "inscricao_estadual",
            "email",
            "telefone",
            "whatsapp",
            "cep",
            "endereco",
            "numero",
            "complemento",
            "bairro",
            "cidade",
            "estado",
            "observacoes",
            "ativo",
        ]

        widgets = {
            "tipo_pessoa": forms.Select(
                attrs={
                    "class": "form-select",
                    "id": "id_tipo_pessoa",
                }
            ),

            "classificacao": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "razao_social": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nome ou razão social",
                }
            ),

            "nome_fantasia": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nome fantasia",
                }
            ),

            "cpf_cnpj": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "CPF ou CNPJ",
                    "maxlength": "18",
                    "inputmode": "numeric",
                    "autocomplete": "off",
                    "id": "id_cpf_cnpj",
                }
            ),

            "inscricao_estadual": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Inscrição estadual",
                }
            ),

            "email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "email@empresa.com.br",
                }
            ),

            "telefone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "(00) 0000-0000",
                }
            ),

            "whatsapp": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "(00) 00000-0000",
                }
            ),

            "cep": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "00000-000",
                }
            ),

            "endereco": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "numero": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "complemento": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "bairro": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "cidade": forms.TextInput(
                attrs={
                    "class": "form-control",
                }
            ),

            "estado": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "UF",
                    "maxlength": "2",
                }
            ),

            "observacoes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                }
            ),

            "ativo": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
        }

    def clean_cpf_cnpj(self):
        cpf_cnpj = self.cleaned_data.get("cpf_cnpj", "")

        if not cpf_cnpj:
            return ""

        cpf_cnpj = re.sub(r"\D", "", cpf_cnpj)

        tipo_pessoa = self.cleaned_data.get("tipo_pessoa")

        if tipo_pessoa == Pessoa.TipoPessoa.FISICA:

            if len(cpf_cnpj) != 11:
                raise forms.ValidationError(
                    "O CPF deve possuir 11 dígitos."
                )

            if not self.validar_cpf(cpf_cnpj):
                raise forms.ValidationError(
                    "CPF inválido."
                )

        elif tipo_pessoa == Pessoa.TipoPessoa.JURIDICA:

            if len(cpf_cnpj) != 14:
                raise forms.ValidationError(
                    "O CNPJ deve possuir 14 dígitos."
                )

            if not self.validar_cnpj(cpf_cnpj):
                raise forms.ValidationError(
                    "CNPJ inválido."
                )

        return cpf_cnpj

    @staticmethod
    def validar_cpf(cpf):

        if len(cpf) != 11:
            return False

        if cpf == cpf[0] * 11:
            return False

        soma = sum(
            int(cpf[i]) * (10 - i)
            for i in range(9)
        )

        resto = (soma * 10) % 11

        if resto == 10:
            resto = 0

        if resto != int(cpf[9]):
            return False

        soma = sum(
            int(cpf[i]) * (11 - i)
            for i in range(10)
        )

        resto = (soma * 10) % 11

        if resto == 10:
            resto = 0

        return resto == int(cpf[10])

    @staticmethod
    def validar_cnpj(cnpj):

        if len(cnpj) != 14:
            return False

        if cnpj == cnpj[0] * 14:
            return False

        pesos_primeiro = [
            5, 4, 3, 2,
            9, 8, 7, 6,
            5, 4, 3, 2,
        ]

        soma = sum(
            int(cnpj[i]) * pesos_primeiro[i]
            for i in range(12)
        )

        resto = soma % 11

        primeiro_digito = (
            0 if resto < 2 else 11 - resto
        )

        if primeiro_digito != int(cnpj[12]):
            return False

        pesos_segundo = [
            6, 5, 4, 3, 2,
            9, 8, 7, 6,
            5, 4, 3, 2,
        ]

        soma = sum(
            int(cnpj[i]) * pesos_segundo[i]
            for i in range(13)
        )

        resto = soma % 11

        segundo_digito = (
            0 if resto < 2 else 11 - resto
        )

        return segundo_digito == int(cnpj[13])