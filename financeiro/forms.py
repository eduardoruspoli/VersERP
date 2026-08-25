from decimal import Decimal, ROUND_DOWN

from django import forms
from django.db.models import Q
from django.forms import BaseFormSet, formset_factory

from .models import (
    BaixaFinanceira,
    CentroCusto,
    ContaBancaria,
    Empresa,
    LancamentoFinanceiro,
    PlanoConta,
    TransferenciaBancaria,
)
from core.access import empresas_usuario


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


class CentroCustoForm(forms.ModelForm):

    class Meta:
        model = CentroCusto
        fields = [
            "empresa",
            "codigo",
            "nome",
            "cliente",
            "descricao",
            "ativo",
        ]
        widgets = {
            "empresa": forms.Select(attrs={"class": "form-select"}),
            "codigo": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ex.: VERS1917",
                    "autocomplete": "off",
                }
            ),
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "cliente": forms.Select(attrs={"class": "form-select"}),
            "descricao": forms.Textarea(
                attrs={"class": "form-control", "rows": 4}
            ),
            "ativo": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)

        if usuario is not None:
            self.fields["empresa"].queryset = empresas_usuario(usuario, ativas=True)
        queryset = self.fields["cliente"].queryset.filter(ativo=True)

        if self.instance and self.instance.cliente_id:
            queryset = self.fields["cliente"].queryset.filter(
                Q(ativo=True)
                | Q(pk=self.instance.cliente_id)
            )

        self.fields["cliente"].queryset = queryset.order_by("razao_social")
        self.fields["cliente"].empty_label = "Nenhum cliente selecionado"

    def clean_codigo(self):
        return self.cleaned_data["codigo"].strip().upper()

    def clean_nome(self):
        return self.cleaned_data["nome"].strip()


class RateioCentroCustoForm(forms.Form):
    centro_custo = forms.ModelChoiceField(
        label="Obra",
        queryset=CentroCusto.objects.none(),
        empty_label="Selecione a obra",
        widget=forms.Select(attrs={"class": "form-select rateio-centro"}),
    )
    valor = DecimalBRField(
        label="Valor",
        required=False,
        max_digits=15,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.TextInput(
            attrs={
                "class": "form-control campo-moeda rateio-valor",
                "inputmode": "decimal",
                "autocomplete": "off",
            }
        ),
    )
    percentual = DecimalBRField(
        label="Percentual",
        required=False,
        max_digits=7,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        max_value=Decimal("100.0000"),
        widget=forms.NumberInput(
            attrs={
                "class": "form-control rateio-percentual",
                "step": "0.0001",
                "min": "0.0001",
                "max": "100",
            }
        ),
    )

    def __init__(
        self,
        *args,
        empresa=None,
        centros_existentes=(),
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        queryset = CentroCusto.objects.filter(ativo=True)

        if empresa is not None:
            queryset = CentroCusto.objects.filter(
                empresa=empresa,
            ).filter(
                Q(ativo=True)
                | Q(pk__in=centros_existentes)
            )

        self.fields["centro_custo"].queryset = queryset.order_by("codigo")


class BaseRateioCentroCustoFormSet(BaseFormSet):

    def __init__(
        self,
        *args,
        empresa=None,
        valor_total=None,
        modo_rateio="VALOR",
        centros_existentes=(),
        **kwargs,
    ):
        self.empresa = empresa
        self.valor_total = valor_total
        self.modo_rateio = modo_rateio
        self.centros_existentes = tuple(centros_existentes)
        self.rateios_calculados = []
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs.update({
            "empresa": self.empresa,
            "centros_existentes": self.centros_existentes,
        })
        return kwargs

    def clean(self):
        super().clean()

        if any(self.errors):
            return

        linhas = []
        centros = set()

        for form in self.forms:
            dados = form.cleaned_data

            if not dados or dados.get("DELETE"):
                continue

            centro = dados.get("centro_custo")

            if centro is None:
                continue

            if centro.pk in centros:
                raise forms.ValidationError(
                    "A mesma obra não pode aparecer mais de uma vez no rateio."
                )

            centros.add(centro.pk)

            if centro.empresa_id != getattr(self.empresa, "pk", None):
                raise forms.ValidationError(
                    "Todas as obras devem pertencer à empresa do lançamento."
                )

            linhas.append(dados)

        if not linhas:
            raise forms.ValidationError(
                "Informe ao menos uma obra para o rateio."
            )

        if self.valor_total is None:
            raise forms.ValidationError(
                "Informe o valor total do lançamento antes do rateio."
            )

        if self.modo_rateio == "PERCENTUAL":
            self._calcular_por_percentual(linhas)
        else:
            self._validar_por_valor(linhas)

    def _validar_por_valor(self, linhas):
        if any(dados.get("valor") is None for dados in linhas):
            raise forms.ValidationError(
                "Informe o valor de todas as linhas do rateio."
            )

        total = sum(
            (dados["valor"] for dados in linhas),
            Decimal("0.00"),
        )

        if total != self.valor_total:
            raise forms.ValidationError(
                "A soma do rateio deve ser igual ao valor total do lançamento."
            )

        self.rateios_calculados = [
            {
                "centro_custo": dados["centro_custo"],
                "valor": dados["valor"],
            }
            for dados in linhas
        ]

    def _calcular_por_percentual(self, linhas):
        if any(dados.get("percentual") is None for dados in linhas):
            raise forms.ValidationError(
                "Informe o percentual de todas as linhas do rateio."
            )

        total_percentual = sum(
            (dados["percentual"] for dados in linhas),
            Decimal("0.0000"),
        )

        if total_percentual != Decimal("100.0000"):
            raise forms.ValidationError(
                "A soma dos percentuais do rateio deve ser igual a 100%."
            )

        calculados = []
        total_calculado = Decimal("0.00")

        for indice, dados in enumerate(linhas):
            if indice == len(linhas) - 1:
                valor = self.valor_total - total_calculado
            else:
                valor = (
                    self.valor_total
                    * dados["percentual"]
                    / Decimal("100")
                ).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
                total_calculado += valor

            calculados.append({
                "centro_custo": dados["centro_custo"],
                "valor": valor,
            })

        self.rateios_calculados = calculados


RateioCentroCustoFormSet = formset_factory(
    RateioCentroCustoForm,
    formset=BaseRateioCentroCustoFormSet,
    extra=1,
    can_delete=True,
)


class RelatorioObraFiltroForm(forms.Form):
    empresa = forms.ModelChoiceField(
        label="Empresa",
        queryset=Empresa.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    obra = forms.ModelChoiceField(
        label="Obra / Centro de Custo",
        queryset=CentroCusto.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    data_inicial = forms.DateField(
        label="Data inicial",
        widget=forms.DateInput(
            attrs={"class": "form-control", "type": "date"}
        ),
    )
    data_final = forms.DateField(
        label="Data final",
        widget=forms.DateInput(
            attrs={"class": "form-control", "type": "date"}
        ),
    )

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empresa"].queryset = (empresas_usuario(usuario, ativas=True) if usuario is not None else Empresa.objects.filter(ativa=True)).order_by("razao_social")

        obras = CentroCusto.objects.select_related("empresa").order_by(
            "empresa__razao_social", "codigo"
        )
        if usuario is not None and not usuario.is_superuser:
            obras = obras.filter(empresa__usuarios_autorizados__usuario=usuario)
        empresa_id = self.data.get("empresa") if self.is_bound else None
        if empresa_id and str(empresa_id).isdigit():
            obras = obras.filter(empresa_id=empresa_id)
        self.fields["obra"].queryset = obras

    def clean(self):
        dados = super().clean()
        empresa = dados.get("empresa")
        obra = dados.get("obra")
        data_inicial = dados.get("data_inicial")
        data_final = dados.get("data_final")

        if empresa and obra and obra.empresa_id != empresa.pk:
            self.add_error(
                "obra",
                "A obra deve pertencer à empresa selecionada.",
            )
        if data_inicial and data_final and data_inicial > data_final:
            self.add_error(
                "data_final",
                "A data final deve ser igual ou posterior à data inicial.",
            )
        return dados


class DREFiltroForm(forms.Form):
    COMPARACAO_CHOICES = [
        ("NENHUMA", "Sem comparação"),
        ("ANTERIOR", "Período anterior equivalente"),
        ("ANO_ANTERIOR", "Mesmo período do ano anterior"),
    ]

    empresa = forms.ModelChoiceField(
        label="Empresa",
        queryset=Empresa.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    data_inicial = forms.DateField(
        label="Competência inicial",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    data_final = forms.DateField(
        label="Competência final",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    obra = forms.ModelChoiceField(
        label="Obra / Centro de Custo",
        queryset=CentroCusto.objects.none(),
        required=False,
        empty_label="Todas as obras / Consolidado",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    plano_conta = forms.ModelChoiceField(
        label="Plano de Contas",
        queryset=PlanoConta.objects.none(),
        required=False,
        empty_label="Todas as contas",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    comparacao = forms.ChoiceField(
        label="Comparação",
        choices=COMPARACAO_CHOICES,
        initial="NENHUMA",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    usar_fallback = forms.BooleanField(
        label="Usar data de emissão quando a competência estiver vazia",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empresa"].queryset = (empresas_usuario(usuario, ativas=True) if usuario is not None else Empresa.objects.filter(ativa=True)).order_by("razao_social")
        obras = CentroCusto.objects.select_related("empresa").order_by(
            "empresa__razao_social", "codigo"
        )
        if usuario is not None and not usuario.is_superuser:
            obras = obras.filter(empresa__usuarios_autorizados__usuario=usuario)
        empresa_id = self.data.get("empresa") if self.is_bound else None
        if empresa_id and str(empresa_id).isdigit():
            obras = obras.filter(empresa_id=empresa_id)
        self.fields["obra"].queryset = obras
        self.fields["plano_conta"].queryset = PlanoConta.objects.filter(
            tipo__in=("RECEITA", "CUSTO", "DESPESA")
        ).order_by("codigo")

    def clean(self):
        dados = super().clean()
        empresa = dados.get("empresa")
        obra = dados.get("obra")
        inicio = dados.get("data_inicial")
        fim = dados.get("data_final")
        if empresa and obra and obra.empresa_id != empresa.pk:
            self.add_error("obra", "A obra deve pertencer à empresa selecionada.")
        if inicio and fim and inicio > fim:
            self.add_error(
                "data_final",
                "A competência final deve ser igual ou posterior à inicial.",
            )
        return dados


class DashboardFinanceiroFiltroForm(forms.Form):
    empresa = forms.ModelChoiceField(
        label="Empresa",
        queryset=Empresa.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    data_inicial = forms.DateField(
        label="Data inicial",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    data_final = forms.DateField(
        label="Data final",
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    obra = forms.ModelChoiceField(
        label="Obra / Centro de Custo",
        queryset=CentroCusto.objects.none(),
        required=False,
        empty_label="Todas as obras / Consolidado",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empresa"].queryset = (empresas_usuario(usuario, ativas=True) if usuario is not None else Empresa.objects.filter(ativa=True)).order_by("razao_social")
        obras = CentroCusto.objects.select_related("empresa").order_by(
            "empresa__razao_social", "codigo"
        )
        if usuario is not None and not usuario.is_superuser:
            obras = obras.filter(empresa__usuarios_autorizados__usuario=usuario)
        empresa_id = self.data.get("empresa") if self.is_bound else None
        if empresa_id and str(empresa_id).isdigit():
            obras = obras.filter(empresa_id=empresa_id)
        self.fields["obra"].queryset = obras

    def clean(self):
        dados = super().clean()
        empresa = dados.get("empresa")
        obra = dados.get("obra")
        inicio = dados.get("data_inicial")
        fim = dados.get("data_final")
        if empresa and obra and obra.empresa_id != empresa.pk:
            self.add_error("obra", "A obra deve pertencer à empresa selecionada.")
        if inicio and fim and inicio > fim:
            self.add_error(
                "data_final", "A data final deve ser igual ou posterior à inicial."
            )
        return dados


class PlanoContaForm(forms.ModelForm):

    class Meta:
        model = PlanoConta

        fields = [
            "codigo",
            "nome",
            "tipo",
            "natureza",
            "conta_redutora",
            "conta_pai",
            "aceita_lancamento",
            "estrutural",
            "ativo",
        ]

        widgets = {
            "codigo": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ex.: 6.01.04",
                    "autocomplete": "off",
                }
            ),
            "nome": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nome da conta",
                    "autocomplete": "off",
                }
            ),
            "tipo": forms.Select(
                attrs={"class": "form-select"}
            ),
            "natureza": forms.Select(
                attrs={"class": "form-select"}
            ),
            "conta_redutora": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "conta_pai": forms.Select(
                attrs={"class": "form-select"}
            ),
            "aceita_lancamento": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "estrutural": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "ativo": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        tipo = None

        if self.is_bound:
            tipo = self.data.get("tipo") or None
        elif self.instance and self.instance.pk:
            tipo = self.instance.tipo

        queryset = PlanoConta.objects.all().order_by("codigo")

        if tipo:
            queryset = queryset.filter(tipo=tipo)

        if self.instance and self.instance.pk:
            ids_bloqueados = {self.instance.pk}
            pendentes = [self.instance.pk]

            while pendentes:
                filhos = list(
                    PlanoConta.objects.filter(
                        conta_pai_id__in=pendentes
                    ).values_list("pk", flat=True)
                )
                novos = [
                    pk for pk in filhos
                    if pk not in ids_bloqueados
                ]
                ids_bloqueados.update(novos)
                pendentes = novos

            queryset = queryset.exclude(
                pk__in=ids_bloqueados
            )

        self.fields["conta_pai"].queryset = queryset
        self.fields["conta_pai"].empty_label = (
            "Nenhuma — conta de nível superior"
        )

    def clean_codigo(self):
        return self.cleaned_data["codigo"].strip()

    def clean_nome(self):
        return self.cleaned_data["nome"].strip()

    def clean(self):
        cleaned_data = super().clean()

        tipo = cleaned_data.get("tipo")
        conta_pai = cleaned_data.get("conta_pai")
        aceita_lancamento = cleaned_data.get(
            "aceita_lancamento"
        )
        estrutural = cleaned_data.get("estrutural")
        ativo = cleaned_data.get("ativo")

        if conta_pai and tipo and conta_pai.tipo != tipo:
            self.add_error(
                "conta_pai",
                "A conta superior deve pertencer "
                "ao mesmo grupo contábil.",
            )

        if (
            conta_pai
            and ativo
            and not conta_pai.ativo
        ):
            self.add_error(
                "conta_pai",
                "Uma conta ativa não pode ficar "
                "abaixo de uma conta inativa.",
            )

        if estrutural and aceita_lancamento:
            self.add_error(
                "aceita_lancamento",
                "Uma conta estrutural não deve "
                "receber lançamentos diretamente.",
            )

        return cleaned_data


class LancamentoFinanceiroForm(forms.ModelForm):

    classificacao_multipla = forms.BooleanField(
        label="Distribuir em mais de uma conta contábil", required=False,
    )

    modo_rateio = forms.ChoiceField(
        label="Ratear por",
        choices=[
            ("VALOR", "Valor"),
            ("PERCENTUAL", "Percentual"),
        ],
        initial="VALOR",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

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
        tipo=None,
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

        tipo_lancamento = (
            tipo
            or getattr(
                self.instance,
                "tipo",
                None,
            )
        )

        self.fields[
            "plano_conta"
        ].queryset = (
            PlanoConta.objects
            .filter(
                tipo__in=PlanoConta.tipos_para_lancamento(
                    tipo_lancamento
                ),
                ativo=True,
                aceita_lancamento=True,
            )
            .order_by(
                "codigo"
            )
        )
        if self.instance.pk and self.instance.classificacoes_contabeis.count() > 1:
            self.fields["classificacao_multipla"].initial = True
            self.fields["plano_conta"].required = False
        if self.is_bound and self.data.get("classificacao_multipla"):
            self.fields["plano_conta"].required = False

    def clean(self):
        dados = super().clean()
        if dados.get("classificacao_multipla"):
            self.fields["plano_conta"].required = False
            dados["plano_conta"] = None
        elif not dados.get("plano_conta"):
            self.add_error("plano_conta", "Informe o Plano de Contas.")
        return dados


class ClassificacaoContabilForm(forms.Form):
    plano_conta = forms.ModelChoiceField(queryset=PlanoConta.objects.none(), widget=forms.Select(attrs={"class":"form-select classificacao-conta"}))
    valor = DecimalBRField(max_digits=15, decimal_places=2, min_value=Decimal("0.01"), widget=forms.TextInput(attrs={"class":"form-control campo-moeda classificacao-valor","inputmode":"decimal"}))
    observacao = forms.CharField(required=False, widget=forms.TextInput(attrs={"class":"form-control","placeholder":"Observação opcional"}))

    def __init__(self, *args, tipo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plano_conta"].queryset = PlanoConta.objects.filter(
            tipo__in=PlanoConta.tipos_para_lancamento(tipo), ativo=True,
            estrutural=False, aceita_lancamento=True,
        ).order_by("codigo")


class BaseClassificacaoContabilFormSet(BaseFormSet):
    def __init__(self, *args, tipo=None, **kwargs):
        self.tipo = tipo
        super().__init__(*args, **kwargs)
        for form in self.forms:
            form.fields["plano_conta"].queryset = PlanoConta.objects.filter(
                tipo__in=PlanoConta.tipos_para_lancamento(tipo), ativo=True,
                estrutural=False, aceita_lancamento=True,
            ).order_by("codigo")

    def clean(self):
        if any(self.errors): return
        contas=[]
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"): continue
            conta=form.cleaned_data.get("plano_conta")
            if conta in contas: raise forms.ValidationError("Não repita a mesma conta contábil.")
            contas.append(conta)


ClassificacaoContabilFormSet = formset_factory(
    ClassificacaoContabilForm, formset=BaseClassificacaoContabilFormSet,
    extra=1, can_delete=True,
)


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
        usuario=None,
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
                ativa=True,
                empresa__in=empresas_usuario(usuario) if usuario is not None else Empresa.objects.none(),
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

    modo_rateio = forms.ChoiceField(
        label="Ratear por",
        choices=[
            ("VALOR", "Valor"),
            ("PERCENTUAL", "Percentual"),
        ],
        initial="VALOR",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

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

        else:
            self.fields[
                "pessoa"
            ].label = "Cliente"

        if tipo is not None:
            self.fields[
                "plano_conta"
            ].queryset = (
                PlanoConta.objects
                .filter(
                    tipo__in=PlanoConta.tipos_para_lancamento(
                        tipo
                    ),
                    ativo=True,
                    aceita_lancamento=True,
                )
                .order_by(
                    "codigo"
                )
            )

class TransferenciaBancariaForm(forms.ModelForm):

    valor = DecimalBRField(
        label="Valor",
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
        model = TransferenciaBancaria

        fields = [
            "conta_origem",
            "conta_destino",
            "data",
            "valor",
            "documento",
            "observacoes",
        ]

        widgets = {
            "conta_origem": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "conta_destino": forms.Select(
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

            "documento": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "TED, PIX, DOC, referência..."
                    ),
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

        contas = (
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

        self.fields[
            "conta_origem"
        ].queryset = contas

        self.fields[
            "conta_destino"
        ].queryset = contas

        self.fields[
            "data"
        ].input_formats = [
            "%Y-%m-%d",
        ]

    def clean(self):
        cleaned_data = super().clean()

        conta_origem = cleaned_data.get(
            "conta_origem"
        )

        conta_destino = cleaned_data.get(
            "conta_destino"
        )

        if (
            conta_origem
            and conta_destino
            and conta_origem.pk
            == conta_destino.pk
        ):
            self.add_error(
                "conta_destino",
                (
                    "A conta de destino deve ser "
                    "diferente da conta de origem."
                ),
            )

        if (
            conta_origem
            and conta_destino
            and conta_origem.empresa_id
            != conta_destino.empresa_id
        ):
            self.add_error(
                "conta_destino",
                (
                    "Nesta etapa, a conta de destino "
                    "deve pertencer à mesma empresa "
                    "da conta de origem."
                ),
            )

        return cleaned_data
